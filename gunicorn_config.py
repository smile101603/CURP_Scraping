"""
Gunicorn Configuration
Production WSGI server configuration for CURP Automation API.
"""
import multiprocessing

# Server socket
bind = "0.0.0.0:5000"
backlog = 2048

# Worker processes
# Use fewer workers for better stability with Playwright
workers = min(multiprocessing.cpu_count() + 1, 4)  # Max 4 workers
worker_class = 'eventlet'  # Required for WebSocket support
worker_connections = 1000
timeout = 300  # Increased timeout for long-running searches
keepalive = 5
graceful_timeout = 30  # Graceful shutdown timeout

# Logging
accesslog = 'logs/gunicorn_access.log'
errorlog = 'logs/gunicorn_error.log'
loglevel = 'info'
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'

# Process naming
proc_name = 'curp_automation_api'

# Server mechanics
daemon = False
pidfile = 'logs/gunicorn.pid'
umask = 0
user = None
group = None
tmp_upload_dir = None

# SSL (uncomment and configure for HTTPS)
# keyfile = '/path/to/keyfile'
# certfile = '/path/to/certfile'
