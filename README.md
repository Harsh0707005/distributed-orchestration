# Distributed Orchestration System

A master-slave distributed task orchestration system for managing website processing across multiple nodes.

## Architecture

```
distributed-orchestration/
├── master/          # Master orchestrator
│   ├── models.py    # Database models
│   ├── database.py  # Database setup
│   ├── config/      # Configuration
│   ├── api/         # API endpoints
│   └── utils/       # Utilities
└── slave/           # Worker nodes (to be implemented)
```

## Components

### Master
The master orchestrator is responsible for:
- Managing the database schema
- Tracking node health and status
- Distributing tasks to slave nodes
- Monitoring task progress
- Coordinating website processing

### Slave
Slave/worker nodes will:
- Register with the master
- Receive and process tasks
- Report health and progress
- Complete website processing tasks

## Quick Start

1. Set up the master:
```bash
cd master
pip install -r requirements.txt
# Create .env file with database credentials
python database.py
```

2. Set up slave nodes (coming soon)

See `master/README.md` for detailed master setup instructions.

