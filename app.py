"""
Main Application Entry Point
Flask API server for CURP automation tool.
"""
import sys
import os
import json
import logging
import time
import threading
from pathlib import Path
from datetime import datetime

# Add src directory to path
src_path = str(Path(__file__).parent / 'src')
if src_path not in sys.path:
    sys.path.insert(0, src_path)

# Create necessary directories first
Path('logs').mkdir(exist_ok=True)
Path('data/uploads').mkdir(parents=True, exist_ok=True)
Path('data/results').mkdir(parents=True, exist_ok=True)
Path('checkpoints').mkdir(exist_ok=True)

# Configure logging with filter to suppress noisy errors
class WerkzeugErrorFilter(logging.Filter):
    """Filter out noisy Werkzeug errors from bots/scanners."""
    def filter(self, record):
        message = str(record.getMessage())
        
        # Suppress "Bad request version" errors (from bots/scanners)
        if 'Bad request version' in message:
            return False
        
        # Suppress "write() before start response" errors (Werkzeug internal issues)
        if 'write() before start response' in message:
            return False
        
        # Suppress AssertionError from werkzeug serving (WebSocket upgrade issues)
        if 'AssertionError' in message and 'write() before start' in message:
            return False
        
        # Suppress WebSocket upgrade errors (harmless, already handled by SocketIO)
        if 'upgrade to websocket' in message.lower() and 'error' in message.lower():
            return False
        
        # Suppress common bot/scanner 404 requests (reduce log noise)
        # These are harmless probes looking for vulnerabilities
        bot_patterns = [
            '/cgi-bin/',
            '/solr/',
            '/v2/_cata',
            '/admin/',
            '/wp-admin/',
            '/phpmyadmin/',
            '/.env',
            '/.git/',
            '/favicon.ico',  # Common but harmless
            '/robots.txt',   # Common but harmless
        ]
        
        # Check if this is a 404 request to a known bot pattern
        if '"GET ' in message or '"POST ' in message:
            for pattern in bot_patterns:
                if pattern in message and ('404' in message or ' 404 ' in message):
                    return False  # Suppress bot/scanner 404 requests
        
        # Suppress malformed HTTP version requests (HTTP/I.1 instead of HTTP/1.1)
        if 'HTTP/I.' in message or 'HTTP/O.' in message:
            return False
        
        return True

# Enhanced logging configuration for headless operation
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    handlers=[
        logging.FileHandler('logs/api.log', encoding='utf-8'),
        logging.FileHandler('logs/server.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

# Add filter to suppress noisy errors
werkzeug_logger = logging.getLogger('werkzeug')
werkzeug_logger.addFilter(WerkzeugErrorFilter())

# Also suppress AssertionError from werkzeug (WebSocket upgrade issues)
werkzeug_serving_logger = logging.getLogger('werkzeug.serving')
werkzeug_serving_logger.addFilter(WerkzeugErrorFilter())

logger = logging.getLogger(__name__)
server_logger = logging.getLogger('server')
api_logger = logging.getLogger('api')

# Import API app
# Note: api module is in src/api/, but src/ is added to sys.path above
from api import app, socketio  # type: ignore  # noqa: F401

def load_config():
    """Load configuration from settings.json."""
    config_path = Path('./config/settings.json')
    if config_path.exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


# Global start time for uptime calculation
start_time = None

def log_health_status():
    """Log server health status periodically."""
    while True:
        time.sleep(300)  # Every 5 minutes
        try:
            from api.search_manager import search_manager  # type: ignore
            from api.models import JobStatus  # type: ignore
            
            active_jobs = len([j for j in search_manager.jobs.values() 
                             if j.status == JobStatus.RUNNING])
            total_jobs = len(search_manager.jobs)
            uptime = time.time() - start_time if start_time else 0
            
            server_logger.info(f"Health Check - Active Jobs: {active_jobs}/{total_jobs}, "
                             f"Uptime: {uptime:.0f}s")
        except Exception as e:
            server_logger.error(f"Health check error: {e}", exc_info=True)

def main():
    """Run the Flask application."""
    global start_time
    start_time = time.time()
    
    try:
        config = load_config()
        api_config = config.get('api', {})
        
        port = api_config.get('port', 5000)
        host = api_config.get('host', '0.0.0.0')
        debug = api_config.get('debug', False)
        
        server_logger.info("=" * 60)
        server_logger.info("Starting CURP Automation API Server")
        server_logger.info(f"Host: {host}, Port: {port}")
        server_logger.info(f"Debug mode: {debug}")
        server_logger.info(f"Start time: {datetime.now().isoformat()}")
        server_logger.info("=" * 60)
        
        # Start health logging thread
        health_thread = threading.Thread(target=log_health_status, daemon=True)
        health_thread.start()
        server_logger.info("Health monitoring thread started")
        
        # Run the application
        # Use use_reloader=False to avoid issues with Werkzeug 3.x and WebSocket upgrades
        # Use threaded=True to handle concurrent requests properly
        socketio.run(
            app,
            host=host,
            port=port,
            debug=debug,
            allow_unsafe_werkzeug=True,  # For development
            use_reloader=False,  # Disable reloader to avoid WebSocket upgrade issues
            log_output=False,  # Reduce log noise
            threaded=True,  # Enable threading for concurrent request handling
            processes=1  # Single process (threading handles concurrency)
        )
    
    except KeyboardInterrupt:
        server_logger.info("Server stopped by user")
        logger.info("Server stopped by user")
    except Exception as e:
        server_logger.error(f"Error starting server: {e}", exc_info=True)
        logger.error(f"Error starting server: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
