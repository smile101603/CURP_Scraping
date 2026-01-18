"""
Browser Automation
Handles browser automation using Playwright to interact with the CURP portal.
"""
import time
import random
import asyncio
import logging
import threading
import queue
import sys
import concurrent.futures
from typing import Optional, Dict
from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext
from state_codes import get_state_code

logger = logging.getLogger(__name__)


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
        
        # Track browser process IDs for force cleanup if needed
        self.browser_process_pids = []
    
    def start_browser(self):
        """Start browser and navigate to CURP page."""
        # Enhanced logging for diagnosis
        thread_id = threading.get_ident()
        thread_name = threading.current_thread().name
        logger.info(f"Starting browser in thread {thread_id} ({thread_name}), Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
        
        # More aggressive asyncio cleanup for Python 3.12+
        try:
            # Method 1: Try to get running loop (only returns if actually running)
            use_isolated_thread = False
            try:
                running_loop = asyncio.get_running_loop()
                logger.warning(f"Found running asyncio event loop in thread {thread_id}, attempting to handle...")
                # Can't close running loop from sync context, need different approach
                logger.info("Running event loop detected - using isolated thread method")
                use_isolated_thread = True
            except RuntimeError as e:
                if "no running event loop" not in str(e).lower():
                    # There IS a running loop - this is the problem
                    logger.error(f"Running event loop detected: {e}")
                    logger.info("Using isolated thread method to start Playwright")
                    use_isolated_thread = True
                else:
                    # No running loop - continue with cleanup
                    logger.debug("No running event loop detected")
            except AttributeError:
                # get_running_loop() not available (Python < 3.7)
                logger.debug("get_running_loop() not available, using fallback method")
            
            # If we detected a running loop, use isolated thread method
            if use_isolated_thread:
                self._start_playwright_in_isolated_thread()
                # Playwright is now started, skip normal initialization and continue to browser launch
            else:
                # Method 2: Try to get any event loop (even if not running)
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_closed():
                        # Loop exists but is closed - remove it
                        logger.debug("Found closed event loop, removing it")
                        asyncio.set_event_loop(None)
                    else:
                        # Loop exists and is not closed - close it
                        logger.warning(f"Found non-running event loop in thread {thread_id}, closing it...")
                        loop.close()
                        asyncio.set_event_loop(None)
                        logger.debug("Event loop closed and removed")
                except RuntimeError:
                    # No event loop exists - this is what we want
                    logger.debug("No event loop exists (expected)")
                
                # Method 3: Explicitly set event loop to None
                asyncio.set_event_loop(None)
                logger.debug("Event loop explicitly set to None")
                
                # Method 4: Log asyncio state for debugging
                try:
                    current_loop = asyncio.get_event_loop()
                    logger.debug(f"Event loop still exists after cleanup: {current_loop}")
                except RuntimeError:
                    logger.debug("Event loop successfully cleared (no loop exists)")
                
                # Now try to start Playwright normally
                logger.debug("Attempting to start Playwright...")
                self.playwright = sync_playwright().start()
                logger.info("Playwright started successfully")
            
        except Exception as e:
            error_msg = str(e).lower()
            if 'asyncio' in error_msg or 'event loop' in error_msg:
                logger.error(f"Playwright asyncio conflict after cleanup: {e}")
                logger.info("Attempting to start Playwright in isolated thread...")
                # Last resort: start in isolated thread
                self._start_playwright_in_isolated_thread()
                # Continue with browser launch after isolated thread method completes
            else:
                # Some other error, re-raise it
                logger.error(f"Unexpected error starting Playwright: {e}")
                raise
        
        # Launch browser
        self.browser = self.playwright.chromium.launch(
            headless=self.headless,
            args=['--disable-blink-features=AutomationControlled']
        )
        
        # Track browser process ID for force cleanup if needed
        try:
            if hasattr(self.browser, 'process') and self.browser.process:
                pid = self.browser.process.pid
                self.browser_process_pids.append(pid)
                logger.debug(f"Browser process started with PID: {pid}")
        except Exception as e:
            logger.debug(f"Could not track browser process PID: {e}")
        
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
    
    def _start_playwright_in_isolated_thread(self):
        """
        Start Playwright in an isolated thread with no asyncio context.
        This is a fallback when normal initialization fails due to asyncio conflicts.
        """
        logger.info("Starting Playwright in isolated thread...")
        result_queue = queue.Queue()
        error_queue = queue.Queue()
        
        def isolated_start():
            """Run Playwright start in completely isolated thread."""
            try:
                import sys
                thread_id = threading.get_ident()
                thread_name = threading.current_thread().name
                logger.debug(f"Isolated thread {thread_id} ({thread_name}) starting Playwright")
                
                # Ensure no event loop in this thread
                try:
                    asyncio.set_event_loop(None)
                    logger.debug(f"Isolated thread {thread_id}: Event loop cleared")
                except Exception as clear_error:
                    logger.debug(f"Isolated thread {thread_id}: Could not clear event loop: {clear_error}")
                
                # Try to get running loop in isolated thread
                try:
                    running_loop = asyncio.get_running_loop()
                    logger.warning(f"Isolated thread {thread_id}: Running loop detected, this shouldn't happen")
                except RuntimeError:
                    logger.debug(f"Isolated thread {thread_id}: No running loop (expected)")
                
                # Start Playwright
                logger.debug(f"Isolated thread {thread_id}: Starting Playwright...")
                playwright = sync_playwright().start()
                logger.info(f"Isolated thread {thread_id}: Playwright started successfully")
                result_queue.put(playwright)
            except Exception as e:
                logger.error(f"Isolated thread error: {e}", exc_info=True)
                error_queue.put(e)
        
        # Start isolated thread
        thread = threading.Thread(target=isolated_start, daemon=False, name="PlaywrightInitThread")
        thread.start()
        thread.join(timeout=30)  # Wait up to 30 seconds
        
        if thread.is_alive():
            logger.error("Playwright initialization timed out in isolated thread")
            raise RuntimeError("Playwright initialization timed out in isolated thread")
        
        if not error_queue.empty():
            error = error_queue.get()
            logger.error(f"Failed to start Playwright in isolated thread: {error}")
            raise RuntimeError(f"Failed to start Playwright in isolated thread: {error}")
        
        if result_queue.empty():
            logger.error("Playwright initialization completed but no result returned")
            raise RuntimeError("Playwright initialization completed but no result returned")
        
        self.playwright = result_queue.get()
        logger.info("Playwright started successfully in isolated thread, continuing with browser launch")
        
        # Continue with browser launch (in original thread)
        # Note: Playwright object can be used from any thread
    
    def _start_playwright_with_new_loop(self):
        """
        Alternative: Start Playwright by creating a new event loop.
        This is a fallback if isolated thread method doesn't work.
        """
        logger.info("Starting Playwright with new event loop wrapper...")
        
        def start_in_executor():
            """Start Playwright in executor with new event loop."""
            thread_id = threading.get_ident()
            logger.debug(f"Executor thread {thread_id}: Creating new event loop")
            
            # Create new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                logger.debug(f"Executor thread {thread_id}: Starting Playwright")
                # Start Playwright (sync API doesn't need asyncio, but we ensure clean state)
                playwright = sync_playwright().start()
                logger.info(f"Executor thread {thread_id}: Playwright started")
                return playwright
            finally:
                logger.debug(f"Executor thread {thread_id}: Cleaning up event loop")
                loop.close()
                asyncio.set_event_loop(None)
        
        # Run in thread pool executor
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(start_in_executor)
                self.playwright = future.result(timeout=30)
                logger.info("Playwright started successfully with new loop wrapper")
        except concurrent.futures.TimeoutError:
            logger.error("Playwright initialization timed out in executor")
            raise RuntimeError("Playwright initialization timed out in executor")
        except Exception as e:
            logger.error(f"Error starting Playwright in executor: {e}")
            raise
    
    def close_browser(self):
        """Close browser and cleanup with enhanced error handling and logging."""
        cleanup_errors = []
        
        # Close in reverse order with proper error handling
        # This helps avoid asyncio cleanup warnings on Windows
        # Note: RuntimeError warnings from asyncio on Windows are harmless
        
        # Close page
        if self.page:
            try:
                logger.debug("Closing browser page...")
                self.page.close()
                time.sleep(0.1)  # Small delay between closes
                logger.debug("Browser page closed successfully")
            except Exception as e:
                error_msg = f"Error closing page: {e}"
                logger.warning(error_msg)
                cleanup_errors.append(error_msg)
        
        # Close context
        if self.context:
            try:
                logger.debug("Closing browser context...")
                self.context.close()
                time.sleep(0.1)  # Small delay between closes
                logger.debug("Browser context closed successfully")
            except Exception as e:
                error_msg = f"Error closing context: {e}"
                logger.warning(error_msg)
                cleanup_errors.append(error_msg)
        
        # Close browser
        if self.browser:
            try:
                logger.debug("Closing browser...")
                self.browser.close()
                time.sleep(0.2)  # Longer delay before stopping playwright
                logger.debug("Browser closed successfully")
            except Exception as e:
                error_msg = f"Error closing browser: {e}"
                logger.warning(error_msg)
                cleanup_errors.append(error_msg)
        
        # Stop playwright
        if self.playwright:
            try:
                logger.debug("Stopping Playwright...")
                # Stop playwright - this might trigger asyncio cleanup warnings on Windows
                # but they are harmless and can be safely ignored
                self.playwright.stop()
                logger.debug("Playwright stopped successfully")
            except Exception as e:
                error_msg = f"Error stopping Playwright: {e}"
                logger.warning(error_msg)
                cleanup_errors.append(error_msg)
        
        # Reset references
        self.page = None
        self.context = None
        self.browser = None
        self.playwright = None
        self.form_ready = False
        self.browser_process_pids = []
        
        if cleanup_errors:
            logger.warning(f"Browser cleanup completed with {len(cleanup_errors)} error(s): {cleanup_errors}")
        else:
            logger.info("Browser cleanup completed successfully")
    
    def force_kill_browser_processes(self):
        """
        Force kill browser processes if normal cleanup fails.
        This is a last resort cleanup method.
        """
        if not self.browser_process_pids:
            return
        
        try:
            import psutil
            killed_count = 0
            for pid in self.browser_process_pids:
                try:
                    process = psutil.Process(pid)
                    if process.is_running():
                        logger.warning(f"Force killing browser process {pid}")
                        process.kill()
                        killed_count += 1
                except psutil.NoSuchProcess:
                    # Process already dead
                    pass
                except Exception as e:
                    logger.error(f"Error force killing process {pid}: {e}")
            
            if killed_count > 0:
                logger.warning(f"Force killed {killed_count} browser process(es)")
            self.browser_process_pids = []
        except ImportError:
            logger.warning("psutil not available - cannot force kill browser processes")
        except Exception as e:
            logger.error(f"Error in force_kill_browser_processes: {e}")
    
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
    
    def _type_like_human(self, locator, text: str, clear_first: bool = True):
        """
        Type text character by character like a human would.
        
        Args:
            locator: Playwright locator for the input field
            text: Text to type
            clear_first: Whether to clear the field first
        """
        try:
            # Click on the field first (humans click before typing)
            locator.click(timeout=5000)
            self._human_like_delay(0.1, 0.2)  # Small pause after clicking
            
            # Clear field if needed
            if clear_first:
                # Select all and delete (like humans do with Ctrl+A or triple-click)
                self.page.keyboard.press('Control+a')
                time.sleep(0.05)
                self.page.keyboard.press('Delete')
                self._human_like_delay(0.1, 0.15)
            
            # Type character by character with variable speed
            # Use average delay for the whole string, but add occasional pauses
            avg_delay_ms = random.randint(80, 120)  # Average typing speed
            
            # Type the text with variable delays by typing in small chunks
            # This simulates human typing patterns better than typing all at once
            chunk_size = random.randint(2, 4)  # Type 2-4 characters at a time
            i = 0
            
            while i < len(text):
                # Determine chunk size (smaller chunks = more human-like)
                current_chunk_size = min(chunk_size, len(text) - i)
                chunk = text[i:i + current_chunk_size]
                
                # Variable delay based on character types in chunk
                chunk_delay = avg_delay_ms
                if any(c.isdigit() for c in chunk):
                    chunk_delay = random.randint(100, 150)  # Numbers typed slower
                elif any(c.isupper() for c in chunk):
                    chunk_delay = random.randint(120, 180)  # Capitals slower
                
                # Occasional longer pause (like thinking or correcting)
                if random.random() < 0.08:  # 8% chance of longer pause
                    time.sleep(random.uniform(0.2, 0.5))
                
                # Type the chunk
                self.page.keyboard.type(chunk, delay=chunk_delay)
                
                # Small pause between chunks (like humans pause between words/numbers)
                if i + current_chunk_size < len(text):
                    time.sleep(random.uniform(0.05, 0.15))
                
                i += current_chunk_size
                # Vary chunk size for next iteration
                chunk_size = random.randint(2, 4)
            
            # Final pause after typing (humans pause to review)
            self._human_like_delay(0.1, 0.2)
        except Exception as e:
            logger.warning(f"Error in human-like typing, falling back to fill: {e}")
            # Fallback to regular fill if typing fails
            try:
                if clear_first:
                    locator.fill('')
                locator.fill(text)
            except Exception as fill_error:
                logger.error(f"Fallback fill also failed: {fill_error}")
                raise
    
    def _select_dropdown_like_human(self, locator, value: str):
        """
        Select dropdown option like a human would (hover, focus, select).
        Ensures dropdown is ready and focused before selection, and waits for each action to complete.
        
        Args:
            locator: Playwright locator for the select element
            value: Value to select
        """
        try:
            # Step 1: Wait for dropdown to be visible and ready (ensures it's the right time)
            locator.wait_for(state='visible', timeout=5000)
            self._human_like_delay(0.1, 0.15)
            
            # Step 2: Scroll to element if needed (humans scroll to see options)
            locator.scroll_into_view_if_needed()
            self._human_like_delay(0.1, 0.15)
            
            # Step 3: Hover over the dropdown first (humans often hover before interacting)
            locator.hover(timeout=5000)
            self._human_like_delay(0.1, 0.2)
            
            # Step 4: Focus on the dropdown (ensures it's ready for interaction, prevents other actions)
            # This ensures the dropdown is the active element before selection
            locator.focus(timeout=5000)
            self._human_like_delay(0.15, 0.25)  # Wait after focus to ensure it's ready
            
            # Step 5: Verify dropdown is still attached and ready (double-check)
            try:
                locator.wait_for(state='attached', timeout=2000)
            except:
                pass  # If wait fails, continue anyway
            
            # Step 6: Select the option directly (for HTML select elements, select_option works without clicking)
            # This is the actual selection - happens only when dropdown is focused and ready
            locator.select_option(value, timeout=5000)
            
            # Step 7: Wait briefly to ensure selection is applied and dropdown closes
            self._human_like_delay(0.15, 0.2)
            
            # Step 8: Verify selection was successful
            try:
                selected_value = locator.input_value(timeout=1000)
                if selected_value != value:
                    logger.debug(f"Dropdown selection verification: Expected {value}, Got {selected_value}")
                    # Try once more if value doesn't match
                    locator.select_option(value, timeout=5000)
                    self._human_like_delay(0.1, 0.15)
            except:
                pass  # If verification fails, assume selection worked
            
            # Step 9: Small pause after selection (humans verify their choice)
            self._human_like_delay(0.15, 0.3)
            
        except Exception as e:
            logger.warning(f"Error in human-like dropdown selection, falling back to select_option: {e}")
            # Fallback to regular select_option if human-like method fails
            try:
                # Ensure element is visible and ready before fallback
                locator.wait_for(state='visible', timeout=5000)
                locator.focus(timeout=5000)
                locator.select_option(value, timeout=5000)
            except Exception as fallback_error:
                logger.error(f"Fallback select_option also failed: {fallback_error}")
                raise
    
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
                    # Results detected - verify they are stable and return immediately
                    # If results are clearly present, return immediately regardless of loading indicators
                    # (loading indicators might be leftover UI elements)
                    
                    if has_match_result:
                        # Verify match result is present (check key indicators)
                        still_has_match = (
                            '#dwnldLnk' in content or 
                            'Descarga del CURP' in content or
                            'Datos del solicitante' in content
                        )
                        if still_has_match:
                            # Results are clearly present - return immediately
                            logger.debug("Match result detected, returning immediately")
                            return True
                    
                    if has_no_match_modal:
                        # Verify modal is present
                        still_has_modal = (
                            'Aviso importante' in content or
                            'warningMenssage' in content or
                            self.page.locator('button[data-dismiss="modal"]').count() > 0
                        )
                        if still_has_modal:
                            # No-match modal is clearly present - return immediately
                            logger.debug("No-match modal detected, returning immediately")
                            return True
                    
                    # If we detected results but verification failed, wait briefly and re-check
                    # This handles edge cases where results appear but aren't fully loaded yet
                    time.sleep(0.3)
                    continue  # Continue loop to re-check
                
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
            # Try to reload the page
            # If reload fails due to stale page object, try navigating fresh
            try:
                self.page.reload(wait_until='load', timeout=90000)
                time.sleep(2.0)  # Page load wait
            except (AttributeError, Exception) as reload_error:
                # If reload fails (e.g., stale page object), try navigating fresh
                error_str = str(reload_error).lower()
                if '_object' in error_str or 'dict' in error_str:
                    logger.warning(f"Page reload failed due to stale object in recovery, navigating fresh: {reload_error}")
                    try:
                        # Navigate to the page fresh instead of reloading
                        self.page.goto(self.url, wait_until='load', timeout=90000)
                        time.sleep(2.0)  # Page load wait
                    except Exception as nav_error:
                        logger.error(f"Failed to navigate fresh during recovery: {nav_error}")
                        return False
                else:
                    # Some other error, re-raise it
                    raise
            
            # Click on "Datos Personales" tab to access the form
            try:
                self.page.wait_for_selector('a[href="#tab-02"]', timeout=10000)
                tab = self.page.locator('a[href="#tab-02"]').first
                tab_class = tab.get_attribute('class') or ''
                if 'active' not in tab_class:
                    tab.click()
                    time.sleep(0.4)  # Tab switch delay
            except Exception as e:
                logger.warning(f"Could not click 'Datos Personales' tab during recovery: {e}")
                return False
            
            # Wait for form fields to be available
            self.page.wait_for_selector('input#nombre', timeout=5000)
            self.form_ready = True
            
            return True
            
        except Exception as e:
            logger.error(f"Error during recovery: {e}", exc_info=True)
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
            
            # First name (nombres) - type character by character like a human
            nombre_locator = self.page.locator('input#nombre')
            self._type_like_human(nombre_locator, first_name)
            self._human_like_delay(0.15, 0.25)  # Pause to "read" or "think" before moving to next field
            
            # First last name (primerApellido) - type character by character
            primer_apellido_locator = self.page.locator('input#primerApellido')
            self._type_like_human(primer_apellido_locator, last_name_1)
            self._human_like_delay(0.15, 0.25)
            
            # Second last name (segundoApellido) - type character by character
            segundo_apellido_locator = self.page.locator('input#segundoApellido')
            self._type_like_human(segundo_apellido_locator, last_name_2)
            self._human_like_delay(0.2, 0.35)  # Slightly longer pause before dropdowns
            
            # Day - format as "01", "02", etc. (humans click dropdown, wait, then select)
            day_str = str(day).zfill(2)
            dia_locator = self.page.locator('select#diaNacimiento')
            self._select_dropdown_like_human(dia_locator, day_str)
            self._human_like_delay(0.2, 0.3)  # Pause after dropdown selection
            
            # Month - format as "01", "02", etc.
            month_str = str(month).zfill(2)
            mes_locator = self.page.locator('select#mesNacimiento')
            self._select_dropdown_like_human(mes_locator, month_str)
            self._human_like_delay(0.2, 0.3)
            
            # Year (humans type numbers character by character)
            year_str = str(year)
            year_locator = self.page.locator('input#selectedYear')
            self._type_like_human(year_locator, year_str)
            self._human_like_delay(0.15, 0.25)
            
            # Gender (sexo) - values: "H", "M", or "X" (humans click dropdown, wait, then select)
            gender_value = "H" if gender.upper() == "H" else "M"
            sexo_locator = self.page.locator('select#sexo')
            self._select_dropdown_like_human(sexo_locator, gender_value)
            self._human_like_delay(0.2, 0.3)
            
            # State (claveEntidad) - convert state name to code (longer pause for state selection)
            state_code = get_state_code(state)
            estado_locator = self.page.locator('select#claveEntidad')
            self._select_dropdown_like_human(estado_locator, state_code)
            self._human_like_delay(0.25, 0.4)  # Longer pause before submitting (humans review state selection)
            
            # Submit form - humans pause before clicking submit button
            self._human_like_delay(0.2, 0.4)  # "Review" the form before submitting
            submitted = False
            
            try:
                # Method 1: Look for submit button within the active tab form
                # The form is in tab-02, so submit button should be there
                submit_button = self.page.locator('#tab-02 form button[type="submit"]').first
                if submit_button.count() > 0:
                    # Human-like button click: hover first, then click
                    submit_button.scroll_into_view_if_needed()
                    self._human_like_delay(0.1, 0.15)
                    submit_button.hover()
                    self._human_like_delay(0.1, 0.2)  # Brief pause after hover
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
                        # Human-like button click: hover first, then click
                        submit_button.scroll_into_view_if_needed()
                        self._human_like_delay(0.1, 0.15)
                        submit_button.hover()
                        self._human_like_delay(0.1, 0.2)
                        submit_button.click()
                        submitted = True
                        self._human_like_delay(0.3, 0.6)  # Form submission delay
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
                        # Re-fill the form and resubmit using human-like methods
                        # First name
                        nombre_locator = self.page.locator('input#nombre')
                        self._type_like_human(nombre_locator, first_name)
                        self._human_like_delay(0.1, 0.15)
                        # First last name
                        primer_apellido_locator = self.page.locator('input#primerApellido')
                        self._type_like_human(primer_apellido_locator, last_name_1)
                        self._human_like_delay(0.1, 0.15)
                        # Second last name
                        segundo_apellido_locator = self.page.locator('input#segundoApellido')
                        self._type_like_human(segundo_apellido_locator, last_name_2)
                        self._human_like_delay(0.1, 0.15)
                        # Day
                        day_str = str(day).zfill(2)
                        dia_locator = self.page.locator('select#diaNacimiento')
                        self._select_dropdown_like_human(dia_locator, day_str)
                        self._human_like_delay(0.1, 0.15)
                        # Month
                        month_str = str(month).zfill(2)
                        mes_locator = self.page.locator('select#mesNacimiento')
                        self._select_dropdown_like_human(mes_locator, month_str)
                        self._human_like_delay(0.1, 0.15)
                        # Year
                        year_str = str(year)
                        year_locator = self.page.locator('input#selectedYear')
                        self._type_like_human(year_locator, year_str)
                        self._human_like_delay(0.1, 0.15)
                        # Gender
                        gender_value = "H" if gender.upper() == "H" else "M"
                        sexo_locator = self.page.locator('select#sexo')
                        self._select_dropdown_like_human(sexo_locator, gender_value)
                        self._human_like_delay(0.1, 0.15)
                        # State
                        state_code = get_state_code(state)
                        estado_locator = self.page.locator('select#claveEntidad')
                        self._select_dropdown_like_human(estado_locator, state_code)
                        self._human_like_delay(0.15, 0.25)
                        # Resubmit
                        self._human_like_delay(0.3, 0.6)
                        try:
                            submit_button = self.page.locator('#tab-02 form button[type="submit"]').first
                            if submit_button.count() > 0:
                                # Human-like button click: hover first, then click
                                submit_button.scroll_into_view_if_needed()
                                self._human_like_delay(0.1, 0.15)
                                submit_button.hover()
                                self._human_like_delay(0.1, 0.2)
                                submit_button.click()
                                self._human_like_delay(0.3, 0.6)
                            else:
                                self.page.keyboard.press('Enter')
                                self._human_like_delay(0.3, 0.6)
                        except Exception as submit_error:
                            logger.debug(f"Submit button click failed, using Enter key: {submit_error}")
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
            search_completed = self._wait_for_search_completion(timeout=20.0)
            
            if not search_completed:
                # Timeout occurred - reload page and move to next input
                logger.warning("Search timeout after 20 seconds, reloading page and moving to next input...")
                try:
                    # Try to reload the page
                    # If reload fails due to stale page object, try navigating fresh
                    try:
                        self.page.reload(wait_until='load', timeout=90000)
                        time.sleep(2.0)  # Page load wait
                    except (AttributeError, Exception) as reload_error:
                        # If reload fails (e.g., stale page object), try navigating fresh
                        error_str = str(reload_error).lower()
                        if '_object' in error_str or 'dict' in error_str:
                            logger.warning(f"Page reload failed due to stale object, navigating fresh: {reload_error}")
                            try:
                                # Navigate to the page fresh instead of reloading
                                self.page.goto(self.url, wait_until='load', timeout=90000)
                                time.sleep(2.0)  # Page load wait
                            except Exception as nav_error:
                                logger.error(f"Failed to navigate fresh after reload error: {nav_error}")
                                # If navigation also fails, just continue - we'll try to use existing page
                                self.form_ready = True
                                return ""
                        else:
                            # Some other error, re-raise it
                            raise
                    
                    # Click on "Datos Personales" tab
                    # Note: After reload/navigation, all locators become stale, so we need to recreate them
                    try:
                        self.page.wait_for_selector('a[href="#tab-02"]', timeout=10000)
                        # Recreate locator after reload to avoid stale reference
                        tab = self.page.locator('a[href="#tab-02"]').first
                        # Use evaluate_handle or get_attribute safely
                        try:
                            tab_class = tab.get_attribute('class') or ''
                            if 'active' not in tab_class:
                                tab.click()
                                time.sleep(0.4)  # Tab switch delay
                        except Exception as attr_error:
                            # If get_attribute fails (stale object), just try clicking
                            logger.debug(f"Could not get tab attribute, trying direct click: {attr_error}")
                            tab.click()
                            time.sleep(0.4)  # Tab switch delay
                    except Exception as tab_error:
                        logger.debug(f"Could not switch to Datos Personales tab during timeout recovery: {tab_error}")
                        # Continue anyway - form might still be usable
                        pass
                    
                    self.form_ready = True
                    # Return empty content to indicate no result
                    return ""
                except Exception as e:
                    logger.error(f"Error during timeout recovery: {e}", exc_info=True)
                    # Try to ensure form is ready even if recovery failed
                    try:
                        self.form_ready = True
                    except:
                        pass
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

