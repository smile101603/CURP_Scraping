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
    logger=True,
    engineio_logger=True
)

# Import routes and websocket handlers after app initialization
from . import routes, websocket
