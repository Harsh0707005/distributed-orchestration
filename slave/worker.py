import os
import time
import json
import requests
import threading
from datetime import datetime, timezone, timedelta
from typing import Optional
from dotenv import load_dotenv
from sqs_client import get_sqs_client
from scraper import Scraper
from priority_scraper import PriorityScraper
from prompts import PRODUCT_EXTRACTION_PROMPT, get_region_specific_prompt
from log_sender import setup_logging

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    print("Warning: psutil not available. CPU and memory usage will not be reported.")

load_dotenv()

AWS_SQS_URL_WEBSITES = os.getenv('AWS_SQS_URL_WEBSITES')
AWS_SQS_URL_PRIORITY_WEBSITES = os.getenv('AWS_SQS_URL_PRIORITY_WEBSITES')

MASTER_API_URL = os.getenv('MASTER_API_URL', 'http://localhost:8000/api/v1')
BATCH_SIZE = int(os.getenv('BATCH_SIZE', '50'))
POLL_INTERVAL = 60
HEARTBEAT_INTERVAL = int(os.getenv('HEARTBEAT_INTERVAL', '60'))

class ScrapingWorker:
    def __init__(self):
        self.is_scraping = False
        self.current_website_id = None
        self.current_url = None
        self.scraper = None
        self.scraper_thread = None
        self.instance_id = None
        self.public_ip = None
        self._last_heartbeat = 0
        self.website_start_time = None  # Track when website processing started
        self.last_progress_time = None  # Track last time a page was successfully processed
        self.MAX_PROCESSING_TIME_HOURS = 24  # 1 day in hours
        self.NO_PROGRESS_TIMEOUT_SECONDS = 1200
        self.node_region = self._get_node_region()  # AWS region this node is in
        self.sample_size = self._fetch_sample_size()  # Fetch sample size from master
        self.is_paused_for_sample = False  # Track if paused for sample review

    def _get_node_region(self) -> str:
        try:
            token = self._get_imds_token()
            headers = {'X-aws-ec2-metadata-token': token} if token else {}
            resp = requests.get(
                'http://169.254.169.254/latest/meta-data/placement/availability-zone',
                headers=headers,
                timeout=2
            )
            if resp.status_code == 200:
                az = resp.text.strip()
                region = az[:-1]
                print(f"Node region from EC2 metadata: {region}")
                return region
        except Exception as e:
            print(f"Could not get region from EC2 metadata: {e}")
        
        region = os.getenv('AWS_REGION')
        if region:
            print(f"Node region from AWS_REGION env (fallback): {region}")
            return region
        
        default_region = 'ap-south-1'
        print(f"Node region defaulting to: {default_region}")
        return default_region
    
    def _fetch_sample_size(self) -> int:
        try:
            response = requests.get(f"{MASTER_API_URL}/settings/sample-size", timeout=5)
            if response.status_code == 200:
                data = response.json()
                sample_size = data.get('sample_size', 100)
                print(f"Fetched sample size from master: {sample_size}")
                return sample_size
        except Exception as e:
            print(f"Error fetching sample size from master: {e}")
        
        print(f"Using default sample size: 100")
        return 100
    
    def _on_sample_completion(self, sample_count: int):
        """
        Temporarily disabled sample-completion pause logic.
        We don't want the worker to auto-pause or terminate nodes based on sample size right now.
        """
        print(f"Sample size reached ({sample_count}) - sample completion handling is temporarily disabled (no pause/terminate).")

    def _get_imds_token(self):
        try:
            resp = requests.put(
                'http://169.254.169.254/latest/api/token',
                headers={'X-aws-ec2-metadata-token-ttl-seconds': '21600'},
                timeout=1
            )
            if resp.status_code == 200:
                return resp.text
        except Exception:
            pass
        return None

    def _get_instance_metadata(self):
        try:
            token = self._get_imds_token()
            headers = {'X-aws-ec2-metadata-token': token} if token else {}
            iid = requests.get('http://169.254.169.254/latest/meta-data/instance-id', headers=headers, timeout=1).text
            pip = None
            try:
                pip = requests.get('http://169.254.169.254/latest/meta-data/public-ipv4', headers=headers, timeout=1).text
            except Exception:
                pip = None
            return iid, pip
        except Exception:
            return None, None

    def _ensure_instance_identity(self):
        if not self.instance_id:
            iid, pip = self._get_instance_metadata()
            self.instance_id = iid
            self.public_ip = pip

    def _get_system_metrics(self):
        cpu_usage = None
        memory_usage = None
        
        if PSUTIL_AVAILABLE:
            try:
                cpu_usage = psutil.cpu_percent(interval=1)
                memory = psutil.virtual_memory()
                memory_usage = memory.percent
            except Exception as e:
                print(f"Error getting system metrics: {e}")
        
        return cpu_usage, memory_usage
    
    def _send_heartbeat(self):
        try:
            self._ensure_instance_identity()
            if not self.instance_id:
                return
            url = f"{MASTER_API_URL}/nodes/heartbeat"
            payload = {"instance_id": self.instance_id}
            if self.public_ip:
                payload["ip_address"] = self.public_ip
            
            cpu_usage, memory_usage = self._get_system_metrics()
            if cpu_usage is not None:
                payload["cpu_usage"] = round(cpu_usage, 2)
            if memory_usage is not None:
                payload["memory_usage"] = round(memory_usage, 2)
            
            if self.current_website_id is not None:
                payload["current_website_id"] = self.current_website_id
            else:
                payload["current_website_id"] = None
            
            resp = requests.post(url, json=payload, timeout=5)
            if resp.status_code == 200:
                metrics_str = ""
                if cpu_usage is not None or memory_usage is not None:
                    cpu_str = f"{cpu_usage}%" if cpu_usage is not None else "N/A"
                    mem_str = f"{memory_usage}%" if memory_usage is not None else "N/A"
                    metrics_str = f" (CPU: {cpu_str}, Memory: {mem_str})"
                print(f"Heartbeat OK for {self.instance_id}{metrics_str}")
            else:
                print(f"Heartbeat failed {resp.status_code}: {resp.text}")
        except Exception as e:
            print(f"Error sending heartbeat: {e}")

    def _notify_master_event(self, event_type, payload: Optional[dict] = None):
        try:
            self._ensure_instance_identity()
            url = f"{MASTER_API_URL}/notifications/events"
            data = {"event_type": event_type}
            if payload:
                data.update(payload)
            response = requests.post(url, json=data, timeout=5)
            if response.status_code != 200:
                print(f"Notification event failed ({response.status_code}): {response.text}")
        except Exception as e:
            print(f"Error notifying master ({event_type}): {e}")
    
    def _is_message_for_this_region(self, body: dict) -> bool:
        message_region = body.get('scrape_region', 'ap-south-1')
        
        if not message_region:
            message_region = 'ap-south-1'
        
        return message_region == self.node_region
    
    def _return_message_to_queue(self, client, queue_url: str, receipt_handle: str, website_url: str):
        try:
            client.change_message_visibility(
                QueueUrl=queue_url,
                ReceiptHandle=receipt_handle,
                VisibilityTimeout=0
            )
            print(f"Returned message for {website_url} to queue (wrong region)")
        except Exception as e:
            print(f"Error returning message to queue: {e}")
    
    def _validate_website_data(self, body: dict) -> bool:
        """Validate that website data has all required fields"""
        required_fields = ['id', 'url']
        for field in required_fields:
            if not body.get(field):
                print(f"Website data missing required field: {field}")
                return False
        return True
    
    def poll_sqs(self):
        try:
            client = get_sqs_client()
            
            if AWS_SQS_URL_PRIORITY_WEBSITES:
                try:
                    response = client.receive_message(
                        QueueUrl=AWS_SQS_URL_PRIORITY_WEBSITES,
                        MaxNumberOfMessages=1,
                        WaitTimeSeconds=0
                    )
                    
                    if 'Messages' in response and len(response['Messages']) > 0:
                        message = response['Messages'][0]
                        receipt_handle = message['ReceiptHandle']
                        body = json.loads(message['Body'])
                        body['is_priority'] = True
                        
                        # Validate region first
                        if not self._is_message_for_this_region(body):
                            message_region = body.get('scrape_region', 'ap-south-1')
                            print(f"Skipping priority website (region {message_region} != {self.node_region})")
                            self._return_message_to_queue(client, AWS_SQS_URL_PRIORITY_WEBSITES, receipt_handle, body.get('url', 'unknown'))
                            return None
                        
                        # Validate required fields before deleting
                        if not self._validate_website_data(body):
                            print(f"Invalid priority website data, returning to queue: {body.get('url', 'unknown')}")
                            self._return_message_to_queue(client, AWS_SQS_URL_PRIORITY_WEBSITES, receipt_handle, body.get('url', 'unknown'))
                            return None
                        
                        # All validations passed - delete message from queue
                        try:
                            client.delete_message(
                                QueueUrl=AWS_SQS_URL_PRIORITY_WEBSITES,
                                ReceiptHandle=receipt_handle
                            )
                            print(f"✅ Received PRIORITY website from SQS and deleted message (region: {self.node_region}, website_id: {body.get('id')})")
                            return body
                        except Exception as delete_error:
                            print(f"❌ Failed to delete priority message from queue: {delete_error}")
                            # Return message to queue if deletion fails
                            self._return_message_to_queue(client, AWS_SQS_URL_PRIORITY_WEBSITES, receipt_handle, body.get('url', 'unknown'))
                            return None
                except Exception as e:
                    print(f"Error polling priority SQS: {e}")
            
            if AWS_SQS_URL_WEBSITES:
                try:
                    response = client.receive_message(
                        QueueUrl=AWS_SQS_URL_WEBSITES,
                        MaxNumberOfMessages=1,
                        WaitTimeSeconds=0
                    )
                    
                    if 'Messages' in response and len(response['Messages']) > 0:
                        message = response['Messages'][0]
                        receipt_handle = message['ReceiptHandle']
                        body = json.loads(message['Body'])
                        body['is_priority'] = False
                        
                        # Validate region first
                        if not self._is_message_for_this_region(body):
                            message_region = body.get('scrape_region', 'ap-south-1')
                            print(f"Skipping website (region {message_region} != {self.node_region})")
                            self._return_message_to_queue(client, AWS_SQS_URL_WEBSITES, receipt_handle, body.get('url', 'unknown'))
                            return None
                        
                        # Validate required fields before deleting
                        if not self._validate_website_data(body):
                            print(f"Invalid website data, returning to queue: {body.get('url', 'unknown')}")
                            self._return_message_to_queue(client, AWS_SQS_URL_WEBSITES, receipt_handle, body.get('url', 'unknown'))
                            return None
                        
                        # All validations passed - delete message from queue
                        try:
                            client.delete_message(
                                QueueUrl=AWS_SQS_URL_WEBSITES,
                                ReceiptHandle=receipt_handle
                            )
                            print(f"✅ Received website from SQS and deleted message (region: {self.node_region}, website_id: {body.get('id')})")
                            return body
                        except Exception as delete_error:
                            print(f"❌ Failed to delete message from queue: {delete_error}")
                            # Return message to queue if deletion fails
                            self._return_message_to_queue(client, AWS_SQS_URL_WEBSITES, receipt_handle, body.get('url', 'unknown'))
                            return None
                except Exception as e:
                    print(f"Error polling regular SQS: {e}")
            
            return None
        except Exception as e:
            print(f"Error in poll_sqs: {e}")
            return None
    
    def update_website_status(self, website_id, status, reason=None):
        try:
            if not website_id:
                print("No website_id provided, skipping status update")
                return False
            
            url = f"{MASTER_API_URL}/websites/{website_id}/status"
            payload = {"status": status}
            if reason is not None:
                payload["reason"] = reason
            
            print(f"PATCH {url} -> {payload}")
            response = requests.patch(url, json=payload, timeout=10)
            
            if response.status_code == 200:
                reason_str = f" with reason: {reason}" if reason else ""
                print(f"Updated website {website_id} status to {status}{reason_str}")
                return True
            else:
                print(f"Failed to update website status ({status}) for {website_id}: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print(f"Error updating website status: {e}")
            return False
    
    def get_product_count(self, website_id):
        """Get the count of products extracted for a website."""
        try:
            # Check PriorityBatch first (for priority scraping)
            response = requests.get(
                f"{MASTER_API_URL}/priority-batches?website_id={website_id}&limit=1",
                timeout=5
            )
            if response.status_code == 200:
                data = response.json()
                priority_count = data.get('total', 0)
                if priority_count > 0:
                    return priority_count
            
            # Check Batch table (for regular scraping)
            response = requests.get(
                f"{MASTER_API_URL}/batches?website_id={website_id}",
                timeout=5
            )
            if response.status_code == 200:
                batches = response.json()
                # For regular scraping, we can't easily count products from batches
                # But if there are batches, we assume products were extracted
                if len(batches) > 0:
                    return 1  # At least one batch means products were processed
            
            return 0
        except Exception as e:
            print(f"Error getting product count: {e}")
            return 0
    
    def mark_progress(self):
        """Mark that progress was made (a page was successfully processed)"""
        self.last_progress_time = datetime.now(timezone.utc)
    
    def check_no_progress_timeout(self):
        """Check if no progress has been made for the timeout period"""
        if not self.is_scraping or not self.current_website_id:
            return False
        
        if not self.last_progress_time:
            # If we just started, give it some time
            if self.website_start_time:
                elapsed = (datetime.now(timezone.utc) - self.website_start_time).total_seconds()
                if elapsed < self.NO_PROGRESS_TIMEOUT_SECONDS:
                    return False
            # No progress time set and enough time has passed since start
            return True
        
        elapsed = (datetime.now(timezone.utc) - self.last_progress_time).total_seconds()
        return elapsed >= self.NO_PROGRESS_TIMEOUT_SECONDS
    
    def handle_no_progress_timeout(self):
        """Handle no progress timeout - mark website rejected and terminate node"""
        if not self.is_scraping or not self.current_website_id:
            return False
        
        website_id = self.current_website_id
        website_url = self.current_url
        
        timeout_minutes = self.NO_PROGRESS_TIMEOUT_SECONDS // 60
        print(f"⚠️ No progress detected for {self.NO_PROGRESS_TIMEOUT_SECONDS} seconds ({timeout_minutes} minutes) on website {website_id}. Marking as rejected and terminating node...")
        
        # Stop the scraper
        if self.scraper:
            if hasattr(self.scraper, 'should_stop'):
                self.scraper.should_stop = True
                print(f"Set scraper should_stop flag for website {website_id}")
            if hasattr(self.scraper, '_stop'):
                try:
                    self.scraper._stop()
                    print(f"Called scraper._stop() for website {website_id}")
                except Exception as e:
                    print(f"Error calling scraper._stop(): {e}")
        
        # Temporarily disable auto-rejection/termination on no-progress.
        # We only want manual termination from the dashboard to mark websites as rejected.
        print(
            f"⚠️ No progress detected for {self.NO_PROGRESS_TIMEOUT_SECONDS} seconds "
            f"({timeout_minutes} minutes) on website {website_id}, "
            "but auto-reject/terminate is DISABLED (manual action required)."
        )
        return False
    
    def terminate_current_website(self):
        """Terminate the current website if it's been running too long"""
        # Temporarily disable auto-termination based on max processing time.
        # Termination/rejection should only happen via manual actions in the dashboard.
        return False
    
    def scrape_website(self, website_data):
        website_id = website_data.get('id')
        url = website_data.get('url')
        website_type = website_data.get('type')
        validator = website_data.get('validator')
        is_priority = website_data.get('is_priority', False)
        scrape_region = website_data.get('scrape_region', 'ap-south-1')
        # Temporarily disable sample/pause behavior – always scrape fully without pausing for manual review
        sample_needed = False
        
        if not url:
            print("No URL provided in website data")
            self.is_scraping = False
            return
        
        full_url = url if url.startswith(('http://', 'https://')) else f"https://{url}"
        
        mode = "PRIORITY" if is_priority else "REGULAR"
        print(f"Starting {mode} scraper for website ID: {website_id}, URL: {full_url}")
        
        if not validator and url:
            try:
                resp = requests.get(f"{MASTER_API_URL}/websites/{url}", timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    validator = data.get('validator')
                    if validator:
                        print("Validator fetched from master API")
                    else:
                        print("No validator set on master API")
                else:
                    print(f"Failed to fetch website from master API: {resp.status_code}")
            except Exception as e:
                print(f"Error fetching validator from master API: {e}")
        
        extraction_prompt = get_region_specific_prompt(scrape_region)
        if scrape_region and scrape_region != 'ap-south-1':
            print(f"Using region-specific prompt for {scrape_region} (hardcoded country/currency)")
        
        # With sample handling disabled, always scrape without a sample limit
        effective_sample_size = None
        print(f"Sample/pause logic disabled for website {website_id} - scraping without sample limit")
        
        was_terminated = False
        validation_failures_exceeded = False
        try:
            self.update_website_status(website_id, 'processing')
            self.website_start_time = datetime.now(timezone.utc)
            self.last_progress_time = None
            print(f"Started processing website {website_id} at {self.website_start_time}")
            
            if is_priority:
                scraper = PriorityScraper(
                    start_url=full_url,
                    system_prompt=extraction_prompt,
                    selector=validator,
                    num_threads=10,
                    website_id=website_id,
                    progress_callback=self.mark_progress,
                    sample_size=effective_sample_size,
                    sample_completion_callback=None  # disable sample-completion pauses
                )
                print(f"Using PRIORITY scraper (iterative processing, no sample limit, sample/pause disabled)")
            else:
                scraper = Scraper(
                    start_url=full_url,
                    system_prompt=extraction_prompt,
                    selector=validator,
                    num_threads=10,
                    batch_size=BATCH_SIZE,
                    website_id=website_id,
                    progress_callback=self.mark_progress
                )
                print(f"Using REGULAR scraper (batch processing with size {BATCH_SIZE})")
            
            self.scraper = scraper
            scraper.crawl()
            
            # Check if scraper was stopped due to validation failures or other reasons
            validation_failures_exceeded = False
            if hasattr(scraper, 'validation_failures') and hasattr(scraper, 'max_validation_failures'):
                if scraper.validation_failures >= scraper.max_validation_failures:
                    validation_failures_exceeded = True
                    print(f"Validation failures exceeded: {scraper.validation_failures}/{scraper.max_validation_failures}")
            
            if hasattr(scraper, 'should_stop') and scraper.should_stop:
                if self.current_website_id != website_id:
                    was_terminated = True
                    print(f"{mode} scraping was terminated due to timeout for website ID: {website_id}")
                else:
                    print(f"{mode} scraping was stopped for website ID: {website_id}")
            else:
                print(f"{mode} scraping completed for website ID: {website_id}")
        except requests.exceptions.HTTPError as e:
            # Handle HTTP errors like 403, blocked, etc., but DO NOT auto-reject.
            error_code = getattr(e.response, 'status_code', None) if hasattr(e, 'response') else None
            if error_code == 403:
                reason = "HTTP 403 Forbidden - Access blocked by website"
            elif error_code == 429:
                reason = "HTTP 429 Too Many Requests - Rate limited by website"
            else:
                reason = f"HTTP error during scraping: {str(e)}"
            print(f"HTTP error during scraping for website ID {website_id}: {reason} (auto-reject disabled)")
            was_terminated = True
        except Exception as e:
            # Log scraping errors but DO NOT auto-reject. Manual review/termination will handle these.
            print(f"Error during scraping for website ID {website_id}: {e} (auto-reject disabled)")
            was_terminated = True
        finally:
            try:
                if not was_terminated and self.current_website_id == website_id:
                    # Auto status transitions are simplified:
                    # - We still mark successful runs as completed
                    # - We NEVER auto-mark as rejected here; that must be done manually via the dashboard
                    try:
                        resp = requests.get(f"{MASTER_API_URL}/websites/{url}", timeout=5)
                        if resp.status_code == 200:
                            website_status = resp.json().get('status')
                            if website_status == 'paused':
                                print(f"Website {website_id} is paused. Skipping status update (manual control).")
                            else:
                                self.update_website_status(website_id, 'completed')
                        else:
                            # If we can't check status, still consider it completed (no auto-rejects)
                            self.update_website_status(website_id, 'completed')
                    except Exception as e:
                        print(f"Error checking website status before updating: {e}")
                        # Fallback: best-effort mark as completed, but never rejected automatically
                        self.update_website_status(website_id, 'completed')
            except Exception as status_error:
                print(f"Error updating status after scraping: {status_error}")
            finally:
                if self.current_website_id == website_id:
                    # Always clear tracking; sample/pause flow is disabled
                    self.is_scraping = False
                    self.current_website_id = None
                    self.current_url = None
                    self.website_start_time = None
                    self.last_progress_time = None
                    self.is_paused_for_sample = False
    
    def start_scraping_thread(self, website_data):
        self.scraper_thread = threading.Thread(
            target=self.scrape_website,
            args=(website_data,)
        )
        self.scraper_thread.daemon = True
        self.scraper_thread.start()
    
    def run(self):
        print(f"Worker started. Polling SQS every {POLL_INTERVAL} seconds...")
        print(f"Master API URL: {MASTER_API_URL}")
        print(f"Batch Size: {BATCH_SIZE}")
        print(f"Node Region: {self.node_region} (will only process websites for this region)")
        print("Auto-terminate & auto-reject logic is DISABLED (only manual termination from dashboard will reject websites).")
        print("Sample/pause logic is DISABLED (websites will not be auto-paused for manual review).")
        
        while True:
            try:
                now = time.time()
                if now - self._last_heartbeat >= HEARTBEAT_INTERVAL:
                    self._send_heartbeat()
                    self._last_heartbeat = now
                
                # Auto termination / rejection is disabled; we only maintain heartbeats while scraping
                
                if not self.is_scraping:
                    website_data = self.poll_sqs()
                    
                    if website_data:
                        website_id = website_data.get('id')
                        print(f"Received website from SQS: {website_data}")
                        
                        self.update_website_status(website_id, 'processing')
                        
                        self.is_scraping = True
                        self.current_website_id = website_id
                        self.current_url = website_data.get('url')
                        self._ensure_instance_identity()
                        self._notify_master_event("scrape_started", {
                            "website_id": website_id,
                            "website_url": self.current_url,
                            "node_instance_id": self.instance_id
                        })
                        
                        self.start_scraping_thread(website_data)
                
                if self.is_scraping and self.scraper_thread and not self.scraper_thread.is_alive():
                    print("Scraping thread completed, cleaning up")
                    self.current_website_id = None
                    self.current_url = None
                    self.scraper = None
                    self.scraper_thread = None
                    self.website_start_time = None
                    self.last_progress_time = None
                
                time.sleep(POLL_INTERVAL)
                
            except KeyboardInterrupt:
                print("\nWorker stopped by user")
                break
            except Exception as e:
                print(f"Error in worker loop: {e}")
                time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    # Setup logging to send to master API
    setup_logging()
    
    worker = ScrapingWorker()
    worker.run()

