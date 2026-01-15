# CURP Automation Tool

Automated tool for searching Mexican CURP (Clave Única de Registro de Población) on the official government portal (gob.mx/curp/) using controlled browser automation.

## Overview

This tool reads personal data from an Excel file, generates combinations of birth dates, months, states, and years, and performs controlled searches on the official CURP portal to find valid CURP matches. Results are saved to an Excel file with found CURPs, birth dates, states, and summary statistics.

## Features

- **Web Frontend**: Modern HTML/JavaScript interface for easy interaction
- **REST API**: Flask-based API for programmatic access
- **Real-time Progress**: WebSocket-based live progress updates
- **Excel Input/Output**: Read input data from Excel and export results to Excel format
- **Combination Generation**: Automatically generates all combinations of dates (1-31), months (1-12), 33 states/options, and configurable year ranges
- **Controlled Browser Automation**: Uses Playwright for reliable browser automation with rate limiting
- **Checkpoint System**: Saves progress and allows resuming interrupted searches
- **Result Validation**: Validates and extracts CURP information from search results
- **Rate Limiting**: Configurable delays (2-5 seconds) with randomization to avoid detection
- **Error Handling**: Robust error handling for network issues, CAPTCHAs, and browser crashes
- **VPS Deployment Ready**: Designed for backend deployment on VPS with local frontend access

## Requirements

- Python 3.9 or higher
- Windows, macOS, or Linux

## Installation

1. **Clone or download this repository**

2. **Create a virtual environment (recommended):**
   ```bash
   python -m venv venv
   
   # On Windows:
   venv\Scripts\activate
   
   # On macOS/Linux:
   source venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Install Playwright browsers:**
   ```bash
   playwright install chromium
   ```

## Configuration

Edit `config/settings.json` to configure:

- **Year Range**: Set `start_year` and `end_year` for the birth year range to search
- **Delays**: Adjust `min_seconds` and `max_seconds` for delays between searches
- **Pause Settings**: Configure `pause_every_n` (pause frequency) and `pause_duration` (pause length in seconds)
- **Browser Mode**: Set `headless` to `true` or `false` (false shows browser window)
- **Paths**: Configure `output_dir`, `input_dir`, and `checkpoint_dir`
- **API Settings**: Configure server host, port, CORS, and SSL settings

Example configuration:
```json
{
  "year_range": {
    "start": 1950,
    "end": 1960
  },
  "delays": {
    "min_seconds": 2,
    "max_seconds": 5
  },
  "pause_every_n": 50,
  "pause_duration": 30,
  "browser": {
    "headless": false
  },
  "num_workers": 6,
  "output_dir": "./data/results",
  "input_dir": "./data",
  "checkpoint_dir": "./checkpoints",
  "api": {
    "port": 5000,
    "host": "0.0.0.0",
    "debug": false,
    "max_upload_size": 10,
    "cors_origins": ["*"],
    "ssl_enabled": false,
    "ssl_cert_path": "",
    "ssl_key_path": ""
  }
}
```

### API Configuration Options

- **port**: Server port (default: 5000)
- **host**: Server host (`0.0.0.0` for network access, `127.0.0.1` for local only)
- **debug**: Enable debug mode (default: false)
- **max_upload_size**: Maximum file upload size in MB (default: 10)
- **cors_origins**: Allowed CORS origins (`["*"]` for all, or specific domains)
- **ssl_enabled**: Enable HTTPS/WSS (default: false)
- **ssl_cert_path**: Path to SSL certificate file (if using HTTPS)
- **ssl_key_path**: Path to SSL key file (if using HTTPS)

## Usage

The tool can be used in two ways:
1. **Web Interface** (Recommended): Use the modern web frontend
2. **Command Line**: Use the original command-line interface

---

## Web Interface Usage

### 1. Start the API Server

First, start the Flask API server:

```bash
python app.py
```

The server will start on `http://0.0.0.0:5000` by default (configurable in `config/settings.json`).

### 2. Open the Frontend

