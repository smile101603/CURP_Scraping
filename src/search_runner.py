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
from work_distributor import WorkDistributor
from google_sheets_writer import GoogleSheetsWriter
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
        output_dir = config.get('output_dir', './web/Result')
        checkpoint_dir = config.get('checkpoint_dir', './checkpoints')
        num_workers = config.get('num_workers', 5)
        
        # Get VPS configuration
        vps_config = config.get('vps', {})
        vps_enabled = vps_config.get('enabled', False)
        vps_ips = vps_config.get('vps_ips', [])
        current_vps_index = vps_config.get('current_vps_index', 0)
        
        # Initialize work distributor if VPS is enabled
        work_distributor = None
        if vps_enabled and len(vps_ips) >= 2:
            work_distributor = WorkDistributor(vps_ips, current_vps_index)
            logger.info(f"VPS distribution enabled. Current VPS index: {current_vps_index}, IP: {vps_ips[current_vps_index] if current_vps_index < len(vps_ips) else 'N/A'}")
        
        # Get Google Sheets configuration
        sheets_config = config.get('google_sheets', {})
        sheets_enabled = sheets_config.get('enabled', False)
        sheets_writer = None
        if sheets_enabled:
            try:
                spreadsheet_id = sheets_config.get('spreadsheet_id')
                credentials_file = sheets_config.get('credentials_file')
                if spreadsheet_id and credentials_file:
                    sheets_writer = GoogleSheetsWriter(spreadsheet_id, credentials_file)
                    logger.info(f"Google Sheets integration enabled. Spreadsheet ID: {spreadsheet_id}")
                else:
                    logger.warning("Google Sheets enabled but missing spreadsheet_id or credentials_file")
            except Exception as e:
                logger.error(f"Failed to initialize Google Sheets writer: {e}")
                sheets_writer = None
        
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
        
        # Get row range from config_overrides if provided (VPS-aware mode)
        start_row = None
        end_row = None
        last_person_year_start = None
        last_person_year_end = None
        last_person_month_start = None
        last_person_month_end = None
        if config_overrides:
            start_row = config_overrides.get('start_row')  # 1-based
            end_row = config_overrides.get('end_row')  # 1-based
            last_person_year_start = config_overrides.get('last_person_year_start')
            last_person_year_end = config_overrides.get('last_person_year_end')
            last_person_month_start = config_overrides.get('last_person_month_start')
            last_person_month_end = config_overrides.get('last_person_month_end')
        
        # Filter rows if row range specified (VPS-aware mode)
        original_row_count = len(input_df)
        if start_row is not None and end_row is not None:
            # Convert to 0-based indexing for pandas
            start_idx = max(0, start_row - 1)
            end_idx = min(len(input_df), end_row)
            input_df = input_df.iloc[start_idx:end_idx].copy()
            logger.info(f"VPS-aware mode: Processing rows {start_row}-{end_row} "
                       f"({len(input_df)} rows out of {original_row_count} total)")
            if last_person_year_start is not None and last_person_year_end is not None:
                logger.info(f"Last person year range override: {last_person_year_start}-{last_person_year_end}")
            if last_person_month_start is not None and last_person_month_end is not None:
                logger.info(f"Last person month range override: {last_person_month_start}-{last_person_month_end}")
        else:
            logger.info(f"Processing all rows: {len(input_df)} person(s)")
        
        # Validate columns
        required_columns = ['first_name', 'last_name_1', 'last_name_2', 'gender']
        missing_columns = [col for col in required_columns if col not in input_df.columns]
        
        if missing_columns:
            raise ValueError(f"Missing required columns: {missing_columns}")
        
        # Add person_id if not present
        if 'person_id' not in input_df.columns:
            # Adjust person_id based on row range if applicable
            if start_row is not None:
                input_df.insert(0, 'person_id', range(start_row, start_row + len(input_df)))
            else:
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
        
        # Get work assignments if VPS distribution is enabled
        work_assignments = {}
        if work_distributor:
            assignments = work_distributor.distribute_work(len(input_df), year_start, year_end)
            for assignment in assignments:
                person_idx = assignment['person_index']
                work_assignments[person_idx] = {
                    'year_start': assignment['year_start'],
                    'year_end': assignment['year_end']
                }
            logger.info(f"VPS {current_vps_index} assigned {len(assignments)} person(s) to process")
            for assignment in assignments:
                logger.info(f"  Person {assignment['person_index']}: years {assignment['year_start']}-{assignment['year_end']}")
        
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
            
            # Determine year range for this person (VPS distribution or full range)
            # Check if this is the last person and has year range override (for odd number split)
            is_last_person = (idx == input_df.index[-1])
            has_last_person_override = (last_person_year_start is not None and 
                                       last_person_year_end is not None)
            has_last_person_month_override = (last_person_month_start is not None and 
                                             last_person_month_end is not None)
            
            # Initialize month range (default: all months, or use global month range override)
            # Check for global month range override (applies to all persons)
            global_month_start = config_overrides.get('month_start')
            global_month_end = config_overrides.get('month_end')
            
            if global_month_start is not None and global_month_end is not None:
                # Use global month range for all persons
                person_month_start = global_month_start
                person_month_end = global_month_end
            else:
                # Default: all months
                person_month_start = 1
                person_month_end = 12
            
            if is_last_person and has_last_person_override:
                # Use year range override for last person (odd number split)
                person_year_start = last_person_year_start
                person_year_end = last_person_year_end
                # Use month range override if provided (for 1-year range split)
                if has_last_person_month_override:
                    person_month_start = last_person_month_start
                    person_month_end = last_person_month_end
                    logger.info(f"Person {person_id} (last person) using year range override: "
                              f"{person_year_start}-{person_year_end}, month range: {person_month_start}-{person_month_end}")
                else:
                    logger.info(f"Person {person_id} (last person) using year range override: "
                              f"{person_year_start}-{person_year_end}")
            elif work_distributor and idx in work_assignments:
                # Use assigned year range for this person (old VPS distribution)
                assigned_years = work_assignments[idx]
                person_year_start = assigned_years['year_start']
                person_year_end = assigned_years['year_end']
                logger.info(f"Person {person_id} assigned to VPS {current_vps_index}: years {person_year_start}-{person_year_end}")
            else:
                # No VPS distribution or person not assigned to this VPS
                if work_distributor:
                    # This person is not assigned to this VPS, skip
                    logger.info(f"Person {person_id} not assigned to VPS {current_vps_index}, skipping...")
                    continue
                else:
                    # No VPS distribution, use full range
                    person_year_start = year_start
                    person_year_end = year_end
            
            # Create combination generator with assigned year range and month range
            combination_generator = CombinationGenerator(person_year_start, person_year_end, 
                                                       person_month_start, person_month_end)
            total_combinations = combination_generator.get_total_count()
            
            logger.info(f"Processing person {person_id}: {person_name}")
            logger.info(f"Total combinations for this person: {total_combinations}")
            
            # Send initial progress update
            initial_progress = JobProgress(
                person_id=person_id,
                person_name=person_name,
                combination_index=0,
                total_combinations=total_combinations,
                matches_found=0,
                current_combination=None
            )
            initial_progress.percentage = 0.0
            search_manager.update_job_progress(job_id, initial_progress)
            emit_progress_update(job_id, {
                'job_id': job_id,
                'progress': {
                    'person_id': initial_progress.person_id,
                    'person_name': initial_progress.person_name,
                    'combination_index': initial_progress.combination_index,
                    'total_combinations': initial_progress.total_combinations,
                    'matches_found': initial_progress.matches_found,
                    'current_combination': initial_progress.current_combination,
                    'percentage': initial_progress.percentage
                }
            })
            
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
        
        # Generate output Excel - ALWAYS save to local file
        timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M")
        output_filename = f"curp_results_{job_id}_{timestamp}.xlsx"
        
        logger.info(f"Writing results to local Excel file: {output_filename}")
        excel_handler.write_results(all_results, summary_data, output_filename)
        
        result_file_path = str(Path(output_dir) / output_filename)
        logger.info(f"Results saved to local file: {result_file_path}")
        
        # Write to Google Sheets if enabled (in addition to local file)
        sheets_url = None
        if sheets_writer:
            logger.info("Writing results to Google Sheets (in addition to local file)...")
            try:
                create_sheet_per_job = sheets_config.get('create_sheet_per_job', True)
                append_results = sheets_config.get('append_results', True)
                
                if create_sheet_per_job:
                    # Create new sheet for this job
                    job_name = f"Job_{job_id}_{timestamp}"
                    worksheet = sheets_writer.create_sheet_for_job(job_id, job_name)
                    
                    if append_results:
                        # Append results (for multi-VPS scenarios)
                        sheets_writer.append_results(worksheet, all_results)
                    else:
                        # Write all results (overwrite)
                        sheets_writer.write_results(worksheet, all_results, summary_data, job_id, current_vps_index if vps_enabled else None)
                    
                    sheets_url = sheets_writer.get_sheet_url(worksheet)
                    logger.info(f"Results written to Google Sheets: {sheets_url}")
                    logger.info(f"Results saved to BOTH locations: 1) Local Excel: {result_file_path}, 2) Google Sheets: {sheets_url}")
                else:
                    # Use first sheet or default sheet
                    worksheet = sheets_writer.spreadsheet.sheet1
                    if append_results:
                        sheets_writer.append_results(worksheet, all_results)
                    else:
                        sheets_writer.write_results(worksheet, all_results, summary_data, job_id, current_vps_index if vps_enabled else None)
                    sheets_url = sheets_writer.get_sheet_url(worksheet)
                    logger.info(f"Results written to Google Sheets: {sheets_url}")
                    logger.info(f"Results saved to BOTH locations: 1) Local Excel: {result_file_path}, 2) Google Sheets: {sheets_url}")
            
            except Exception as e:
                logger.error(f"Error writing to Google Sheets: {e}", exc_info=True)
                # Don't fail the job if Sheets write fails - local Excel file is already saved
                logger.warning("Google Sheets write failed, but local Excel file was saved successfully")
                logger.info(f"Results saved to local file only: {result_file_path}")
        else:
            logger.info(f"Google Sheets not enabled. Results saved to local file only: {result_file_path}")
        
        # Update job with result file
        search_manager.set_job_result(job_id, result_file_path)
        search_manager.update_job_status(job_id, JobStatus.COMPLETED)
        
        # Emit completion (include Sheets URL if available)
        completion_data = {
            'result_file': result_file_path,
            'sheets_url': sheets_url
        }
        emit_job_complete(job_id, completion_data)
        
        # Clear checkpoint on successful completion
        checkpoint_manager.clear_checkpoint()
        logger.info(f"Search completed successfully for job {job_id}")
        if sheets_url:
            logger.info(f"Google Sheets URL: {sheets_url}")
    
    except Exception as e:
        logger.error(f"Error in search job {job_id}: {e}", exc_info=True)
        search_manager.update_job_status(job_id, JobStatus.FAILED, str(e))
        emit_job_error(job_id, str(e))
