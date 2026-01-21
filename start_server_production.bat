@echo off
REM Production server startup script using Gunicorn for Windows
REM This provides better performance and stability than the development server

cd /d "%~dp0"

REM Activate virtual environment if it exists
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
)

REM Start Gunicorn with eventlet workers for WebSocket support
REM Note: On Windows, you may need to use 'gevent' instead of 'eventlet'
gunicorn --config gunicorn_config.py app:app
