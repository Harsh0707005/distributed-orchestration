from sqlalchemy import event, inspect
from sqlalchemy.orm import Session
from models import Website
from utils.sqs_client import send_website_to_sqs
from database import SessionLocal
from config.settings import AWS_SQS_URL_WEBSITES, AWS_SQS_URL_PRIORITY_WEBSITES
from datetime import datetime, timezone
import threading

def website_to_dict(website, sample_needed=True):
    return {
        'id': website.id,
        'url': website.url,
        'type': website.type,
        'validator': website.validator,
        'scrape_region': website.scrape_region or 'ap-south-1',
        'sample_needed': sample_needed
    }

def push_website_to_sqs(website):
    website_data = website_to_dict(website)
    
    queue_url = None
    if website.priority and AWS_SQS_URL_PRIORITY_WEBSITES:
        queue_url = AWS_SQS_URL_PRIORITY_WEBSITES
    else:
        queue_url = AWS_SQS_URL_WEBSITES
    
    success = send_website_to_sqs(website_data, queue_url)
    
    if success:
        db = SessionLocal()
        try:
            db_website = db.query(Website).filter(Website.id == website.id).first()
            if db_website:
                db_website.status = 'in_queue'
                db_website.updated_at = datetime.now(timezone.utc)
                db.commit()
                print(f"Updated website {website.url} status to in_queue")
            else:
                print(f"Website {website.id} not found in database")
        except Exception as e:
            db.rollback()
            print(f"Error updating website status to in_queue: {e}")
        finally:
            db.close()

def on_website_update(mapper, connection, target):
    session = Session.object_session(target)
    if session is None:
        return
    
    insp = inspect(target)
    status_history = insp.attrs.status.history
    
    if status_history.has_changes():
        if len(status_history.deleted) > 0 and len(status_history.added) > 0:
            old_status = status_history.deleted[0]
            new_status = status_history.added[0]
            if old_status != 'ready' and new_status == 'ready':
                thread = threading.Thread(target=push_website_to_sqs, args=(target,))
                thread.daemon = True
                thread.start()

def on_website_insert(mapper, connection, target):
    if target.status == 'ready':
        thread = threading.Thread(target=push_website_to_sqs, args=(target,))
        thread.daemon = True
        thread.start()

def register_events():
    event.listen(Website, 'after_update', on_website_update)
    event.listen(Website, 'after_insert', on_website_insert)

