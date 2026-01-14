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
                 output_dir: str = "./data/results"):
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
                    stop_event: threading.Event, progress_callback=None):
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
        """
        browser_automation = None
        
        try:
            # Initialize browser for this worker
            browser_automation = BrowserAutomation(
                headless=self.headless,
                min_delay=self.min_delay,
                max_delay=self.max_delay,
                pause_every_n=self.pause_every_n,
                pause_duration=self.pause_duration
            )
            
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
                        raise
            
            if not browser_started:
                logger.error(f"Worker {worker_id}: Could not start browser, exiting")
                return
            
            worker_search_count = 0
            
            while not stop_event.is_set():
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
                                from pathlib import Path
                                
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
                        
                        worker_search_count += 1
                        
                        # Update processed count
                        with self.processed_count_lock:
                            processed_count['count'] = processed_count.get('count', 0) + 1
                            current_count = processed_count['count']
                        
                        # Call progress callback if provided
                        if progress_callback and current_count % 10 == 0:  # Update every 10 for smoother progress
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
            logger.error(f"Worker {worker_id}: Fatal error: {e}")
        
        finally:
            if browser_automation:
                browser_automation.close_browser()
                logger.info(f"Worker {worker_id}: Browser closed")
    
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
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
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
                              progress_callback=None):
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
                     processed_count, stop_event, progress_callback),
                daemon=True
            )
            thread.start()
            threads.append(thread)
            # Stagger worker starts to avoid simultaneous connections
            # Longer delay for more workers to prevent server overload
            time.sleep(1.0 + (worker_id * 0.3))
        
        logger.info(f"Started {self.num_workers} worker threads")
        
        # Wait for all combinations to be processed
        try:
            # Wait for queue to be fully processed
            combinations_queue.join()
            logger.info(f"All combinations processed for person {person_id}")
        except KeyboardInterrupt:
            logger.info("Interrupted by user. Stopping workers...")
            stop_event.set()
            # Wait a bit for threads to finish current work
            time.sleep(2)
        
        # Signal all workers to stop (in case any are still waiting)
        stop_event.set()
        
        # Wait for all threads to complete (with longer timeout)
        logger.info(f"Waiting for {len(threads)} worker threads to complete...")
        for thread in threads:
            thread.join(timeout=30)  # Increased timeout to 30 seconds
            if thread.is_alive():
                logger.warning(f"Thread {thread.name} did not complete within timeout")
        
        # Final check - ensure queue is truly empty
        remaining_items = combinations_queue.qsize()
        if remaining_items > 0:
            logger.warning(f"Warning: {remaining_items} items still in queue after processing")
        
        logger.info(f"Completed parallel processing for person {person_id}")

