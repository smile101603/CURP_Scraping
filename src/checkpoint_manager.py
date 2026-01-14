"""
Checkpoint Manager
Saves and restores progress to allow resuming interrupted searches.
"""
import json
import os
from pathlib import Path
from typing import Optional, Dict, List
from datetime import datetime


class CheckpointManager:
    """Manage checkpoints for resuming searches."""
    
    def __init__(self, checkpoint_dir: str = "./checkpoints"):
        """
        Initialize checkpoint manager.
        
        Args:
            checkpoint_dir: Directory to store checkpoint files
        """
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoint_file = self.checkpoint_dir / "checkpoint.json"
    
    def save_checkpoint(self, person_id: int, person_name: str, 
                       combination_index: int, day: int, month: int, 
                       state: str, year: int, matches: List[Dict],
                       total_processed: int, total_combinations: int,
                       config: Dict = None):
        """
        Save current progress to checkpoint file.
        
        Args:
            person_id: Current person ID being processed
            person_name: Name of current person
            combination_index: Index of last processed combination
            day: Day of last combination
            month: Month of last combination
            state: State of last combination
            year: Year of last combination
            matches: List of matches found so far
            total_processed: Total combinations processed
            total_combinations: Total combinations to process
            config: Configuration dict to track test settings
        """
        checkpoint_data = {
            'timestamp': datetime.now().isoformat(),
            'person_id': person_id,
            'person_name': person_name,
            'combination_index': combination_index,
            'last_combination': {
                'day': day,
                'month': month,
                'state': state,
                'year': year
            },
            'matches': matches,
            'progress': {
                'total_processed': total_processed,
                'total_combinations': total_combinations,
                'percentage': (total_processed / total_combinations * 100) if total_combinations > 0 else 0
            },
            'config': config or {}
        }
        
        try:
            with open(self.checkpoint_file, 'w', encoding='utf-8') as f:
                json.dump(checkpoint_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Warning: Failed to save checkpoint: {e}")
    
    def load_checkpoint(self) -> Optional[Dict]:
        """
        Load checkpoint data if it exists.
        
        Returns:
            Dictionary with checkpoint data or None if no checkpoint exists
        """
        if not self.checkpoint_file.exists():
            return None
        
        try:
            with open(self.checkpoint_file, 'r', encoding='utf-8') as f:
                checkpoint_data = json.load(f)
            return checkpoint_data
        except Exception as e:
            print(f"Warning: Failed to load checkpoint: {e}")
            return None
    
    def clear_checkpoint(self):
        """Delete checkpoint file."""
        if self.checkpoint_file.exists():
            try:
                self.checkpoint_file.unlink()
                print("Checkpoint cleared.")
            except Exception as e:
                print(f"Warning: Failed to clear checkpoint: {e}")
    
    def has_checkpoint(self) -> bool:
        """Check if a checkpoint exists."""
        return self.checkpoint_file.exists()
    
    def save_matches(self, matches: List[Dict], filename: str = "matches_backup.json"):
        """
        Save matches to a separate backup file.
        
        Args:
            matches: List of match dictionaries
            filename: Name of the backup file
        """
        backup_file = self.checkpoint_dir / filename
        
        backup_data = {
            'timestamp': datetime.now().isoformat(),
            'matches': matches
        }
        
        try:
            with open(backup_file, 'w', encoding='utf-8') as f:
                json.dump(backup_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Warning: Failed to save matches backup: {e}")

