#!/bin/bash
# Production server startup script using Gunicorn
# This provides better performance and stability than the development server

cd "$(dirname "$0")"

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Start Gunicorn with eventlet workers for WebSocket support
gunicorn --config gunicorn_config.py app:app
