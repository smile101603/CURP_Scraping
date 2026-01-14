"""
Search Runner
Refactored search logic that can be called from API.
"""
import threading
import logging
from pathlib import Path
from typing import Dict, Optional, Callable
from datetime import datetime

from excel_handler import ExcelHandler
from combination_generator import CombinationGenerator
from checkpoint_manager import CheckpointManager
from parallel_worker import ParallelWorker
from api.search_manager import search_manager
from api.models import JobStatus, JobProgress
from api.websocket import emit_progress_update, emit_job_complete, emit_job_error

logger = logging.getLogger(__name__)


def run_search_async(job_id: str, input_file_path: str, year_start: int, year_end: int,
                    config_overrides: Optional[Dict] = None):
    """
    Run search in background thread.
    
    Args:
        job_id: Job ID
        input_file_path: Path to input Excel file
        year_start: Start year
        year_end: End year
        config_overrides: Optional configuration overrides
    """
    thread = threading.Thread(
        target=run_search,
        args=(job_id, input_file_path, year_start, year_end, config_overrides),
        daemon=True
    )
    thread.start()
    logger.info(f"Started search thread for job {job_id}")


def run_search(job_id: str, input_file_path: str, year_start: int, year_end: int,
              config_overrides: Optional[Dict] = None,
              progress_callback: Optional[Callable] = None):
    """
    Run CURP search for a job.
    
    Args:
        job_id: Job ID
        input_file_path: Path to input Excel file
        year_start: Start year
        year_end: End year
        config_overrides: Optional configuration overrides
        progress_callback: Optional progress callback function
    """
    try:
        # Update job status to running
        search_manager.update_job_status(job_id, JobStatus.RUNNING)
        
        # Load configuration
        import json
        config_path = Path("./config/settings.json")
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
        else:
            config = {}
        
        # Apply overrides
        if config_overrides:
            config.update(config_overrides)
        
        # Get configuration values
        min_delay = config.get('delays', {}).get('min_seconds', 1.0)
        max_delay = config.get('delays', {}).get('max_seconds', 2.0)
        pause_every_n = config.get('pause_every_n', 75)
        pause_duration = config.get('pause_duration', 15)
        headless = config.get('browser', {}).get('headless', False)
        output_dir = config.get('output_dir', './data/results')
        checkpoint_dir = config.get('checkpoint_dir', './checkpoints')
        num_workers = config.get('num_workers', 5)
        
        # Initialize components
        excel_handler = ExcelHandler(output_dir=output_dir)
        checkpoint_manager = CheckpointManager(checkpoint_dir=checkpoint_dir)
        
        # Read input Excel
        input_path = Path(input_file_path)
        logger.info(f"Reading input file: {input_path}")
        
        # Check if file exists
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")
        
        # Read Excel file directly using the full path
        import pandas as pd
        input_df = pd.read_excel(input_path, engine='openpyxl')
        
        # Validate columns
        required_columns = ['first_name', 'last_name_1', 'last_name_2', 'gender']
        missing_columns = [col for col in required_columns if col not in input_df.columns]
        
        if missing_columns:
            raise ValueError(f"Missing required columns: {missing_columns}")
        
        # Add person_id if not present
        if 'person_id' not in input_df.columns:
            input_df.insert(0, 'person_id', range(1, len(input_df) + 1))
        
        logger.info(f"Loaded {len(input_df)} person(s) from input file")
        
        # Prepare results storage
        all_results = []
        summary_data = []
        
        # Initialize parallel worker
        parallel_worker = ParallelWorker(
            num_workers=num_workers,
            headless=headless,
            min_delay=min_delay,
            max_delay=max_delay,
            pause_every_n=pause_every_n,
            pause_duration=pause_duration,
            output_dir=output_dir
        )
        
        # Process each person
        for idx, row in input_df.iterrows():
            person_id = row['person_id']
            first_name = row['first_name']
            last_name_1 = row['last_name_1']
            last_name_2 = row['last_name_2']
            gender = row['gender']
            
            person_name = f"{first_name} {last_name_1} {last_name_2}"
            
            # Check if job was cancelled
            job = search_manager.get_job(job_id)
            if job and job.status == JobStatus.CANCELLED:
                logger.info(f"Job {job_id} was cancelled")
                return
            
            # Create combination generator
            combination_generator = CombinationGenerator(year_start, year_end)
            total_combinations = combination_generator.get_total_count()
            
            logger.info(f"Processing person {person_id}: {person_name}")
            logger.info(f"Total combinations for this person: {total_combinations}")
            
            # Create progress callback that emits via WebSocket
            def progress_cb(progress_data: Dict):
                """Progress callback that updates job and emits WebSocket."""
                try:
                    # Update job progress
                    job_progress = JobProgress(
                        person_id=progress_data.get('person_id', person_id),
                        person_name=person_name,
                        combination_index=progress_data.get('combination_index', 0),
                        total_combinations=progress_data.get('total_combinations', total_combinations),
                        matches_found=progress_data.get('matches_found', len(all_results)),
                        current_combination=progress_data.get('current_combination')
                    )
                    
                    # Calculate percentage
                    if job_progress.total_combinations > 0:
                        job_progress.percentage = (job_progress.combination_index / job_progress.total_combinations) * 100
                    
                    search_manager.update_job_progress(job_id, job_progress)
                    
                    # Emit via WebSocket
                    emit_progress_update(job_id, {
                        'job_id': job_id,
                        'progress': {
                            'person_id': job_progress.person_id,
                            'person_name': job_progress.person_name,
                            'combination_index': job_progress.combination_index,
                            'total_combinations': job_progress.total_combinations,
                            'matches_found': job_progress.matches_found,
                            'current_combination': job_progress.current_combination,
                            'percentage': job_progress.percentage
                        }
                    })
                    
                    # Call external progress callback if provided
                    if progress_callback:
                        progress_callback(progress_data)
                
                except Exception as e:
                    logger.error(f"Error in progress callback: {e}", exc_info=True)
            
            # Create cancellation check function
            def is_cancelled():
                job = search_manager.get_job(job_id)
                return job and job.status == JobStatus.CANCELLED
            
            # Process using parallel workers
            parallel_worker.process_person_parallel(
                person_data={
                    'person_id': person_id,
                    'first_name': first_name,
                    'last_name_1': last_name_1,
                    'last_name_2': last_name_2,
                    'gender': gender
                },
                combinations=combination_generator.generate_combinations(),
                total_combinations=total_combinations,
                checkpoint_manager=checkpoint_manager,
                all_results=all_results,
                start_index=0,
                person_name=person_name,
                progress_callback=progress_cb,
                job_id=job_id,
                check_cancellation=is_cancelled
            )
            
            # Check if cancelled after processing
            if is_cancelled():
                logger.info(f"Job {job_id} was cancelled, stopping search")
                return
            
            # Count matches found for this person
            person_matches = [r for r in all_results if r.get('person_id') == person_id]
            
            # Add person summary
            summary_data.append({
                'person_id': person_id,
                'first_name': first_name,
                'last_name_1': last_name_1,
                'last_name_2': last_name_2,
                'total_matches': len(person_matches)
            })
            
            logger.info(f"Completed person {person_id}: {len(person_matches)} match(es) found")
        
        # Generate output Excel
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"curp_results_{job_id}_{timestamp}.xlsx"
        
        logger.info(f"Writing results to Excel: {output_filename}")
        excel_handler.write_results(all_results, summary_data, output_filename)
        
        result_file_path = str(Path(output_dir) / output_filename)
        
        # Update job with result file
        search_manager.set_job_result(job_id, result_file_path)
        search_manager.update_job_status(job_id, JobStatus.COMPLETED)
        
        # Emit completion
        emit_job_complete(job_id, result_file_path)
        
        # Clear checkpoint on successful completion
        checkpoint_manager.clear_checkpoint()
        logger.info(f"Search completed successfully for job {job_id}")
    
    except Exception as e:
        logger.error(f"Error in search job {job_id}: {e}", exc_info=True)
        search_manager.update_job_status(job_id, JobStatus.FAILED, str(e))
        emit_job_error(job_id, str(e))
