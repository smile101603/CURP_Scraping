"""
Test script for specific date: 1977/12/09
This script tests the CURP search for a specific date combination.
"""
import sys
import os
from pathlib import Path

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from browser_automation import BrowserAutomation
from result_validator import ResultValidator
from state_codes import get_state_code
from excel_handler import ExcelHandler
from datetime import datetime
import json

def test_specific_date():
    """Test search for 1977/12/09 across all states."""
    
    # Load configuration
    config_path = Path("./config/settings.json")
    if config_path.exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
    else:
        config = {}
    
    # Get browser settings
    headless = config.get('browser', {}).get('headless', False)
    min_delay = config.get('delays', {}).get('min_seconds', 0.5)
    max_delay = config.get('delays', {}).get('max_seconds', 1.0)
    output_dir = config.get('output_dir', './web/Result')
    
    # Initialize Excel handler
    excel_handler = ExcelHandler(output_dir=output_dir)
    
    # Test parameters
    first_name = "Eduardo"
    last_name_1 = "Basich"
    last_name_2 = "Muguiro"
    gender = "H"
    day = 9
    month = 12
    year = 1977
    
    # All Mexican states
    states = [
        "Aguascalientes", "Baja California", "Baja California Sur", "Campeche",
        "Chiapas", "Chihuahua", "Coahuila", "Colima", "Durango", "Guanajuato",
        "Guerrero", "Hidalgo", "Jalisco", "Michoacán", "Morelos", "Nayarit",
        "Nuevo León", "Oaxaca", "Puebla", "Querétaro", "Quintana Roo",
        "San Luis Potosí", "Sinaloa", "Sonora", "Tabasco", "Tamaulipas",
        "Tlaxcala", "Veracruz", "Yucatán", "Zacatecas", "Ciudad de México",
        "Nacido en el extranjero"
    ]
    
    print(f"Testing CURP search for:")
    print(f"  Name: {first_name} {last_name_1} {last_name_2}")
    print(f"  Gender: {gender}")
    print(f"  Date: {day:02d}/{month:02d}/{year}")
    print(f"  Testing all {len(states)} states...")
    print()
    
    # Initialize browser
    browser = BrowserAutomation(
        headless=headless,
        min_delay=min_delay,
        max_delay=max_delay
    )
    
    validator = ResultValidator()
    matches_found = []
    
    try:
        # Start browser
        print("Starting browser...")
        browser.start_browser()
        print("Browser started successfully!")
        print()
        
        # Test each state
        for i, state in enumerate(states, 1):
            print(f"[{i}/{len(states)}] Testing {state}...")
            
            try:
                # Search for CURP
                result_content = browser.search_curp(
                    first_name=first_name,
                    last_name_1=last_name_1,
                    last_name_2=last_name_2,
                    gender=gender,
                    day=day,
                    month=month,
                    state=state,
                    year=year
                )
                
                # Debug: Check if content was returned
                if result_content:
                    # Debug: Check for match indicators in content
                    has_download_link = ('dwnldLnk' in result_content or '#dwnldLnk' in result_content or 
                                        'Descarga del CURP' in result_content or 
                                        'Datos del solicitante' in result_content)
                    
                    if has_download_link:
                        print(f"  [DEBUG] Match indicators found in content!")
                    
                    # Validate result
                    validation_result = validator.validate_result(result_content)
                    
                    # Debug: Print validation result details
                    if validation_result:
                        print(f"  [DEBUG] Validation result: found={validation_result.get('found')}, valid={validation_result.get('valid')}, curp={validation_result.get('curp')}")
                    
                    if validation_result and validation_result.get('curp'):
                        curp = validation_result['curp']
                        birth_date = validation_result.get('birth_date', 'N/A')
                        birth_state = validation_result.get('birth_state', state)  # Use state if not found
                        
                        match_info = {
                            'state': state,
                            'curp': curp,
                            'birth_date': birth_date,
                            'birth_state': birth_state
                        }
                        matches_found.append(match_info)
                        
                        print(f"  ✓ MATCH FOUND!")
                        print(f"    CURP: {curp}")
                        print(f"    Birth Date: {birth_date}")
                        print(f"    Birth State: {birth_state}")
                    else:
                        # Debug: Save content to file for inspection
                        if has_download_link:
                            debug_file = f"debug_jalisco_content.html"
                            with open(debug_file, 'w', encoding='utf-8') as f:
                                f.write(result_content)
                            print(f"  ✗ No match found (but match indicators present!)")
                            print(f"  [DEBUG] Content saved to {debug_file} for inspection")
                        else:
                            print(f"  ✗ No match found")
                else:
                    print(f"  ✗ No match found (no content returned)")
                    
            except Exception as e:
                print(f"  ✗ Error: {e}")
            
            print()
        
        # Summary
        print("=" * 60)
        print("TEST SUMMARY")
        print("=" * 60)
        print(f"Total states tested: {len(states)}")
        print(f"Matches found: {len(matches_found)}")
        print()
        
        if matches_found:
            print("MATCHES FOUND:")
            for match in matches_found:
                print(f"  - {match['state']}: {match['curp']} ({match['birth_date']})")
            
            # Save results to Excel
            print()
            print("Saving results to Excel...")
            
            # Format results for Excel
            results_data = []
            for i, match in enumerate(matches_found, 1):
                results_data.append({
                    'person_id': 1,
                    'first_name': first_name,
                    'last_name_1': last_name_1,
                    'last_name_2': last_name_2,
                    'gender': gender,
                    'curp': match['curp'],
                    'birth_date': match['birth_date'],
                    'birth_state': match['state'],
                    'match_number': i
                })
            
            # Create summary
            summary_data = [{
                'person_id': 1,
                'first_name': first_name,
                'last_name_1': last_name_1,
                'last_name_2': last_name_2,
                'total_matches': len(matches_found)
            }]
            
            # Generate filename with timestamp
            timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M")
            output_filename = f"test_results_{timestamp}.xlsx"
            
            # Save to Excel
            result_path = excel_handler.write_results(results_data, summary_data, output_filename)
            print(f"Results saved to: {result_path}")
        else:
            print("No matches found for this date combination.")
        
    except Exception as e:
        print(f"Error during test: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Close browser
        print()
        print("Closing browser...")
        browser.close_browser()
        print("Test completed!")


if __name__ == "__main__":
    test_specific_date()
