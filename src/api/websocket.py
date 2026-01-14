"""
WebSocket Handlers
Real-time progress updates via WebSocket.
"""
from flask_socketio import emit, disconnect
from flask import request
import logging
from . import socketio
from .search_manager import search_manager

logger = logging.getLogger(__name__)


@socketio.on('connect')
def handle_connect():
    """Handle client connection."""
    logger.info(f"Client connected: {request.sid}")
    emit('connected', {'message': 'Connected to CURP Automation API'})


@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection."""
    logger.info(f"Client disconnected: {request.sid}")


@socketio.on('subscribe_job')
def handle_subscribe_job(data):
    """Subscribe to job progress updates."""
    try:
        job_id = data.get('job_id')
        
        if not job_id:
            emit('error', {'message': 'job_id is required'})
            return
        
        job = search_manager.get_job(job_id)
        
        if not job:
            emit('error', {'message': 'Job not found'})
            return
        
        # Join room for this job
        socketio.server.enter_room(request.sid, f'job_{job_id}')
        
        logger.info(f"Client {request.sid} subscribed to job {job_id}")
        emit('subscribed', {'job_id': job_id, 'status': job.status.value})
    
    except Exception as e:
        logger.error(f"Error subscribing to job: {e}", exc_info=True)
        emit('error', {'message': str(e)})


@socketio.on('unsubscribe_job')
def handle_unsubscribe_job(data):
    """Unsubscribe from job progress updates."""
    try:
        job_id = data.get('job_id')
        
        if job_id:
            socketio.server.leave_room(request.sid, f'job_{job_id}')
            logger.info(f"Client {request.sid} unsubscribed from job {job_id}")
            emit('unsubscribed', {'job_id': job_id})
    
    except Exception as e:
        logger.error(f"Error unsubscribing from job: {e}", exc_info=True)


def emit_progress_update(job_id: str, progress_data: dict):
    """
    Emit progress update to all clients subscribed to a job.
    
    Args:
        job_id: Job ID
        progress_data: Progress data dictionary
    """
    try:
        socketio.emit('progress_update', progress_data, room=f'job_{job_id}')
    except Exception as e:
        logger.error(f"Error emitting progress update: {e}")


def emit_job_complete(job_id: str, result_file_path: str = None):
    """
    Emit job completion event.
    
    Args:
        job_id: Job ID
        result_file_path: Path to result file
    """
    try:
        socketio.emit('job_complete', {
            'job_id': job_id,
            'result_file_path': result_file_path
        }, room=f'job_{job_id}')
    except Exception as e:
        logger.error(f"Error emitting job complete: {e}")


def emit_job_error(job_id: str, error_message: str):
    """
    Emit job error event.
    
    Args:
        job_id: Job ID
        error_message: Error message
    """
    try:
        socketio.emit('job_error', {
            'job_id': job_id,
            'error_message': error_message
        }, room=f'job_{job_id}')
    except Exception as e:
        logger.error(f"Error emitting job error: {e}")
