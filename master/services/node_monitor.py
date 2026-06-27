import threading
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from database import SessionLocal
from models import Node, Website
from services.ec2_manager import terminate_instance
from config.settings import AWS_REGION


class NodeMonitor:
    def __init__(self, check_interval_seconds: int = 240, stale_after_seconds: int = 180):
        self.check_interval_seconds = check_interval_seconds
        self.stale_after_seconds = stale_after_seconds
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def _mark_dead_and_terminate(self, db: Session, node: Node):
        try:
            # Check if node is processing a website and reset its status
            if node.current_website_id is not None:
                db_website = db.query(Website).filter(Website.id == node.current_website_id).first()
                if db_website and db_website.status == 'processing':
                    db_website.status = 'ready'
                    print(f"Website {db_website.id} ({db_website.url}) status changed from 'processing' to 'ready' due to node termination")
            
            # Clear the current website from the node
            node.current_website_id = None
            
            if node.status != 'dead':
                node.status = 'dead'
                db.commit()
            try:
                terminate_instance(node.instance_id)
                print(f"Terminate requested for instance {node.instance_id}")
            except Exception as e:
                print(f"Terminate attempt for {node.instance_id} ignored: {e}")
        except Exception as e:
            db.rollback()
            print(f"Error updating node {node.id} to dead: {e}")

    def _tick(self):
        db = SessionLocal()
        try:
            now = datetime.now(timezone.utc)
            stale_before = now - timedelta(seconds=self.stale_after_seconds)
            nodes = db.query(Node).filter(Node.status.in_(['alive', 'processing'])).all()
            for node in nodes:
                try:
                    if node.last_seen is None or node.last_seen < stale_before:
                        self._mark_dead_and_terminate(db, node)
                    elif node.null_heartbeat_count >= 5:
                        print(f"Node {node.instance_id} has {node.null_heartbeat_count} consecutive null heartbeats. Terminating...")
                        self._mark_dead_and_terminate(db, node)
                except Exception as e:
                    print(f"Error processing node {getattr(node, 'id', '?')}: {e}")
        finally:
            db.close()

    def _run(self):
        print(f"Node monitor started. Interval: {self.check_interval_seconds}s, stale after: {self.stale_after_seconds}s")
        while self._running:
            try:
                self._tick()
            except Exception as e:
                print(f"Node monitor loop error: {e}")
            time.sleep(self.check_interval_seconds)

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        if not self._running:
            return
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)


_monitor_instance: Optional[NodeMonitor] = None


def get_node_monitor(check_interval_seconds: int = 240, stale_after_seconds: int = 180) -> NodeMonitor:
    global _monitor_instance
    if _monitor_instance is None:
        _monitor_instance = NodeMonitor(check_interval_seconds, stale_after_seconds)
    return _monitor_instance


