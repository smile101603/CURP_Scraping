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
from pathlib import Path
from . import app, socketio
from .search_manager import search_manager
from .models import JobStatus
from excel_handler import ExcelHandler
from search_runner import run_search_async

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
    """Health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'service': 'CURP Automation API'
    }), 200


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
        
        # Check if file exists
        file_path = UPLOAD_FOLDER / filename
        if not file_path.exists():
            return jsonify({'error': 'File not found'}), 404
        
        # Create job
        job_id = search_manager.create_job(year_start, year_end, filename)
        
        # Start search in background
        run_search_async(job_id, str(file_path), year_start, year_end)
        
        # If VPS distribution is enabled, trigger other VPSs to start the same job
        try:
            from pathlib import Path
            config_path = Path('./config/settings.json')
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    vps_config = config.get('vps', {})
                    vps_enabled = vps_config.get('enabled', False)
                    vps_ips = vps_config.get('vps_ips', [])
                    current_vps_index = vps_config.get('current_vps_index', 0)
                    
                    if vps_enabled and len(vps_ips) >= 2:
                        # Trigger other VPSs to start the same job
                        for idx, vps_ip in enumerate(vps_ips):
                            if idx != current_vps_index:
                                try:
                                    # First, upload the file to the other VPS
                                    with open(file_path, 'rb') as f:
                                        files = {'file': (filename, f, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}
                                        upload_url = f"http://{vps_ip}:5000/api/upload"
                                        upload_response = requests.post(upload_url, files=files, timeout=30)
                                        
                                        if upload_response.status_code == 200:
                                            upload_data = upload_response.json()
                                            uploaded_filename = upload_data.get('filename', filename)
                                            
                                            # Then start the job on the other VPS
                                            start_url = f"http://{vps_ip}:5000/api/start"
                                            start_data = {
                                                'filename': uploaded_filename,
                                                'year_start': year_start,
                                                'year_end': year_end
                                            }
                                            start_response = requests.post(start_url, json=start_data, timeout=10)
                                            
                                            if start_response.status_code == 200:
                                                logger.info(f"Successfully triggered job on VPS {idx} ({vps_ip})")
                                            else:
                                                logger.warning(f"Failed to start job on VPS {idx} ({vps_ip}): {start_response.status_code} - {start_response.text}")
                                        else:
                                            logger.warning(f"Failed to upload file to VPS {idx} ({vps_ip}): {upload_response.status_code} - {upload_response.text}")
                                except Exception as e:
                                    logger.error(f"Error triggering VPS {idx} ({vps_ip}): {e}")
        except Exception as e:
            logger.warning(f"Error triggering other VPSs (job will continue on this VPS): {e}")
        
        return jsonify({
            'message': 'Search started',
            'job_id': job_id
        }), 200
    
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
