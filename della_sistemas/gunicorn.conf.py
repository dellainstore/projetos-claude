# Gunicorn config — D'ELLA Sistemas
# Unix socket (Nginx lê o socket; não expõe porta na rede)
bind = "unix:/run/della-sistemas/gunicorn.sock"
workers = 4
worker_class = "sync"
timeout = 120
keepalive = 5

# Logs
accesslog = "/home/neto/logs/della-sistemas/access.log"
errorlog  = "/home/neto/logs/della-sistemas/error.log"
loglevel  = "info"

# Graceful reload
preload_app = True
max_requests = 500
max_requests_jitter = 50
