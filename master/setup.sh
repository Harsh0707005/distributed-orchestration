#!/bin/bash
# Master Setup Script
# This script sets up the master orchestrator

set -e

echo "=========================================="
echo "Master Setup Script"
echo "=========================================="

# Check if Python 3 is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.8 or higher."
    exit 1
fi

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "📥 Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Check for .env file
if [ ! -f ".env" ]; then
    echo "⚠️  .env file not found. Creating template..."
    cat > .env << EOF
# Database Configuration
DB_USER=postgres
DB_PASSWORD=root
DB_HOST=localhost
DB_PORT=5432
DB_NAME=distributed_orchestration_db

# API Configuration
MASTER_HOST=0.0.0.0
MASTER_PORT=8000

# AWS Configuration
AWS_REGION=ap-south-1
AWS_SQS_URL_WEBSITES=
AWS_SQS_URL_PRIORITY_WEBSITES=
AWS_SQS_URL_BATCHES=
AWS_SQS_URL_PRIORITY_BATCHES=
LAUNCH_TEMPLATE_ID=lt-0ed411ff83de7246e

# OpenAI Configuration
OPENAI_API_KEY=your_openai_api_key_here

# Node Monitoring
NODE_MONITOR_INTERVAL=240
NODE_STALE_AFTER_SECONDS=180
NODE_HEARTBEAT_INTERVAL=30
NODE_TIMEOUT=90

# Batch Processing
BATCH_POLL_INTERVAL=10

# Product Sync
SYNC_INTERVAL=20
SYNC_BATCH_SIZE=50
BACKEND_API_URL=http://3.109.112.5:4000
EOF
    echo "✅ Created .env template. Please update it with your actual values."
    echo "   Then run this script again to continue setup."
    exit 0
fi

# Check PostgreSQL connection
echo "🔍 Checking database connection..."
python3 -c "
from config.settings import DATABASE_URL
from sqlalchemy import create_engine, text
try:
    engine = create_engine(DATABASE_URL)
    with engine.connect() as conn:
        conn.execute(text('SELECT 1'))
    print('✅ Database connection successful')
except Exception as e:
    print(f'❌ Database connection failed: {e}')
    print('Please ensure PostgreSQL is running and .env is configured correctly.')
    exit(1)
"

# Run migrations
echo "🔄 Running database migrations..."
python3 run_migrations.py

# Initialize database tables (creates tables from models)
echo "📊 Initializing database tables..."
python3 database.py

echo ""
echo "=========================================="
echo "✅ Master setup complete!"
echo "=========================================="
echo ""
echo "To start the master API:"
echo "  source venv/bin/activate"
echo "  python run_api.py"
echo ""
echo "To start the dashboard:"
echo "  source venv/bin/activate"
echo "  streamlit run dashboard/app.py"
echo ""

