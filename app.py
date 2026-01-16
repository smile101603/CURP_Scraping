"""
Main Application Entry Point
Flask API server for CURP automation tool.
"""
import sys
import os
import json
import logging
from pathlib import Path

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

# Create necessary directories first
Path('logs').mkdir(exist_ok=True)
Path('data/uploads').mkdir(parents=True, exist_ok=True)
Path('data/results').mkdir(parents=True, exist_ok=True)
Path('checkpoints').mkdir(exist_ok=True)

# Configure logging with filter to suppress noisy errors
class WerkzeugErrorFilter(logging.Filter):
    """Filter out noisy Werkzeug errors from bots/scanners."""
    def filter(self, record):
        # Suppress "Bad request version" errors (from bots/scanners)
        if 'Bad request version' in str(record.getMessage()):
            return False
        # Suppress "write() before start response" errors (Werkzeug internal issues)
        if 'write() before start response' in str(record.getMessage()):
            return False
        return True

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/api.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

# Add filter to suppress noisy errors
werkzeug_logger = logging.getLogger('werkzeug')
werkzeug_logger.addFilter(WerkzeugErrorFilter())

logger = logging.getLogger(__name__)

# Import API app
from api import app, socketio

def load_config():
    """Load configuration from settings.json."""
    config_path = Path('./config/settings.json')
    if config_path.exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def main():
    """Run the Flask application."""
    try:
        config = load_config()
        api_config = config.get('api', {})
        
        port = api_config.get('port', 5000)
        host = api_config.get('host', '0.0.0.0')
        debug = api_config.get('debug', False)
        
        logger.info(f"Starting CURP Automation API server on {host}:{port}")
        logger.info(f"Debug mode: {debug}")
        
        # Run the application
        socketio.run(
            app,
            host=host,
            port=port,
            debug=debug,
            allow_unsafe_werkzeug=True  # For development
        )
    
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Error starting server: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
