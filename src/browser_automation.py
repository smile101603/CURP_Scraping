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
                time.sleep(2)  # Page load wait
                
                # Click on "Datos Personales" tab to access the form
                try:
                    # Wait for the tab to be available
                    self.page.wait_for_selector('a[href="#tab-02"]', timeout=15000)
                    # Click the "Datos Personales" tab
                    self.page.click('a[href="#tab-02"]')
                    time.sleep(0.7)  # Tab switch delay
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
    
    def _close_modal_if_present(self):
        """Close the error modal if it appears (no match found)."""
        if not self.page:
            return
        
        try:
            # Check for the modal close button
            close_button = self.page.query_selector('button[data-dismiss="modal"]')
            if close_button:
                close_button.click()
                time.sleep(0.2)  # Reduced from 0.5 seconds
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
                time.sleep(2)  # Page load wait
                
                # Click on "Datos Personales" tab to access the form
                try:
                    self.page.wait_for_selector('a[href="#tab-02"]', timeout=10000)
                    tab = self.page.locator('a[href="#tab-02"]').first
                    # Check if tab needs to be clicked (might already be active)
                    try:
                        tab_class = tab.get_attribute('class') or ''
                        if 'active' not in tab_class:
                            tab.click()
                            time.sleep(0.7)  # Tab switch delay
                    except:
                        # If we can't check, just click it anyway
                        tab.click()
                        time.sleep(0.7)  # Tab switch delay
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
                        time.sleep(0.7)  # Tab switch delay
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
            
            # Fill form fields directly (fill() will replace existing values, no need to clear)
            # Fill form fields using the actual IDs from the website
            
            # First name (nombres)
            self.page.fill('input#nombre', first_name, timeout=5000)
            
            # First last name (primerApellido)
            self.page.fill('input#primerApellido', last_name_1, timeout=5000)
            
            # Second last name (segundoApellido)
            self.page.fill('input#segundoApellido', last_name_2, timeout=5000)
            
            # Day - format as "01", "02", etc.
            day_str = str(day).zfill(2)
            self.page.select_option('select#diaNacimiento', day_str, timeout=5000)
            
            # Month - format as "01", "02", etc.
            month_str = str(month).zfill(2)
            self.page.select_option('select#mesNacimiento', month_str, timeout=5000)
            
            # Year
            year_str = str(year)
            self.page.fill('input#selectedYear', year_str, timeout=5000)
            
            # Gender (sexo) - values: "H", "M", or "X"
            gender_value = "H" if gender.upper() == "H" else "M"
            self.page.select_option('select#sexo', gender_value, timeout=5000)
            
            # State (claveEntidad) - convert state name to code
            state_code = get_state_code(state)
            self.page.select_option('select#claveEntidad', state_code, timeout=5000)
            
            # Submit form - for Ember.js forms, we need to click the submit button, not use form.submit()
            time.sleep(0.2)  # Reduced from 0.5 seconds
            submitted = False
            
            try:
                # Method 1: Look for submit button within the active tab form
                # The form is in tab-02, so submit button should be there
                submit_button = self.page.locator('#tab-02 form button[type="submit"]').first
                if submit_button.count() > 0:
                    submit_button.click()
                    submitted = True
                    time.sleep(0.2)  # Reduced from 0.5 seconds
            except Exception as e:
                pass
            
            if not submitted:
                try:
                    # Method 2: Look for any submit button in the current form
                    submit_button = self.page.locator('form button[type="submit"]').first
                    if submit_button.count() > 0:
                        submit_button.click()
                        submitted = True
                        time.sleep(0.2)  # Reduced from 0.5 seconds
                except Exception as e:
                    pass
            
            if not submitted:
                try:
                    # Method 3: Look for button with text "Buscar" or "Consultar"
                    buscar_button = self.page.locator('button:has-text("Buscar"), button:has-text("Consultar")').first
                    if buscar_button.count() > 0:
                        buscar_button.click()
                        submitted = True
                        time.sleep(0.2)  # Reduced from 0.5 seconds
                except Exception as e:
                    pass
            
            if not submitted:
                try:
                    # Method 4: Press Enter on the year field (last field filled)
                    self.page.keyboard.press('Enter')
                    submitted = True
                    time.sleep(0.2)  # Reduced from 0.5 seconds
                except Exception as e:
                    print(f"Warning: All form submission methods failed: {e}")
            
            # Wait for results with better detection (optimized)
            # Wait for either error modal OR results table to appear
            try:
                # Wait for either the modal button OR download link (which indicates results)
                self.page.wait_for_selector(
                    'button[data-dismiss="modal"], #dwnldLnk, table.panel-default, .panel-body table',
                    timeout=15000,  # Reduced from 20000
                    state='visible'
                )
            except Exception as e:
                # Wait a bit more and try again
                time.sleep(1)  # Reduced from 2 seconds
                try:
                    self.page.wait_for_selector(
                        'button[data-dismiss="modal"], #dwnldLnk, .panel-body',
                        timeout=8000  # Reduced from 10000
                    )
                except:
                    pass
            
            # Reduced wait for content to fully load
            time.sleep(0.8)  # Reduced from 2 seconds
            
            # Reduced wait for dynamic content (the site uses Ember.js)
            time.sleep(0.7)  # Reduced from 1.5 seconds
            
            # Check for results FIRST before closing modal
            # Get page content to check for matches
            content = self.page.content()
            
            # Check if we have results by looking for key indicators
            has_results = (
                '#dwnldLnk' in content or 
                'dwnldLnk' in content or 
                'Descarga del CURP' in content or
                'Datos del solicitante' in content
            )
            
            if not has_results:
                # No results, so close modal if present
                self._close_modal_if_present()
                # Re-get content after modal closes
                time.sleep(0.2)
                content = self.page.content()
                # Don't navigate - we're already on the form page, just continue
                # Set flag to indicate we don't need navigation next time
                self.form_ready = True
            else:
                # Match found! Navigate back to form for next search
                # This ensures clean state for next search
                self.form_ready = False  # Force navigation next time
            
            # Increment search count
            self.search_count += 1
            
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

