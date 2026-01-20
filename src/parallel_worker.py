"""
Parallel Worker
Manages multiple browser instances for parallel CURP searches.
"""
import threading
import time
import logging
from typing import List, Dict, Iterator, Tuple
from queue import Queue
from pathlib import Path
from datetime import datetime

from browser_automation import BrowserAutomation
from result_validator import ResultValidator
from combination_generator import CombinationGenerator
from checkpoint_manager import CheckpointManager
from excel_handler import ExcelHandler

logger = logging.getLogger(__name__)


class ParallelWorker:
    """Manages parallel browser instances for CURP searches."""
    
    def __init__(self, num_workers: int = 5, headless: bool = False,
                 min_delay: float = 1.0, max_delay: float = 2.0,
                 pause_every_n: int = 75, pause_duration: int = 15,
                 output_dir: str = "./web/Result"):
        """
        Initialize parallel worker.
        
        Args:
            num_workers: Number of parallel browser instances
            headless: Run browsers in headless mode
            min_delay: Minimum delay between searches (seconds)
            max_delay: Maximum delay between searches (seconds)
            pause_every_n: Pause every N searches
            pause_duration: Duration of pause (seconds)
            output_dir: Directory for output Excel files
        """
        self.num_workers = num_workers
        self.headless = headless
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.pause_every_n = pause_every_n
        self.pause_duration = pause_duration
        self.output_dir = output_dir
        
        self.result_validator = ResultValidator()
        self.results_lock = threading.Lock()
        self.checkpoint_lock = threading.Lock()
        self.processed_count_lock = threading.Lock()
        self.excel_lock = threading.Lock()
        
        # Initialize Excel handler
        self.excel_handler = ExcelHandler(output_dir=output_dir)
        
        # Track output file per person
        self.output_files = {}  # person_id -> filename
        
    def worker_thread(self, worker_id: int, combinations_queue: Queue,
                    first_name: str, last_name_1: str, last_name_2: str,
                    gender: str, person_id: int, person_name: str,
                    total_combinations: int, checkpoint_manager: CheckpointManager,
                    all_results: List[Dict], processed_count: Dict,
                    stop_event: threading.Event, progress_callback=None,
                    check_cancellation=None):
        """
        Worker thread that processes combinations from the queue.
        
        Args:
            worker_id: Unique ID for this worker
            combinations_queue: Queue of combinations to process
            first_name: First name
            last_name_1: First last name
            last_name_2: Second last name
            gender: Gender
            person_id: Person ID
            person_name: Person name for logging
            total_combinations: Total number of combinations
            checkpoint_manager: Checkpoint manager instance
            all_results: Shared list for results
            processed_count: Shared dict for processed count
            stop_event: Event to signal stop
            progress_callback: Optional callback function for progress updates
            check_cancellation: Optional function to check if job is cancelled
        """
        browser_automation = None
        
        try:
            # Initialize browser for this worker
            try:
                    browser_automation = BrowserAutomation(
                        headless=self.headless,
                        min_delay=self.min_delay,
                        max_delay=self.max_delay,
                        pause_every_n=self.pause_every_n,
                        pause_duration=self.pause_duration,
                        check_cancellation=check_cancellation
                    )
            except Exception as e:
                logger.error(f"Worker {worker_id}: Failed to initialize BrowserAutomation: {e}")
                # Ensure cleanup even if initialization fails
                if browser_automation:
                    try:
                        browser_automation.close_browser()
                    except Exception as cleanup_error:
                        logger.error(f"Worker {worker_id}: Error during initialization cleanup: {cleanup_error}")
                raise
            
            # Retry browser startup if it fails
            max_start_retries = 3
            browser_started = False
            for start_attempt in range(max_start_retries):
                try:
                    browser_automation.start_browser()
                    browser_started = True
                    logger.info(f"Worker {worker_id}: Browser started successfully")
                    break
                except Exception as e:
                    if start_attempt < max_start_retries - 1:
                        logger.warning(f"Worker {worker_id}: Browser start failed (attempt {start_attempt + 1}/{max_start_retries}): {e}")
                        logger.info(f"Worker {worker_id}: Retrying in 5 seconds...")
                        time.sleep(5)
                    else:
                        logger.error(f"Worker {worker_id}: Failed to start browser after {max_start_retries} attempts: {e}")
                        # Ensure cleanup before raising
                        if browser_automation:
                            try:
                                browser_automation.close_browser()
                            except Exception as cleanup_error:
                                logger.error(f"Worker {worker_id}: Error during startup failure cleanup: {cleanup_error}")
                        raise
            
            if not browser_started:
                logger.error(f"Worker {worker_id}: Could not start browser, exiting")
                # Ensure cleanup
                if browser_automation:
                    try:
                        browser_automation.close_browser()
                    except Exception as cleanup_error:
                        logger.error(f"Worker {worker_id}: Error during cleanup after startup failure: {cleanup_error}")
                return
            
            worker_search_count = 0
            
            while not stop_event.is_set():
                # Check for cancellation periodically
                if check_cancellation and check_cancellation():
                    logger.info(f"Worker {worker_id}: Job cancelled, stopping...")
                    stop_event.set()
                    break
                
                try:
                    # Get combination from queue (with timeout)
                    try:
                        combo_data = combinations_queue.get(timeout=2)
                    except:
                        # Queue empty - check if we should continue
                        # Only break if queue is empty (other workers might still be processing items they already got)
                        # We rely on queue.join() in the main thread to ensure all work is done
                        if combinations_queue.empty():
                            # Give other workers a chance to finish their current items
                            time.sleep(0.5)
                        if combinations_queue.empty():
                            break
                        continue
                    
                    combo_idx, day, month, state, year = combo_data
                    
                    # Perform search
                    try:
                        html_content = browser_automation.search_curp(
                            first_name=first_name,
                            last_name_1=last_name_1,
                            last_name_2=last_name_2,
                            gender=gender,
                            day=day,
                            month=month,
                            state=state,
                            year=year
                        )
                        
                        # Check if job was cancelled during search (empty content indicates cancellation)
                        if html_content == "" and check_cancellation and check_cancellation():
                            logger.info(f"Worker {worker_id}: Job cancelled during search, stopping...")
                            stop_event.set()
                            break
                        
                        # Validate result
                        validation_result = self.result_validator.validate_result(html_content, state)
                        
                        # Debug: Log if we get HTML but no match (to help diagnose)
                        if html_content and not validation_result['found']:
                            # Check if HTML contains download link or result indicators (indicates match)
                            result_indicators = ['#dwnldLnk', 'dwnldLnk', 'Descargar pdf', 'Descarga del CURP', 
                                               'Datos del solicitante', 'datos del solicitante']
                            if any(indicator in html_content for indicator in result_indicators):
                                logger.warning(f"Worker {worker_id}: HTML contains result indicators but validation failed! "
                                             f"State: {state}, Day: {day:02d}, Month: {month:02d}, Year: {year}")
                                
                                # Try to extract CURP directly from HTML as fallback using multiple patterns
                                import re
                                
                                # Pattern 1: Standard CURP format
                                curp_patterns = [
                                    r'\b([A-Z]{4}\d{6}[HM][A-Z]{5}[0-9A-Z]\d)\b',
                                    r'<td[^>]*>([A-Z]{4}\d{6}[HM][A-Z]{5}[0-9A-Z]\d)</td>',
                                    r'>([A-Z]{4}\d{6}[HM][A-Z]{5}[0-9A-Z]\d)<',
                                ]
                                
                                found_curp = None
                                for pattern in curp_patterns:
                                    curp_matches = re.findall(pattern, html_content, re.IGNORECASE)
                                    if curp_matches:
                                        potential_curp = curp_matches[0].upper()
                                        if self.result_validator.is_valid_curp(potential_curp):
                                            found_curp = potential_curp
                                            logger.warning(f"Worker {worker_id}: Found valid CURP using fallback pattern: {found_curp}")
                                            break
                                
                                if found_curp:
                                    # Re-validate with found CURP
                                    validation_result['found'] = True
                                    validation_result['valid'] = True
                                    validation_result['curp'] = found_curp
                                    validation_result['birth_date'] = self.result_validator.extract_date_from_curp(found_curp)
                                    validation_result['state_code'] = self.result_validator.extract_state_code_from_curp(found_curp)
                                    logger.info(f"Worker {worker_id}: MATCH FOUND via fallback! CURP: {found_curp} ({day:02d}/{month:02d}/{year}, {state})")
                                else:
                                    # Save HTML for debugging if no CURP found
                                    debug_dir = Path('./debug_html')
                                    debug_dir.mkdir(exist_ok=True)
                                    debug_file = debug_dir / f"debug_{person_id}_{state}_{day:02d}_{month:02d}_{year}.html"
                                    try:
                                        with open(debug_file, 'w', encoding='utf-8') as f:
                                            f.write(html_content)
                                        logger.warning(f"Worker {worker_id}: Saved HTML to {debug_file} for debugging")
                                    except Exception as e:
                                        logger.error(f"Worker {worker_id}: Failed to save debug HTML: {e}")
                        
                        # Process match if found
                        if validation_result.get('found') and validation_result.get('valid'):
                            # Match found!
                            with self.results_lock:
                                person_match_count = len([r for r in all_results if r.get('person_id') == person_id])
                            
                            match_data = {
                                'person_id': person_id,
                                'first_name': first_name,
                                'last_name_1': last_name_1,
                                'last_name_2': last_name_2,
                                'gender': gender,
                                'curp': validation_result['curp'],
                                'birth_date': validation_result['birth_date'],
                                'birth_state': state,
                                'match_number': person_match_count + 1
                            }
                            
                            with self.results_lock:
                                all_results.append(match_data)
                            
                            logger.info(f"Worker {worker_id}: MATCH FOUND! Person {person_id}: "
                                      f"CURP {validation_result['curp']} ({day:02d}/{month:02d}/{year}, {state})")
                            
                            # Immediately save to Excel file
                            self._save_match_immediately(person_id, match_data, all_results)
                        else:
                            # Match detected but validation failed - log details
                            logger.warning(f"Worker {worker_id}: Match detected but validation failed!")
                            logger.warning(f"  - validation_result['found']: {validation_result.get('found')}")
                            logger.warning(f"  - validation_result['valid']: {validation_result.get('valid')}")
                            logger.warning(f"  - validation_result keys: {validation_result.keys()}")
                            if html_content:
                                # Check if button id="download" exists in HTML
                                has_download_button = (
                                    'id="download"' in html_content or
                                    'button id="download"' in html_content or
                                    '<button id="download"' in html_content
                                )
                                logger.warning(f"  - button id='download' in HTML: {has_download_button}")
                                # Save HTML for debugging
                                debug_dir = Path('./debug_content')
                                debug_dir.mkdir(exist_ok=True)
                                debug_file = debug_dir / f"validation_failed_{person_id}_{state}_{day:02d}_{month:02d}_{year}.html"
                                try:
                                    with open(debug_file, 'w', encoding='utf-8') as f:
                                        f.write(html_content)
                                    logger.warning(f"Worker {worker_id}: Saved HTML to {debug_file} for debugging validation failure")
                                except Exception as e:
                                    logger.error(f"Worker {worker_id}: Failed to save debug HTML: {e}")
                        
                        worker_search_count += 1
                        
                        # Update processed count
                        with self.processed_count_lock:
                            processed_count['count'] = processed_count.get('count', 0) + 1
                            current_count = processed_count['count']
                        
                        # Call progress callback if provided
                        # Update every 5 searches for better responsiveness (changed from 10)
                        if progress_callback and (current_count % 5 == 0 or current_count == 1):
                            try:
                                progress_callback({
                                    'person_id': person_id,
                                    'combination_index': combo_idx,
                                    'total_combinations': total_combinations,
                                    'matches_found': len([r for r in all_results if r.get('person_id') == person_id]),
                                    'current_combination': {
                                        'day': day,
                                        'month': month,
                                        'state': state,
                                        'year': year
                                    }
                                })
                            except Exception as e:
                                logger.error(f"Error in progress callback: {e}")
                        
                        # Check for cancellation before checkpoint
                        if check_cancellation and check_cancellation():
                            logger.info(f"Worker {worker_id}: Job cancelled during processing, stopping...")
                            stop_event.set()
                            break
                        
                        # Save checkpoint periodically (every 100 combinations across all workers)
                        if current_count % 100 == 0:
                            with self.checkpoint_lock:
                                checkpoint_manager.save_checkpoint(
                                    person_id=person_id,
                                    person_name=person_name,
                                    combination_index=combo_idx,
                                    day=day,
                                    month=month,
                                    state=state,
                                    year=year,
                                    matches=all_results.copy(),
                                    total_processed=current_count,
                                    total_combinations=total_combinations,
                                    config={}
                                )
                            logger.info(f"Checkpoint saved. Progress: {current_count}/{total_combinations} "
                                      f"({current_count/total_combinations*100:.2f}%)")
                        
                        # Log progress periodically
                        if current_count % 1000 == 0:
                            logger.info(f"Progress: {current_count}/{total_combinations} "
                                      f"({current_count/total_combinations*100:.2f}%)")
                        
                        # Mark task as done
                        combinations_queue.task_done()
                        
                    except Exception as e:
                        logger.error(f"Worker {worker_id}: Error processing combination "
                                   f"(day={day}, month={month}, state={state}, year={year}): {e}")
                        combinations_queue.task_done()
                        continue
                
                except Exception as e:
                    logger.error(f"Worker {worker_id}: Error in worker loop: {e}")
                    break
            
            logger.info(f"Worker {worker_id}: Completed {worker_search_count} searches")
        
        except Exception as e:
            logger.error(f"Worker {worker_id}: Fatal error: {e}", exc_info=True)
            # Ensure cleanup on fatal error
            if browser_automation:
                try:
                    logger.info(f"Worker {worker_id}: Cleaning up browser after fatal error...")
                    browser_automation.close_browser()
                except Exception as cleanup_error:
                    logger.error(f"Worker {worker_id}: Error during fatal error cleanup: {cleanup_error}")
        
        finally:
            # Enhanced cleanup - ensure browser is always closed
            if browser_automation:
                try:
                    logger.debug(f"Worker {worker_id}: Final cleanup - closing browser...")
                    browser_automation.close_browser()
                    logger.info(f"Worker {worker_id}: Browser closed successfully")
                except Exception as cleanup_error:
                    logger.error(f"Worker {worker_id}: Error during final cleanup: {cleanup_error}", exc_info=True)
            else:
                logger.debug(f"Worker {worker_id}: No browser instance to clean up")
    
    def _save_match_immediately(self, person_id: int, match_data: Dict, all_results: List[Dict]):
        """
        Immediately save a match to Excel file (thread-safe).
        
        Args:
            person_id: Person ID
            match_data: Match data dictionary
            all_results: All results list
        """
        try:
            with self.excel_lock:
                # Get or create output filename for this person
                if person_id not in self.output_files:
                    timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M")
                    filename = f"curp_results_person_{person_id}_{timestamp}.xlsx"
                    self.output_files[person_id] = filename
                
                filename = self.output_files[person_id]
                
                # Get all matches for this person
                person_matches = [r for r in all_results if r.get('person_id') == person_id]
                
                # Create summary for this person
                summary = [{
                    'person_id': person_id,
                    'first_name': match_data['first_name'],
                    'last_name_1': match_data['last_name_1'],
                    'last_name_2': match_data['last_name_2'],
                    'total_matches': len(person_matches)
                }]
                
                # Save to Excel (this will create or append)
                self.excel_handler.write_results(person_matches, summary, filename)
                
                logger.info(f"Match saved immediately to {filename} (Person {person_id}, Match #{len(person_matches)})")
        
        except Exception as e:
            logger.error(f"Error saving match immediately: {e}")
    
    def process_person_parallel(self, person_data: Dict, combinations: Iterator[Tuple[int, int, str, int]],
                              total_combinations: int, checkpoint_manager: CheckpointManager,
                              all_results: List[Dict], start_index: int = 0, person_name: str = None,
                              progress_callback=None, job_id: str = None, check_cancellation=None):
        """
        Process a person's combinations using parallel workers.
        
        Args:
            person_data: Dictionary with person information
            combinations: Iterator of (day, month, state, year) tuples
            total_combinations: Total number of combinations
            checkpoint_manager: Checkpoint manager
            all_results: List to store results
            start_index: Starting combination index (for resume)
            person_name: Person's full name (for checkpoints)
            progress_callback: Optional callback function for progress updates
            job_id: Optional job ID for cancellation checking
            check_cancellation: Optional function to check if job is cancelled
        """
        first_name = person_data['first_name']
        last_name_1 = person_data['last_name_1']
        last_name_2 = person_data['last_name_2']
        gender = person_data['gender']
        person_id = person_data['person_id']
        if person_name is None:
            person_name = f"{first_name} {last_name_1} {last_name_2}"
        
        # Create queue for combinations
        combinations_queue = Queue()
        
        # Skip to start_index if resuming, but validate against total
        if start_index >= total_combinations:
            logger.warning(f"Start index {start_index} exceeds total combinations {total_combinations}. Starting from beginning.")
            start_index = 0
        
        combo_idx = 0
        skipped_count = 0
        for combo in combinations:
            if combo_idx < start_index:
                skipped_count += 1
                combo_idx += 1
                continue
            
            day, month, state, year = combo
            combinations_queue.put((combo_idx, day, month, state, year))
            combo_idx += 1
        
        if skipped_count > 0:
            logger.info(f"Skipped {skipped_count} combinations (resuming from index {start_index})")
        logger.info(f"Queued {combinations_queue.qsize()} combinations for parallel processing")
        
        # Shared state
        processed_count = {'count': start_index}
        stop_event = threading.Event()
        
        # Create and start worker threads
        threads = []
        for worker_id in range(1, self.num_workers + 1):
            thread = threading.Thread(
                target=self.worker_thread,
                args=(worker_id, combinations_queue, first_name, last_name_1,
                     last_name_2, gender, person_id, person_name,
                     total_combinations, checkpoint_manager, all_results,
                     processed_count, stop_event, progress_callback, 
                     check_cancellation),
                daemon=True
            )
            thread.start()
            threads.append(thread)
            # Stagger worker starts to avoid simultaneous connections
            # Longer delay for more workers to prevent server overload
            time.sleep(1.0 + (worker_id * 0.3))
        
        logger.info(f"Started {self.num_workers} worker threads")
        
        # Wait for all combinations to be processed or cancellation
        try:
            # Wait for queue to be fully processed, but check for cancellation periodically
            while True:
                # Check for cancellation first
                if check_cancellation and check_cancellation():
                    logger.info(f"Job cancelled, stopping all workers for person {person_id}")
                    stop_event.set()
                    break
                
                # Check if queue is empty and all tasks done
                if combinations_queue.empty():
                    # Try to join with short timeout to check if all tasks are done
                    try:
                        combinations_queue.join(timeout=0.1)
                        # If join succeeds, all tasks are done
                        logger.info(f"All combinations processed for person {person_id}")
                        break
                    except:
                        # Still processing, continue waiting
                        pass
                
                time.sleep(0.5)
        except KeyboardInterrupt:
            logger.info("Interrupted by user. Stopping workers...")
            stop_event.set()
            # Wait a bit for threads to finish current work
            time.sleep(2)
        
        # Signal all workers to stop (in case any are still waiting)
        stop_event.set()
        
        # Wait for all threads to complete (with longer timeout)
        logger.info(f"Waiting for {len(threads)} worker threads to complete...")
        for idx, thread in enumerate(threads, 1):
            worker_num = idx  # Worker number for logging
            thread.join(timeout=30)  # Increased timeout to 30 seconds
            if thread.is_alive():
                logger.warning(f"Worker {worker_num}: Thread did not complete within 30s timeout. "
                             f"Browser cleanup may be incomplete. Attempting force cleanup...")
                # Force cleanup: Try to kill browser processes if thread doesn't respond
                # Note: We can't access browser_automation from here, but the finally block
                # in worker_thread should handle cleanup. This is a fallback warning.
                # In a production system, you might want to track browser instances and
                # call force_kill_browser_processes() here if needed.
            else:
                logger.debug(f"Worker {worker_num}: Thread completed successfully")
        
        # Final check - ensure queue is truly empty
        remaining_items = combinations_queue.qsize()
        if remaining_items > 0:
            logger.warning(f"Warning: {remaining_items} items still in queue after processing")
        
        logger.info(f"Completed parallel processing for person {person_id}")

