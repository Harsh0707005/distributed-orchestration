import os
from dotenv import load_dotenv

load_dotenv()

DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'root')
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '5432')
DB_NAME = os.getenv('DB_NAME', 'distributed_orchestration_db')

BASE_DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/postgres"

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

MASTER_HOST = os.getenv('MASTER_HOST', '0.0.0.0')
MASTER_PORT = int(os.getenv('MASTER_PORT', '8000'))

NODE_HEARTBEAT_INTERVAL = int(os.getenv('NODE_HEARTBEAT_INTERVAL', '30'))
NODE_TIMEOUT = int(os.getenv('NODE_TIMEOUT', '100'))

AWS_SQS_URL_WEBSITES = os.getenv('AWS_SQS_URL_WEBSITES', None)
AWS_SQS_URL_PRIORITY_WEBSITES = os.getenv('AWS_SQS_URL_PRIORITY_WEBSITES', None)
AWS_SQS_URL_BATCHES = os.getenv('AWS_SQS_URL_BATCHES', None)
AWS_SQS_URL_PRIORITY_BATCHES = os.getenv('AWS_SQS_URL_PRIORITY_BATCHES', None)
AWS_REGION = os.getenv('AWS_REGION', 'ap-south-1')

BATCH_POLL_INTERVAL = int(os.getenv('BATCH_POLL_INTERVAL', '10'))

NODE_MONITOR_INTERVAL = int(os.getenv('NODE_MONITOR_INTERVAL', '240'))
NODE_STALE_AFTER_SECONDS = int(os.getenv('NODE_STALE_AFTER_SECONDS', '180'))

LAUNCH_TEMPLATE_ID = os.getenv('LAUNCH_TEMPLATE_ID', 'lt-0ed411ff83de7246e')

# Product Sync Settings
SYNC_INTERVAL = int(os.getenv('SYNC_INTERVAL', '20'))  # seconds
SYNC_BATCH_SIZE = int(os.getenv('SYNC_BATCH_SIZE', '50'))  # max products per sync
BACKEND_API_URL = os.getenv('BACKEND_API_URL', 'http://3.109.112.5:4000')

