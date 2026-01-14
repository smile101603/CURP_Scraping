"""
API Models
Data models for job tracking and status.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime
from enum import Enum


class JobStatus(Enum):
    """Job status enumeration."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class JobProgress:
    """Progress information for a job."""
    person_id: int = 0
    person_name: str = ""
    combination_index: int = 0
    total_combinations: int = 0
    matches_found: int = 0
    current_combination: Optional[Dict] = None
    percentage: float = 0.0
    estimated_time_remaining: Optional[float] = None  # seconds


@dataclass
class Job:
    """Job information and status."""
    job_id: str
    status: JobStatus
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    progress: JobProgress = field(default_factory=JobProgress)
    error_message: Optional[str] = None
    result_file_path: Optional[str] = None
    year_start: Optional[int] = None
    year_end: Optional[int] = None
    input_filename: Optional[str] = None
    
    def to_dict(self) -> Dict:
        """Convert job to dictionary for JSON serialization."""
        return {
            'job_id': self.job_id,
            'status': self.status.value,
            'created_at': self.created_at.isoformat(),
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'progress': {
                'person_id': self.progress.person_id,
                'person_name': self.progress.person_name,
                'combination_index': self.progress.combination_index,
                'total_combinations': self.progress.total_combinations,
                'matches_found': self.progress.matches_found,
                'current_combination': self.progress.current_combination,
                'percentage': self.progress.percentage,
                'estimated_time_remaining': self.progress.estimated_time_remaining
            },
            'error_message': self.error_message,
            'result_file_path': self.result_file_path,
            'year_start': self.year_start,
            'year_end': self.year_end,
            'input_filename': self.input_filename
        }