Open `web/index.html` in your web browser. You can:
- Open it directly (file:// protocol)
- Or serve it with a simple HTTP server (optional)

### 3. Configure API Connection

In the frontend:
1. Enter your VPS API URL in the "API Configuration" field
   - For local testing: `http://localhost:5000`
   - For VPS: `http://your-vps-ip:5000` or `https://your-vps-domain.com`
2. The connection status will show "Connected" when ready

### 4. Upload Excel File

1. Click the upload area or drag and drop your Excel file
2. The file will be uploaded to the server
3. Verify the filename appears in the file info section

### 5. Set Year Range

Enter the start and end years for the search range.

### 6. Start Search

1. Click "Start Search" button
2. Monitor real-time progress in the dashboard:
   - Progress bar with percentage
   - Current person being processed
   - Current combination (day/month/year/state)
   - Matches found count
   - Estimated time remaining
3. Results are automatically saved as they're found

### 7. Download Results

Once the search completes:
1. Click "Download Results" to get the Excel file
2. Or download from the Job History section

### 8. Job Management

- View all jobs in the "Job History" section
- Download results from completed jobs
- Monitor job status (pending, running, completed, failed)

---

## Command Line Usage

### 1. Prepare Input Excel File

The input Excel file should have the following columns:
- `first_name`: First name(s) (can be one or two names)
- `last_name_1`: First last name
- `last_name_2`: Second last name
- `gender`: Gender (`H` for Hombre/Male or `M` for Mujer/Female)

Example:
| first_name | last_name_1 | last_name_2 | gender |
|------------|-------------|-------------|--------|
| Eduardo    | Basich      | Muguiro     | H      |
| María      | González    | López       | M      |

**Note**: If no input file exists, the script will create a template file (`input_template.xlsx`) that you can fill with your data.

### 2. Run the Script

```bash
python src/main.py [input_filename.xlsx]
```

If no filename is provided, it will look for `input.xlsx` in the `data` directory.

Example:
```bash
python src/main.py input_file.xlsx
```

### 3. Monitor Progress

The script will:
- Display progress in the console
- Log activities to `logs/curp_automation.log`
- Save checkpoints periodically (every 100 combinations)
- Show match notifications when CURPs are found

### 4. View Results

Results are saved to the `data/results` directory with a timestamp:
- `curp_results_YYYYMMDD_HHMMSS.xlsx`

The Excel file contains two sheets:

**Results Sheet**: All found matches with:
- Person ID, name, gender
- Found CURP
- Birth date
- Birth state
- Match number

**Summary Sheet**: Summary per person with:
- Person ID, name
- Total matches found

### 5. Resume Interrupted Search

If the script is interrupted (Ctrl+C) or crashes:
- A checkpoint is automatically saved
- Simply run the script again with the same input file
- It will automatically resume from the last position
- To start fresh, delete the checkpoint file in the `checkpoints` directory

## Timing Configuration

This section documents all timing elements and delays used in the search process. These can be adjusted in `src/browser_automation.py` and `config/settings.json`.

### 1. Initial Browser Setup (One-time per browser session)

- **Page load wait**: `3.0` seconds (after navigating to CURP portal)
- **Tab switch delay**: `0.7` seconds (when clicking "Datos Personales" tab)
- **Navigation timeout**: `90000` ms (90 seconds) for page load operations

### 2. Form Filling Delays (Per Search)

Each form field has specific delays to simulate human behavior:

| Field | Typing Delay | Thinking Delay | Total Range |
|-------|-------------|----------------|-------------|
| First Name | 0.15-0.4s (random) | 0.2-0.5s (random) | ~0.35-0.9s |
| First Last Name | 0.15-0.4s (random) | 0.2-0.5s (random) | ~0.35-0.9s |
| Second Last Name | 0.15-0.4s (random) | 0.3-0.7s (random) | ~0.45-1.1s |
| Day (dropdown) | - | 0.4-0.8s (random) | ~0.4-0.8s |
| Month (dropdown) | - | 0.4-0.8s (random) | ~0.4-0.8s |
| Year (input) | 0.15-0.4s (random) | 0.3-0.6s (random) | ~0.45-1.0s |
| Gender (dropdown) | - | 0.3-0.7s (random) | ~0.3-0.7s |
| State (dropdown) | - | 0.5-1.2s (random) | ~0.5-1.2s |
| Pre-submit review | - | 0.8-1.5s (random) | ~0.8-1.5s |

**Total Form Filling Time**: Approximately `3.5-7.0` seconds per search

### 3. Form Submission (Per Search)

- **After clicking submit**: `1.0-2.0` seconds (random delay)
- **Fallback method delays**: `0.5-1.0` seconds (if alternative submission methods are used)
- **Field operation timeout**: `5000` ms (5 seconds) per form field

### 4. Waiting for Results (Per Search)

- **Maximum wait timeout**: `20.0` seconds (waits for result or error modal)
- **After detecting result/modal**: `1.0` seconds (fixed, ensures content is loaded)
- **Content stability check**: `0.5` seconds (fixed, verifies DOM stability)
- **Check interval**: `0.3-0.8` seconds (random, polling interval)
- **Error retry delay**: `0.5` seconds (fixed, on error during wait)
- **Post-result reading delay**: `0.5-1.0` seconds (random, after getting results)

**Total Wait Time**: `~1.5-20.0` seconds (depends on server response speed)

### 5. Modal Closing (Per No-Match Result)

- **After closing modal**: `0.6` seconds (fixed delay)

### 6. Post-Search Delays (Per Search)

- **Random delay between searches**: `1-2` seconds (configurable in `config/settings.json`)
  - Default: `min_seconds: 1`, `max_seconds: 2`

### 7. Periodic Pauses

- **Pause frequency**: Every `75` searches (configurable in `config/settings.json`)
- **Pause duration**: `15` seconds (configurable in `config/settings.json`)

### 8. Error Recovery Delays

- **Recovery form filling**: `0.1` seconds per field (fixed, faster during recovery)
- **Recovery form submission**: `1.0-2.0` seconds (random delay)
- **Page reload wait**: `3.0` seconds (fixed, when reloading due to errors)
- **Tab switch after reload**: `0.7` seconds (fixed)

### 9. Page Reload (On Match/Timeout/Error)

- **Page reload wait**: `3.0` seconds (fixed, after reloading page)
- **Tab switch after reload**: `0.7` seconds (fixed, to return to form)

---

### Timing Summary

**Best Case Scenario (Fast Server Response)**:
- Form filling: `~3.5s`
- Submission: `~1.0s`
- Wait for results: `~1.5s`
- Modal close (if no match): `~0.6s`
- Random delay: `~1.0s`
- **Total: ~7.6 seconds per search**

**Worst Case Scenario (Slow Server Response)**:
- Form filling: `~7.0s`
- Submission: `~2.0s`
- Wait for results: `~20.0s` (timeout)
- Modal close: `~0.6s`
- Random delay: `~2.0s`
- **Total: ~31.6 seconds per search**

**Average Case**:
- **Approximately: ~15-20 seconds per search**

---

### Configuration Files

**Timing settings in `config/settings.json`**:
```json
{
  "delays": {
    "min_seconds": 1,      // Minimum delay between searches
    "max_seconds": 2       // Maximum delay between searches
  },
  "pause_every_n": 75,     // Pause every N searches
  "pause_duration": 15     // Pause duration in seconds
}
```

**Timing settings in `src/browser_automation.py`**:
- Form filling delays (lines 502-543)
- Submission delays (lines 553-584)
- Wait for results timeout (line 651)
- Modal closing delay (line 178)
- Page load waits (multiple locations)

**Note**: Adjusting these values may affect detection risk. Reducing delays too much may increase the chance of being blocked by the portal.

## Performance Expectations

- **Search Rate**: Approximately 3-8 searches per minute (depending on server response time)
- **Time per Person**: For a 10-year range:
  - Total combinations: ~122,760 per person
  - Estimated time: ~255-409 hours per person (at 15-20 seconds per search average)
  
**Important**: This is intentionally slow to avoid getting blocked by the portal. Adjust delays at your own risk.

## Testing Strategy

Before running full searches, test with:
1. **1 person, 1 year, 1 state**: Verify the automation works
2. **1 person, 1 year, all states**: Test state selection
3. **1 person, 10 years, 1 state**: Test year range
4. **Gradually scale up**: Only run full searches after confirming everything works

## States Supported

The tool searches all 33 options:
- 32 Mexican states
- "Nacido en el extranjero" (Born abroad)

Complete list: Aguascalientes, Baja California, Baja California Sur, Campeche, Chiapas, Chihuahua, Coahuila, Colima, Durango, Guanajuato, Guerrero, Hidalgo, Jalisco, Michoacán, Morelos, Nayarit, Nuevo León, Oaxaca, Puebla, Querétaro, Quintana Roo, San Luis Potosí, Sinaloa, Sonora, Tabasco, Tamaulipas, Tlaxcala, Veracruz, Yucatán, Zacatecas, Ciudad de México, Nacido en el extranjero

## API Endpoints

The API provides the following endpoints:

- `GET /api/health` - Health check
- `POST /api/upload` - Upload Excel file
- `POST /api/start` - Start search job
- `GET /api/status/<job_id>` - Get job status
- `GET /api/jobs` - List all jobs
- `GET /api/download/<job_id>` - Download results
- `POST /api/cancel/<job_id>` - Cancel a job

### WebSocket Events

- `connect` - Client connects
- `subscribe_job` - Subscribe to job progress
- `progress_update` - Real-time progress updates
- `job_complete` - Job completion notification
- `job_error` - Error notification

## Troubleshooting

### API Server Issues

**Server won't start:**
- Check if port 5000 is already in use
- Verify all dependencies are installed: `pip install -r requirements.txt`
- Check logs in `logs/api.log`

**CORS errors:**
- Update `cors_origins` in `config/settings.json`
- For development, use `["*"]` to allow all origins
- For production, specify exact domains

**WebSocket connection fails:**
- Ensure firewall allows WebSocket connections
- Check if using HTTPS/WSS for secure connections
- Verify Socket.IO client library is loaded in frontend

### Frontend Issues

**Can't connect to API:**
- Verify API server is running
- Check API URL in `web/config.js` or frontend input field
- Ensure CORS is properly configured
- Check browser console for errors

**File upload fails:**
- Verify file is Excel format (.xlsx or .xls)
- Check file size (max 10MB by default)
- Ensure API server is accessible

**Progress not updating:**
- Check WebSocket connection status
- Verify job subscription is active
- Check browser console for WebSocket errors

### CAPTCHA Detected
- If CAPTCHA appears, the script will pause and prompt you to solve it manually
- Press Enter after solving to continue

### Browser Issues
- If browser fails to start, ensure Playwright browsers are installed: `playwright install chromium`
- Try running with `headless: false` to see what's happening

### Form Field Issues
- The website structure may change. If searches fail, check the form field selectors in `src/browser_automation.py`
- You may need to inspect the website and update the selectors

### Network Errors
- Check your internet connection
- The script will retry, but persistent failures may require manual intervention

## Important Notes

⚠️ **Legal and Ethical Considerations**:
- This tool is for legitimate use cases only
- Respect the website's terms of service
- Do not abuse the system with excessive requests
- The rate limiting is intentionally conservative

⚠️ **No Guarantees**:
- The website structure may change, breaking the automation
- There is no official API, so this relies on web scraping
- Results depend on data available on the portal

## VPS Deployment

### Backend Deployment (VPS)

1. **Install Dependencies on VPS:**
   ```bash
   pip install -r requirements.txt
   playwright install chromium
   ```

2. **Configure Firewall:**
   - Open the API port (default: 5000)
   - For HTTPS, open port 443

3. **Set Up SSL (Recommended for Production):**
   - Use Let's Encrypt for free SSL certificates
   - Update `config/settings.json` with SSL paths
   - Set `ssl_enabled: true`

4. **Run with Gunicorn (Production):**
   ```bash
   gunicorn -c gunicorn_config.py app:app
   ```

5. **Or Use Systemd Service:**
   Create `/etc/systemd/system/curp-api.service`:
   ```ini
   [Unit]
   Description=CURP Automation API
   After=network.target

   [Service]
   User=your-user
   WorkingDirectory=/path/to/CURP_Scraping
   ExecStart=/path/to/venv/bin/gunicorn -c gunicorn_config.py app:app
   Restart=always

   [Install]
   WantedBy=multi-user.target
   ```

6. **Start Service:**
   ```bash
   sudo systemctl enable curp-api
   sudo systemctl start curp-api
   ```

### Frontend Configuration (Local)

1. **Update API URL:**
   - Edit `web/config.js`
   - Set `baseURL` to your VPS address:
     ```javascript
     baseURL: 'https://your-vps-domain.com:5000'
     ```

2. **Open Frontend:**
   - Simply open `web/index.html` in your browser
   - Or serve locally with: `python -m http.server 8000` (optional)

3. **Connect to VPS:**
   - Enter VPS API URL in the frontend configuration field
   - Connection status will show when connected

## Project Structure

```
CURP_Scraping/
├── src/
│   ├── __init__.py
│   ├── api/                        # Flask API module
│   │   ├── __init__.py             # Flask app initialization
│   │   ├── routes.py                # API endpoints
│   │   ├── websocket.py             # WebSocket handlers
│   │   ├── search_manager.py       # Job management
│   │   └── models.py               # Data models
│   ├── excel_handler.py            # Excel I/O operations
│   ├── combination_generator.py    # Generate date/state/year combos
│   ├── browser_automation.py      # Playwright automation
│   ├── result_validator.py         # Validate and extract CURPs
│   ├── checkpoint_manager.py      # Save/resume progress
│   ├── parallel_worker.py          # Parallel processing
│   ├── search_runner.py           # Search execution logic
│   ├── state_codes.py              # State name/code mapping
│   └── main.py                    # CLI orchestrator
├── web/                            # Frontend files
│   ├── index.html                 # Main HTML page
│   ├── config.js                  # API configuration
│   └── static/
│       ├── css/
│       │   └── style.css          # Styles
│       └── js/
│           ├── app.js             # Main application logic
│           └── websocket.js       # WebSocket client
├── data/
│   ├── uploads/                   # Uploaded files
│   ├── input_template.xlsx        # Input template
│   └── results/                   # Output directory
├── config/
│   └── settings.json              # Configuration
├── logs/                          # Log files
├── checkpoints/                   # Checkpoint files
├── app.py                         # API server entry point
├── gunicorn_config.py             # Production WSGI config
├── requirements.txt
├── README.md
└── .gitignore
```

## License

This project is provided as-is for educational and legitimate use purposes.

## Support

For issues or questions:
1. Check the logs in `logs/curp_automation.log`
2. Review the configuration in `config/settings.json`
3. Verify your input Excel file format
4. Test with a small subset first

## Development

### Running in Development Mode

1. **Start API Server:**
   ```bash
   python app.py
   ```

2. **Open Frontend:**
   - Open `web/index.html` in browser
   - Or use a local server: `cd web && python -m http.server 8000`

3. **Enable Debug Mode:**
   - Set `"debug": true` in `config/settings.json` API section
   - This enables Flask debug mode and detailed logging

### Testing

1. **Test API Endpoints:**
   ```bash
   # Health check
   curl http://localhost:5000/api/health
   
   # Upload file
   curl -X POST -F "file=@data/input_file.xlsx" http://localhost:5000/api/upload
   
   # Start search
   curl -X POST -H "Content-Type: application/json" \
     -d '{"filename":"input_file.xlsx","year_start":1970,"year_end":1980}' \
     http://localhost:5000/api/start
   ```

2. **Test WebSocket:**
   - Use browser console or WebSocket testing tools
   - Connect to `ws://localhost:5000/socket.io/`

---

**Version**: 2.0.0  
**Last Updated**: 2024

### Changelog

**v2.0.0** - Web Interface & API
- Added Flask REST API
- Added WebSocket support for real-time updates
- Added modern web frontend
- Added job management system
- Added VPS deployment support
- Improved progress tracking

**v1.0.0** - Initial Release
- Command-line interface
- Excel input/output
- Parallel processing
- Checkpoint system
