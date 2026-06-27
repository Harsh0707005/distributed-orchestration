# Setup Guide

Complete setup instructions for both Master and Slave nodes.

## Prerequisites

- Python 3.8 or higher
- PostgreSQL database
- AWS credentials (for EC2 and SQS)
- OpenAI API key

## Master Setup

### 1. Initial Setup

```bash
cd master
chmod +x setup.sh
./setup.sh
```

This will:
- Create a virtual environment
- Install all dependencies
- Create a `.env` template (if it doesn't exist)
- Check database connection
- Run all migrations
- Initialize database tables

### 2. Configure Environment Variables

Edit `master/.env` with your actual values:

```env
# Database Configuration
DB_USER=postgres
DB_PASSWORD=your_password
DB_HOST=localhost
DB_PORT=5432
DB_NAME=distributed_orchestration_db

# AWS Configuration
AWS_REGION=ap-south-1
AWS_SQS_URL_WEBSITES=your_sqs_queue_url
AWS_SQS_URL_PRIORITY_WEBSITES=your_priority_queue_url
AWS_SQS_URL_BATCHES=your_batches_queue_url
AWS_SQS_URL_PRIORITY_BATCHES=your_priority_batches_queue_url
LAUNCH_TEMPLATE_ID=lt-0ed411ff83de7246e

# OpenAI Configuration
OPENAI_API_KEY=your_openai_api_key_here
```

### 3. Run Migrations (if needed)

If you need to run migrations manually:

```bash
cd master
source venv/bin/activate
python run_migrations.py
```

This runs all migrations in the correct order:
1. `add_terminated_column`
2. `move_terminated_to_status`
3. `add_priority_column`
4. `add_priority_batches_table`
5. `add_sync_column`
6. `add_null_heartbeat_count`
7. `update_node_current_website`
8. `add_node_logs_table`
9. `add_country_info_to_websites`
10. `add_notification_settings_table`

### 4. Start Master API

```bash
cd master
source venv/bin/activate
python run_api.py
```

The API will be available at `http://localhost:8000`

### 5. Start Dashboard (Optional)

In a new terminal:

```bash
cd master
source venv/bin/activate
streamlit run dashboard/app.py
```

The dashboard will be available at `http://localhost:8501`

### 6. Verify Setup

- Check API health: `curl http://localhost:8000/`
- Check API docs: `http://localhost:8000/docs`
- Access dashboard: `http://localhost:8501`

## Slave Setup

### 1. Initial Setup

```bash
cd slave
chmod +x setup.sh
./setup.sh
```

This will:
- Create a virtual environment
- Install all dependencies
- Create a `.env` template (if it doesn't exist)
- Create necessary directories

### 2. Configure Environment Variables

Edit `slave/.env` with your actual values:

```env
# Master API Configuration
MASTER_API_URL=http://your-master-ip:8000/api/v1

# AWS SQS Configuration
AWS_SQS_URL_WEBSITES=your_sqs_queue_url
AWS_SQS_URL_PRIORITY_WEBSITES=your_priority_queue_url
AWS_SQS_URL_BATCHES=your_batches_queue_url
AWS_SQS_URL_PRIORITY_BATCHES=your_priority_batches_queue_url
AWS_REGION=ap-south-1

# Scraping Configuration
BATCH_SIZE=50
HEARTBEAT_INTERVAL=60
MAX_VALIDATION_FAILURES=100

# OpenAI Configuration
OPENAI_API_KEY=your_openai_api_key_here
```

**Important**: Update `MASTER_API_URL` to point to your master server's IP address or domain.

### 3. Start Slave Worker

```bash
cd slave
source venv/bin/activate
python worker.py
```

The slave will:
- Automatically register with the master
- Send heartbeats every 60 seconds (configurable)
- Poll SQS queues for websites to scrape
- Send logs to master dashboard
- Send notification events to master
- Auto-terminate websites running longer than 24 hours

### 4. Verify Slave is Running

- Check master dashboard → Nodes page
- You should see the slave node appear with status "alive"
- Check logs in the master dashboard

## Logging

### Master Logs

Master logs are printed to stdout/stderr. For production, consider redirecting to files:

```bash
python run_api.py >> logs/master.log 2>&1
```

### Slave Logs

Slave logs are:
1. Printed to stdout/stderr
2. Automatically sent to master API (visible in dashboard)
3. Can be redirected to files:

```bash
python worker.py >> logs/slave.log 2>&1
```

### Viewing Logs in Dashboard

1. Go to master dashboard
2. Navigate to "🖥️ Nodes" page
3. Select a node from the dropdown
4. View logs in real-time

## Database Migrations

### Running Migrations

Migrations are automatically run when you execute `run_migrations.py`:

```bash
cd master
source venv/bin/activate
python run_migrations.py
```

### Migration Order

Migrations must be run in order. The `run_migrations.py` script handles this automatically.

### Manual Migration

If you need to run a specific migration:

```bash
cd master
source venv/bin/activate
python migrations/add_node_logs_table.py
```

## Troubleshooting

### Database Connection Issues

1. Ensure PostgreSQL is running: `pg_isready`
2. Check `.env` file has correct credentials
3. Verify database exists: `psql -U postgres -l`

### Master API Not Starting

1. Check if port 8000 is available: `lsof -i :8000`
2. Check database connection
3. Verify all migrations ran successfully
4. Check logs for errors

### Slave Not Connecting to Master

1. Verify `MASTER_API_URL` in slave `.env` is correct
2. Check master API is accessible: `curl http://master-ip:8000/`
3. Check firewall rules allow connection
4. Verify AWS credentials are configured

### Logs Not Appearing in Dashboard

1. Check slave is sending logs: Look for "Notification event failed" in slave output
2. Verify master API `/nodes/logs` endpoint is working
3. Check database has `node_logs` table: `\d node_logs` in psql

## Production Deployment

### Master

1. Use a process manager (systemd, supervisor, etc.)
2. Set up reverse proxy (nginx) for API
3. Configure SSL certificates
4. Set up log rotation
5. Configure database backups
6. Set up monitoring/alerting

### Slave

1. Deploy on EC2 instances (or use launch template)
2. Use systemd service for auto-restart
3. Configure log rotation
4. Set up monitoring
5. Configure auto-scaling if needed

## Environment Variables Reference

### Master Required Variables

- `DB_USER` - PostgreSQL username
- `DB_PASSWORD` - PostgreSQL password
- `DB_HOST` - PostgreSQL host
- `DB_PORT` - PostgreSQL port
- `DB_NAME` - Database name
- `OPENAI_API_KEY` - OpenAI API key

### Master Optional Variables

- `MASTER_HOST` - API host (default: 0.0.0.0)
- `MASTER_PORT` - API port (default: 8000)
- `AWS_REGION` - AWS region (default: ap-south-1)
- `NODE_MONITOR_INTERVAL` - Node check interval in seconds (default: 240)
- `NODE_STALE_AFTER_SECONDS` - Seconds before node marked stale (default: 180)

### Slave Required Variables

- `MASTER_API_URL` - Master API URL
- `OPENAI_API_KEY` - OpenAI API key

### Slave Optional Variables

- `BATCH_SIZE` - Batch size for processing (default: 50)
- `HEARTBEAT_INTERVAL` - Heartbeat interval in seconds (default: 60)
- `MAX_VALIDATION_FAILURES` - Max validation failures before stopping (default: 100)

## Next Steps

1. Configure notification emails in dashboard Settings page
2. Add websites via dashboard
3. Launch slave nodes (manually or via dashboard)
4. Monitor progress in dashboard

