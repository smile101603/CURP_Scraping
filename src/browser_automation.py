"""
Browser Automation
Handles browser automation using Playwright to interact with the CURP portal.
"""
import time
import random
from typing import Optional, Dict
from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext
from state_codes import get_state_code


class BrowserAutomation:
    """Handle browser automation for CURP searches."""
    
    def __init__(self, headless: bool = False, min_delay: float = 2.0, 
                 max_delay: float = 5.0, pause_every_n: int = 50, 
                 pause_duration: int = 30):
        """
        Initialize browser automation.
        
        Args:
            headless: Run browser in headless mode
            min_delay: Minimum delay between searches (seconds)
            max_delay: Maximum delay between searches (seconds)
            pause_every_n: Pause every N searches
            pause_duration: Duration of pause (seconds)
        """
        self.headless = headless
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.pause_every_n = pause_every_n
        self.pause_duration = pause_duration
        
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        
        self.search_count = 0
        self.url = "https://www.gob.mx/curp/"
        self.form_ready = False  # Track if form has been initialized
        
        # Track time for periodic 40-second pause
        self.last_pause_time = time.time()
    
    def start_browser(self):
        """Start browser and navigate to CURP page."""
        self.playwright = sync_playwright().start()
        
        # Launch browser
        self.browser = self.playwright.chromium.launch(
            headless=self.headless,
            args=['--disable-blink-features=AutomationControlled']
        )
        
        # Create context with realistic settings
        self.context = self.browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        
        # Create page
        self.page = self.context.new_page()
        
        # Navigate to CURP page with retry logic
        max_retries = 3
        retry_delay = 3
        
        for attempt in range(max_retries):
            try:
                # Use 'load' instead of 'networkidle' for faster loading
                # Increase timeout to 90 seconds
                self.page.goto(self.url, wait_until='load', timeout=90000)
                time.sleep(2.0)  # Page load wait
                
                # Click on "Datos Personales" tab to access the form
                try:
                    # Wait for the tab to be available
                    self.page.wait_for_selector('a[href="#tab-02"]', timeout=15000)
                    # Click the "Datos Personales" tab
                    self.page.click('a[href="#tab-02"]')
                    time.sleep(0.4)  # Tab switch delay
                except Exception as e:
                    print(f"Warning: Could not click 'Datos Personales' tab: {e}")
                
                # Success - break out of retry loop
                break
                
            except Exception as e:
                if attempt < max_retries - 1:
                    print(f"Error navigating to {self.url} (attempt {attempt + 1}/{max_retries}): {e}")
                    print(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                    retry_delay *= 1.5  # Exponential backoff
                else:
                    print(f"Error navigating to {self.url} after {max_retries} attempts: {e}")
                    raise
    
    def close_browser(self):
        """Close browser and cleanup."""
        # Close in reverse order with proper error handling
        # This helps avoid asyncio cleanup warnings on Windows
        # Note: RuntimeError warnings from asyncio on Windows are harmless
        try:
            if self.page:
                try:
                    self.page.close()
                    time.sleep(0.1)  # Small delay between closes
                except Exception:
                    # Ignore errors during page close
                    pass
        except Exception:
            pass
        
        try:
            if self.context:
                try:
                    self.context.close()
                    time.sleep(0.1)  # Small delay between closes
                except Exception:
                    # Ignore errors during context close
                    pass
        except Exception:
            pass
        
        try:
            if self.browser:
                try:
                    self.browser.close()
                    time.sleep(0.2)  # Longer delay before stopping playwright
                except Exception:
                    # Ignore errors during browser close
                    pass
        except Exception:
            pass
        
        try:
            if self.playwright:
                try:
                    # Stop playwright - this might trigger asyncio cleanup warnings on Windows
                    # but they are harmless and can be safely ignored
                    self.playwright.stop()
                except Exception:
                    # Ignore errors during playwright stop
                    pass
        except Exception:
            pass
    
    def _random_delay(self):
        """Apply random delay between searches."""
        delay = random.uniform(self.min_delay, self.max_delay)
        time.sleep(delay)
    
    def _human_like_delay(self, min_seconds: float = 0.2, max_seconds: float = 0.8):
        """
        Apply human-like variable delay (simulates thinking/reading time).
        
        Args:
            min_seconds: Minimum delay in seconds
            max_seconds: Maximum delay in seconds
        """
        delay = random.uniform(min_seconds, max_seconds)
        time.sleep(delay)
    
    def _human_like_typing_delay(self):
        """Apply delay that simulates human typing speed."""
        # Humans type at different speeds, add variable delay
        delay = random.uniform(0.1, 0.2)
        time.sleep(delay)
    
    def _close_modal_if_present(self):
        """Close the error modal if it appears (no match found)."""
        if not self.page:
            return
        
        try:
            # Check for the modal close button
            close_button = self.page.query_selector('button[data-dismiss="modal"]')
            if close_button:
                close_button.click()
                time.sleep(0.4)  # Fixed 0.4s delay after closing modal
        except:
            pass
    
    def _ensure_form_ready(self):
        """Navigate to form and ensure it's ready for input. Only navigate when needed."""
        try:
            # If form is already ready and we're on the form page, skip navigation
            if self.form_ready:
                # Quick check if we're still on form page
                try:
                    # Check if form fields are available without navigation
                    self.page.wait_for_selector('input#nombre', timeout=2000)
                    return  # Already on form, no need to navigate
                except:
                    # Form not available, need to navigate
                    self.form_ready = False
            
            # Check if we're on results page or need to navigate
            current_url = self.page.url
            page_content = self.page.content()
            
            # Only navigate if we're actually on results page or wrong page
            needs_navigation = (
                not self.form_ready or
                'gob.mx/curp' not in current_url or 
                'Descarga del CURP' in page_content or 
                'dwnldLnk' in page_content or
                'Aviso importante' in page_content
            )
            
            if needs_navigation:
                # Navigate back to form (only when necessary)
                self.page.goto(self.url, wait_until='load', timeout=90000)
                time.sleep(2.0)  # Page load wait
                
                # Click on "Datos Personales" tab to access the form
                try:
                    self.page.wait_for_selector('a[href="#tab-02"]', timeout=10000)
                    tab = self.page.locator('a[href="#tab-02"]').first
                    # Check if tab needs to be clicked (might already be active)
                    try:
                        tab_class = tab.get_attribute('class') or ''
                        if 'active' not in tab_class:
                            tab.click()
                            time.sleep(0.4)  # Tab switch delay
                    except:
                        # If we can't check, just click it anyway
                        tab.click()
                        time.sleep(0.4)  # Tab switch delay
                except Exception as e:
                    print(f"Warning: Could not click 'Datos Personales' tab: {e}")
                    raise
            else:
                # We're already on form page, just ensure tab is active
                try:
                    self.page.wait_for_selector('a[href="#tab-02"]', timeout=5000)
                    tab = self.page.locator('a[href="#tab-02"]').first
                    tab_class = tab.get_attribute('class') or ''
                    if 'active' not in tab_class:
                        tab.click()
                        time.sleep(0.4)  # Tab switch delay
                except:
                    pass  # Tab might already be active or not critical
            
            # Wait for form fields to be available
            self.page.wait_for_selector('input#nombre', timeout=5000)
            self.form_ready = True
            
        except Exception as e:
            print(f"Error ensuring form is ready: {e}")
            raise
    
    def _clear_form_fields(self):
        """Clear all form fields before filling with new data."""
        try:
            # Clear text inputs
            self.page.fill('input#nombre', '')
            self.page.fill('input#primerApellido', '')
            self.page.fill('input#segundoApellido', '')
            self.page.fill('input#selectedYear', '')
            
            # Reset selects to default/empty if possible
            # Note: Some selects might not have a default empty option
            # Removed delay - not necessary
        except Exception as e:
            # If clearing fails, continue anyway - form submission will overwrite
            pass
    
    def _wait_for_search_completion(self, timeout: float = 10.0) -> bool:
        """
        Wait for search to complete (results or error modal appear).
        Uses longer timeout to handle slow bot detection responses.
        
        Args:
            timeout: Maximum time to wait in seconds (default 10.0)
        
        Returns:
            True if search completed, False if timeout
        """
        start_time = time.time()
        last_check_time = start_time
        consecutive_no_change = 0
        
        while (time.time() - start_time) < timeout:
            try:
                # Get page content to check for both result types
                content = self.page.content()
                content_lower = content.lower()
                
                # Check for match found result (CURP data page)
                has_match_result = (
                    '#dwnldLnk' in content or 
                    'dwnldLnk' in content or 
                    'Descarga del CURP' in content or
                    'Datos del solicitante' in content or
                    'id="download"' in content or
                    'Descargar pdf' in content
                )
                
                # Check for no match modal (error modal with specific structure)
                has_no_match_modal = (
                    'Aviso importante' in content or
                    'warningMenssage' in content or
                    'id="warningMenssage"' in content or
                    'Los datos ingresados no son correctos' in content or
                    self.page.locator('button[data-dismiss="modal"]').count() > 0
                )
                
                if has_match_result or has_no_match_modal:
                    # Wait longer to ensure content is fully loaded (site may be slow)
                    time.sleep(1.0)
                    
                    # Re-check content after wait
                    content = self.page.content()
                    content_lower = content.lower()
                    
                    # Check for various loading indicators
                    has_loading_text = (
                        'cargando' in content_lower or 
                        'loading' in content_lower or
                        'procesando' in content_lower or
                        'buscando' in content_lower
                    )
                    
                    # Check for spinners or loaders
                    has_spinner = self.page.locator('.spinner, .loader, .loading, [class*="loading"], [class*="spinner"]').count() > 0
                    
                    if not has_loading_text and not has_spinner:
                        # Verify we still have the result after waiting
                        if has_match_result:
                            # Double-check match result is still present
                            still_has_match = (
                                '#dwnldLnk' in content or 
                                'Descarga del CURP' in content or
                                'Datos del solicitante' in content
                            )
                            if still_has_match:
                                # Additional wait to ensure DOM is stable
                                time.sleep(0.3)
                                return True
                        elif has_no_match_modal:
                            # Verify modal is still present
                            still_has_modal = (
                                'Aviso importante' in content or
                                'warningMenssage' in content or
                                self.page.locator('button[data-dismiss="modal"]').count() > 0
                            )
                            if still_has_modal:
                                time.sleep(0.3)
                                return True
                
                # Use variable check interval (more human-like)
                check_interval = random.uniform(0.3, 0.8)
                time.sleep(check_interval)
                
            except Exception as e:
                # If there's an error, wait a bit longer before retrying
                time.sleep(0.5)
        
        return False  # Timeout
    
    def _detect_unrecognized_errors(self) -> bool:
        """
        Detect unrecognized error messages (not the standard "no match" modal).
        
        Returns:
            True if unrecognized error is detected, False otherwise
        """
        if not self.page:
            return False
        
        try:
            content = self.page.content()
            content_lower = content.lower()
            
            # Known errors that are handled normally (not unrecognized)
            known_error_patterns = [
                'aviso importante',
                'los datos ingresados no son correctos',
                'warningmenssage'
            ]
            
            # Check for known errors - these are NOT unrecognized
            has_known_error = any(pattern in content_lower for pattern in known_error_patterns)
            
            # Unrecognized error patterns
            unrecognized_patterns = [
                'error 500',
                'error 503',
                'error 404',
                'internal server error',
                'service unavailable',
                'network error',
                'timeout',
                'connection refused',
                'javascript error',
                'script error',
                'uncaught exception',
                'failed to load',
                'networkerror',
                'syntaxerror'
            ]
            
            # Check for unrecognized errors
            has_unrecognized = any(pattern in content_lower for pattern in unrecognized_patterns)
            
            # Also check for JavaScript console errors
            try:
                console_errors = self.page.evaluate("""
                    () => {
                        if (window.errors && window.errors.length > 0) {
                            return true;
                        }
                        return false;
                    }
                """)
                if console_errors:
                    has_unrecognized = True
            except:
                pass
            
            # Check for page load failures
            try:
                # Check if page is in error state
                page_title = self.page.title()
                if 'error' in page_title.lower() or 'not found' in page_title.lower():
                    has_unrecognized = True
            except:
                pass
            
            # Return True only if we have unrecognized errors AND not known errors
            return has_unrecognized and not has_known_error
            
        except Exception:
            return False
    
    def _recover_from_error(self) -> bool:
        """
        Recover from error by reloading the page and re-initializing the form.
        
        Returns:
            True if recovery successful, False otherwise
        """
        if not self.page:
            return False
        
        try:
            # Reload the page
            self.page.reload(wait_until='load', timeout=90000)
            time.sleep(2.0)  # Page load wait
            
            # Click on "Datos Personales" tab to access the form
            try:
                self.page.wait_for_selector('a[href="#tab-02"]', timeout=10000)
                tab = self.page.locator('a[href="#tab-02"]').first
                tab_class = tab.get_attribute('class') or ''
                if 'active' not in tab_class:
                    tab.click()
                    time.sleep(0.4)  # Tab switch delay
            except Exception as e:
                print(f"Warning: Could not click 'Datos Personales' tab during recovery: {e}")
                return False
            
            # Wait for form fields to be available
            self.page.wait_for_selector('input#nombre', timeout=5000)
            self.form_ready = True
            
            return True
            
        except Exception as e:
            print(f"Error during recovery: {e}")
            return False
    
    def search_curp(self, first_name: str, last_name_1: str, last_name_2: str,
                   gender: str, day: int, month: int, state: str, year: int) -> str:
        """
        Search for CURP with given parameters.
        
        Args:
            first_name: First name(s)
            last_name_1: First last name
            last_name_2: Second last name
            gender: Gender (H or M)
            day: Day of birth (1-31)
            month: Month of birth (1-12)
            state: State name
            year: Year of birth
            
        Returns:
            HTML content of the result page
        """
        if not self.page:
            raise RuntimeError("Browser not started. Call start_browser() first.")
        
        try:
            # Ensure form is ready (only navigate if we're on results page)
            # Don't navigate if we're already on the form page
            self._ensure_form_ready()
            
            # Fill form fields with human-like timing (simulates real user behavior)
            # Fill form fields using the actual IDs from the website
            
            # First name (nombres) - humans type at variable speeds
            self.page.fill('input#nombre', first_name, timeout=5000)
            self._human_like_typing_delay()
            self._human_like_delay(0.1, 0.2)  # Pause to "read" or "think"
            
            # First last name (primerApellido)
            self.page.fill('input#primerApellido', last_name_1, timeout=5000)
            self._human_like_typing_delay()
            self._human_like_delay(0.1, 0.2)
            
            # Second last name (segundoApellido)
            self.page.fill('input#segundoApellido', last_name_2, timeout=5000)
            self._human_like_typing_delay()
            self._human_like_delay(0.1, 0.3)  # Slightly longer pause before dropdowns
            
            # Day - format as "01", "02", etc. (humans take time to select from dropdown)
            day_str = str(day).zfill(2)
            self.page.select_option('select#diaNacimiento', day_str, timeout=5000)
            self._human_like_delay(0.2, 0.4)  # Dropdown selection delay
            
            # Month - format as "01", "02", etc.
            month_str = str(month).zfill(2)
            self.page.select_option('select#mesNacimiento', month_str, timeout=5000)
            self._human_like_delay(0.2, 0.4)
            
            # Year (humans type numbers at variable speeds)
            year_str = str(year)
            self.page.fill('input#selectedYear', year_str, timeout=5000)
            self._human_like_typing_delay()
            self._human_like_delay(0.1, 0.2)
            
            # Gender (sexo) - values: "H", "M", or "X"
            gender_value = "H" if gender.upper() == "H" else "M"
            self.page.select_option('select#sexo', gender_value, timeout=5000)
            self._human_like_delay(0.2, 0.3)
            
            # State (claveEntidad) - convert state name to code (longer pause for state selection)
            state_code = get_state_code(state)
            self.page.select_option('select#claveEntidad', state_code, timeout=5000)
            self._human_like_delay(0.2, 0.3)  # Reduced pause before submitting
            
            # Submit form - humans pause before clicking submit button
            self._human_like_delay(0.2, 0.4)  # "Review" the form before submitting
            submitted = False
            
            try:
                # Method 1: Look for submit button within the active tab form
                # The form is in tab-02, so submit button should be there
                submit_button = self.page.locator('#tab-02 form button[type="submit"]').first
                if submit_button.count() > 0:
                    submit_button.click()
                    submitted = True
                    self._human_like_delay(0.3, 0.6)  # Variable delay after clicking
            except Exception as e:
                pass
            
            if not submitted:
                try:
                    # Method 2: Look for any submit button in the current form
                    submit_button = self.page.locator('form button[type="submit"]').first
                    if submit_button.count() > 0:
                        submit_button.click()
                        submitted = True
                        time.sleep(0.3)  # Form submission delay
                except Exception as e:
                    pass
            
            if not submitted:
                try:
                    # Method 3: Look for button with text "Buscar" or "Consultar"
                    buscar_button = self.page.locator('button:has-text("Buscar"), button:has-text("Consultar")').first
                    if buscar_button.count() > 0:
                        buscar_button.click()
                        submitted = True
                        time.sleep(0.3)  # Form submission delay
                except Exception as e:
                    pass
            
            if not submitted:
                try:
                    # Method 4: Press Enter on the year field (last field filled)
                    self.page.keyboard.press('Enter')
                    submitted = True
                    time.sleep(0.5)  # Form submission delay
                except Exception as e:
                    print(f"Warning: All form submission methods failed: {e}")
            
            # Record search start time for timeout detection
            search_start_time = time.time()
            
            # Check for unrecognized errors and recover if needed
            max_recovery_attempts = 3
            recovery_attempt = 0
            while recovery_attempt < max_recovery_attempts:
                if self._detect_unrecognized_errors():
                    print(f"Unrecognized error detected, attempting recovery (attempt {recovery_attempt + 1}/{max_recovery_attempts})...")
                    if self._recover_from_error():
                        print("Recovery successful, retrying search...")
                        # Re-fill the form and resubmit
                        # First name
                        self.page.fill('input#nombre', first_name, timeout=5000)
                        time.sleep(0.1)
                        # First last name
                        self.page.fill('input#primerApellido', last_name_1, timeout=5000)
                        time.sleep(0.1)
                        # Second last name
                        self.page.fill('input#segundoApellido', last_name_2, timeout=5000)
                        time.sleep(0.1)
                        # Day
                        day_str = str(day).zfill(2)
                        self.page.select_option('select#diaNacimiento', day_str, timeout=5000)
                        time.sleep(0.1)
                        # Month
                        month_str = str(month).zfill(2)
                        self.page.select_option('select#mesNacimiento', month_str, timeout=5000)
                        time.sleep(0.1)
                        # Year
                        year_str = str(year)
                        self.page.fill('input#selectedYear', year_str, timeout=5000)
                        time.sleep(0.1)
                        # Gender
                        gender_value = "H" if gender.upper() == "H" else "M"
                        self.page.select_option('select#sexo', gender_value, timeout=5000)
                        time.sleep(0.1)
                        # State
                        state_code = get_state_code(state)
                        self.page.select_option('select#claveEntidad', state_code, timeout=5000)
                        time.sleep(0.2)
                        # Resubmit
                        self._human_like_delay(0.3, 0.6)
                        try:
                            submit_button = self.page.locator('#tab-02 form button[type="submit"]').first
                            if submit_button.count() > 0:
                                submit_button.click()
                                self._human_like_delay(0.3, 0.6)
                            else:
                                self.page.keyboard.press('Enter')
                                self._human_like_delay(0.3, 0.6)
                        except:
                            self.page.keyboard.press('Enter')
                            self._human_like_delay(0.3, 0.6)
                        search_start_time = time.time()  # Reset start time
                    else:
                        print("Recovery failed")
                    recovery_attempt += 1
                else:
                    break  # No unrecognized errors, proceed with search
            
            # Wait for search completion with 20 second timeout
            # If no result appears within 20s, reload and proceed to next input
            search_completed = self._wait_for_search_completion(timeout=5.0)
            
            if not search_completed:
                # Timeout occurred - reload page and move to next input
                print(f"Search timeout after 20 seconds, reloading page and moving to next input...")
                try:
                    self.page.reload(wait_until='load', timeout=90000)
                    time.sleep(2.0)  # Page load wait
                    
                    # Click on "Datos Personales" tab
                    try:
                        self.page.wait_for_selector('a[href="#tab-02"]', timeout=10000)
                        tab = self.page.locator('a[href="#tab-02"]').first
                        tab_class = tab.get_attribute('class') or ''
                        if 'active' not in tab_class:
                            tab.click()
                            time.sleep(0.4)  # Tab switch delay
                    except:
                        pass
                    
                    self.form_ready = True
                    # Return empty content to indicate no result
                    return ""
                except Exception as e:
                    print(f"Error during timeout recovery: {e}")
                    return ""
            
            # Search completed - verify page stability and get results
            # Add human-like pause to "read" the results
            self._human_like_delay(0.2, 0.3)  # Humans pause to read results
            
            # Check for results FIRST before closing modal
            # Get page content to check for matches
            content = self.page.content()
            
            # Check for match found (CURP result page)
            # Look for specific indicators from the match result HTML
            has_match_result = (
                '#dwnldLnk' in content or 
                'dwnldLnk' in content or 
                'Descarga del CURP' in content or
                'Datos del solicitante' in content or
                'id="download"' in content or
                'Descargar pdf' in content
            )
            
            # Check for no match modal (error modal)
            # Look for the specific modal structure
            has_no_match_modal = (
                'Aviso importante' in content or
                'warningMenssage' in content or
                'id="warningMenssage"' in content or
                'Los datos ingresados no son correctos' in content
            )
            
            if has_match_result:
                # Match found! Save the result (content is already captured)
                # Reload page and proceed to next input
                print("Match found! Reloading page for next search...")
                try:
                    self.page.reload(wait_until='load', timeout=90000)
                    time.sleep(2.0)  # Page load wait
                    
                    # Click on "Datos Personales" tab
                    try:
                        self.page.wait_for_selector('a[href="#tab-02"]', timeout=10000)
                        tab = self.page.locator('a[href="#tab-02"]').first
                        tab_class = tab.get_attribute('class') or ''
                        if 'active' not in tab_class:
                            tab.click()
                            time.sleep(0.4)  # Tab switch delay
                    except:
                        pass
                    
                    self.form_ready = True
                    # Return content with match result
                    return content
                except Exception as e:
                    print(f"Error during reload after match: {e}")
                    # Return content anyway so match can be processed
                    return content
                    
            elif has_no_match_modal:
                # No match found - close modal and proceed to next input (NO PAGE RELOAD)
                self._close_modal_if_present()
                # Content already updated, form is ready for next input
                self.form_ready = True
                return content
            else:
                # Neither result type detected - this shouldn't happen if wait worked correctly
                # But handle it anyway by closing any modal and proceeding
                print("Warning: Neither match nor no-match modal detected, closing any modal and proceeding...")
                self._close_modal_if_present()
                self.form_ready = True
                return content
            
            # Increment search count
            self.search_count += 1
            
            # Check if 40 seconds have elapsed since last pause
            current_time = time.time()
            elapsed_time = current_time - self.last_pause_time
            if elapsed_time >= 40.0:
                print(f"40 seconds elapsed, pausing for 10 seconds...")
                time.sleep(10.0)
                self.last_pause_time = time.time()
            
            # After every 5 searches, sleep 3s, reload page, and reinitialize form
            if self.search_count % 5 == 0:
                print(f"After {self.search_count} searches: sleeping 3s, reloading page, and reinitializing form...")
                time.sleep(3.0)  # Sleep for 3 seconds
                
                # Reload the page
                try:
                    self.page.reload(wait_until='load', timeout=90000)
                    time.sleep(2.0)  # Page load wait
                    
                    # Click on "Datos Personales" tab to access the form
                    try:
                        self.page.wait_for_selector('a[href="#tab-02"]', timeout=10000)
                        tab = self.page.locator('a[href="#tab-02"]').first
                        tab_class = tab.get_attribute('class') or ''
                        if 'active' not in tab_class:
                            tab.click()
                            time.sleep(0.4)  # Tab switch delay
                    except Exception as e:
                        print(f"Warning: Could not click 'Datos Personales' tab after reload: {e}")
                    
                    # Wait for form fields to be available
                    self.page.wait_for_selector('input#nombre', timeout=5000)
                    self.form_ready = True
                    print("Page reloaded and form reinitialized successfully.")
                except Exception as e:
                    print(f"Error during page reload after 10 searches: {e}")
                    # Try to recover by ensuring form is ready
                    try:
                        self._ensure_form_ready()
                    except:
                        pass
            
            # Apply delay after search
            self._random_delay()
            
            # Pause every N searches
            if self.search_count % self.pause_every_n == 0:
                print(f"Pausing for {self.pause_duration} seconds after {self.search_count} searches...")
                time.sleep(self.pause_duration)
            
            return content
            
        except Exception as e:
            print(f"Error during search: {e}")
            # Return empty content on error
            return ""
    
    def __enter__(self):
        """Context manager entry."""
        self.start_browser()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close_browser()

