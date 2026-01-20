"""
Result Validator
Extracts and validates CURP results from the website response.
"""
import re
from typing import Optional, Dict
from datetime import datetime


# CURP format: 18 characters (letters and numbers)
CURP_REGEX = re.compile(r'^[A-Z]{4}\d{6}[HM][A-Z]{5}[0-9A-Z]\d$')


class ResultValidator:
    """Validate and extract CURP information."""
    
    @staticmethod
    def is_valid_curp(curp: str) -> bool:
        """
        Validate CURP format (18 characters, standard pattern).
        
        Args:
            curp: CURP string to validate
            
        Returns:
            True if valid format, False otherwise
        """
        if not curp or not isinstance(curp, str):
            return False
        
        curp_clean = curp.strip().upper()
        
        # Check length
        if len(curp_clean) != 18:
            return False
        
        # Check regex pattern
        return bool(CURP_REGEX.match(curp_clean))
    
    @staticmethod
    def extract_curp_from_text(text: str) -> Optional[str]:
        """
        Extract CURP from text content (web page text).
        
        Args:
            text: Text content from web page
            
        Returns:
            CURP string if found, None otherwise
        """
        if not text:
            return None
        
        # Look for CURP pattern in text
        matches = CURP_REGEX.findall(text.upper())
        
        if matches:
            return matches[0]
        
        return None
    
    @staticmethod
    def extract_date_from_curp(curp: str) -> Optional[str]:
        """
        Extract birth date from CURP (positions 5-10: YYMMDD).
        
        Args:
            curp: Valid CURP string
            
        Returns:
            Date string in YYYY-MM-DD format or None
        """
        if not ResultValidator.is_valid_curp(curp):
            return None
        
        curp_clean = curp.strip().upper()
        
        # Extract date portion (characters 5-10: YYMMDD)
        year_2digit = curp_clean[4:6]
        month = curp_clean[6:8]
        day = curp_clean[8:10]
        
        # Determine full year (assuming 1900-2099 range)
        year = int(year_2digit)
        if year >= 0 and year <= 30:  # 2000-2030
            full_year = 2000 + year
        else:  # 1900-1999
            full_year = 1900 + year
        
        try:
            # Validate date
            date_obj = datetime(int(full_year), int(month), int(day))
            return date_obj.strftime('%Y-%m-%d')
        except ValueError:
            return None
    
    @staticmethod
    def extract_state_code_from_curp(curp: str) -> Optional[str]:
        """
        Extract state code from CURP (characters 12-13).
        
        Args:
            curp: Valid CURP string
            
        Returns:
            State code (2 characters) or None
        """
        if not ResultValidator.is_valid_curp(curp):
            return None
        
        curp_clean = curp.strip().upper()
        
        # State code is at positions 12-13 (0-indexed: 11-12)
        if len(curp_clean) >= 13:
            return curp_clean[11:13]
        
        return None
    
    @staticmethod
    def validate_result(html_content: str, expected_state: str = None) -> Dict:
        """
        Validate search result and extract CURP information.
        
        Args:
            html_content: HTML content from the search result page
            expected_state: Expected state name (for validation)
            
        Returns:
            Dictionary with validation result:
            {
                'valid': bool,
                'curp': str or None,
                'birth_date': str or None,
                'state_code': str or None,
                'found': bool
            }
        """
        result = {
            'valid': False,
            'curp': None,
            'birth_date': None,
            'state_code': None,
            'found': False
        }
        
        if not html_content:
            return result
        
        html_lower = html_content.lower()
        
        # Check for error modal (no match found) - check this FIRST before looking for results
        # The modal structure: <h4 class="modal-title">Aviso importante</h4> and "Los datos ingresados no son correctos"
        # But we need to make sure we don't have results table at the same time
        
        # Check for results table indicators first (more reliable)
        # Check for both CSS selector format and HTML attribute format
        has_results = (
            'dwnldLnk' in html_content or 
            '#dwnldLnk' in html_content or
            'id="dwnldLnk"' in html_content or
            'id=\'dwnldLnk\'' in html_content or
            'Descarga del CURP' in html_content or 
            'Datos del solicitante' in html_content or
            'panel-body' in html_content
        )
        
        # Check for error modal indicators
        has_error_modal = (
            'Aviso importante' in html_content or
            'los datos ingresados no son correctos' in html_lower or
            'warningmenssage' in html_lower or
            'id="warningMenssage"' in html_content
        )
        
        # Only return no match if we have error modal AND no results
        if has_error_modal and not has_results:
            result['found'] = False
            return result
        
        # If we have results, continue to extract CURP (ignore error modal if it exists)
        
        # Check for results table (match found)
        # Multiple patterns to catch different HTML structures
        import re
        
        # Pattern 1: Exact structure from the website
        # <td style="font-weight: 700; ...">CURP:</td> followed by <td style="text-transform: uppercase;">CURP_VALUE</td>
        curp_patterns = [
            # Exact match for the actual HTML structure (handles semicolon in style)
            r'<td[^>]*>\s*CURP:\s*</td>\s*<td[^>]*style="[^"]*text-transform:\s*uppercase[^";]*"[^>]*>([A-Z0-9]{18})</td>',
            # More flexible: CURP: in td, then any td with uppercase style (handles semicolon)
            r'CURP:\s*</td>\s*<td[^>]*style="[^"]*text-transform:\s*uppercase[^";]*"[^>]*>([A-Z0-9]{18})</td>',
            # Pattern matching exact structure from user's HTML example
            r'CURP:\s*</td>\s*<td[^>]*style="text-transform:\s*uppercase;">([A-Z0-9]{18})</td>',
            # Even more flexible: any td with CURP: followed by td with CURP
            r'<td[^>]*>CURP:\s*</td>\s*<td[^>]*>([A-Z0-9]{18})</td>',
            # Pattern with newlines and whitespace (actual HTML structure)
            r'CURP:\s*</td>\s*\s*<td[^>]*style="text-transform:\s*uppercase;">([A-Z0-9]{18})</td>',
            # Fallback: any td containing CURP: followed by td with 18-char alphanumeric
            r'CURP:.*?</td>\s*<td[^>]*>([A-Z0-9]{18})</td>',
            # Very flexible: find 18-char alphanumeric after "CURP:" text
            r'CURP:[^<]*</td>[^<]*<td[^>]*>([A-Z0-9]{18})</td>',
            # Most flexible: find CURP: anywhere, then look for 18-char pattern in next 200 chars
            r'CURP:[^<]*</td>[^<]*<td[^>]*>([A-Z]{4}\d{6}[HM][A-Z]{5}[0-9A-Z]\d)</td>',
        ]
        
        curp = None
        for pattern in curp_patterns:
            curp_match = re.search(pattern, html_content, re.IGNORECASE | re.DOTALL | re.MULTILINE)
            if curp_match:
                potential_curp = curp_match.group(1).strip().upper()
                # Validate it's actually a CURP (18 chars, alphanumeric, valid format)
                if len(potential_curp) == 18 and potential_curp.isalnum() and ResultValidator.is_valid_curp(potential_curp):
                    curp = potential_curp
                    break
        
        # If still not found, try a more aggressive search: look for any 18-char alphanumeric near "CURP:"
        if not curp:
            # Find all positions where "CURP:" appears
            curp_label_positions = [m.start() for m in re.finditer(r'CURP:\s*</td>', html_content, re.IGNORECASE)]
            for pos in curp_label_positions:
                # Look in the next 500 characters for a CURP pattern
                search_area = html_content[pos:pos+500]
                # Look for <td> followed by 18 alphanumeric chars
                td_curp_match = re.search(r'<td[^>]*>([A-Z0-9]{18})</td>', search_area, re.IGNORECASE)
                if td_curp_match:
                    potential_curp = td_curp_match.group(1).strip().upper()
                    if ResultValidator.is_valid_curp(potential_curp):
                        curp = potential_curp
                        break
        
        if curp:
            result['found'] = True
            result['valid'] = True
            result['curp'] = curp
            result['birth_date'] = ResultValidator.extract_date_from_curp(curp)
            result['state_code'] = ResultValidator.extract_state_code_from_curp(curp)
            
            # Try to extract birth date from the table if available
            # Multiple patterns for date extraction (matching actual HTML structure)
            date_patterns = [
                # Exact structure: Fecha de nacimiento: ... </td> followed by <td>DD/MM/YYYY</td>
                r'<td[^>]*>\s*Fecha de nacimiento:[^<]*</td>\s*<td[^>]*style="[^"]*text-transform:\s*uppercase[^"]*"[^>]*>(\d{2}/\d{2}/\d{4})</td>',
                r'Fecha de nacimiento:[^<]*</td>\s*<td[^>]*style="text-transform:\s*uppercase;">(\d{2}/\d{2}/\d{4})</td>',
                r'<td[^>]*>\s*Fecha de nacimiento:[^<]*</td>\s*<td[^>]*>(\d{2}/\d{2}/\d{4})</td>',
                r'Fecha de nacimiento:.*?</td>\s*<td[^>]*>(\d{2}/\d{2}/\d{4})</td>',
                r'Fecha de nacimiento.*?(\d{2}/\d{2}/\d{4})',
            ]
            
            for date_pattern in date_patterns:
                date_match = re.search(date_pattern, html_content, re.IGNORECASE | re.DOTALL | re.MULTILINE)
                if date_match:
                    date_str = date_match.group(1)
                    # Convert DD/MM/YYYY to YYYY-MM-DD
                    try:
                        from datetime import datetime
                        date_obj = datetime.strptime(date_str, '%d/%m/%Y')
                        result['birth_date'] = date_obj.strftime('%Y-%m-%d')
                        break
                    except:
                        pass
            
            # Extract state from table if available
            state_patterns = [
                # Exact structure: Entidad de nacimiento: ... </td> followed by <td>STATE</td>
                r'<td[^>]*>\s*Entidad de nacimiento:[^<]*</td>\s*<td[^>]*style="[^"]*text-transform:\s*uppercase[^"]*"[^>]*>([^<]+)</td>',
                r'Entidad de nacimiento:[^<]*</td>\s*<td[^>]*style="text-transform:\s*uppercase;">([^<]+)</td>',
                r'<td[^>]*>\s*Entidad de nacimiento:[^<]*</td>\s*<td[^>]*>([^<]+)</td>',
                r'Entidad de nacimiento:.*?</td>\s*<td[^>]*>([^<]+)</td>',
            ]
            
            for state_pattern in state_patterns:
                state_match = re.search(state_pattern, html_content, re.IGNORECASE | re.DOTALL | re.MULTILINE)
                if state_match:
                    state_name = state_match.group(1).strip()
                    # Store the state name found in results
                    result['state_name'] = state_name
                    break
        
        # Fallback: try to extract CURP from anywhere in the HTML if not found in table
        # This is important because the HTML structure might vary
        if not result['found']:
            # First try regex extraction from HTML text (more flexible)
            curp_in_text = ResultValidator.extract_curp_from_text(html_content)
            if curp_in_text and ResultValidator.is_valid_curp(curp_in_text):
                # Additional check: make sure it's in a context that suggests it's a result
                # Look for nearby indicators like "CURP" or download link
                curp_lower = html_content.lower()
                curp_index = curp_lower.find(curp_in_text.lower())
                if curp_index >= 0:
                    # Check surrounding context (200 chars before and after)
                    context_start = max(0, curp_index - 200)
                    context_end = min(len(html_content), curp_index + 200)
                    context = html_content[context_start:context_end].lower()
                    
                    # If context contains result indicators, it's likely a match
                    result_indicators = ['curp:', 'descarga', 'download', 'dwnldlnk', 'panel-body', 'datos del solicitante']
                    if any(indicator in context for indicator in result_indicators):
                        result['found'] = True
                        result['valid'] = True
                        result['curp'] = curp_in_text
                        result['birth_date'] = ResultValidator.extract_date_from_curp(curp_in_text)
                        result['state_code'] = ResultValidator.extract_state_code_from_curp(curp_in_text)
        
        return result

