import os
import sys
import requests
import threading
from queue import Queue
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

MASTER_API_URL = os.getenv('MASTER_API_URL', 'http://localhost:8000/api/v1')
INSTANCE_ID = None

# Queue to batch log messages
log_queue = Queue()
log_thread = None
log_thread_running = False

def get_instance_id():
    """Get the EC2 instance ID"""
    global INSTANCE_ID
    if INSTANCE_ID:
        return INSTANCE_ID
    
    try:
        resp = requests.put(
            'http://169.254.169.254/latest/api/token',
            headers={'X-aws-ec2-metadata-token-ttl-seconds': '21600'},
            timeout=1
        )
        token = resp.text if resp.status_code == 200 else None
        headers = {'X-aws-ec2-metadata-token': token} if token else {}
        
        instance_id = requests.get(
            'http://169.254.169.254/latest/meta-data/instance-id',
            headers=headers,
            timeout=1
        ).text
        
        INSTANCE_ID = instance_id
        return instance_id
    except Exception:
        return None

def send_log_to_master(message, level='INFO'):
    """Send a log message to the master API"""
    instance_id = get_instance_id()
    if not instance_id:
        return False
    
    try:
        url = f"{MASTER_API_URL}/nodes/logs"
        payload = {
            "instance_id": instance_id,
            "message": message,
            "level": level
        }
        response = requests.post(url, json=payload, timeout=2)
        return response.status_code == 200
    except Exception:
        # Silently fail - don't want logging to break the application
        return False

def log_worker():
    """Background thread to send logs from queue"""
    global log_thread_running
    log_thread_running = True
    
    while log_thread_running:
        try:
            # Get log from queue with timeout
            try:
                log_item = log_queue.get(timeout=1)
                if log_item is None:  # Shutdown signal
                    break
                
                message, level = log_item
                send_log_to_master(message, level)
                log_queue.task_done()
            except:
                continue
        except Exception:
            continue

def start_log_worker():
    """Start the background log worker thread"""
    global log_thread
    if log_thread is None or not log_thread.is_alive():
        log_thread = threading.Thread(target=log_worker, daemon=True)
        log_thread.start()

def queue_log(message, level='INFO'):
    """Queue a log message to be sent to master"""
    if not log_thread_running:
        start_log_worker()
    
    # Truncate very long messages
    if len(message) > 10000:
        message = message[:10000] + "... [truncated]"
    
    try:
        log_queue.put((message, level), block=False)
    except:
        pass  # Queue full, skip this log

class LogSender:
    """A file-like object that sends logs to master API"""
    def __init__(self, original_stream, level='INFO'):
        self.original_stream = original_stream
        self.level = level
        self.buffer = ""
    
    def write(self, text):
        # Write to original stream
        self.original_stream.write(text)
        self.original_stream.flush()
        
        # Buffer the text
        self.buffer += text
        
        # Send complete lines to master
        while '\n' in self.buffer:
            line, self.buffer = self.buffer.split('\n', 1)
            line = line.strip()
            if line:  # Only send non-empty lines
                queue_log(line, self.level)
    
    def flush(self):
        self.original_stream.flush()
        # Send any remaining buffer
        if self.buffer.strip():
            queue_log(self.buffer.strip(), self.level)
            self.buffer = ""

def setup_logging():
    """Setup logging to send to master API"""
    start_log_worker()
    
    # Wrap stdout and stderr
    sys.stdout = LogSender(sys.stdout, 'INFO')
    sys.stderr = LogSender(sys.stderr, 'ERROR')

