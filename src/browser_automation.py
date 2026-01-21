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
                 pause_duration: int = 30, check_cancellation=None):
        """
        Initialize browser automation.
        
        Args:
            headless: Run browser in headless mode
            min_delay: Minimum delay between searches (seconds)
            max_delay: Maximum delay between searches (seconds)
            pause_every_n: Pause every N searches
            pause_duration: Duration of pause (seconds)
            check_cancellation: Optional function to check if job is cancelled
        """
        self.headless = headless
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.pause_every_n = pause_every_n
        self.pause_duration = pause_duration
        self.check_cancellation = check_cancellation
        
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        
        self.search_count = 0
        self.url = "https://www.gob.mx/curp/"
        self.form_ready = False  # Track if form has been initialized
        self._last_match_content = None  # Store match content when detected
        
        # Track browser process IDs for force cleanup if needed
        self.browser_process_pids = []
        
        # Track last entered values to skip re-entering unchanged fields
        self.last_nombre = None
        self.last_primer_apellido = None
        self.last_segundo_apellido = None
        self.last_dia = None
        self.last_mes = None
        self.last_year = None
        self.last_sexo = None
        self.last_estado = None
    
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
                logger.debug("[DELAY] Page load wait: 2.0s")
                time.sleep(2.0)  # Page load wait
                
                # Click on "Datos Personales" tab to access the form
                try:
                    # Wait for the tab to be available
                    self.page.wait_for_selector('a[href="#tab-02"]', timeout=15000)
                    # Click the "Datos Personales" tab
                    self.page.click('a[href="#tab-02"]')
                    logger.debug("[DELAY] Tab switch delay: 0.4s")
                    time.sleep(0.4)  # Tab switch delay
                except Exception as e:
                    print(f"Warning: Could not click 'Datos Personales' tab: {e}")
                    break
                
                # If we got here, navigation was successful
                break
            except Exception as e:
                if attempt < max_retries - 1:
                    print(f"Error navigating to {self.url} (attempt {attempt + 1}/{max_retries}): {e}")
                    print(f"Retrying in {retry_delay} seconds...")
                    logger.debug(f"[DELAY] Retry delay: {retry_delay}s")
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
        logger.debug(f"[DELAY] Typing delay: {delay:.3f}s (range: 0.1-0.2s)")
        time.sleep(delay)
    
    def _get_field_value(self, locator):
        """Get current value of a form field."""
        try:
            # Try input_value for input fields
            return locator.input_value(timeout=1000)
        except:
            try:
                # Try get_attribute for select fields
                return locator.get_attribute('value') or ''
            except:
                return None
    
    def _should_skip_field(self, field_name: str, new_value: str) -> bool:
        """
        Check if a field should be skipped because it already has the correct value.
        
        Args:
            field_name: Name of the field (e.g., 'nombre', 'dia', etc.)
            new_value: The value we want to set
            
        Returns:
            True if field should be skipped (value already matches), False otherwise
        """
        last_value_map = {
            'nombre': self.last_nombre,
            'primer_apellido': self.last_primer_apellido,
            'segundo_apellido': self.last_segundo_apellido,
            'dia': self.last_dia,
            'mes': self.last_mes,
            'year': self.last_year,
            'sexo': self.last_sexo,
            'estado': self.last_estado
        }
        
        last_value = last_value_map.get(field_name)
        if last_value is None:
            return False  # First time filling this field, don't skip
        
        # Normalize values for comparison (strip whitespace, handle case)
        last_normalized = str(last_value).strip()
        new_normalized = str(new_value).strip()
        
        return last_normalized == new_normalized
    
    def _reset_field_tracking(self):
        """Reset all tracked field values (called when page is reloaded)."""
        self.last_nombre = None
        self.last_primer_apellido = None
        self.last_segundo_apellido = None
        self.last_dia = None
        self.last_mes = None
        self.last_year = None
        self.last_sexo = None
        self.last_estado = None
        logger.debug("Reset field tracking values after page reload")
    
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
        Select dropdown option like a human would: click dropdown, wait for options, then click option.
        This mimics real human behavior of opening dropdown and selecting from visible options.
        
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
            
            # Step 3: Hover over the dropdown first (humans often hover before clicking)
            locator.hover(timeout=5000)
            self._human_like_delay(0.1, 0.2)
            
            # Step 4: Click on the dropdown to open it (like a human would)
            # This opens the dropdown and shows the options - humans click first to see options
            locator.click(timeout=5000)
            self._human_like_delay(0.2, 0.4)  # Wait for dropdown options to appear (humans see options before selecting)
            
            # Step 5: Wait for options to be visible/available
            # For HTML select elements, options appear after clicking
            # Humans take a moment to see and read the options before selecting
            self._human_like_delay(0.15, 0.25)  # Additional pause to "read" options
            
            # Step 6: Select the option by clicking on it (human-like: see option, click it)
            # After clicking dropdown and seeing options, humans click the desired option
            # Use select_option which will click the option with matching value
            # This simulates clicking on the visible option that appeared after opening dropdown
            locator.select_option(value, timeout=5000)
            
            # Step 7: Wait briefly to ensure selection is applied and dropdown closes
            self._human_like_delay(0.15, 0.2)
            
            # Step 8: Verify selection was successful
            try:
                selected_value = locator.input_value(timeout=1000)
                if selected_value != value:
                    logger.debug(f"Dropdown selection verification: Expected {value}, Got {selected_value}")
                    # If value doesn't match, try clicking dropdown again and selecting
                    logger.debug("Retrying dropdown selection...")
                    locator.click(timeout=5000)
                    self._human_like_delay(0.2, 0.3)
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
                locator.click(timeout=5000)
                self._human_like_delay(0.2, 0.3)
                locator.select_option(value, timeout=5000)
            except Exception as fallback_error:
                logger.error(f"Fallback select_option also failed: {fallback_error}")
                raise
    
    def _close_modal_if_present(self):
        """Close the error modal if it appears (no match found)."""
        time.sleep(2.0)
        if not self.page:
            return
        
        try:
            # Verify page is still valid before attempting to close modal
            if not self.page:
                return
            
            # Check if page is closed by trying to access a property
            try:
                _ = self.page.url  # This will raise if page is closed
            except Exception:
                return
            
            # OPTIMIZATION: Try clicking the close button first (more reliable than Escape)
            # Escape key can sometimes cause unexpected navigation
            try:
                # Check if modal button exists before trying to click
                modal_button = self.page.locator('button[data-dismiss="modal"]').first
                if modal_button.count() > 0:
                    # Use locator with shorter timeout (1 second max) to ensure total time stays under 2s
                    modal_button.click(timeout=1000)
                    
                    # Minimal delay after button click
                    time.sleep(0.1)  # Reduced delay
                    
                    # Verify page is still valid after click
                    try:
                        _ = self.page.url  # This will raise if page is closed
                        return
                    except Exception:
                        return
            except Exception as click_error:
                error_str = str(click_error).lower()
                if 'closed' in error_str or 'target page' in error_str:
                    return
                # Try Escape key as fallback
            
            # Fallback: Try Escape key if button click failed
            try:
                # Verify page is still valid before using Escape
                if not self.page:
                    return
                try:
                    _ = self.page.url  # This will raise if page is closed
                except Exception:
                    return
                
                self.page.keyboard.press('Escape')
                
                # Minimal delay after Escape (modal should close immediately)
                time.sleep(0.1)  # Reduced from 0.2s to 0.1s
                
                # Verify page is still valid after Escape
                try:
                    _ = self.page.url  # This will raise if page is closed
                except Exception:
                    return
            except Exception as escape_error:
                error_str = str(escape_error).lower()
                if 'closed' in error_str or 'target page' in error_str:
                    return
                # Modal may have already closed or be unresponsive - continue
        except Exception as e:
            error_str = str(e).lower()
            if 'closed' not in error_str and 'target page' not in error_str:
                logger.error(f"Error closing modal: {e}")
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
    
    def _wait_for_search_completion(self, timeout: float = 5.0):
        """
        Wait for search to complete (results or error modal appear).
        Uses longer timeout to handle slow bot detection responses.
        
        Args:
            timeout: Maximum time to wait in seconds (default 5.0)
        
        Returns:
            True if search completed successfully,
            False if timeout,
            "ERROR_DETECTED" if error message detected (service unavailable or required field)
        """
        start_time = time.time()
        
        # OPTIMIZATION: Use fast polling instead of wait_for_selector to detect immediately
        # Poll every 0.1 seconds - this is faster than wait_for_selector for modals that appear quickly
        check_interval = 0.1  # Check every 100ms
        max_checks = int(timeout / check_interval)  # Maximum number of checks
        
        for i in range(max_checks):
            # Check for cancellation during wait
            if self.check_cancellation and self.check_cancellation():
                logger.info("Job cancelled during search completion wait")
                return "CANCELLED"
            
            elapsed = time.time() - start_time
            if elapsed >= timeout:
                break
            
            # Check for modal button (most common case - no match)
            try:
                modal_button = self.page.locator('button[data-dismiss="modal"]')
                if modal_button.count() > 0:
                    return True
            except Exception as e:
                pass
            
            # Check for match result (download button)
            try:
                download_button = self.page.locator('button#download')
                if download_button.count() > 0:
                    return True
            except Exception as e:
                pass
            
            # Small delay before next check (only if not found yet)
            if i < max_checks - 1:  # Don't sleep on last iteration
                time.sleep(check_interval)
        
        # Fallback: Polling method (for cases where selectors don't work)
        last_check_time = start_time
        consecutive_no_change = 0
        first_check = True
        
        while (time.time() - start_time) < timeout:
            # Check for cancellation during polling
            if self.check_cancellation and self.check_cancellation():
                logger.info("Job cancelled during search completion polling")
                return "CANCELLED"
            
            try:
                # Get page content to check for both result types
                content = self.page.content()
                content_lower = content.lower()
                
                # PRIORITY: Check for no-match modal FIRST (faster to detect, common case)
                # This allows us to return immediately when modal appears
                has_no_match_modal = False
                try:
                    # Quick check for modal indicators (faster than checking for matches)
                    content_has_modal = (
                        'Aviso importante' in content or
                        'warningMenssage' in content or
                        'id="warningMenssage"' in content or
                        'Los datos ingresados no son correctos' in content
                    )
                    
                    # Check for modal button using locator
                    try:
                        locator_has_modal = self.page.locator('button[data-dismiss="modal"]').count() > 0
                    except:
                        locator_has_modal = False
                    
                    has_no_match_modal = content_has_modal or locator_has_modal
                    
                    # If modal detected, return immediately (no delays)
                    if has_no_match_modal:
                        logger.info("No-match modal detected via polling - returning")
                        return True
                except Exception as e:
                    logger.debug(f"Error checking for no-match modal: {e}")
                    has_no_match_modal = False
                
                # Check for error messages that require page reload
                has_service_error = (
                    'El servicio no está disponible, por favor intenta más tarde.' in content or
                    'el servicio no está disponible' in content_lower or
                    'id="errorLog"' in content and 'alert-danger' in content and 'servicio no está disponible' in content_lower
                )
                
                has_required_field_error = (
                    'Te falta completar algún campo requerido. Por favor verifica.' in content or
                    'te falta completar algún campo requerido' in content_lower or
                    'id="errorLog"' in content and 'alert-danger' in content and 'falta completar' in content_lower
                )
                
                # If service error or required field error detected, return special code
                if has_service_error or has_required_field_error:
                    error_type = "service unavailable" if has_service_error else "required field missing"
                    logger.warning(f"Error message detected ({error_type}), will reload page and skip this combination")
                    return "ERROR_DETECTED"
                
                # Accurately check for match found result (CURP data page)
                # PRIMARY INDICATOR: button id="download" - if this exists, there's a match
                has_match_result = False
                try:
                    # PRIMARY METHOD: Check for button id="download" using locator (most reliable)
                    locator_has_download_button = False
                    try:
                        download_button_count = self.page.locator('button#download').count()
                        if download_button_count > 0:
                            # Verify it's visible
                            download_button = self.page.locator('button#download').first
                            if download_button.is_visible(timeout=1000):
                                locator_has_download_button = True
                                logger.info("PRIMARY INDICATOR: button#download found and visible - MATCH CONFIRMED!")
                    except Exception as loc_error:
                        logger.debug(f"Error checking download button locator: {loc_error}")
                    
                    # SECONDARY METHOD: Check content for button id="download" (PRIMARY indicator in HTML)
                    content_has_download_button = (
                        'id="download"' in content or
                        'button id="download"' in content or
                        '<button id="download"' in content or
                        'button#download' in content
                    )
                    if content_has_download_button:
                        logger.info("PRIMARY INDICATOR: button id='download' found in content - MATCH CONFIRMED!")
                    
                    # FALLBACK METHODS: Check for other indicators (ALWAYS check, not just if primary not found)
                    # These are strong indicators that should be checked regardless
                    content_has_other = (
                        '#dwnldLnk' in content or 
                        'dwnldLnk' in content or
                        'id="dwnldLnk"' in content or
                        '<a id="dwnldLnk"' in content or
                        'Descarga del CURP' in content or
                        'Datos del solicitante' in content or
                        'Descargar pdf' in content or
                        'panel-body' in content
                    )
                    
                    try:
                        locator_has_other = (
                            self.page.locator('#dwnldLnk').count() > 0 or
                            self.page.locator('a[href*="download"]').count() > 0
                        )
                    except:
                        locator_has_other = False
                    
                    # Match confirmed if PRIMARY indicator exists OR fallback indicators exist
                    has_match_result = (
                        locator_has_download_button or  # PRIMARY: locator
                        content_has_download_button or   # PRIMARY: content
                        content_has_other or            # Fallback: content
                        locator_has_other               # Fallback: locator
                    )
                    
                    if has_match_result:
                        if locator_has_download_button or content_has_download_button:
                            logger.info("PRIMARY INDICATOR: Download button found - MATCH CONFIRMED!")
                        elif content_has_other or locator_has_other:
                            logger.info("FALLBACK INDICATORS: Other download indicators found - MATCH CONFIRMED!")
                except Exception as e:
                    logger.error(f"Error checking for match result: {e}")
                    import traceback
                    traceback.print_exc()
                    has_match_result = False
                
                # Accurately check for no match modal (error modal with specific structure)
                # Use multiple verification methods to ensure accuracy
                has_no_match_modal = False
                try:
                    # Method 1: Check content for modal indicators
                    content_has_modal = (
                        'Aviso importante' in content or
                        'warningMenssage' in content or
                        'id="warningMenssage"' in content or
                        'Los datos ingresados no son correctos' in content
                    )
                    
                    # Method 2: Check for modal button using locator
                    try:
                        locator_has_modal = self.page.locator('button[data-dismiss="modal"]').count() > 0
                    except:
                        locator_has_modal = False
                    
                    # Modal is confirmed only if either method detects it
                    has_no_match_modal = content_has_modal or locator_has_modal
                except Exception as e:
                    logger.debug(f"Error checking for no-match modal: {e}")
                    has_no_match_modal = False
                
                # Check for error messages that require page reload
                has_service_error = (
                    'El servicio no está disponible, por favor intenta más tarde.' in content or
                    'el servicio no está disponible' in content_lower or
                    'id="errorLog"' in content and 'alert-danger' in content and 'servicio no está disponible' in content_lower
                )
                
                has_required_field_error = (
                    'Te falta completar algún campo requerido. Por favor verifica.' in content or
                    'te falta completar algún campo requerido' in content_lower or
                    'id="errorLog"' in content and 'alert-danger' in content and 'falta completar' in content_lower
                )
                
                # If service error or required field error detected, return special code
                if has_service_error or has_required_field_error:
                    error_type = "service unavailable" if has_service_error else "required field missing"
                    logger.warning(f"Error message detected ({error_type}), will reload page and skip this combination")
                    # Return a special value to indicate error detected
                    return "ERROR_DETECTED"
                
                # Accurately determine if search is complete using multiple verification checks
                if has_match_result:
                    # Verify match result is actually present and stable (multiple checks)
                    # PRIMARY: Check for button id="download" (definitive indicator)
                    download_button_match = False
                    try:
                        download_button_count = self.page.locator('button#download').count()
                        if download_button_count > 0:
                            download_button = self.page.locator('button#download').first
                            if download_button.is_visible(timeout=1000):
                                download_button_match = True
                                logger.info("PRIMARY VERIFICATION: button#download confirmed visible")
                    except:
                        pass
                    
                    # Check 1: Content-based indicators (PRIMARY: button id="download")
                    content_has_download_button = (
                        'id="download"' in content or
                        'button id="download"' in content or
                        '<button id="download"' in content
                    )
                    
                    # Check 2: Other content-based indicators (fallback)
                    content_match_other = (
                        '#dwnldLnk' in content or 
                        'Descarga del CURP' in content or
                        'Datos del solicitante' in content
                    )
                    
                    # Check 3: Locator-based verification (fallback)
                    try:
                        locator_match = (
                            self.page.locator('#dwnldLnk').count() > 0 or
                            self.page.locator('a[href*="download"]').count() > 0
                        )
                    except:
                        locator_match = False
                    
                    # Match confirmed if PRIMARY indicator exists OR fallback indicators exist
                    if download_button_match or content_has_download_button or content_match_other or locator_match:
                        # Match result confirmed - verify it's stable by checking twice
                        logger.debug("[DELAY] Stability check pause: 0.2s")
                        time.sleep(0.2)  # Brief pause to ensure stability
                        # Re-check to confirm result is still there
                        content2 = self.page.content()
                        
                        # PRIMARY: Re-check for button id="download"
                        still_has_download_button = False
                        try:
                            if self.page.locator('button#download').count() > 0:
                                if self.page.locator('button#download').first.is_visible(timeout=1000):
                                    still_has_download_button = True
                        except:
                            pass
                        
                        still_has_match = (
                            still_has_download_button or  # PRIMARY indicator
                            'id="download"' in content2 or  # PRIMARY in content
                            '#dwnldLnk' in content2 or 
                            'Descarga del CURP' in content2 or
                            'Datos del solicitante' in content2
                        )
                        if still_has_match:
                            # Results are confirmed and stable
                            # IMPORTANT: Capture content IMMEDIATELY before any delays (to prevent page changes)
                            match_content = None
                            try:
                                # Get the current page content IMMEDIATELY (before any sleep)
                                match_content = self.page.content()
                                logger.info(f"Match content captured immediately ({len(match_content)} chars)")
                                
                                # Verify it has match indicators (check multiple formats)
                                # PRIMARY: Check for button id="download"
                                has_download_button = (
                                    'id="download"' in match_content or
                                    'button id="download"' in match_content or
                                    '<button id="download"' in match_content
                                )
                                
                                # FALLBACK: Other indicators
                                has_other_indicators = (
                                    '#dwnldLnk' in match_content or 
                                    'dwnldLnk' in match_content or
                                    'id="dwnldLnk"' in match_content or
                                    'id=\'dwnldLnk\'' in match_content or
                                    'Descarga del CURP' in match_content or 
                                    'Datos del solicitante' in match_content or
                                    'panel-body' in match_content
                                )
                                
                                has_indicators = has_download_button or has_other_indicators
                                
                                # Also check for CURP pattern directly
                                import re
                                curp_check = re.search(r'[A-Z]{4}\d{6}[HM][A-Z]{5}[0-9A-Z]\d', match_content)
                                has_curp_pattern = curp_check is not None
                                
                                if has_indicators or has_curp_pattern:
                                    # Store in instance variable so it can be retrieved after return
                                    self._last_match_content = match_content
                                    logger.info(f"Match content stored successfully - indicators: {has_indicators}, CURP pattern: {has_curp_pattern}")
                                    if curp_check:
                                        logger.info(f"CURP found in stored content: {curp_check.group(0)}")
                                else:
                                    logger.error("Match detected but content doesn't have indicators - this shouldn't happen!")
                                    # Store anyway - might be a detection issue
                                    self._last_match_content = match_content
                            except Exception as e:
                                logger.error(f"CRITICAL: Could not capture match content: {e}")
                                import traceback
                                traceback.print_exc()
                            
                            # Now wait before proceeding (content already captured)
                            wait_time = 0.7 + random.uniform(0.3, 0.6)
                            logger.info(f"[DELAY] Match result wait: {wait_time:.3f}s (0.7 + random 0.3-0.6s)")
                            time.sleep(wait_time)
                            
                            return True
                        else:
                            # Result disappeared - might be loading, continue checking
                            logger.debug("Match result detected but not stable, continuing to check...")
                            time.sleep(0.3)
                            continue
                    else:
                        # Indicators found but verification failed - might be false positive
                        logger.debug("Match indicators found but verification failed, continuing to check...")
                        time.sleep(0.3)
                        continue
                
                # Modal check already done at the start of loop - skip duplicate check
                
                # Use variable check interval (more human-like)
                # Skip delay on first check to catch quick responses
                if not first_check:
                    check_interval = random.uniform(0.2, 0.5)  # Reduced from 0.3-0.8s
                    time.sleep(check_interval)
                else:
                    first_check = False
                
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
                self._reset_field_tracking()  # Reset tracking after reload
            except (AttributeError, Exception) as reload_error:
                # If reload fails (e.g., stale page object), try navigating fresh
                error_str = str(reload_error).lower()
                if '_object' in error_str or 'dict' in error_str:
                    logger.warning(f"Page reload failed due to stale object in recovery, navigating fresh: {reload_error}")
                    try:
                        # Navigate to the page fresh instead of reloading
                        self.page.goto(self.url, wait_until='load', timeout=90000)
                        time.sleep(2.0)  # Page load wait
                        self._reset_field_tracking()  # Reset tracking after navigation
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
        
        # CRITICAL: Clear any stored match content from previous searches at the START
        # This ensures each search starts with a clean state and prevents false positives
        if hasattr(self, '_last_match_content'):
            if self._last_match_content:
                logger.debug("Clearing stored match content from previous search at start of new search")
            self._last_match_content = None
        
        try:
            # Ensure form is ready (only navigate if we're on results page)
            # Don't navigate if we're already on the form page
            self._ensure_form_ready()
            
            # Fill form fields with human-like timing (simulates real user behavior)
            # Fill form fields using the actual IDs from the website
            # Skip fields that already have the correct value to optimize performance
            
            # First name (nombres) - type character by character like a human
            # Total time target: ~1.0-2.45s
            if not self._should_skip_field('nombre', first_name):
                nombre_locator = self.page.locator('input#nombre')
                start_time = time.time()
                self._type_like_human(nombre_locator, first_name)
                elapsed = time.time() - start_time
                # Adjust delay to meet total time target (1.0-2.45s)
                target_min, target_max = 1.0, 2.45
                if elapsed < target_min:
                    remaining_delay = target_min - elapsed
                    time.sleep(remaining_delay + random.uniform(0, target_max - target_min))
                elif elapsed < target_max:
                    time.sleep(random.uniform(0, target_max - elapsed))
                self._human_like_delay(0.1, 0.15)  # Small transition delay
                self.last_nombre = first_name
            else:
                logger.debug(f"Skipping nombre field - already set to '{first_name}'")
                self._human_like_delay(0.1, 0.15)  # Small transition delay
            
            # First last name (primerApellido) - type character by character
            # Total time target: ~1.15-2.5s
            if not self._should_skip_field('primer_apellido', last_name_1):
                primer_apellido_locator = self.page.locator('input#primerApellido')
                start_time = time.time()
                self._type_like_human(primer_apellido_locator, last_name_1)
                elapsed = time.time() - start_time
                target_min, target_max = 1.15, 2.5
                if elapsed < target_min:
                    remaining_delay = target_min - elapsed
                    time.sleep(remaining_delay + random.uniform(0, target_max - target_min))
                elif elapsed < target_max:
                    time.sleep(random.uniform(0, target_max - elapsed))
                self._human_like_delay(0.1, 0.15)
                self.last_primer_apellido = last_name_1
            else:
                logger.debug(f"Skipping primer_apellido field - already set to '{last_name_1}'")
                self._human_like_delay(0.1, 0.15)
            
            # Second last name (segundoApellido) - type character by character
            # Total time target: ~1.2-2.7s
            if not self._should_skip_field('segundo_apellido', last_name_2):
                segundo_apellido_locator = self.page.locator('input#segundoApellido')
                start_time = time.time()
                self._type_like_human(segundo_apellido_locator, last_name_2)
                elapsed = time.time() - start_time
                target_min, target_max = 1.2, 2.7
                if elapsed < target_min:
                    remaining_delay = target_min - elapsed
                    time.sleep(remaining_delay + random.uniform(0, target_max - target_min))
                elif elapsed < target_max:
                    time.sleep(random.uniform(0, target_max - elapsed))
                self._human_like_delay(0.1, 0.15)
                self.last_segundo_apellido = last_name_2
            else:
                logger.debug(f"Skipping segundo_apellido field - already set to '{last_name_2}'")
                self._human_like_delay(0.1, 0.15)
            
            # Day - format as "01", "02", etc. (humans click dropdown, wait, then select)
            # Total time target: ~1.15-1.85s
            day_str = str(day).zfill(2)
            if not self._should_skip_field('dia', day_str):
                dia_locator = self.page.locator('select#diaNacimiento')
                start_time = time.time()
                self._select_dropdown_like_human(dia_locator, day_str)
                elapsed = time.time() - start_time
                target_min, target_max = 1.15, 1.85
                if elapsed < target_min:
                    remaining_delay = target_min - elapsed
                    time.sleep(remaining_delay + random.uniform(0, target_max - target_min))
                elif elapsed < target_max:
                    time.sleep(random.uniform(0, target_max - elapsed))
                self._human_like_delay(0.1, 0.15)
                self.last_dia = day_str
            else:
                logger.debug(f"Skipping dia field - already set to '{day_str}'")
                self._human_like_delay(0.1, 0.15)
            
            # Month - format as "01", "02", etc.
            # Total time target: ~1.35-2.0s
            month_str = str(month).zfill(2)
            if not self._should_skip_field('mes', month_str):
                mes_locator = self.page.locator('select#mesNacimiento')
                start_time = time.time()
                self._select_dropdown_like_human(mes_locator, month_str)
                elapsed = time.time() - start_time
                target_min, target_max = 1.35, 2.0
                if elapsed < target_min:
                    remaining_delay = target_min - elapsed
                    time.sleep(remaining_delay + random.uniform(0, target_max - target_min))
                elif elapsed < target_max:
                    time.sleep(random.uniform(0, target_max - elapsed))
                self._human_like_delay(0.1, 0.15)
                self.last_mes = month_str
            else:
                logger.debug(f"Skipping mes field - already set to '{month_str}'")
                self._human_like_delay(0.1, 0.15)
            
            # Year (humans type numbers character by character)
            # Total time target: ~0.9-1.45s
            year_str = str(year)
            if not self._should_skip_field('year', year_str):
                year_locator = self.page.locator('input#selectedYear')
                start_time = time.time()
                self._type_like_human(year_locator, year_str)
                elapsed = time.time() - start_time
                target_min, target_max = 0.9, 1.45
                if elapsed < target_min:
                    remaining_delay = target_min - elapsed
                    time.sleep(remaining_delay + random.uniform(0, target_max - target_min))
                elif elapsed < target_max:
                    time.sleep(random.uniform(0, target_max - elapsed))
                self._human_like_delay(0.1, 0.15)
                self.last_year = year_str
            else:
                logger.debug(f"Skipping year field - already set to '{year_str}'")
                self._human_like_delay(0.1, 0.15)
            
            # Gender (sexo) - values: "H", "M", or "X" (humans click dropdown, wait, then select)
            # Total time target: ~1.35-1.95s
            gender_value = "H" if gender.upper() == "H" else "M"
            if not self._should_skip_field('sexo', gender_value):
                sexo_locator = self.page.locator('select#sexo')
                start_time = time.time()
                self._select_dropdown_like_human(sexo_locator, gender_value)
                elapsed = time.time() - start_time
                target_min, target_max = 1.35, 1.95
                if elapsed < target_min:
                    remaining_delay = target_min - elapsed
                    time.sleep(remaining_delay + random.uniform(0, target_max - target_min))
                elif elapsed < target_max:
                    time.sleep(random.uniform(0, target_max - elapsed))
                self._human_like_delay(0.1, 0.15)
                self.last_sexo = gender_value
            else:
                logger.debug(f"Skipping sexo field - already set to '{gender_value}'")
                self._human_like_delay(0.1, 0.15)
            
            # State (claveEntidad) - convert state name to code (longer pause for state selection)
            # Total time target: ~1.4-2.05s
            state_code = get_state_code(state)
            if not self._should_skip_field('estado', state_code):
                estado_locator = self.page.locator('select#claveEntidad')
                start_time = time.time()
                self._select_dropdown_like_human(estado_locator, state_code)
                elapsed = time.time() - start_time
                target_min, target_max = 1.4, 2.05
                if elapsed < target_min:
                    remaining_delay = target_min - elapsed
                    time.sleep(remaining_delay + random.uniform(0, target_max - target_min))
                elif elapsed < target_max:
                    time.sleep(random.uniform(0, target_max - elapsed))
                self._human_like_delay(0.1, 0.15)
                self.last_estado = state_code
            else:
                logger.debug(f"Skipping estado field - already set to '{state_code}'")
                self._human_like_delay(0.1, 0.15)
            
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
                        # Reduced delay after clicking - modal detection will handle timing
                        logger.debug("[DELAY] Form submission delay (reduced): 0.1s")
                        time.sleep(0.1)  # Minimal delay - wait_for_selector will handle the rest
                except Exception as e:
                    pass
            
            if not submitted:
                try:
                    # Method 3: Look for button with text "Buscar" or "Consultar"
                    buscar_button = self.page.locator('button:has-text("Buscar"), button:has-text("Consultar")').first
                    if buscar_button.count() > 0:
                        buscar_button.click()
                    submitted = True
                    # NO DELAY after clicking - start checking for modal immediately!
                    logger.debug("[DELAY] Form submitted (Buscar button) - starting immediate modal detection (no delay)")
                except Exception as e:
                    pass
            
            if not submitted:
                try:
                    # Method 4: Press Enter on the year field (last field filled)
                    self.page.keyboard.press('Enter')
                    submitted = True
                    # Reduced delay after Enter - wait_for_selector will handle timing
                    logger.debug("[DELAY] Form submission delay (Enter key, reduced): 0.1s")
                    time.sleep(0.1)  # Minimal delay - wait_for_selector will handle the rest
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
            
            # Wait for search completion with 10-second timeout
            # Modal usually appears within 1-2 seconds, but we allow up to 10s for slow responses
            # If no result after 10s, we'll reload the page and move to next input
            # Start checking IMMEDIATELY after form submission (no delays)
            search_completed = self._wait_for_search_completion(timeout=5.0)
            
            # Check if job was cancelled
            if search_completed == "CANCELLED":
                logger.info("Job cancelled during search, returning empty result")
                return ""
            
            # CRITICAL: Check if no-match modal was detected BEFORE doing expensive result checks
            # If modal was detected, skip all the expensive selector checks and go straight to closing
            has_no_match_modal_detected = False
            if search_completed:
                # Quick check if modal is present (no-match case) - don't wait, just check count
                # This MUST happen immediately after _wait_for_search_completion returns
                try:
                    modal_button = self.page.locator('button[data-dismiss="modal"]')
                    modal_count = modal_button.count()  # This is fast, no wait
                    
                    if modal_count > 0:
                        has_no_match_modal_detected = True
                except Exception as modal_check_error:
                    import traceback
                    traceback.print_exc()
                    pass
            
            # Check if error messages were detected (service unavailable or required field missing)
            if search_completed == "ERROR_DETECTED":
                # Error message detected - reload page and move to next input
                logger.warning("Error message detected (service unavailable or required field), reloading page and moving to next input...")
                page_reloaded = False
                
                # Attempt to reload the page
                try:
                    logger.debug("Attempting to reload page after error detection...")
                    self.page.reload(wait_until='load', timeout=90000)
                    logger.debug("[DELAY] Page reload wait: 2.0s")
                    time.sleep(2.0)  # Page load wait
                    self._reset_field_tracking()  # Reset tracking after reload
                    page_reloaded = True
                    logger.debug("Page reloaded successfully after error detection")
                except (AttributeError, Exception) as reload_error:
                    # If reload fails (e.g., stale page object), try navigating fresh
                    error_str = str(reload_error).lower()
                    if '_object' in error_str or 'dict' in error_str:
                        logger.warning(f"Page reload failed due to stale object, navigating fresh: {reload_error}")
                        try:
                            logger.debug("Navigating to fresh page after reload failure...")
                            self.page.goto(self.url, wait_until='load', timeout=90000)
                            time.sleep(2.0)  # Page load wait
                            page_reloaded = True
                            logger.debug("Page navigated successfully after reload failure")
                        except Exception as nav_error:
                            logger.error(f"Failed to navigate fresh after reload error: {nav_error}")
                            # If navigation also fails, raise error - we must reload page
                            logger.error(f"All reload attempts failed: {reload_error}, {nav_error}")
                            raise RuntimeError(f"Failed to reload page after error detection: {reload_error}, {nav_error}")
                    else:
                        # Some other error - try navigating fresh
                        logger.warning(f"Reload failed with error: {reload_error}, trying fresh navigation...")
                        try:
                            self.page.goto(self.url, wait_until='load', timeout=90000)
                            time.sleep(2.0)
                            page_reloaded = True
                            logger.debug("Page navigated successfully after reload error")
                        except Exception as nav_error2:
                            logger.error(f"Navigation also failed: {nav_error2}")
                            # All reload attempts failed - raise error
                            raise RuntimeError(f"Failed to reload page after error detection: {reload_error}, {nav_error2}")
                
                # Verify page was reloaded before proceeding
                if not page_reloaded:
                    logger.error("CRITICAL: Page was not reloaded after error detection, but code is continuing!")
                    raise RuntimeError("Page reload failed after error detection - cannot proceed safely")
                
                # Click on "Datos Personales" tab after successful reload
                try:
                    logger.debug("Waiting for Datos Personales tab after reload...")
                    self.page.wait_for_selector('a[href="#tab-02"]', timeout=10000)
                    tab = self.page.locator('a[href="#tab-02"]').first
                    try:
                        tab_class = tab.get_attribute('class') or ''
                        if 'active' not in tab_class:
                            logger.debug("Clicking Datos Personales tab...")
                            tab.click()
                            time.sleep(0.4)  # Tab switch delay
                    except Exception as attr_error:
                        logger.debug(f"Could not get tab attribute, trying direct click: {attr_error}")
                        tab.click()
                        time.sleep(0.4)  # Tab switch delay
                    logger.debug("Successfully switched to Datos Personales tab after reload")
                except Exception as tab_error:
                    logger.warning(f"Could not switch to Datos Personales tab during error recovery: {tab_error}")
                    # Try to ensure form is ready even if tab click failed
                    try:
                        self._ensure_form_ready()
                    except Exception as ensure_error:
                        logger.error(f"Could not ensure form ready after tab error: {ensure_error}")
                
                # Ensure form is actually ready before proceeding (wait for form fields)
                try:
                    logger.debug("Verifying form fields are ready after error recovery...")
                    self.page.wait_for_selector('input#nombre', timeout=5000)
                    self.form_ready = True
                    logger.info("Page reloaded and form ready after error detection - proceeding to next input")
                except Exception as form_error:
                    logger.error(f"Form fields not ready after error recovery: {form_error}")
                    # Try to ensure form is ready using the full method
                    try:
                        self._ensure_form_ready()
                        logger.info("Form ready after full ensure_form_ready() call")
                    except Exception as ensure_error:
                        logger.error(f"Could not ensure form ready: {ensure_error}")
                        # Set form_ready anyway to allow continuation (will be checked on next search)
                        self.form_ready = True
                
                # Return empty content to indicate no result (skip this combination)
                return ""
            
            if not search_completed:
                # Timeout occurred - MUST reload page before moving to next input
                logger.warning(f"Search timeout after {detection_time:.1f} seconds, reloading page and moving to next input...")
                page_reloaded = False
                
                # Helper function to detect loading spinner
                def is_loading_spinner_visible():
                    """Check if the loading spinner (oval.svg) is visible on the page."""
                    try:
                        # Check for the loading spinner image by src attribute
                        spinner_locator = self.page.locator('img[src*="oval.svg"]')
                        count = spinner_locator.count()
                        if count > 0:
                            # Check if any spinner is visible
                            for i in range(count):
                                try:
                                    if spinner_locator.nth(i).is_visible(timeout=100):
                                        return True
                                except:
                                    continue
                            return False
                    except Exception as e:
                        logger.debug(f"Error checking for loading spinner: {e}")
                        return False
                
                # Check if spinner is visible before reload (to confirm page state)
                spinner_before = is_loading_spinner_visible()
                logger.debug(f"Loading spinner visible before reload: {spinner_before}")
                
                # Attempt 1: Try to reload the page
                try:
                    logger.debug("Attempting to reload page after timeout...")
                    self.page.reload(wait_until='load', timeout=90000)
                    
                    # Wait for loading spinner to appear and then disappear (confirms reload is happening)
                    spinner_detected = False
                    max_wait_for_spinner = 2.0  # Wait up to 2 seconds for spinner to appear
                    spinner_check_start = time.time()
                    while (time.time() - spinner_check_start) < max_wait_for_spinner:
                        if is_loading_spinner_visible():
                            spinner_detected = True
                            logger.debug("Loading spinner detected - page is reloading...")
                            break
                        time.sleep(0.1)
                    
                    # If spinner was detected, wait for it to disappear (reload complete)
                    if spinner_detected:
                        max_wait_for_complete = 5.0  # Wait up to 5 seconds for spinner to disappear
                        spinner_complete_start = time.time()
                        while (time.time() - spinner_complete_start) < max_wait_for_complete:
                            if not is_loading_spinner_visible():
                                logger.debug("Loading spinner disappeared - reload complete")
                                break
                            time.sleep(0.1)
                        else:
                            logger.warning("Loading spinner still visible after reload timeout")
                    else:
                        logger.debug("Loading spinner not detected during reload (may have loaded too quickly)")
                    
                    time.sleep(0.5)  # Small delay after reload completes
                    self._reset_field_tracking()  # Reset tracking after reload
                    page_reloaded = True
                    logger.debug("Page reloaded successfully after timeout")
                except (AttributeError, Exception) as reload_error:
                    # If reload fails (e.g., stale page object), try navigating fresh
                    error_str = str(reload_error).lower()
                    if '_object' in error_str or 'dict' in error_str:
                        logger.warning(f"Page reload failed due to stale object, navigating fresh: {reload_error}")
                        try:
                            # Navigate to the page fresh instead of reloading
                            logger.debug("Navigating to fresh page after reload failure...")
                            self.page.goto(self.url, wait_until='load', timeout=90000)
                            
                            # Check for loading spinner to confirm navigation is happening
                            try:
                                spinner_locator = self.page.locator('img[src*="oval.svg"]')
                                if spinner_locator.count() > 0:
                                    logger.debug("Loading spinner detected during navigation")
                                    # Wait for spinner to disappear
                                    for i in range(50):  # Wait up to 5 seconds
                                        if not spinner_locator.first.is_visible(timeout=100):
                                            logger.debug("Loading spinner disappeared - navigation complete")
                                            break
                                        time.sleep(0.1)
                            except:
                                pass  # Spinner check is optional
                            
                            time.sleep(0.5)  # Small delay after navigation
                            self._reset_field_tracking()  # Reset tracking after navigation
                            page_reloaded = True
                            logger.debug("Page navigated successfully after reload failure")
                        except Exception as nav_error:
                            logger.error(f"Failed to navigate fresh after reload error: {nav_error}")
                            # If navigation also fails, raise error - we must reload page
                            logger.error(f"All reload attempts failed: {reload_error}, {nav_error}")
                            raise RuntimeError(f"Failed to reload page after timeout: {reload_error}, {nav_error}")
                    else:
                        # Some other error - try navigating fresh
                        logger.warning(f"Reload failed with error: {reload_error}, trying fresh navigation...")
                        try:
                            self.page.goto(self.url, wait_until='load', timeout=90000)
                            
                            # Check for loading spinner to confirm navigation is happening
                            try:
                                spinner_locator = self.page.locator('img[src*="oval.svg"]')
                                if spinner_locator.count() > 0:
                                    logger.debug("Loading spinner detected during navigation")
                                    # Wait for spinner to disappear
                                    for i in range(50):  # Wait up to 5 seconds
                                        if not spinner_locator.first.is_visible(timeout=100):
                                            logger.debug("Loading spinner disappeared - navigation complete")
                                            break
                                        time.sleep(0.1)
                            except:
                                pass  # Spinner check is optional
                            
                            time.sleep(0.5)  # Small delay after navigation
                            self._reset_field_tracking()  # Reset tracking after navigation
                            page_reloaded = True
                            logger.debug("Page navigated successfully after reload error")
                        except Exception as nav_error2:
                            logger.error(f"Navigation also failed: {nav_error2}")
                            # All reload attempts failed - raise error
                            raise RuntimeError(f"Failed to reload page after timeout: {reload_error}, {nav_error2}")
                
                # Verify page was reloaded before proceeding
                if not page_reloaded:
                    logger.error("CRITICAL: Page was not reloaded after timeout, but code is continuing!")
                    raise RuntimeError("Page reload failed after timeout - cannot proceed safely")
                
                # Click on "Datos Personales" tab after successful reload
                # Note: After reload/navigation, all locators become stale, so we need to recreate them
                try:
                    logger.debug("Waiting for Datos Personales tab after reload...")
                    self.page.wait_for_selector('a[href="#tab-02"]', timeout=10000)
                    # Recreate locator after reload to avoid stale reference
                    tab = self.page.locator('a[href="#tab-02"]').first
                    # Use evaluate_handle or get_attribute safely
                    try:
                        tab_class = tab.get_attribute('class') or ''
                        if 'active' not in tab_class:
                            logger.debug("Clicking Datos Personales tab...")
                            tab.click()
                            time.sleep(0.4)  # Tab switch delay
                    except Exception as attr_error:
                        # If get_attribute fails (stale object), just try clicking
                        logger.debug(f"Could not get tab attribute, trying direct click: {attr_error}")
                        tab.click()
                        time.sleep(0.4)  # Tab switch delay
                    logger.debug("Successfully switched to Datos Personales tab after reload")
                except Exception as tab_error:
                    logger.warning(f"Could not switch to Datos Personales tab during timeout recovery: {tab_error}")
                    # Try to ensure form is ready even if tab click failed
                    try:
                        self._ensure_form_ready()
                    except Exception as ensure_error:
                        logger.error(f"Could not ensure form ready after tab error: {ensure_error}")
                        # Don't raise - we'll try to continue
                
                # Ensure form is actually ready before proceeding (wait for form fields)
                try:
                    logger.debug("Verifying form fields are ready after timeout recovery...")
                    self.page.wait_for_selector('input#nombre', timeout=5000)
                    self.form_ready = True
                    logger.info("Page reloaded and form ready after timeout - proceeding to next input")
                except Exception as form_error:
                    logger.error(f"Form fields not ready after timeout recovery: {form_error}")
                    # Try to ensure form is ready using the full method
                    try:
                        self._ensure_form_ready()
                        logger.info("Form ready after full ensure_form_ready() call")
                    except Exception as ensure_error:
                        logger.error(f"Could not ensure form ready: {ensure_error}")
                        # Set form_ready anyway to allow continuation (will be checked on next search)
                        self.form_ready = True
                
                # Return empty content to indicate no result
                return ""
            
            # ====================================================================
            # CRITICAL: Check and record results FIRST before any other actions
            # ====================================================================
            # SKIP expensive checks if we already know it's a no-match modal
            if has_no_match_modal_detected:
                logger.info("=== SKIPPING EXPENSIVE RESULT CHECKS - No-match modal already detected ===")
                content = self.page.content()  # Get content for validation, but skip expensive selector checks
                has_match_result = False
            else:
                logger.info("=== CHECKING FOR RESULTS FIRST (before any other actions) ===")
                
                # Step 1: Check if _wait_for_search_completion already detected a match
                # If it did, trust it and use the stored content directly
                if hasattr(self, '_last_match_content') and self._last_match_content:
                    stored_content = self._last_match_content
                    logger.info(f"Using stored match content from _wait_for_search_completion ({len(stored_content)} chars)")
                    # Verify stored content has match indicators (check ALL indicators)
                    has_download_button = (
                        'id="download"' in stored_content or 
                        'button id="download"' in stored_content or
                        '<button id="download"' in stored_content
                    )
                    has_dwnldLnk = (
                        '#dwnldLnk' in stored_content or 
                        'id="dwnldLnk"' in stored_content or
                        '<a id="dwnldLnk"' in stored_content
                    )
                    has_descarga = 'Descarga del CURP' in stored_content
                    has_datos = 'Datos del solicitante' in stored_content
                    
                    has_match_indicators = (
                        has_download_button or
                        has_dwnldLnk or
                        has_descarga or
                        has_datos
                    )
                    
                    if has_match_indicators:
                        logger.info("✓ Stored content has match indicators - MATCH CONFIRMED!")
                        logger.info(f"  - Download button: {has_download_button}")
                        logger.info(f"  - dwnldLnk: {has_dwnldLnk}")
                        logger.info(f"  - Descarga del CURP: {has_descarga}")
                        logger.info(f"  - Datos del solicitante: {has_datos}")
                        content = stored_content
                        has_match_result = True
                        # Clear stored content after use
                        self._last_match_content = None
                        # Skip to processing - don't re-check
                        logger.info("=== Using stored match content - skipping re-check ===")
                    else:
                        logger.warning("Stored content doesn't have match indicators - will re-check")
                        # Fall through to re-check
                        content = None
                        has_match_result = False
                else:
                    # No stored content - will check current page state
                    content = None
                    has_match_result = False
                
                # Step 2: If no stored content or stored content invalid, check current page state
                if not has_match_result:
                    # ALWAYS check current page state FIRST (most reliable)
                    # Check for button id="download" using locator FIRST (before getting content)
                    locator_has_download_button = False
                    try:
                        # Wait a bit for dynamic content to load
                        time.sleep(0.3)
                        
                        # Try multiple selector strategies
                        selectors_to_try = [
                            'button#download',
                            'button[id="download"]',
                            '#download',
                            'button[id*="download"]',
                            'button:has-text("Descargar")',
                        ]
                        
                        for selector in selectors_to_try:
                            try:
                                # Wait for selector to appear (up to 3 seconds)
                                try:
                                    self.page.wait_for_selector(selector, timeout=3000, state='visible')
                                except:
                                    pass  # Continue even if wait times out
                                
                                count = self.page.locator(selector).count()
                                logger.info(f"Checking selector '{selector}': found {count} elements")
                                if count > 0:
                                    element = self.page.locator(selector).first
                                    if element.is_visible(timeout=2000):
                                        locator_has_download_button = True
                                        logger.info(f"✓✓✓ PRIMARY INDICATOR: Found via selector '{selector}' - MATCH CONFIRMED! ✓✓✓")
                                        break
                            except Exception as sel_error:
                                logger.debug(f"Selector '{selector}' failed: {sel_error}")
                                continue
                        
                        if not locator_has_download_button:
                            logger.debug("No download button found via any locator selector")
                    except Exception as loc_error:
                        logger.warning(f"Error checking download button locator: {loc_error}")
                        import traceback
                        traceback.print_exc()
                
                    # Step 3: Get page content to check
                    if content is None:
                        content = self.page.content()
                        logger.info(f"Got fresh page content ({len(content)} chars)")
            
                # Step 4: Check content for button id="download" (PRIMARY indicator in HTML)
                # Try multiple patterns to find the button
                content_has_download_button = False
                download_patterns = [
                    'id="download"',
                    'button id="download"',
                    '<button id="download"',
                    'button#download',
                    'id=\'download\'',
                    'button[id="download"]',
                    'button[id=\'download\']',
                ]
                
                for pattern in download_patterns:
                    if pattern in content:
                        content_has_download_button = True
                        logger.info(f"✓ PRIMARY INDICATOR: Found pattern '{pattern}' in content - MATCH CONFIRMED!")
                        # Also check if "Descargar pdf" text is nearby (confirms it's the right button)
                        pattern_index = content.find(pattern)
                        if pattern_index != -1:
                            nearby_text = content[max(0, pattern_index-200):min(len(content), pattern_index+200)]
                            if 'Descargar' in nearby_text or 'descargar' in nearby_text.lower():
                                logger.info("✓ Confirmed: 'Descargar' text found near download button")
                        break
                
                if not content_has_download_button:
                    logger.debug("No download button patterns found in content")
                    # Debug: Show a sample of content to help diagnose
                    if 'Descargar' in content or 'descargar' in content.lower():
                        descargar_index = content.lower().find('descargar')
                        if descargar_index != -1:
                            sample = content[max(0, descargar_index-100):min(len(content), descargar_index+200)]
                            logger.warning(f"⚠️ Found 'Descargar' text but no button pattern! Sample: {sample[:300]}")
                            # If "Descargar pdf" exists, it's likely a match even without button pattern
                            if 'Descargar pdf' in content or 'descargar pdf' in content.lower():
                                logger.warning("⚠️ 'Descargar pdf' text found - treating as match indicator")
                                content_has_download_button = True
            
                # Step 5: FALLBACK METHODS: Check for other indicators (ALWAYS check, not just if primary not found)
                # These are strong indicators that should be checked regardless
                has_other_indicators = False
                has_dwnldLnk = (
                    '#dwnldLnk' in content or 
                    'dwnldLnk' in content or
                    'id="dwnldLnk"' in content or
                    'id=\'dwnldLnk\'' in content or
                    '<a id="dwnldLnk"' in content
                )
                has_descarga_text = 'Descarga del CURP' in content
                has_datos_text = 'Datos del solicitante' in content
                has_descargar_pdf = 'Descargar pdf' in content or 'descargar pdf' in content.lower()
                has_panel_body = 'panel-body' in content
                
                has_other_indicators = (
                    has_dwnldLnk or
                    has_descarga_text or
                    has_datos_text or
                    has_descargar_pdf or
                    has_panel_body
                )
                
                if has_other_indicators:
                    logger.info("FALLBACK INDICATORS: Other download indicators found")
                    logger.info(f"  - dwnldLnk: {has_dwnldLnk}")
                    logger.info(f"  - Descarga del CURP: {has_descarga_text}")
                    logger.info(f"  - Datos del solicitante: {has_datos_text}")
                    logger.info(f"  - Descargar pdf: {has_descargar_pdf}")
                    logger.info(f"  - panel-body: {has_panel_body}")
                
                # Step 6: Also check for CURP pattern directly
                import re
                curp_pattern_check = re.search(r'[A-Z]{4}\d{6}[HM][A-Z]{5}[0-9A-Z]\d', content)
                has_curp_pattern = curp_pattern_check is not None
                
                # Step 7: Determine if match exists (PRIMARY indicator OR fallback indicators OR CURP pattern)
                # CRITICAL: Check ALL indicators - ANY match means we found a result
                has_match_result = (
                    locator_has_download_button or  # PRIMARY: locator check (MOST RELIABLE - TRUST THIS!)
                    content_has_download_button or   # PRIMARY: content check
                    has_other_indicators or          # Fallback: other indicators (STRONG SIGNAL)
                    has_curp_pattern                 # Fallback: CURP pattern
                )
                
                # CRITICAL: If ANY strong indicator found, ensure match is detected
                if (locator_has_download_button or content_has_download_button or has_other_indicators) and not has_match_result:
                    logger.error("CRITICAL: Strong indicators found but has_match_result is False - FORCING MATCH!")
                    has_match_result = True
                    if not content_has_download_button:
                        content_has_download_button = True
                
                # Also check: if we have dwnldLnk OR Descarga del CURP OR Datos del solicitante, it's definitely a match
                if (has_dwnldLnk or has_descarga_text or has_datos_text) and not has_match_result:
                    logger.warning("CRITICAL: Strong fallback indicators found but not detected as match - FORCING!")
                    has_match_result = True
                else:
                    # Using stored content - already confirmed as match
                    import re
                    curp_pattern_check = re.search(r'[A-Z]{4}\d{6}[HM][A-Z]{5}[0-9A-Z]\d', content)
                    has_curp_pattern = curp_pattern_check is not None
                    locator_has_download_button = True  # Already confirmed
                    content_has_download_button = True  # Already confirmed
                    # Check other indicators in stored content too
                    has_dwnldLnk = (
                        '#dwnldLnk' in content or 
                        'dwnldLnk' in content or
                        'id="dwnldLnk"' in content or
                        '<a id="dwnldLnk"' in content
                    )
                    has_descarga_text = 'Descarga del CURP' in content
                    has_datos_text = 'Datos del solicitante' in content
                    has_other_indicators = (
                        has_dwnldLnk or
                        has_descarga_text or
                        has_datos_text or
                        'Descargar pdf' in content or
                        'panel-body' in content
                    )
                
                # Log detection results
                logger.info(f"Result detection summary:")
                logger.info(f"  - Download button (locator): {locator_has_download_button} {'✓' if locator_has_download_button else '✗'}")
                logger.info(f"  - Download button (content): {content_has_download_button} {'✓' if content_has_download_button else '✗'}")
                logger.info(f"  - Other indicators: {has_other_indicators} {'✓' if has_other_indicators else '✗'}")
                logger.info(f"  - CURP pattern: {has_curp_pattern} {'✓' if has_curp_pattern else '✗'}")
                logger.info(f"  - FINAL RESULT: {'✓ MATCH FOUND' if has_match_result else '✗ NO MATCH'}")
                
                if has_match_result and curp_pattern_check:
                    logger.info(f"  - CURP found: {curp_pattern_check.group(0)}")
                
                # Step 10: Store content for later use (if match found)
                # This ensures we have the results page content even if page reloads
                if has_match_result:
                    # Store content immediately so it can be retrieved after any reloads
                    self._last_match_content = content
                    logger.info(f"Match content stored ({len(content)} chars) for later retrieval")
                
                logger.info("=== RESULT CHECK COMPLETE ===")
            
            # If we skipped expensive checks, still need to set variables for the rest of the code
            if has_no_match_modal_detected:
                # Initialize variables that are expected later
                locator_has_download_button = False
                content_has_download_button = False
                has_other_indicators = False
                has_curp_pattern = False
                curp_pattern_check = None
                logger.info("=== RESULT CHECK COMPLETE (skipped - no-match modal) ===")
            
            # Add human-like pause to "read" the results (after checking)
            logger.debug("[DELAY] Reading results pause")
            self._human_like_delay(0.2, 0.3)  # Humans pause to read results
            
            # Increment search count BEFORE processing results
            self.search_count += 1
            
            # Process results IMMEDIATELY if match found (before checking for modal)
            if has_match_result:
                logger.info("=== MATCH FOUND - Processing match result ===")
                # Additional verification: check if we're actually on results page
                current_url = self.page.url
                logger.info(f"Current URL: {current_url}")
                # Check for CURP in content as additional verification
                import re
                curp_in_content = re.search(r'[A-Z]{4}\d{6}[HM][A-Z]{5}[0-9A-Z]\d', content)
                if curp_in_content:
                    logger.info(f"CURP found in content: {curp_in_content.group(0)}")
                else:
                    logger.warning("Match indicators found but no CURP pattern detected in content")
                
                # Return content immediately - don't check for modal if match is found
                # Match found! Save the result (content is already captured)
                logger.info("Match found! Returning content for validation...")
                
                # Store the content with match result BEFORE reloading
                match_content = content
                
                # Now reload page and proceed to next input
                try:
                    self.page.reload(wait_until='load', timeout=90000)
                    logger.debug("[DELAY] Page reload wait: 2.0s")
                    time.sleep(2.0)  # Page load wait
                    
                    # Reset field tracking since form is cleared after reload
                    self._reset_field_tracking()
                    
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
                    
                    # Apply delay after search (before returning)
                    logger.debug("[DELAY] Random delay after search")
                    self._random_delay()
                    
                    # Pause every N searches (check before returning)
                    if self.search_count % self.pause_every_n == 0 and self.search_count > 0:
                        print(f"Pausing for {self.pause_duration} seconds after {self.search_count} searches...")
                        time.sleep(self.pause_duration)
                    
                    # Return the match content (captured BEFORE reload)
                    logger.info(f"Returning match content ({len(match_content)} chars) for validation")
                    return match_content
                except Exception as e:
                    logger.error(f"Error during reload after match: {e}")
                    # Apply delay even on error
                    self._random_delay()
                    # Return content anyway so match can be processed
                    logger.info(f"Returning match content despite reload error ({len(match_content)} chars)")
                    return match_content
            
            # Check for no match modal (error modal) - only if no match was found
            # Look for the specific modal structure
            has_no_match_modal = (
                'Aviso importante' in content or
                'warningMenssage' in content or
                'id="warningMenssage"' in content or
                'Los datos ingresados no son correctos' in content
            )
            
            # Helper function to reload page and reinitialize form
            def reload_page_and_reinit():
                """Reload page and reinitialize form."""
                try:
                    self.page.reload(wait_until='load', timeout=90000)
                    # No need to sleep - wait_until='load' already waits for page to be ready
                    # Small delay to ensure DOM is fully ready
                    logger.debug("[DELAY] Page reload DOM ready wait: 0.3s")
                    time.sleep(0.3)  # Reduced from 2.0s - page is already loaded
                    
                    # Reset field tracking since form is cleared after reload
                    self._reset_field_tracking()
                    
                    # Click on "Datos Personales" tab to access the form
                    try:
                        # Reduced timeout - tab should be available quickly after reload
                        self.page.wait_for_selector('a[href="#tab-02"]', timeout=3000)
                        tab = self.page.locator('a[href="#tab-02"]').first
                        tab_class = tab.get_attribute('class') or ''
                        if 'active' not in tab_class:
                            tab.click()
                            logger.debug("[DELAY] Tab switch delay (reduced): 0.2s")
                            time.sleep(0.2)  # Reduced tab switch delay from 0.4s
                    except Exception as e:
                        print(f"Warning: Could not click 'Datos Personales' tab after reload: {e}")
                    
                    # Wait for form fields to be available
                    # Reduced timeout - fields should be available quickly after tab click
                    self.page.wait_for_selector('input#nombre', timeout=2000)
                    self.form_ready = True
                    return True
                except Exception as e:
                    print(f"Error during page reload: {e}")
                    # Try to recover by ensuring form is ready
                    try:
                        self._ensure_form_ready()
                        # Reset tracking even if recovery method is used
                        self._reset_field_tracking()
                        return True
                    except:
                        return False
            
            # Check for periodic pause: every 3 searches (but NOT if we already processed a match)
            # After every 3 searches: sleep 1s + reload page
            if not has_match_result and self.search_count % 3 == 0 and self.search_count > 0:
                logger.debug(f"Search count check: {self.search_count} % 3 == {self.search_count % 3}")
                print(f"After {self.search_count} searches: sleeping 1s, reloading page, and reinitializing form...")
                logger.info(f"[DELAY] Periodic pause (every 3 searches): 1.0s")
                time.sleep(1.0)  # Sleep for 1 second
                reload_page_and_reinit()
                print("Page reloaded and form reinitialized successfully.")
                    
            elif has_no_match_modal:
                # No match found - wait 2 seconds after detection, then close modal and proceed to next input (NO PAGE RELOAD)
                logger.info("No-match modal detected - waiting 2 seconds before closing modal")
                
                # Wait 2 seconds after detection before closing
                time.sleep(2.0)
                
                self._close_modal_if_present()
                
                # Verify page is still valid after closing modal
                if not self.page:
                    raise RuntimeError("Page object is None after closing modal")
                
                try:
                    _ = self.page.url  # This will raise if page is closed
                except Exception as e:
                    raise RuntimeError("Page was closed unexpectedly after closing modal")
                
                # Wait a bit to ensure modal is fully closed and page state is stable
                time.sleep(0.2)  # Small wait to ensure modal is fully closed
                
                # Verify page is still valid after stability wait
                try:
                    _ = self.page.url  # This will raise if page is closed
                except Exception as e:
                    raise RuntimeError("Page was closed unexpectedly during stability wait")
                
                # Content already updated, form is ready for next input
                self.form_ready = True
                
                # Reduced delay after closing modal (was using _random_delay which is 1-2s)
                # Use minimal delay to speed up no-match cases
                minimal_delay = random.uniform(0.2, 0.4)
                time.sleep(minimal_delay)
                
                # Pause every N searches (check before returning)
                if self.search_count % self.pause_every_n == 0 and self.search_count > 0:
                    logger.info(f"[DELAY] Periodic pause (every {self.pause_every_n} searches): {self.pause_duration}s after {self.search_count} searches")
                    print(f"Pausing for {self.pause_duration} seconds after {self.search_count} searches...")
                    time.sleep(self.pause_duration)
                
                return content
            else:
                # Neither result type detected - this shouldn't happen if wait worked correctly
                # But handle it anyway by closing any modal and proceeding
                print("Warning: Neither match nor no-match modal detected, closing any modal and proceeding...")
                self._close_modal_if_present()
                self.form_ready = True
                
                # Apply delay after search (before returning)
                self._random_delay()
                
                # Pause every N searches (check before returning)
                if self.search_count % self.pause_every_n == 0 and self.search_count > 0:
                    logger.info(f"[DELAY] Periodic pause (every {self.pause_every_n} searches): {self.pause_duration}s after {self.search_count} searches")
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

