"""
Search Manager
Manages search jobs and progress tracking.
"""
import threading
import uuid
from typing import Dict, Optional
from datetime import datetime, timedelta
from .models import Job, JobStatus, JobProgress
import logging

logger = logging.getLogger(__name__)


class SearchManager:
    """Manages search jobs and their progress."""
    
    def __init__(self):
        """Initialize search manager."""
        self.jobs: Dict[str, Job] = {}
        self.jobs_lock = threading.Lock()
        self.cleanup_interval = timedelta(hours=24)  # Clean up jobs older than 24 hours
    
    def create_job(self, year_start: int, year_end: int, input_filename: str) -> str:
        """
        Create a new search job.
        
        Args:
            year_start: Start year for search
            year_end: End year for search
            input_filename: Name of uploaded input file
            
        Returns:
            Job ID
        """
        job_id = str(uuid.uuid4())
        
        job = Job(
            job_id=job_id,
            status=JobStatus.PENDING,
            created_at=datetime.now(),
            year_start=year_start,
            year_end=year_end,
            input_filename=input_filename
        )
        
        with self.jobs_lock:
            self.jobs[job_id] = job
        
        logger.info(f"Created job {job_id}")
        return job_id
    
    def get_job(self, job_id: str) -> Optional[Job]:
        """
        Get job by ID.
        
        Args:
            job_id: Job ID
            
        Returns:
            Job object or None if not found
        """
        with self.jobs_lock:
            return self.jobs.get(job_id)
    
    def update_job_status(self, job_id: str, status: JobStatus, 
                         error_message: Optional[str] = None):
        """
        Update job status.
        
        Args:
            job_id: Job ID
            status: New status
            error_message: Error message if status is FAILED
        """
        with self.jobs_lock:
            if job_id in self.jobs:
                job = self.jobs[job_id]
                job.status = status
                
                if status == JobStatus.RUNNING and not job.started_at:
                    job.started_at = datetime.now()
                elif status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
                    job.completed_at = datetime.now()
                
                if error_message:
                    job.error_message = error_message
                
                logger.info(f"Job {job_id} status updated to {status.value}")
    
    def update_job_progress(self, job_id: str, progress: JobProgress):
        """
        Update job progress.
        
        Args:
            job_id: Job ID
            progress: Progress information
        """
        with self.jobs_lock:
            if job_id in self.jobs:
                job = self.jobs[job_id]
                job.progress = progress
                
                # Calculate percentage
                if progress.total_combinations > 0:
                    progress.percentage = (progress.combination_index / progress.total_combinations) * 100
    
    def set_job_result(self, job_id: str, result_file_path: str):
        """
        Set result file path for completed job.
        
        Args:
            job_id: Job ID
            result_file_path: Path to result Excel file
        """
        with self.jobs_lock:
            if job_id in self.jobs:
                self.jobs[job_id].result_file_path = result_file_path
                logger.info(f"Job {job_id} result file set: {result_file_path}")
    
    def list_jobs(self) -> Dict[str, Dict]:
        """
        List all jobs.
        
        Returns:
            Dictionary of job_id -> job_dict
        """
        with self.jobs_lock:
            return {job_id: job.to_dict() for job_id, job in self.jobs.items()}
    
    def cleanup_old_jobs(self):
        """Remove jobs older than cleanup_interval."""
        cutoff_time = datetime.now() - self.cleanup_interval
        
        with self.jobs_lock:
            jobs_to_remove = [
                job_id for job_id, job in self.jobs.items()
                if job.completed_at and job.completed_at < cutoff_time
            ]
            
            for job_id in jobs_to_remove:
                del self.jobs[job_id]
                logger.info(f"Cleaned up old job {job_id}")
    
    def cancel_job(self, job_id: str) -> bool:
        """
        Cancel a job.
        
        Args:
            job_id: Job ID
            
        Returns:
            True if job was cancelled, False if not found or already completed
        """
        with self.jobs_lock:
            if job_id in self.jobs:
                job = self.jobs[job_id]
                if job.status in [JobStatus.PENDING, JobStatus.RUNNING]:
                    job.status = JobStatus.CANCELLED
                    job.completed_at = datetime.now()
                    logger.info(f"Job {job_id} cancelled")
                    return True
        return False


# Global search manager instance
search_manager = SearchManager()
