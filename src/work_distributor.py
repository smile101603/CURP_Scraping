"""
Work Distributor
Distributes work between multiple VPS servers.
"""
from typing import List, Dict, Tuple
import math


class WorkDistributor:
    """Distributes work between VPS servers."""
    
    def __init__(self, vps_ips: List[str], current_vps_index: int):
        """
        Initialize work distributor.
        
        Args:
            vps_ips: List of VPS IP addresses
            current_vps_index: Index of current VPS (0-based)
        """
        self.vps_ips = vps_ips
        self.current_vps_index = current_vps_index
        self.num_vps = len(vps_ips)
    
    def distribute_work(self, num_people: int, year_start: int, year_end: int) -> List[Dict]:
        """
        Distribute work between VPS servers.
        
        Rules:
        - For 1 person: split year range in half between VPSs
        - For 2 people: each VPS handles 1 person (with year range split in half)
        - For 3+ people: distribute people evenly, and if odd number, 
          the remaining person's year range is split between both VPSs
        
        Args:
            num_people: Total number of people to process
            year_start: Start year
            year_end: End year (inclusive)
            
        Returns:
            List of work assignments for current VPS
            Each assignment: {
                'person_index': int,
                'year_start': int,
                'year_end': int
            }
        """
        assignments = []
        total_years = year_end - year_start + 1
        
        if num_people == 1:
            # Single person: split year range in half
            mid_year = self._calculate_mid_year(year_start, year_end, total_years)
            if self.current_vps_index == 0:
                assignments.append({
                    'person_index': 0,
                    'year_start': year_start,
                    'year_end': mid_year - 1 if total_years > 1 else year_start
                })
            else:
                assignments.append({
                    'person_index': 0,
                    'year_start': mid_year if total_years > 1 else year_start,
                    'year_end': year_end
                })
        elif num_people == 2:
            # Two people: each person's year range is split between VPSs
            # VPS1: person 0 (first half) + person 1 (first half)
            # VPS2: person 0 (second half) + person 1 (second half)
            mid_year = self._calculate_mid_year(year_start, year_end, total_years)
            if self.current_vps_index == 0:
                # VPS 1: first half of years for both people
                assignments.append({
                    'person_index': 0,
                    'year_start': year_start,
                    'year_end': mid_year - 1 if total_years > 1 else year_start
                })
                assignments.append({
                    'person_index': 1,
                    'year_start': year_start,
                    'year_end': mid_year - 1 if total_years > 1 else year_start
                })
            else:
                # VPS 2: second half of years for both people
                assignments.append({
                    'person_index': 0,
                    'year_start': mid_year if total_years > 1 else year_start,
                    'year_end': year_end
                })
                assignments.append({
                    'person_index': 1,
                    'year_start': mid_year if total_years > 1 else year_start,
                    'year_end': year_end
                })
        else:
            # 3+ people: distribute people evenly, remaining person's year range is split
            # For 3 people: VPS1 gets person 1 (all years) + person 3 (first half)
            #              VPS2 gets person 2 (all years) + person 3 (second half)
            people_per_vps = num_people // self.num_vps
            remaining_people = num_people % self.num_vps
            last_person_idx = num_people - 1
            
            # Process each person
            for person_idx in range(num_people):
                if person_idx == last_person_idx and remaining_people > 0:
                    # Last person with odd count: split year range between both VPSs
                    mid_year = self._calculate_mid_year(year_start, year_end, total_years)
                    if self.current_vps_index == 0:
                        assignments.append({
                            'person_index': person_idx,
                            'year_start': year_start,
                            'year_end': mid_year - 1 if total_years > 1 else year_start
                        })
                    else:
                        assignments.append({
                            'person_index': person_idx,
                            'year_start': mid_year if total_years > 1 else year_start,
                            'year_end': year_end
                        })
                else:
                    # Regular person: assign to VPS based on index
                    # VPS 0 gets even indices, VPS 1 gets odd indices
                    assigned_vps = person_idx % self.num_vps
                    
                    if assigned_vps == self.current_vps_index:
                        # This person is assigned to current VPS, use full year range
                        assignments.append({
                            'person_index': person_idx,
                            'year_start': year_start,
                            'year_end': year_end
                        })
        
        return assignments
    
    def _calculate_mid_year(self, year_start: int, year_end: int, total_years: int) -> int:
        """Calculate the midpoint year for splitting."""
        if total_years <= 1:
            return year_start
        # For year ranges, split in the middle
        # If even number of years, split evenly
        # If odd, first VPS gets the extra year
        mid_point = total_years // 2
        return year_start + mid_point
    
    def get_assignment_for_person(self, person_index: int, year_start: int, year_end: int) -> Tuple[int, int]:
        """
        Get year range assignment for a specific person on current VPS.
        
        Args:
            person_index: Person index (0-based)
            year_start: Full year range start
            year_end: Full year range end (inclusive)
            
        Returns:
            Tuple of (assigned_year_start, assigned_year_end)
        """
        total_years = year_end - year_start + 1
        
        # Split year range in half
        mid_year = year_start + (total_years // 2)
        
        if self.current_vps_index == 0:
            # First VPS: first half
            return (year_start, mid_year - 1 if total_years > 1 else year_start)
        else:
            # Second VPS: second half
            return (mid_year if total_years > 1 else year_start, year_end)
