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
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
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
            return jsonify({'error': 'No data provided'}), 400
        
        filename = data.get('filename')
        year_start = data.get('year_start')
        year_end = data.get('year_end')
        
        if not filename:
            return jsonify({'error': 'Filename is required'}), 400
        
        if not year_start or not year_end:
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
                return jsonify({'error': 'Both start_row and end_row must be provided together'}), 400
            try:
                start_row = int(start_row)
                end_row = int(end_row)
            except (ValueError, TypeError):
                return jsonify({'error': 'start_row and end_row must be integers'}), 400
            if start_row < 1:
                return jsonify({'error': 'start_row must be >= 1'}), 400
            if end_row < start_row:
                return jsonify({'error': 'end_row must be >= start_row'}), 400
        
        # Check if file exists
        file_path = UPLOAD_FOLDER / filename
        if not file_path.exists():
            return jsonify({'error': 'File not found'}), 404
        
        # Create job
        job_id = search_manager.create_job(year_start, year_end, filename)
        
        # Prepare config overrides with row range if provided
        config_overrides = {}
        if start_row is not None and end_row is not None:
            config_overrides['start_row'] = start_row
            config_overrides['end_row'] = end_row
            logger.info(f"Job {job_id}: Starting with row range {start_row}-{end_row}")
        
        # Start search in background
        run_search_async(job_id, str(file_path), year_start, year_end, config_overrides)
        
        logger.info(f"Job {job_id} started: file={filename}, year_range={year_start}-{year_end}, "
                   f"row_range={'{}-{}'.format(start_row, end_row) if start_row else 'all'}")
        
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
