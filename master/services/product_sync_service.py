import threading
import time
import json
import requests
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from database import SessionLocal
from models import PriorityBatch
from config.settings import SYNC_INTERVAL, SYNC_BATCH_SIZE, BACKEND_API_URL


class ProductSyncService:
    """
    Background service that periodically syncs priority batch products to the backend API.
    Fetches all unsynced priority batches and sends them to the backend /product/sync endpoint.
    Processes in batches of SYNC_BATCH_SIZE, sending oldest products first.
    """
    
    def __init__(self, interval: int = SYNC_INTERVAL, batch_size: int = SYNC_BATCH_SIZE):
        self.interval = interval
        self.batch_size = batch_size
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.backend_url = f"{BACKEND_API_URL}/api/product/sync"
        self._last_sync_time: Optional[datetime] = None
        self._last_sync_count: int = 0
        print(f"ProductSyncService initialized with interval={interval}s, batch_size={batch_size}, backend_url={self.backend_url}")
    
    def is_running(self) -> bool:
        """Check if the sync service is currently running."""
        return self._thread is not None and self._thread.is_alive()
    
    def get_status(self) -> dict:
        """Get the current status of the sync service."""
        db: Session = SessionLocal()
        try:
            total_unsynced = db.query(PriorityBatch).filter(
                PriorityBatch.sync == False
            ).count()
            total_synced = db.query(PriorityBatch).filter(
                PriorityBatch.sync == True
            ).count()
        except Exception as e:
            print(f"Error getting sync status: {e}")
            total_unsynced = 0
            total_synced = 0
        finally:
            db.close()
        
        return {
            "running": self.is_running(),
            "interval_seconds": self.interval,
            "batch_size": self.batch_size,
            "backend_url": self.backend_url,
            "total_unsynced": total_unsynced,
            "total_synced": total_synced,
            "last_sync_time": self._last_sync_time.isoformat() if self._last_sync_time else None,
            "last_sync_count": self._last_sync_count
        }
    
    def start(self):
        """Start the sync service in a background thread."""
        if self._thread is not None and self._thread.is_alive():
            print("ProductSyncService already running")
            return
        
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        print("ProductSyncService started")
    
    def stop(self):
        """Stop the sync service."""
        if self._thread is None or not self._thread.is_alive():
            print("ProductSyncService not running")
            return
        
        print("Stopping ProductSyncService...")
        self._stop_event.set()
        self._thread.join(timeout=5)
        print("ProductSyncService stopped")
    
    def _run(self):
        """Main loop that runs in the background thread."""
        while not self._stop_event.is_set():
            try:
                self._sync_products()
            except Exception as e:
                print(f"Error in ProductSyncService: {e}")
            
            # Wait for the next interval or until stop is called
            self._stop_event.wait(self.interval)
    
    def _sync_products(self):
        """Fetch unsynced products and send to backend API in batches."""
        db: Session = SessionLocal()
        
        try:
            # Count total unsynced batches
            total_unsynced = db.query(PriorityBatch).filter(
                PriorityBatch.sync == False
            ).count()
            
            if total_unsynced == 0:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] No unsynced products found")
                return
            
            # Fetch oldest unsynced batches up to batch_size limit
            unsynced_batches = db.query(PriorityBatch).filter(
                PriorityBatch.sync == False
            ).order_by(PriorityBatch.created_at.asc()).limit(self.batch_size).all()
            
            remaining = total_unsynced - len(unsynced_batches)
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Found {total_unsynced} unsynced products total, syncing oldest {len(unsynced_batches)} now" + 
                  (f" ({remaining} remaining for next sync)" if remaining > 0 else ""))
            
            # Transform priority batches to backend product format
            products = []
            batch_ids = []
            
            for batch in unsynced_batches:
                try:
                    # Parse the result JSON
                    result_data = json.loads(batch.result)
                    
                    # Transform to backend expected format
                    product = {
                        'product_name': result_data.get('product_name', ''),
                        'product_description': result_data.get('product_description', ''),
                        'product_url': result_data.get('product_url', batch.url),
                        'product_id': result_data.get('product_id', ''),
                        'product_images': result_data.get('product_images', []),
                        'product_price': result_data.get('product_price', '0'),
                        'product_brand_name': result_data.get('product_brand_name', ''),
                        'product_category': result_data.get('product_category', 'Uncategorized'),
                        'country_code': result_data.get('country_code', 'US'),
                        'website_logo': result_data.get('website_logo', None)
                    }
                    
                    products.append(product)
                    batch_ids.append(batch.id)
                    
                except json.JSONDecodeError as e:
                    print(f"Error parsing result JSON for batch {batch.id}: {e}")
                    continue
                except Exception as e:
                    print(f"Error transforming batch {batch.id}: {e}")
                    continue
            
            if not products:
                print("No valid products to sync after transformation")
                return
            
            # Send products to backend API
            try:
                print(f"Sending {len(products)} products to {self.backend_url}")
                
                response = requests.post(
                    self.backend_url,
                    json={'products': products},
                    headers={'Content-Type': 'application/json'},
                    timeout=30
                )
                
                if response.status_code == 200:
                    result = response.json()
                    print(f"✅ Sync successful: {result.get('summary', {})}")
                    
                    # Mark batches as synced
                    db.query(PriorityBatch).filter(
                        PriorityBatch.id.in_(batch_ids)
                    ).update(
                        {PriorityBatch.sync: True},
                        synchronize_session=False
                    )
                    db.commit()
                    print(f"✅ Marked {len(batch_ids)} batches as synced")
                    
                    # Update status tracking
                    self._last_sync_time = datetime.now()
                    self._last_sync_count = len(batch_ids)
                    
                else:
                    print(f"❌ Sync failed with status {response.status_code}: {response.text}")
                    
            except requests.exceptions.RequestException as e:
                print(f"❌ Error sending products to backend: {e}")
            except Exception as e:
                print(f"❌ Unexpected error during sync: {e}")
                
        except Exception as e:
            print(f"Error fetching unsynced batches: {e}")
        finally:
            db.close()


# Global instance
_sync_service: Optional[ProductSyncService] = None


def get_sync_service() -> ProductSyncService:
    """Get or create the global sync service instance."""
    global _sync_service
    if _sync_service is None:
        _sync_service = ProductSyncService()
    return _sync_service


def start_sync_service():
    """Start the product sync service."""
    service = get_sync_service()
    service.start()


def stop_sync_service():
    """Stop the product sync service."""
    global _sync_service
    if _sync_service is not None:
        _sync_service.stop()

