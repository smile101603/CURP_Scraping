"""
API Module
Flask API for CURP automation tool.
"""
from flask import Flask
from flask_cors import CORS
from flask_socketio import SocketIO
import logging

logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)

# Configure CORS - allow all origins for development, can be restricted in production
CORS(app, resources={
    r"/api/*": {
        "origins": "*",
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"]
    }
})

# Initialize SocketIO with CORS support
# Use threading mode to avoid conflicts with Playwright's sync API
# Playwright's sync API doesn't work well with eventlet's greenlet-based concurrency
async_mode = 'threading'

socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode=async_mode,
    logger=False,  # Disable SocketIO logger to reduce noise
    engineio_logger=False,  # Disable EngineIO logger to reduce noise
    ping_timeout=60,  # Increase ping timeout for stability
    ping_interval=25,  # Match the ping interval from logs
    max_http_buffer_size=10 * 1024 * 1024,  # 10MB max buffer for file uploads
    cors_credentials=True  # Allow credentials for CORS
)

# Import routes and websocket handlers after app initialization
from . import routes, websocket
