"""
Excel Input/Output Handler
Handles reading input Excel files and writing results to Excel format.
"""
import pandas as pd
import os
from pathlib import Path
from typing import List, Dict, Optional


class ExcelHandler:
    """Handle Excel file operations for CURP automation."""
    
    def __init__(self, input_dir: str = "./data", output_dir: str = "./data/results"):
        """
        Initialize Excel handler.
        
        Args:
            input_dir: Directory containing input Excel files
            output_dir: Directory for output Excel files
        """
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def read_input(self, filename: str) -> pd.DataFrame:
        """
        Read input Excel file with person data.
        
        Expected columns: first_name, last_name_1, last_name_2, gender
        
        Args:
            filename: Name of the Excel file (can be relative or absolute path)
            
        Returns:
            DataFrame with person data
        """
        # Check if filename is already an absolute path or contains directory separators
        file_path_obj = Path(filename)
        if file_path_obj.is_absolute() or '/' in filename or '\\' in filename:
            # It's already a full path, use it directly
            file_path = file_path_obj
        else:
            # It's just a filename, prepend input_dir
            file_path = self.input_dir / filename
        
        if not file_path.exists():
            raise FileNotFoundError(f"Input file not found: {file_path}")
        
        # Read Excel file
        df = pd.read_excel(file_path, engine='openpyxl')
        
        # Validate columns
        required_columns = ['first_name', 'last_name_1', 'last_name_2', 'gender']
        missing_columns = [col for col in required_columns if col not in df.columns]
        
        if missing_columns:
            raise ValueError(f"Missing required columns: {missing_columns}")
        
        # Normalize gender (H/M)
        df['gender'] = df['gender'].astype(str).str.upper().str.strip()
        df['gender'] = df['gender'].replace({'HOMBRE': 'H', 'MUJER': 'M', 'MALE': 'H', 'FEMALE': 'M'})
        
        # Validate gender values
        invalid_genders = df[~df['gender'].isin(['H', 'M'])]['gender'].unique()
        if len(invalid_genders) > 0:
            raise ValueError(f"Invalid gender values found: {invalid_genders}. Expected 'H' or 'M'.")
        
        # Fill NaN values with empty string for string columns
        for col in ['first_name', 'last_name_1', 'last_name_2']:
            df[col] = df[col].fillna('').astype(str).str.strip()
        
        # Add person ID if not present
        if 'person_id' not in df.columns:
            df.insert(0, 'person_id', range(1, len(df) + 1))
        
        return df
    
    def create_template(self, filename: str = "input_template.xlsx"):
        """
        Create a template Excel file with required columns.
        
        Args:
            filename: Name of the template file
        """
        template_data = {
            'first_name': ['Eduardo', 'María'],
            'last_name_1': ['Basich', 'González'],
            'last_name_2': ['Muguiro', 'López'],
            'gender': ['H', 'M']
        }
        
        df = pd.DataFrame(template_data)
        file_path = self.input_dir / filename
        df.to_excel(file_path, index=False, engine='openpyxl')
        print(f"Template created at: {file_path}")
    
    def write_results(self, results: List[Dict], summary: List[Dict], 
                     output_filename: str = "curp_results.xlsx"):
        """
        Write results to Excel file with two sheets: Results and Summary.
        
        Args:
            results: List of dictionaries with match results
            summary: List of dictionaries with summary per person
            output_filename: Name of the output Excel file
        """
        output_path = self.output_dir / output_filename
        
        # Create DataFrames
        results_df = pd.DataFrame(results)
        summary_df = pd.DataFrame(summary)
        
        # Write to Excel with multiple sheets
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            results_df.to_excel(writer, sheet_name='Results', index=False)
            summary_df.to_excel(writer, sheet_name='Summary', index=False)
        
        print(f"Results saved to: {output_path}")
        return output_path
    
    def append_result(self, results: List[Dict], output_filename: str = "curp_results.xlsx"):
        """
        Append results to existing Excel file (for incremental saves).
        
        Args:
            results: List of dictionaries with match results
            output_filename: Name of the output Excel file
        """
        output_path = self.output_dir / output_filename
        
        if output_path.exists():
            # Read existing results
            existing_df = pd.read_excel(output_path, sheet_name='Results', engine='openpyxl')
            new_df = pd.DataFrame(results)
            combined_df = pd.concat([existing_df, new_df], ignore_index=True)
        else:
            combined_df = pd.DataFrame(results)
        
        # Re-read summary or create new
        if output_path.exists():
            try:
                summary_df = pd.read_excel(output_path, sheet_name='Summary', engine='openpyxl')
            except:
                summary_df = pd.DataFrame()
        else:
            summary_df = pd.DataFrame()
        
        # Write combined results
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            combined_df.to_excel(writer, sheet_name='Results', index=False)
            if not summary_df.empty:
                summary_df.to_excel(writer, sheet_name='Summary', index=False)
        
        return output_path

