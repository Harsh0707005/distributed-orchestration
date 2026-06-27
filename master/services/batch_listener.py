import os
import json
import time
import threading
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from dotenv import load_dotenv

from database import SessionLocal
from models import Batch, Website
from utils.sqs_client import get_sqs_client

load_dotenv()

AWS_SQS_URL_BATCHES = os.getenv('AWS_SQS_URL_BATCHES')
POLL_INTERVAL = int(os.getenv('BATCH_POLL_INTERVAL', '10'))


class BatchListener:
    def __init__(self):
        self.running = False
        self.listener_thread = None
        
    def poll_sqs(self):
        if not AWS_SQS_URL_BATCHES:
            print("AWS_SQS_URL_BATCHES not configured")
            return None
        
        try:
            client = get_sqs_client()
            response = client.receive_message(
                QueueUrl=AWS_SQS_URL_BATCHES,
                MaxNumberOfMessages=1,
                WaitTimeSeconds=5
            )
            
            if 'Messages' in response and len(response['Messages']) > 0:
                message = response['Messages'][0]
                receipt_handle = message['ReceiptHandle']
                body = json.loads(message['Body'])
                
                return {
                    'body': body,
                    'receipt_handle': receipt_handle
                }
            return None
        except Exception as e:
            print(f"Error polling SQS batches queue: {e}")
            return None
    
    def delete_message_from_sqs(self, receipt_handle):
        if not AWS_SQS_URL_BATCHES:
            return False
        
        try:
            client = get_sqs_client()
            client.delete_message(
                QueueUrl=AWS_SQS_URL_BATCHES,
                ReceiptHandle=receipt_handle
            )
            return True
        except Exception as e:
            print(f"Error deleting message from SQS: {e}")
            return False
    
    def save_batch_to_db(self, batch_data):
        db = SessionLocal()
        try:
            website_id = batch_data.get('website_id')
            batch_name = batch_data.get('batch_name')
            openai_batch_id = batch_data.get('openai_batch_id')
            
            if not website_id or not batch_name or not openai_batch_id:
                print(f"Invalid batch data: {batch_data}")
                return False
            
            website = db.query(Website).filter(Website.id == website_id).first()
            if not website:
                print(f"Website with ID {website_id} not found")
                return False
            
            existing_batch = db.query(Batch).filter(
                Batch.website_id == website_id,
                Batch.batch_name == batch_name
            ).first()
            
            if existing_batch:
                print(f"Batch {batch_name} already exists for website {website_id}")
                return False
            
            new_batch = Batch(
                website_id=website_id,
                batch_name=batch_name,
                open_ai_batch_id=openai_batch_id,
                created_at=datetime.now(timezone.utc)
            )
            
            db.add(new_batch)
            db.commit()
            db.refresh(new_batch)
            
            print(f"Saved batch {batch_name} (OpenAI ID: {openai_batch_id}) for website {website_id}")
            return True
            
        except Exception as e:
            db.rollback()
            print(f"Error saving batch to database: {e}")
            return False
        finally:
            db.close()
    
    def listen(self):
        print(f"Batch listener started. Polling SQS every {POLL_INTERVAL} seconds...")
        print(f"Queue URL: {AWS_SQS_URL_BATCHES}")
        
        while self.running:
            try:
                message_data = self.poll_sqs()
                
                if message_data:
                    batch_data = message_data['body']
                    receipt_handle = message_data['receipt_handle']
                    print(f"Received batch from SQS: {batch_data}")
                    
                    if self.save_batch_to_db(batch_data):
                        self.delete_message_from_sqs(receipt_handle)
                        print(f"Batch saved to DB and message deleted from SQS")
                    else:
                        print(f"Failed to save batch to DB, message kept in SQS")
                
                time.sleep(POLL_INTERVAL)
                
            except KeyboardInterrupt:
                print("\nBatch listener stopped by user")
                break
            except Exception as e:
                print(f"Error in batch listener loop: {e}")
                time.sleep(POLL_INTERVAL)
    
    def start(self):
        if self.running:
            print("Batch listener is already running")
            return
        
        self.running = True
        self.listener_thread = threading.Thread(target=self.listen)
        self.listener_thread.daemon = True
        self.listener_thread.start()
        print("Batch listener thread started")
    
    def stop(self):
        if not self.running:
            print("Batch listener is not running")
            return
        
        self.running = False
        if self.listener_thread:
            self.listener_thread.join(timeout=5)
        print("Batch listener stopped")


listener_instance = None

def get_batch_listener():
    global listener_instance
    if listener_instance is None:
        listener_instance = BatchListener()
    return listener_instance

