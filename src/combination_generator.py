"""
Combination Generator
Generates all combinations of dates, months, states, and years for CURP search.
"""
from typing import Iterator, Tuple, List, Optional
from itertools import product


# Complete list of 33 Mexican states/options
MEXICAN_STATES = [
    "Aguascalientes",
    "Baja California",
    "Baja California Sur",
    "Campeche",
    "Chiapas",
    "Chihuahua",
    "Coahuila",
    "Colima",
    "Durango",
    "Guanajuato",
    "Guerrero",
    "Hidalgo",
    "Jalisco",
    "Michoacán",
    "Morelos",
    "Nayarit",
    "Nuevo León",
    "Oaxaca",
    "Puebla",
    "Querétaro",
    "Quintana Roo",
    "San Luis Potosí",
    "Sinaloa",
    "Sonora",
    "Tabasco",
    "Tamaulipas",
    "Tlaxcala",
    "Veracruz",
    "Yucatán",
    "Zacatecas",
    "Ciudad de México",
    "Nacido en el extranjero"
]


class CombinationGenerator:
    """Generate combinations for CURP search with year-specific month boundaries."""
    
    def __init__(self, start_year: int, end_year: int, start_month: int = 1, end_month: int = 12,
                 start_year_month: int = None, end_year_month: int = None):
        """
        Initialize combination generator.
        
        Args:
            start_year: Starting year for birth year range
            end_year: Ending year for birth year range (inclusive)
            start_month: Starting month for birth month range (default: 1)
            end_month: Ending month for birth month range (default: 12, inclusive)
            start_year_month: Month to start from for start_year (overrides start_month for first year)
            end_year_month: Month to end at for end_year (overrides end_month for last year)
        """
        self.start_year = start_year
        self.end_year = end_year
        self.start_month = start_month
        self.end_month = end_month
        self.start_year_month = start_year_month if start_year_month is not None else start_month
        self.end_year_month = end_year_month if end_year_month is not None else end_month
        self.states = MEXICAN_STATES
        
        # Validate month range
        if start_month < 1 or start_month > 12:
            raise ValueError(f"start_month must be between 1 and 12, got {start_month}")
        if end_month < 1 or end_month > 12:
            raise ValueError(f"end_month must be between 1 and 12, got {end_month}")
        if self.start_year_month < 1 or self.start_year_month > 12:
            raise ValueError(f"start_year_month must be between 1 and 12, got {self.start_year_month}")
        if self.end_year_month < 1 or self.end_year_month > 12:
            raise ValueError(f"end_year_month must be between 1 and 12, got {self.end_year_month}")
        
        # Calculate total combinations
        days = 31  # 1-31
        states_count = len(self.states)
        years_count = end_year - start_year + 1
        
        # Calculate combinations per year
        total_combinations = 0
        for year in range(start_year, end_year + 1):
            if year == start_year:
                # First year: from start_year_month to 12
                year_months = 12 - self.start_year_month + 1
            elif year == end_year:
                # Last year: from 1 to end_year_month
                year_months = self.end_year_month
            else:
                # Middle years: all months
                year_months = 12
            
            total_combinations += days * year_months * states_count
        
        self.total_combinations = total_combinations
    
    def generate_combinations(self) -> Iterator[Tuple[int, int, str, int]]:
        """
        Generate all combinations of (day, month, state, year) with year-specific month boundaries.
        
        Yields:
            Tuple of (day, month, state_name, year)
        """
        days = range(1, 32)  # 1-31
        years = range(self.start_year, self.end_year + 1)
        
        # Generate combinations with year-specific month ranges
        for year in years:
            # Determine month range for this year
            if year == self.start_year:
                # First year: from start_year_month to 12
                months = range(self.start_year_month, 13)
            elif year == self.end_year:
                # Last year: from 1 to end_year_month
                months = range(1, self.end_year_month + 1)
            else:
                # Middle years: all months
                months = range(1, 13)
            
            # Use itertools.product for efficient combination generation
            for day, month, state in product(days, months, self.states):
                yield (day, month, state, year)
    
    def get_total_count(self) -> int:
        """Get total number of combinations."""
        return self.total_combinations
    
    def get_combination_by_index(self, index: int) -> Optional[Tuple[int, int, str, int]]:
        """
        Get a specific combination by index (for checkpoint resume).
        
        Args:
            index: Zero-based index of the combination
            
        Returns:
            Tuple of (day, month, state_name, year) or None if index out of range
        """
        if index < 0 or index >= self.total_combinations:
            return None
        
        days = list(range(1, 32))
        states_count = len(self.states)
        years = list(range(self.start_year, self.end_year + 1))
        
        # Iterate through years to find the right combination
        remaining_index = index
        for year in years:
            # Determine month range for this year
            if year == self.start_year:
                months = list(range(self.start_year_month, 13))
            elif year == self.end_year:
                months = list(range(1, self.end_year_month + 1))
            else:
                months = list(range(1, 13))
            
            year_combinations = len(days) * len(months) * states_count
            
            if remaining_index < year_combinations:
                # This combination is in this year
                day_idx = remaining_index // (len(months) * states_count)
                remaining = remaining_index % (len(months) * states_count)
                month_idx = remaining // states_count
                state_idx = remaining % states_count
                
                return (days[day_idx], months[month_idx], self.states[state_idx], year)
            
            remaining_index -= year_combinations
        
        return None
    
    def get_index_of_combination(self, day: int, month: int, state: str, year: int) -> Optional[int]:
        """
        Get the index of a specific combination.
        
        Args:
            day: Day of month (1-31)
            month: Month (1-12)
            state: State name
            year: Year
            
        Returns:
            Zero-based index or None if combination is invalid
        """
        if day < 1 or day > 31:
            return None
        if state not in self.states:
            return None
        if year < self.start_year or year > self.end_year:
            return None
        
        # Check if month is valid for this year
        if year == self.start_year:
            if month < self.start_year_month or month > 12:
                return None
        elif year == self.end_year:
            if month < 1 or month > self.end_year_month:
                return None
        else:
            if month < 1 or month > 12:
                return None
        
        days = list(range(1, 32))
        states_count = len(self.states)
        years_list = list(range(self.start_year, self.end_year + 1))
        
        # Calculate index by summing combinations before this year
        index = 0
        for y in years_list:
            if y == year:
                # Found the year, calculate position within this year
                if y == self.start_year:
                    months = list(range(self.start_year_month, 13))
                elif y == self.end_year:
                    months = list(range(1, self.end_year_month + 1))
                else:
                    months = list(range(1, 13))
                
                day_idx = days.index(day)
                month_idx = months.index(month)
                state_idx = self.states.index(state)
                
                index += (day_idx * len(months) * states_count +
                         month_idx * states_count +
                         state_idx)
                break
            else:
                # Add all combinations for this year
                if y == self.start_year:
                    year_months = 12 - self.start_year_month + 1
                elif y == self.end_year:
                    year_months = self.end_year_month
                else:
                    year_months = 12
                
                index += len(days) * year_months * states_count
        
        return index

