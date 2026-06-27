#!/usr/bin/env python3
"""
Run all database migrations in order.
This script should be run before starting the master API.
"""
import sys
import os
import importlib.util

# Add master directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Migration order - must be run in this sequence
MIGRATIONS = [
    "add_terminated_column",
    "move_terminated_to_status",
    "add_priority_column",
    "add_priority_batches_table",
    "add_sync_column",
    "add_null_heartbeat_count",
    "update_node_current_website",
    "add_node_logs_table",
    "add_country_info_to_websites",
    "add_notification_settings_table",
    "add_scrape_region_to_websites",
    "add_region_to_nodes",
    "add_new_website_statuses",
    "add_sample_flag_to_priority_batches",
    "add_system_settings_table",
    "add_resume_command_to_nodes",
    "add_reason_to_websites",
    "add_automated_scraping_configs_table",
]

def run_migration(migration_name):
    """Run a single migration script."""
    migration_path = os.path.join(
        os.path.dirname(__file__),
        "migrations",
        f"{migration_name}.py"
    )
    
    if not os.path.exists(migration_path):
        print(f"⚠️  Migration file not found: {migration_path}")
        return False
    
    try:
        print(f"\n🔄 Running migration: {migration_name}")
        spec = importlib.util.spec_from_file_location(migration_name, migration_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        # Call the main function (assuming it's named after the migration)
        func_name = migration_name.replace("-", "_")
        
        # Try common function names
        if hasattr(module, func_name):
            getattr(module, func_name)()
        elif hasattr(module, "main"):
            module.main()
        elif hasattr(module, f"add_{func_name}"):
            getattr(module, f"add_{func_name}")()
        else:
            # Try to find any function that looks like the migration function
            # (but skip imports and built-ins)
            for attr in dir(module):
                if (not attr.startswith("_") and 
                    callable(getattr(module, attr)) and 
                    attr not in ['sys', 'os', 'text', 'create_engine']):
                    getattr(module, attr)()
                    break
        
        print(f"✅ Migration {migration_name} completed")
        return True
    except Exception as e:
        print(f"❌ Error running migration {migration_name}: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("=" * 60)
    print("Database Migration Runner")
    print("=" * 60)
    
    # Check database connection first
    try:
        from database import engine
        with engine.connect() as conn:
            print("✅ Database connection successful")
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        print("\nPlease check your .env file and ensure PostgreSQL is running.")
        print("Required environment variables:")
        print("  - DB_USER")
        print("  - DB_PASSWORD")
        print("  - DB_HOST")
        print("  - DB_PORT")
        print("  - DB_NAME")
        sys.exit(1)
    
    print(f"\n📋 Found {len(MIGRATIONS)} migrations to run")
    
    failed = []
    for migration in MIGRATIONS:
        if not run_migration(migration):
            failed.append(migration)
    
    print("\n" + "=" * 60)
    if failed:
        print(f"❌ {len(failed)} migration(s) failed:")
        for f in failed:
            print(f"   - {f}")
        sys.exit(1)
    else:
        print("✅ All migrations completed successfully!")
        print("\nYou can now start the master API with: python run_api.py")
    print("=" * 60)

if __name__ == "__main__":
    main()

