from fastapi import FastAPI
from contextlib import asynccontextmanager
from .endpoints import router as api_router
from database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    from services.batch_listener import get_batch_listener
    from services.priority_batch_listener import get_priority_batch_listener
    from services.node_monitor import get_node_monitor
    from services.product_sync_service import get_sync_service
    from config.settings import NODE_MONITOR_INTERVAL, NODE_STALE_AFTER_SECONDS
    
    init_db()
    
    batch_listener = get_batch_listener()
    batch_listener.start()
    
    priority_batch_listener = get_priority_batch_listener()
    priority_batch_listener.start()
    
    node_monitor = get_node_monitor(NODE_MONITOR_INTERVAL, NODE_STALE_AFTER_SECONDS)
    node_monitor.start()
    
    product_sync_service = get_sync_service()
    product_sync_service.start()
    print("✅ Product Sync Service started and running in background")
    
    yield
    
    batch_listener.stop()
    priority_batch_listener.stop()
    node_monitor.stop()
    product_sync_service.stop()


app = FastAPI(
    title="Distributed Orchestration API",
    description="API for managing distributed website processing",
    version="1.0.0",
    lifespan=lifespan
)

app.include_router(api_router, prefix="/api/v1")

@app.get("/")
async def root():
    return {"message": "Welcome to the Distributed Orchestration API"}

