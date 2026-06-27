# Quick Start Guide

## Master - Quick Setup

```bash
cd master
./setup.sh                    # First time setup
source venv/bin/activate      # Activate virtual environment
python run_api.py             # Start API server
```

In another terminal:
```bash
cd master
source venv/bin/activate
streamlit run dashboard/app.py  # Start dashboard
```

## Slave - Quick Setup

```bash
cd slave
./setup.sh                    # First time setup
source venv/bin/activate      # Activate virtual environment
python worker.py              # Start worker
```

## First Time Setup Checklist

### Master
- [ ] Run `./setup.sh`
- [ ] Edit `.env` with your database credentials
- [ ] Edit `.env` with AWS SQS URLs
- [ ] Edit `.env` with OpenAI API key
- [ ] Run `python run_migrations.py` (or it runs automatically in setup.sh)
- [ ] Start API: `python run_api.py`
- [ ] Start dashboard: `streamlit run dashboard/app.py`
- [ ] Configure notification emails in dashboard Settings

### Slave
- [ ] Run `./setup.sh`
- [ ] Edit `.env` with `MASTER_API_URL` (point to master server)
- [ ] Edit `.env` with AWS SQS URLs
- [ ] Edit `.env` with OpenAI API key
- [ ] Start worker: `python worker.py`
- [ ] Verify node appears in master dashboard

## Common Commands

### Master
```bash
# Run migrations
python run_migrations.py

# Start API
python run_api.py

# Start dashboard
streamlit run dashboard/app.py

# Check database connection
python -c "from database import engine; engine.connect()"
```

### Slave
```bash
# Start worker
python worker.py

# Test connection to master
curl http://master-ip:8000/api/v1/nodes
```

## URLs

- Master API: `http://localhost:8000`
- API Docs: `http://localhost:8000/docs`
- Dashboard: `http://localhost:8501`

## Troubleshooting

**Database connection failed?**
- Check PostgreSQL is running: `pg_isready`
- Verify `.env` has correct DB credentials
- Check database exists

**Slave not connecting?**
- Verify `MASTER_API_URL` in slave `.env`
- Check master API is accessible: `curl http://master-ip:8000/`
- Check firewall/security groups

**Migrations failing?**
- Ensure database exists
- Check database user has CREATE/ALTER permissions
- Run migrations one by one to identify issue

**Logs not showing?**
- Check slave is sending logs (look for errors in slave output)
- Verify `node_logs` table exists: `\d node_logs` in psql
- Check master API endpoint: `curl http://localhost:8000/api/v1/nodes/1/logs`

