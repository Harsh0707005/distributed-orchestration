import os
import json
import time
import threading
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from dotenv import load_dotenv

from database import SessionLocal
from models import PriorityBatch, Website
from utils.sqs_client import get_sqs_client

load_dotenv()

AWS_SQS_URL_PRIORITY_BATCHES = os.getenv('AWS_SQS_URL_PRIORITY_BATCHES')
POLL_INTERVAL = int(os.getenv('BATCH_POLL_INTERVAL', '3'))


class PriorityBatchListener:
    def __init__(self):
        self.running = False
        self.listener_thread = None
        
    def poll_sqs(self):
        if not AWS_SQS_URL_PRIORITY_BATCHES:
            print("AWS_SQS_URL_PRIORITY_BATCHES not configured")
            return None
        
        try:
            client = get_sqs_client()
            response = client.receive_message(
                QueueUrl=AWS_SQS_URL_PRIORITY_BATCHES,
                MaxNumberOfMessages=10,
                WaitTimeSeconds=2
            )
            
            if 'Messages' in response and len(response['Messages']) > 0:
                messages = []
                for message in response['Messages']:
                    receipt_handle = message['ReceiptHandle']
                    body = json.loads(message['Body'])
                    messages.append({
                        'body': body,
                        'receipt_handle': receipt_handle
                    })
                return messages
            return []
        except Exception as e:
            print(f"Error polling SQS priority batches queue: {e}")
            return []
    
    def delete_message_from_sqs(self, receipt_handle):
        if not AWS_SQS_URL_PRIORITY_BATCHES:
            return False
        
        try:
            client = get_sqs_client()
            client.delete_message(
                QueueUrl=AWS_SQS_URL_PRIORITY_BATCHES,
                ReceiptHandle=receipt_handle
            )
            return True
        except Exception as e:
            print(f"Error deleting message from SQS: {e}")
            return False
    
    def save_priority_batch_to_db(self, batch_data):
        db = SessionLocal()
        try:
            website_id = batch_data.get('website_id')
            url = batch_data.get('url')
            website_url = batch_data.get('website_url')
            result = batch_data.get('result')
            model = batch_data.get('model')
            
            if not website_id or not url or not result or not model:
                print(f"Invalid priority batch data: {batch_data}")
                return False
            
            website = db.query(Website).filter(Website.id == website_id).first()
            if not website:
                print(f"Website with ID {website_id} not found")
                return False
            
            is_sample = batch_data.get('sample', False)
            
            new_priority_batch = PriorityBatch(
                website_id=website_id,
                url=url,
                website_url=website_url or '',
                result=result,
                model=model,
                sample=is_sample,
                created_at=datetime.now(timezone.utc)
            )
            
            db.add(new_priority_batch)
            db.commit()
            db.refresh(new_priority_batch)
            
            print(f"Saved priority batch for website {website_id}, product URL: {url}")
            return True
            
        except Exception as e:
            db.rollback()
            print(f"Error saving priority batch to database: {e}")
            return False
        finally:
            db.close()
    
    def listen(self):
        print(f"Priority batch listener started. Polling SQS every {POLL_INTERVAL} seconds...")
        print(f"Queue URL: {AWS_SQS_URL_PRIORITY_BATCHES}")
        
        while self.running:
            try:
                messages = self.poll_sqs()
                
                if messages and len(messages) > 0:
                    print(f"Received {len(messages)} priority batch(es) from SQS")
                    
                    for message_data in messages:
                        batch_data = message_data['body']
                        receipt_handle = message_data['receipt_handle']
                        print(f"Processing priority batch: URL={batch_data.get('url')}")
                        
                        if self.save_priority_batch_to_db(batch_data):
                            self.delete_message_from_sqs(receipt_handle)
                            print(f"Priority batch saved to DB and message deleted from SQS")
                        else:
                            print(f"Failed to save priority batch to DB, message kept in SQS")
                
                time.sleep(POLL_INTERVAL)
                
            except KeyboardInterrupt:
                print("\nPriority batch listener stopped by user")
                break
            except Exception as e:
                print(f"Error in priority batch listener loop: {e}")
                time.sleep(POLL_INTERVAL)
    
    def start(self):
        if self.running:
            print("Priority batch listener is already running")
            return
        
        self.running = True
        self.listener_thread = threading.Thread(target=self.listen)
        self.listener_thread.daemon = True
        self.listener_thread.start()
        print("Priority batch listener thread started")
    
    def stop(self):
        if not self.running:
            print("Priority batch listener is not running")
            return
        
        self.running = False
        if self.listener_thread:
            self.listener_thread.join(timeout=5)
        print("Priority batch listener stopped")


priority_listener_instance = None

def get_priority_batch_listener():
    global priority_listener_instance
    if priority_listener_instance is None:
        priority_listener_instance = PriorityBatchListener()
    return priority_listener_instance

