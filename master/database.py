from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import sys
from config.settings import (
    DB_NAME, BASE_DATABASE_URL, DATABASE_URL
)

def create_database():
    try:
        temp_engine = create_engine(BASE_DATABASE_URL)
        conn = temp_engine.connect()
        conn = conn.execution_options(isolation_level="AUTOCOMMIT")
        
        result = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :dbname"),
            {"dbname": DB_NAME}
        )
        
        if not result.scalar():
            print(f"Creating database: {DB_NAME}")
            conn.execute(text(f'CREATE DATABASE "{DB_NAME}"'))
            print("Database created successfully")
        else:
            print(f"Database {DB_NAME} already exists")
        
        conn.close()
        temp_engine.dispose()
    except Exception as e:
        print(f"Error creating database: {e}")
        sys.exit(1)

create_database()

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

from models import Base

def init_db():
    Base.metadata.create_all(bind=engine)
    from events import register_events
    register_events()
    print("Database tables created successfully")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

if __name__ == "__main__":
    init_db()

