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
    """Generate combinations for CURP search."""
    
    def __init__(self, start_year: int, end_year: int, start_month: int = 1, end_month: int = 12):
        """
        Initialize combination generator.
        
        Args:
            start_year: Starting year for birth year range
            end_year: Ending year for birth year range (inclusive)
            start_month: Starting month for birth month range (default: 1)
            end_month: Ending month for birth month range (default: 12, inclusive)
        """
        self.start_year = start_year
        self.end_year = end_year
        self.start_month = start_month
        self.end_month = end_month
        self.states = MEXICAN_STATES
        
        # Validate month range
        if start_month < 1 or start_month > 12:
            raise ValueError(f"start_month must be between 1 and 12, got {start_month}")
        if end_month < 1 or end_month > 12:
            raise ValueError(f"end_month must be between 1 and 12, got {end_month}")
        if start_month > end_month:
            raise ValueError(f"start_month ({start_month}) must be <= end_month ({end_month})")
        
        # Calculate total combinations
        days = 31  # 1-31
        months = (end_month - start_month + 1)  # Month range
        states_count = len(self.states)
        years_count = end_year - start_year + 1
        
        self.total_combinations = days * months * states_count * years_count
    
    def generate_combinations(self) -> Iterator[Tuple[int, int, str, int]]:
        """
        Generate all combinations of (day, month, state, year).
        
        Yields:
            Tuple of (day, month, state_name, year)
        """
        days = range(1, 32)  # 1-31
        months = range(self.start_month, self.end_month + 1)  # Month range
        years = range(self.start_year, self.end_year + 1)
        
        # Use itertools.product for efficient combination generation
        for day, month, state, year in product(days, months, self.states, years):
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
        months = list(range(self.start_month, self.end_month + 1))
        years = list(range(self.start_year, self.end_year + 1))
        
        states_count = len(self.states)
        years_count = len(years)
        months_count = len(months)
        
        # Calculate indices
        day_idx = index // (months_count * states_count * years_count)
        remaining = index % (months_count * states_count * years_count)
        
        month_idx = remaining // (states_count * years_count)
        remaining = remaining % (states_count * years_count)
        
        state_idx = remaining // years_count
        year_idx = remaining % years_count
        
        return (days[day_idx], months[month_idx], self.states[state_idx], years[year_idx])
    
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
        if month < self.start_month or month > self.end_month:
            return None
        if state not in self.states:
            return None
        if year < self.start_year or year > self.end_year:
            return None
        
        days = list(range(1, 32))
        months = list(range(self.start_month, self.end_month + 1))
        years = list(range(self.start_year, self.end_year + 1))
        
        states_count = len(self.states)
        years_count = len(years)
        months_count = len(months)
        
        day_idx = days.index(day)
        month_idx = months.index(month)
        state_idx = self.states.index(state)
        year_idx = years.index(year)
        
        index = (day_idx * months_count * states_count * years_count +
                month_idx * states_count * years_count +
                state_idx * years_count +
                year_idx)
        
        return index

