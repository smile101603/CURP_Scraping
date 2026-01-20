"""
API Routes
Flask API endpoints for CURP automation.
"""
from flask import request, jsonify, send_file
from werkzeug.utils import secure_filename
import os
import logging
import json
import requests
import time
from datetime import datetime
from pathlib import Path
from . import app, socketio
from .search_manager import search_manager
from .models import JobStatus
from excel_handler import ExcelHandler
from search_runner import run_search_async

# Try to import psutil for system metrics, fallback if not available
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("psutil not available - system metrics will be limited")

logger = logging.getLogger(__name__)

# Configuration
UPLOAD_FOLDER = Path('./data/uploads')
UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
ALLOWED_EXTENSIONS = {'xlsx', 'xls'}
MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB

# Initialize Excel handler
excel_handler = ExcelHandler()


def allowed_file(filename):
    """Check if file extension is allowed."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route('/api/health', methods=['GET'])
def health_check():
    """Enhanced health check endpoint with detailed server status."""
    try:
        active_jobs = len([j for j in search_manager.jobs.values() 
                          if j.status == JobStatus.RUNNING])
        total_jobs = len(search_manager.jobs)
        
        # Get system metrics if available
        memory_info = {}
        disk_info = {}
        if PSUTIL_AVAILABLE:
            try:
                memory = psutil.virtual_memory()
                memory_info = {
                    'percent': memory.percent,
                    'total_gb': round(memory.total / (1024**3), 2),
                    'available_gb': round(memory.available / (1024**3), 2)
                }
            except Exception as e:
                logger.warning(f"Could not get memory info: {e}")
            
            try:
                disk = psutil.disk_usage('/')
                disk_info = {
                    'percent': disk.percent,
                    'total_gb': round(disk.total / (1024**3), 2),
                    'free_gb': round(disk.free / (1024**3), 2)
                }
            except Exception as e:
                logger.warning(f"Could not get disk info: {e}")
        
        # Get uptime from app.py if available
        try:
            from app import start_time
            uptime_seconds = time.time() - start_time if start_time else None
        except:
            uptime_seconds = None
        
        return jsonify({
            'status': 'healthy',
            'service': 'CURP Automation API',
            'uptime_seconds': uptime_seconds,
            'active_jobs': active_jobs,
            'total_jobs': total_jobs,
            'memory': memory_info if memory_info else None,
            'disk': disk_info if disk_info else None,
            'timestamp': datetime.now().isoformat()
        }), 200
    except Exception as e:
        logger.error(f"Health check error: {e}", exc_info=True)
        return jsonify({
            'status': 'error',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500


@app.route('/api/status', methods=['GET'])
def get_status():
    """Get detailed server status with comprehensive metrics."""
    try:
        # Job statistics
        jobs_by_status = {}
        for status in JobStatus:
            jobs_by_status[status.value] = len([j for j in search_manager.jobs.values() 
                                                if j.status == status])
        
        active_jobs = jobs_by_status.get('running', 0)
        total_jobs = len(search_manager.jobs)
        
        # Get system metrics
        system_info = {}
        if PSUTIL_AVAILABLE:
            try:
                # CPU
                cpu_percent = psutil.cpu_percent(interval=0.1)
                
                # Memory
                memory = psutil.virtual_memory()
                
                # Disk
                disk = psutil.disk_usage('/')
                
                # Network (if available)
                network_info = {}
                try:
                    net_io = psutil.net_io_counters()
                    network_info = {
                        'bytes_sent': net_io.bytes_sent,
                        'bytes_recv': net_io.bytes_recv
                    }
                except:
                    pass
                
                system_info = {
                    'cpu_percent': cpu_percent,
                    'memory': {
                        'percent': memory.percent,
                        'total_gb': round(memory.total / (1024**3), 2),
                        'available_gb': round(memory.available / (1024**3), 2),
                        'used_gb': round(memory.used / (1024**3), 2)
                    },
                    'disk': {
                        'percent': disk.percent,
                        'total_gb': round(disk.total / (1024**3), 2),
                        'free_gb': round(disk.free / (1024**3), 2),
                        'used_gb': round(disk.used / (1024**3), 2)
                    },
                    'network': network_info if network_info else None
                }
            except Exception as e:
                logger.warning(f"Could not get system info: {e}")
        
        # Get uptime
        try:
            from app import start_time
            uptime_seconds = time.time() - start_time if start_time else None
        except:
            uptime_seconds = None
        
        return jsonify({
            'status': 'operational',
            'service': 'CURP Automation API',
            'uptime_seconds': uptime_seconds,
            'jobs': {
                'total': total_jobs,
                'active': active_jobs,
                'by_status': jobs_by_status
            },
            'system': system_info if system_info else None,
            'timestamp': datetime.now().isoformat()
        }), 200
    except Exception as e:
        logger.error(f"Status endpoint error: {e}", exc_info=True)
        return jsonify({
            'status': 'error',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500


@app.route('/api/file-info', methods=['GET'])
def get_file_info():
    """Get file information including row count."""
    try:
        filename = request.args.get('filename')
        if not filename:
            return jsonify({'error': 'Filename required'}), 400
        
        file_path = UPLOAD_FOLDER / filename
        if not file_path.exists():
            return jsonify({'error': 'File not found'}), 404
        
        # Read file to get row count
        try:
            input_df = excel_handler.read_input(str(file_path))
            row_count = len(input_df)
            
            logger.info(f"File info requested: {filename} - {row_count} rows")
            
            return jsonify({
                'filename': filename,
                'row_count': row_count,
                'file_size': file_path.stat().st_size
            }), 200
        except Exception as e:
            logger.error(f"Error reading file {filename}: {e}", exc_info=True)
            return jsonify({'error': f'Error reading file: {str(e)}'}), 500
    
    except Exception as e:
        logger.error(f"Error in file-info endpoint: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/upload', methods=['POST'])
def upload_file():
    """Upload Excel file."""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if not allowed_file(file.filename):
            return jsonify({'error': 'Invalid file type. Only Excel files (.xlsx, .xls) are allowed'}), 400
        
        # Check file size
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)
        
        if file_size > MAX_UPLOAD_SIZE:
            return jsonify({'error': f'File too large. Maximum size is {MAX_UPLOAD_SIZE / 1024 / 1024} MB'}), 400
        
        # Save file
        filename = secure_filename(file.filename)
        file_path = UPLOAD_FOLDER / filename
        
        # If file exists, add timestamp
        if file_path.exists():
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M")
            name, ext = os.path.splitext(filename)
            filename = f"{name}_{timestamp}{ext}"
            file_path = UPLOAD_FOLDER / filename
        
        file.save(file_path)
        
        logger.info(f"File uploaded: {filename}")
        
        return jsonify({
            'message': 'File uploaded successfully',
            'filename': filename,
            'size': file_size
        }), 200
    
    except Exception as e:
        logger.error(f"Error uploading file: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/start', methods=['POST'])
def start_search():
    """Start a new search job."""
    try:
        data = request.get_json()
        
        # Validate input
        if not data:
            logger.error("No data provided in /api/start request")
            return jsonify({'error': 'No data provided'}), 400
        
        logger.info(f"Received /api/start request data keys: {list(data.keys()) if data else 'None'}")
        logger.debug(f"Received /api/start request data: {data}")
        
        filename = data.get('filename')
        year_start = data.get('year_start')
        year_end = data.get('year_end')
        
        if not filename:
            logger.error("Filename missing in /api/start request")
            return jsonify({'error': 'Filename is required'}), 400
        
        if year_start is None or year_end is None:
            logger.error(f"Year range missing in /api/start request: year_start={year_start}, year_end={year_end}")
            return jsonify({'error': 'year_start and year_end are required'}), 400
        
        try:
            year_start = int(year_start)
            year_end = int(year_end)
        except (ValueError, TypeError):
            return jsonify({'error': 'year_start and year_end must be integers'}), 400
        
        if year_start > year_end:
            return jsonify({'error': 'year_start must be less than or equal to year_end'}), 400
        
        if year_start < 1900 or year_end > 2100:
            return jsonify({'error': 'Year range must be between 1900 and 2100'}), 400
        
        # Get optional row range (for VPS-aware distribution)
        start_row = data.get('start_row')  # 1-based
        end_row = data.get('end_row')  # 1-based
        
        # Validate row range if provided
        if start_row is not None or end_row is not None:
            if start_row is None or end_row is None:
                error_msg = 'Both start_row and end_row must be provided together'
                logger.error(f"{error_msg}: start_row={start_row}, end_row={end_row}")
                return jsonify({'error': error_msg}), 400
            try:
                start_row = int(start_row)
                end_row = int(end_row)
            except (ValueError, TypeError) as e:
                error_msg = 'start_row and end_row must be integers'
                logger.error(f"{error_msg}: start_row={start_row}, end_row={end_row}, error={e}")
                return jsonify({'error': error_msg}), 400
            if start_row < 1:
                error_msg = 'start_row must be >= 1'
                logger.error(f"{error_msg}: start_row={start_row}")
                return jsonify({'error': error_msg}), 400
            if end_row < start_row:
                error_msg = 'end_row must be >= start_row'
                logger.error(f"{error_msg}: start_row={start_row}, end_row={end_row}")
                return jsonify({'error': error_msg}), 400
        
        # Check if file exists
        file_path = UPLOAD_FOLDER / filename
        if not file_path.exists():
            return jsonify({'error': 'File not found'}), 404
        
        # Create job
        job_id = search_manager.create_job(year_start, year_end, filename)
        
        # Get optional last person year range (for odd number split)
        last_person_year_start = data.get('last_person_year_start')
        last_person_year_end = data.get('last_person_year_end')
        
        # Validate last person year range if provided
        if last_person_year_start is not None or last_person_year_end is not None:
            if last_person_year_start is None or last_person_year_end is None:
                error_msg = 'Both last_person_year_start and last_person_year_end must be provided together'
                logger.error(f"{error_msg}: last_person_year_start={last_person_year_start}, last_person_year_end={last_person_year_end}")
                return jsonify({'error': error_msg}), 400
            try:
                last_person_year_start = int(last_person_year_start)
                last_person_year_end = int(last_person_year_end)
            except (ValueError, TypeError) as e:
                error_msg = 'last_person_year_start and last_person_year_end must be integers'
                logger.error(f"{error_msg}: last_person_year_start={last_person_year_start}, last_person_year_end={last_person_year_end}, error={e}")
                return jsonify({'error': error_msg}), 400
            if last_person_year_start < 1900 or last_person_year_end > 2100:
                error_msg = 'Last person year range must be between 1900 and 2100'
                logger.error(f"{error_msg}: last_person_year_start={last_person_year_start}, last_person_year_end={last_person_year_end}")
                return jsonify({'error': error_msg}), 400
            if last_person_year_start > last_person_year_end:
                error_msg = 'last_person_year_start must be <= last_person_year_end'
                logger.error(f"{error_msg}: last_person_year_start={last_person_year_start}, last_person_year_end={last_person_year_end}")
                return jsonify({'error': error_msg}), 400
        
        # Get optional month range (for testing specific months - applies to all persons)
        month_start = data.get('month_start')
        month_end = data.get('month_end')
        
        # Validate month range if provided
        if month_start is not None or month_end is not None:
            if month_start is None or month_end is None:
                error_msg = 'Both month_start and month_end must be provided together'
                logger.error(f"{error_msg}: month_start={month_start}, month_end={month_end}")
                return jsonify({'error': error_msg}), 400
            try:
                month_start = int(month_start)
                month_end = int(month_end)
            except (ValueError, TypeError) as e:
                error_msg = 'month_start and month_end must be integers'
                logger.error(f"{error_msg}: month_start={month_start}, month_end={month_end}, error={e}")
                return jsonify({'error': error_msg}), 400
            if month_start < 1 or month_start > 12:
                error_msg = 'month_start must be between 1 and 12'
                logger.error(f"{error_msg}: month_start={month_start}")
                return jsonify({'error': error_msg}), 400
            if month_end < 1 or month_end > 12:
                error_msg = 'month_end must be between 1 and 12'
                logger.error(f"{error_msg}: month_end={month_end}")
                return jsonify({'error': error_msg}), 400
            if month_start > month_end:
                error_msg = 'month_start must be <= month_end'
                logger.error(f"{error_msg}: month_start={month_start}, month_end={month_end}")
                return jsonify({'error': error_msg}), 400
        
        # Get optional last person month range (for 1-year range split)
        last_person_month_start = data.get('last_person_month_start')
        last_person_month_end = data.get('last_person_month_end')
        
        # Validate last person month range if provided
        if last_person_month_start is not None or last_person_month_end is not None:
            if last_person_month_start is None or last_person_month_end is None:
                error_msg = 'Both last_person_month_start and last_person_month_end must be provided together'
                logger.error(f"{error_msg}: last_person_month_start={last_person_month_start}, last_person_month_end={last_person_month_end}")
                return jsonify({'error': error_msg}), 400
            try:
                last_person_month_start = int(last_person_month_start)
                last_person_month_end = int(last_person_month_end)
            except (ValueError, TypeError) as e:
                error_msg = 'last_person_month_start and last_person_month_end must be integers'
                logger.error(f"{error_msg}: last_person_month_start={last_person_month_start}, last_person_month_end={last_person_month_end}, error={e}")
                return jsonify({'error': error_msg}), 400
            if last_person_month_start < 1 or last_person_month_start > 12:
                error_msg = 'last_person_month_start must be between 1 and 12'
                logger.error(f"{error_msg}: last_person_month_start={last_person_month_start}")
                return jsonify({'error': error_msg}), 400
            if last_person_month_end < 1 or last_person_month_end > 12:
                error_msg = 'last_person_month_end must be between 1 and 12'
                logger.error(f"{error_msg}: last_person_month_end={last_person_month_end}")
                return jsonify({'error': error_msg}), 400
            if last_person_month_start > last_person_month_end:
                error_msg = 'last_person_month_start must be <= last_person_month_end'
                logger.error(f"{error_msg}: last_person_month_start={last_person_month_start}, last_person_month_end={last_person_month_end}")
                return jsonify({'error': error_msg}), 400
        
        # Prepare config overrides with row range, month range, and last person year range if provided
        config_overrides = {}
        if start_row is not None and end_row is not None:
            config_overrides['start_row'] = start_row
            config_overrides['end_row'] = end_row
            logger.info(f"Job {job_id}: Starting with row range {start_row}-{end_row}")
        
        # Add month range if provided (applies to all persons)
        if month_start is not None and month_end is not None:
            config_overrides['month_start'] = month_start
            config_overrides['month_end'] = month_end
            logger.info(f"Job {job_id}: Month range override: {month_start}-{month_end} (applies to all persons)")
        
        if last_person_year_start is not None and last_person_year_end is not None:
            config_overrides['last_person_year_start'] = last_person_year_start
            config_overrides['last_person_year_end'] = last_person_year_end
            logger.info(f"Job {job_id}: Last person year range override: {last_person_year_start}-{last_person_year_end}")
        
        if last_person_month_start is not None and last_person_month_end is not None:
            config_overrides['last_person_month_start'] = last_person_month_start
            config_overrides['last_person_month_end'] = last_person_month_end
            logger.info(f"Job {job_id}: Last person month range override: {last_person_month_start}-{last_person_month_end}")
        
        # Start search in background
        run_search_async(job_id, str(file_path), year_start, year_end, config_overrides)
        
        log_msg = f"Job {job_id} started: file={filename}, year_range={year_start}-{year_end}"
        if start_row:
            log_msg += f", row_range={start_row}-{end_row}"
        if last_person_year_start:
            log_msg += f", last_person_years={last_person_year_start}-{last_person_year_end}"
        if last_person_month_start:
            log_msg += f", last_person_months={last_person_month_start}-{last_person_month_end}"
        logger.info(log_msg)
        
        return jsonify({
            'job_id': job_id,
            'message': 'Search job started',
            'row_range': {'start': start_row, 'end': end_row} if start_row else None
        }), 200
        
        # Note: VPS distribution is now handled by frontend
        # Removed automatic VPS triggering - frontend calculates and sends to each VPS
    
    except Exception as e:
        logger.error(f"Error starting search: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/status/<job_id>', methods=['GET'])
def get_job_status(job_id):
    """Get job status."""
    try:
        job = search_manager.get_job(job_id)
        
        if not job:
            return jsonify({'error': 'Job not found'}), 404
        
        return jsonify(job.to_dict()), 200
    
    except Exception as e:
        logger.error(f"Error getting job status: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/jobs', methods=['GET'])
def list_jobs():
    """List all jobs."""
    try:
        jobs = search_manager.list_jobs()
        return jsonify(jobs), 200
    
    except Exception as e:
        logger.error(f"Error listing jobs: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/download/<job_id>', methods=['GET'])
def download_results(job_id):
    """Download results Excel file."""
    try:
        job = search_manager.get_job(job_id)
        
        if not job:
            return jsonify({'error': 'Job not found'}), 404
        
        if job.status != JobStatus.COMPLETED:
            return jsonify({'error': 'Job not completed yet'}), 400
        
        if not job.result_file_path or not os.path.exists(job.result_file_path):
            return jsonify({'error': 'Result file not found'}), 404
        
        return send_file(
            job.result_file_path,
            as_attachment=True,
            download_name=os.path.basename(job.result_file_path),
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    
    except Exception as e:
        logger.error(f"Error downloading results: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/cancel/<job_id>', methods=['POST'])
def cancel_job(job_id):
    """Cancel a job."""
    try:
        success = search_manager.cancel_job(job_id)
        
        if not success:
            return jsonify({'error': 'Job not found or cannot be cancelled'}), 404
        
        return jsonify({'message': 'Job cancelled'}), 200
    
    except Exception as e:
        logger.error(f"Error cancelling job: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500
