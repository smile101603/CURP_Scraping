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
# Try eventlet first, fallback to threading if not available
try:
    import eventlet
    async_mode = 'eventlet'
except ImportError:
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
