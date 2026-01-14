"""
Google Sheets Writer
Writes CURP search results to Google Sheets.
"""
import logging
from typing import List, Dict, Optional
import gspread
from google.oauth2.service_account import Credentials

logger = logging.getLogger(__name__)


class GoogleSheetsWriter:
    """Write results to Google Sheets."""
    
    def __init__(self, spreadsheet_id: str, credentials_file: str):
        """
        Initialize Google Sheets writer.
        
        Args:
            spreadsheet_id: Google Sheets spreadsheet ID
            credentials_file: Path to Google service account credentials JSON file
        """
        self.spreadsheet_id = spreadsheet_id
        self.credentials_file = credentials_file
        self.client = None
        self.spreadsheet = None
        
        # Authenticate
        try:
            scope = [
                'https://spreadsheets.google.com/feeds',
                'https://www.googleapis.com/auth/drive'
            ]
            creds = Credentials.from_service_account_file(credentials_file, scopes=scope)
            self.client = gspread.authorize(creds)
            self.spreadsheet = self.client.open_by_key(spreadsheet_id)
            logger.info(f"Successfully connected to Google Sheets: {spreadsheet_id}")
        except Exception as e:
            logger.error(f"Failed to authenticate with Google Sheets: {e}")
            raise
    
    def create_sheet_for_job(self, job_id: str, job_name: Optional[str] = None) -> gspread.Worksheet:
        """
        Create a new sheet/tab for a job.
        
        Args:
            job_id: Job ID
            job_name: Optional job name (defaults to job_id)
            
        Returns:
            Worksheet object
        """
        try:
            sheet_name = job_name or f"Job_{job_id}"
            
            # Check if sheet already exists
            try:
                worksheet = self.spreadsheet.worksheet(sheet_name)
                logger.info(f"Sheet '{sheet_name}' already exists, using existing sheet")
                return worksheet
            except gspread.exceptions.WorksheetNotFound:
                pass
            
            # Create new sheet
            worksheet = self.spreadsheet.add_worksheet(
                title=sheet_name,
                rows=1000,
                cols=20
            )
            logger.info(f"Created new sheet: {sheet_name}")
            return worksheet
            
        except Exception as e:
            logger.error(f"Error creating sheet for job {job_id}: {e}")
            raise
    
    def write_results(self, worksheet: gspread.Worksheet, results: List[Dict], 
                     summary_data: List[Dict], job_id: str, vps_index: Optional[int] = None):
        """
        Write results to Google Sheets.
        
        Args:
            worksheet: Worksheet to write to
            results: List of result dictionaries
            summary_data: Summary data
            job_id: Job ID
            vps_index: Optional VPS index (for multi-VPS scenarios)
        """
        try:
            # Clear existing content (in case of retry)
            worksheet.clear()
            
            # Write headers for results
            if results:
                headers = list(results[0].keys())
                worksheet.append_row(headers)
                
                # Write results data
                for result in results:
                    row = [result.get(col, '') for col in headers]
                    worksheet.append_row(row)
                
                logger.info(f"Wrote {len(results)} result rows to Google Sheets")
            
            # Add summary section
            if summary_data:
                # Add empty row
                worksheet.append_row([])
                worksheet.append_row(['Summary'])
                summary_headers = list(summary_data[0].keys())
                worksheet.append_row(summary_headers)
                
                for summary in summary_data:
                    row = [summary.get(col, '') for col in summary_headers]
                    worksheet.append_row(row)
                
                logger.info(f"Wrote {len(summary_data)} summary rows to Google Sheets")
            
            # Add metadata
            worksheet.append_row([])
            worksheet.append_row(['Metadata'])
            worksheet.append_row(['Job ID', job_id])
            if vps_index is not None:
                worksheet.append_row(['VPS Index', vps_index])
            
            # Format headers (make them bold)
            try:
                header_range = worksheet.range(1, 1, 1, len(headers) if results else 1)
                for cell in header_range:
                    cell.format = {'textFormat': {'bold': True}}
                worksheet.update_cells(header_range)
            except Exception as e:
                logger.warning(f"Could not format headers: {e}")
            
            logger.info(f"Successfully wrote results to Google Sheets for job {job_id}")
            
        except Exception as e:
            logger.error(f"Error writing to Google Sheets: {e}", exc_info=True)
            raise
    
    def append_results(self, worksheet: gspread.Worksheet, results: List[Dict]):
        """
        Append results to existing sheet (for multi-VPS scenarios).
        
        Args:
            worksheet: Worksheet to append to
            results: List of result dictionaries to append
        """
        try:
            if not results:
                return
            
            # Get existing headers
            existing_values = worksheet.get_all_values()
            if not existing_values:
                # No data yet, write headers and data
                headers = list(results[0].keys())
                worksheet.append_row(headers)
                for result in results:
                    row = [result.get(col, '') for col in headers]
                    worksheet.append_row(row)
            else:
                # Append data only (headers already exist)
                headers = existing_values[0]
                for result in results:
                    row = [result.get(col, '') for col in headers]
                    worksheet.append_row(row)
            
            logger.info(f"Appended {len(results)} result rows to Google Sheets")
            
        except Exception as e:
            logger.error(f"Error appending to Google Sheets: {e}", exc_info=True)
            raise
    
    def get_sheet_url(self, worksheet: gspread.Worksheet) -> str:
        """
        Get the URL for a specific worksheet.
        
        Args:
            worksheet: Worksheet object
            
        Returns:
            URL string
        """
        return f"https://docs.google.com/spreadsheets/d/{self.spreadsheet_id}/edit#gid={worksheet.id}"
