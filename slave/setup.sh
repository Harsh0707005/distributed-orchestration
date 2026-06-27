#!/bin/bash
# Slave Setup Script
# This script sets up a slave/worker node

set -e

echo "=========================================="
echo "Slave Setup Script"
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
# Master API Configuration
MASTER_API_URL=http://localhost:8000/api/v1

# AWS SQS Configuration
AWS_SQS_URL_WEBSITES=
AWS_SQS_URL_PRIORITY_WEBSITES=
AWS_SQS_URL_BATCHES=
AWS_SQS_URL_PRIORITY_BATCHES=
AWS_REGION=ap-south-1

# Scraping Configuration
BATCH_SIZE=50
HEARTBEAT_INTERVAL=60
MAX_VALIDATION_FAILURES=100

# OpenAI Configuration
OPENAI_API_KEY=your_openai_api_key_here
EOF
    echo "✅ Created .env template. Please update it with your actual values."
    echo "   Then run this script again to continue setup."
    exit 0
fi

# Create necessary directories
echo "📁 Creating necessary directories..."
mkdir -p html
mkdir -p logs

echo ""
echo "=========================================="
echo "✅ Slave setup complete!"
echo "=========================================="
echo ""
echo "To start the slave worker:"
echo "  source venv/bin/activate"
echo "  python worker.py"
echo ""
echo "Note: The slave will automatically:"
echo "  - Register with the master"
echo "  - Send heartbeats"
echo "  - Poll SQS for websites to scrape"
echo "  - Send logs to master"
echo "  - Send notification events to master"
echo ""

