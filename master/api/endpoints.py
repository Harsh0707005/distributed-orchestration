from fastapi import APIRouter, Depends, HTTPException, status, Query, Response
from sqlalchemy.orm import Session
from pydantic import BaseModel, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from urllib.parse import urlparse
import os
import threading
from openai import OpenAI

from models import Website, Node, Task, Batch, PriorityBatch, NodeLog, NotificationSetting, SystemSetting, Base
from database import SessionLocal, engine
from services.ec2_manager import launch_instance_from_template, get_instance_details, terminate_instance
from services.notification_service import (
    get_notification_emails,
    update_notification_emails,
    send_notification_email,
)
from config.settings import LAUNCH_TEMPLATE_ID

Base.metadata.create_all(bind=engine)

def get_domain(url: str) -> str:
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        return domain
    except Exception:
        raise ValueError("Invalid URL format")

router = APIRouter()


def build_notification_email(event_type: str, data: Dict[str, Any]) -> Dict[str, str]:
    website_id = data.get("website_id")
    website_url = data.get("website_url")
    node_instance_id = data.get("node_instance_id")
    extra_message = data.get("message")

    if event_type == "scrape_started":
        subject = "[Orchestration] Scrape started"
        body = (
            f"A slave node has started scraping.\n"
            f"Website ID: {website_id or 'N/A'}\n"
            f"Website URL: {website_url or 'N/A'}\n"
            f"Node Instance: {node_instance_id or 'Unknown'}\n"
        )
    elif event_type == "scrape_auto_terminated":
        subject = "[Orchestration] Scrape auto-terminated"
        body = (
            f"A scrape was terminated automatically after exceeding the allowed time.\n"
            f"Website ID: {website_id or 'N/A'}\n"
            f"Website URL: {website_url or 'N/A'}\n"
            f"Node Instance: {node_instance_id or 'Unknown'}\n"
        )
    elif event_type == "node_launched":
        subject = "[Orchestration] New node launched"
        body = (
            f"A new slave node has been launched.\n"
            f"Instance ID: {node_instance_id or 'Unknown'}\n"
            f"Details: {extra_message or 'N/A'}\n"
        )
    elif event_type == "node_terminated":
        subject = "[Orchestration] Node termination initiated"
        body = (
            f"A slave node termination was requested.\n"
            f"Instance ID: {node_instance_id or 'Unknown'}\n"
            f"Reason: {extra_message or 'N/A'}\n"
        )
    else:
        subject = f"[Orchestration] Event: {event_type}"
        body = extra_message or "No additional details provided."

    return {"subject": subject, "body": body}

@router.get("/health/sync")
def get_sync_status():
    from services.product_sync_service import get_sync_service
    
    service = get_sync_service()
    status = service.get_status()
    
    return {
        "service": "product_sync",
        "status": status
    }

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class CountryInfo(BaseModel):
    country: str
    url: Optional[str] = None


class WebsiteCreate(BaseModel):
    url: str
    country_info: Optional[List[CountryInfo]] = None
    scrape_region: Optional[str] = "ap-south-1"  # AWS region to scrape from, defaults to Mumbai
    
    @field_validator('url')
    @classmethod
    def validate_url(cls, v: str) -> str:
        try:
            return get_domain(v)
        except ValueError as e:
            raise ValueError(str(e))

class WebsiteResponse(BaseModel):
    id: int
    url: str
    status: str
    validator: Optional[str] = None
    type: Optional[str] = None
    priority: bool = False
    country_info: Optional[List[Dict[str, Any]]] = None
    scrape_region: Optional[str] = "ap-south-1"
    reason: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class NotificationSettings(BaseModel):
    emails: List[str]


class NotificationEvent(BaseModel):
    event_type: str
    website_id: Optional[int] = None
    website_url: Optional[str] = None
    node_instance_id: Optional[str] = None
    message: Optional[str] = None

class ValidatorUpdate(BaseModel):
    url: str
    validator: str
    type: Optional[str] = None
    priority: bool = False

@router.post("/websites/", response_model=WebsiteResponse)
def create_website(website: WebsiteCreate, db: Session = Depends(get_db)):
    domain = website.url
    country_info = [info.model_dump() for info in website.country_info] if website.country_info else None
    scrape_region = website.scrape_region or "ap-south-1"
    
    db_website = db.query(Website).filter(Website.url == domain).first()
    if db_website:
        raise HTTPException(status_code=400, detail="Website already exists")
    
    current_time = datetime.now(timezone.utc)
    db_website = Website(
        url=domain,
        status='pending_validator',
        validator=None,
        type=None,
        country_info=country_info,
        scrape_region=scrape_region,
        created_at=current_time,
        updated_at=current_time
    )
    
    db.add(db_website)
    db.commit()
    db.refresh(db_website)
    
    # Don't auto-launch nodes for non-default regions unless priority is set
    # Priority can only be set later via update_validator endpoint
    # So we skip auto-launch here and let update_validator handle it when priority is set
    
    return db_website


@router.get("/settings/notifications", response_model=NotificationSettings)
def get_notification_settings(db: Session = Depends(get_db)):
    emails = get_notification_emails(db)
    return {"emails": emails}


@router.post("/settings/notifications", response_model=NotificationSettings)
def update_notification_settings_endpoint(
    payload: NotificationSettings,
    db: Session = Depends(get_db)
):
    normalized_emails = []
    for email in payload.emails:
        cleaned = email.strip()
        if cleaned and cleaned not in normalized_emails:
            normalized_emails.append(cleaned)
    settings = update_notification_emails(db, normalized_emails)
    return {"emails": settings.emails or []}

@router.patch("/websites/validator", response_model=WebsiteResponse)
def update_validator(
    update_data: ValidatorUpdate,
    db: Session = Depends(get_db)
):
    db_website = db.query(Website).filter(Website.url == update_data.url).first()
    if not db_website:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Website with URL '{update_data.url}' not found"
        )
    
    db_website.validator = update_data.validator
    if update_data.type:
        db_website.type = update_data.type
    
    was_priority = db_website.priority
    db_website.priority = update_data.priority
    db_website.status = 'ready'
    db_website.updated_at = datetime.now(timezone.utc)
    
    try:
        db.commit()
        db.refresh(db_website)
        
        if update_data.priority and not was_priority:
            # When priority is set, launch a node in the website's region
            website_region = db_website.scrape_region or 'ap-south-1'
            
            def launch_priority_node():
                try:
                    node_db = SessionLocal()
                    try:
                        next_node_number = node_db.query(Node).count() + 1
                        node_name = f"Orchestration Slave - Node {next_node_number} ({website_region})"
                        
                        print(f"Auto-launching EC2 instance in {website_region} for priority website: {db_website.url}")
                        instance_info = launch_instance_from_template(
                            launch_template_name="orchestration-slave",
                            region=website_region,
                            tags={'Name': node_name}
                        )
                        
                        if instance_info:
                            instance_id = instance_info.get('instance_id')
                            ip_address = instance_info.get('public_ip', 'pending')
                            
                            new_node = Node(
                                instance_id=instance_id,
                                ip_address=ip_address,
                                region=website_region,
                                status='processing',
                                last_seen=datetime.now(timezone.utc),
                                created_at=datetime.now(timezone.utc)
                            )
                            node_db.add(new_node)
                            node_db.commit()
                            print(f"Successfully launched node {instance_id} in {website_region} for priority website {db_website.url}")
                        else:
                            print(f"Failed to launch EC2 instance in {website_region} for priority website {db_website.url}")
                    except Exception as e:
                        node_db.rollback()
                        print(f"Error creating node in database: {e}")
                    finally:
                        node_db.close()
                except Exception as e:
                    print(f"Error in launch_priority_node: {e}")
            
            thread = threading.Thread(target=launch_priority_node)
            thread.daemon = True
            thread.start()
            print(f"Initiated automatic EC2 launch in {website_region} for priority website: {db_website.url}")
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating validator: {str(e)}"
        )
    
    return db_website

@router.get("/websites/{url}", response_model=WebsiteResponse)
def read_website(url: str, db: Session = Depends(get_db)):
    db_website = db.query(Website).filter(Website.url == url).first()
    if db_website is None:
        raise HTTPException(status_code=404, detail="Website not found")
    return db_website

class WebsiteStatusUpdate(BaseModel):
    status: str
    reason: Optional[str] = None

@router.patch("/websites/{website_id}/status", response_model=WebsiteResponse)
def update_website_status(
    website_id: int,
    status_data: WebsiteStatusUpdate,
    db: Session = Depends(get_db)
):
    db_website = db.query(Website).filter(Website.id == website_id).first()
    if not db_website:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Website with ID '{website_id}' not found"
        )
    
    if status_data.status not in ['pending_validator', 'ready', 'in_queue', 'processing', 'completed', 'terminated', 'rejected']:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status: {status_data.status}"
        )
    
    db_website.status = status_data.status
    if status_data.reason is not None:
        db_website.reason = status_data.reason
    db_website.updated_at = datetime.now(timezone.utc)
    
    try:
        db.commit()
        db.refresh(db_website)
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating website status: {str(e)}"
        )
    
    return db_website

class PaginatedWebsitesResponse(BaseModel):
    items: List[WebsiteResponse]
    total: int
    page: int
    page_size: int

@router.get("/websites", response_model=PaginatedWebsitesResponse)
def get_all_websites(
    status: Optional[str] = Query(None, enum=["pending_validator", "ready", "in_queue", "processing", "completed", "terminated"]),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db)
):
    query = db.query(Website)

    if status:
        query = query.filter(Website.status == status)

    offset = (page - 1) * page_size
    items = query.order_by(Website.created_at.desc()).offset(offset).limit(page_size).all()
    total = query.count()
    
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size
    }

class NodeRegister(BaseModel):
    instance_id: str
    ip_address: str

class NodeResponse(BaseModel):
    id: int
    instance_id: str
    ip_address: str
    region: Optional[str] = "ap-south-1"
    status: str
    last_seen: Optional[datetime] = None
    cpu_usage: Optional[float] = None
    memory_usage: Optional[float] = None
    current_website_id: Optional[int] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True

@router.post("/nodes/register", response_model=NodeResponse)
def register_node(node_data: NodeRegister, db: Session = Depends(get_db)):
    db_node = db.query(Node).filter(Node.instance_id == node_data.instance_id).first()
    
    if db_node:
        if db_node.ip_address != node_data.ip_address:
            db_node.ip_address = node_data.ip_address
        db_node.status = 'alive'
        db_node.last_seen = datetime.now(timezone.utc)
        db.commit()
        db.refresh(db_node)
        return db_node
    
    current_time = datetime.now(timezone.utc)
    db_node = Node(
        instance_id=node_data.instance_id,
        ip_address=node_data.ip_address,
        status='alive',
        last_seen=current_time,
        created_at=current_time
    )
    
    db.add(db_node)
    db.commit()
    db.refresh(db_node)
    
    return db_node

class TaskAssign(BaseModel):
    node_id: int
    website_id: int

class TaskResponse(BaseModel):
    id: int
    node_id: int
    website_id: int
    status: str
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True

@router.post("/tasks/assign", response_model=TaskResponse)
def assign_task(task_data: TaskAssign, db: Session = Depends(get_db)):
    db_node = db.query(Node).filter(Node.id == task_data.node_id).first()
    if not db_node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Node with ID '{task_data.node_id}' not found"
        )
    
    db_website = db.query(Website).filter(Website.id == task_data.website_id).first()
    if not db_website:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Website with ID '{task_data.website_id}' not found"
        )
    
    existing_task = db.query(Task).filter(
        Task.node_id == task_data.node_id,
        Task.website_id == task_data.website_id,
        Task.status == 'processing'
    ).first()
    
    if existing_task:
        return existing_task
    
    current_time = datetime.now(timezone.utc)
    db_task = Task(
        node_id=task_data.node_id,
        website_id=task_data.website_id,
        status='processing',
        created_at=current_time
    )
    
    db.add(db_task)
    db.commit()
    db.refresh(db_task)
    
    return db_task

class NodeHeartbeat(BaseModel):
    instance_id: str
    ip_address: Optional[str] = None
    cpu_usage: Optional[float] = None
    memory_usage: Optional[float] = None
    current_website_id: Optional[int] = None

@router.post("/nodes/heartbeat", response_model=NodeResponse)
def node_heartbeat(heartbeat_data: NodeHeartbeat, db: Session = Depends(get_db)):
    db_node = db.query(Node).filter(Node.instance_id == heartbeat_data.instance_id).first()
    if not db_node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Node with instance_id '{heartbeat_data.instance_id}' not found. Please register first."
        )
    
    if heartbeat_data.ip_address and db_node.ip_address != heartbeat_data.ip_address:
        db_node.ip_address = heartbeat_data.ip_address
    
    if heartbeat_data.cpu_usage is not None:
        db_node.cpu_usage = heartbeat_data.cpu_usage
    
    if heartbeat_data.memory_usage is not None:
        db_node.memory_usage = heartbeat_data.memory_usage
    
    if heartbeat_data.current_website_id is not None:
        website_exists = db.query(Website).filter(Website.id == heartbeat_data.current_website_id).first()
        if website_exists:
            db_node.current_website_id = heartbeat_data.current_website_id
        else:
            db_node.current_website_id = None
        db_node.null_heartbeat_count = 0
    else:
        db_node.current_website_id = None
        db_node.null_heartbeat_count = db_node.null_heartbeat_count + 1
    
    resume_command = db_node.resume_command
    
    db_node.status = 'alive'
    db_node.last_seen = datetime.now(timezone.utc)
    db.commit()
    db.refresh(db_node)
    
    response_data = {
        "id": db_node.id,
        "instance_id": db_node.instance_id,
        "ip_address": db_node.ip_address,
        "region": db_node.region,
        "status": db_node.status,
        "last_seen": db_node.last_seen,
        "cpu_usage": db_node.cpu_usage,
        "memory_usage": db_node.memory_usage,
        "current_website_id": db_node.current_website_id,
        "created_at": db_node.created_at,
        "resume_command": resume_command
    }
    
    return response_data

@router.get("/nodes", response_model=List[NodeResponse])
def get_all_nodes(db: Session = Depends(get_db)):
    nodes = db.query(Node).order_by(Node.last_seen.desc()).all()
    return nodes

@router.get("/nodes/{node_id}", response_model=NodeResponse)
def get_node(node_id: int, db: Session = Depends(get_db)):
    db_node = db.query(Node).filter(Node.id == node_id).first()
    if not db_node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Node with ID '{node_id}' not found"
        )
    return db_node

class LaunchNodeRequest(BaseModel):
    region: Optional[str] = None

class LaunchNodeResponse(BaseModel):
    success: bool
    message: str
    node: Optional[NodeResponse] = None
    instance_details: Optional[Dict[str, Any]] = None

@router.post("/nodes/launch", response_model=LaunchNodeResponse)
def launch_node(launch_request: Optional[LaunchNodeRequest] = None, db: Session = Depends(get_db)):
    try:
        total_nodes = db.query(Node).count()
        next_number = total_nodes + 1
        instance_name = f"Orchestration Slave - Node {next_number}"
        
        region = launch_request.region if launch_request and launch_request.region else None
        launch_template_name = "orchestration-slave"

        instance_info = launch_instance_from_template(
            launch_template_name=launch_template_name,
            region=region,
            tags={"Name": instance_name}
        )
        
        if not instance_info:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to launch EC2 instance"
            )
        
        instance_id = instance_info['instance_id']
        ip_address = instance_info.get('public_ip') or instance_info.get('private_ip', 'pending')
        instance_region = instance_info.get('region') or region or 'ap-south-1'
        
        existing_node = db.query(Node).filter(Node.instance_id == instance_id).first()
        if existing_node:
            existing_node.ip_address = ip_address
            existing_node.region = instance_region
            existing_node.status = 'processing'
            existing_node.last_seen = datetime.now(timezone.utc)
            db.commit()
            db.refresh(existing_node)
            
            return LaunchNodeResponse(
                success=True,
                message=f"Instance {instance_id} already exists in database, updated",
                node=existing_node,
                instance_details=instance_info
            )
        
        new_node = Node(
            instance_id=instance_id,
            ip_address=ip_address,
            region=instance_region,
            status='processing',
            last_seen=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc)
        )
        
        db.add(new_node)
        db.commit()
        db.refresh(new_node)
        
        email_data = build_notification_email("node_launched", {
            "node_instance_id": instance_id,
            "message": f"Instance launched via API at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S %Z')}"
        })
        send_notification_email(db, email_data["subject"], email_data["body"])

        return LaunchNodeResponse(
            success=True,
            message=f"Successfully launched instance {instance_id}",
            node=new_node,
            instance_details=instance_info
        )
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error launching node: {str(e)}"
        )

@router.delete("/nodes/{node_id}/terminate")
def terminate_node(node_id: int, db: Session = Depends(get_db)):
    db_node = db.query(Node).filter(Node.id == node_id).first()
    if not db_node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Node with ID '{node_id}' not found"
        )
    
    try:
        if db_node.current_website_id is not None:
            db_website = db.query(Website).filter(Website.id == db_node.current_website_id).first()
            if db_website and db_website.status == 'processing':
                db_website.status = 'terminated'
                print(f"Website {db_website.id} ({db_website.url}) status changed to 'terminated' due to node termination")
        
        db_node.current_website_id = None
        
        node_region = db_node.region or 'ap-south-1'
        success = terminate_instance(db_node.instance_id, region=node_region)
        
        if success:
            db_node.status = 'dead'
            db.commit()

            email_data = build_notification_email("node_terminated", {
                "node_instance_id": db_node.instance_id,
                "message": f"Termination requested via API at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S %Z')}"
            })
            send_notification_email(db, email_data["subject"], email_data["body"])
            
            return {
                "success": True,
                "message": f"Instance {db_node.instance_id} termination initiated"
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to terminate instance"
            )
            
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error terminating node: {str(e)}"
        )

@router.get("/tasks", response_model=List[TaskResponse])
def get_all_tasks(
    status: Optional[str] = Query(None, enum=["processing", "completed"]),
    node_id: Optional[int] = Query(None, description="Filter by node ID"),
    website_id: Optional[int] = Query(None, description="Filter by website ID"),
    db: Session = Depends(get_db)
):
    query = db.query(Task)
    
    if status:
        query = query.filter(Task.status == status)
    if node_id:
        query = query.filter(Task.node_id == node_id)
    if website_id:
        query = query.filter(Task.website_id == website_id)
    
    tasks = query.order_by(Task.created_at.desc()).all()
    return tasks

@router.get("/tasks/{task_id}", response_model=TaskResponse)
def get_task(task_id: int, db: Session = Depends(get_db)):
    db_task = db.query(Task).filter(Task.id == task_id).first()
    if not db_task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task with ID '{task_id}' not found"
        )
    return db_task

class BatchResponse(BaseModel):
    id: int
    website_id: int
    batch_name: str
    open_ai_batch_id: Optional[str] = None
    created_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

@router.get("/batches", response_model=List[BatchResponse])
def get_batches(
    website_id: Optional[int] = Query(None, description="Filter by website ID"),
    db: Session = Depends(get_db)
):
    query = db.query(Batch)
    
    if website_id:
        query = query.filter(Batch.website_id == website_id)
    
    batches = query.order_by(Batch.created_at.desc()).all()
    return batches

@router.get("/batches/{batch_id}", response_model=BatchResponse)
def get_batch(batch_id: int, db: Session = Depends(get_db)):
    db_batch = db.query(Batch).filter(Batch.id == batch_id).first()
    if not db_batch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Batch with ID '{batch_id}' not found"
        )
    return db_batch

@router.get("/websites/{website_id}/batches", response_model=List[BatchResponse])
def get_website_batches(website_id: int, db: Session = Depends(get_db)):
    db_website = db.query(Website).filter(Website.id == website_id).first()
    if not db_website:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Website with ID '{website_id}' not found"
        )
    
    batches = db.query(Batch).filter(Batch.website_id == website_id).order_by(Batch.created_at.desc()).all()
    return batches

def get_openai_client():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OPENAI_API_KEY not configured"
        )
    return OpenAI(api_key=api_key)

class BatchStatusResponse(BaseModel):
    id: Optional[str] = None
    object: Optional[str] = None
    endpoint: Optional[str] = None
    errors: Optional[Dict[str, Any]] = None
    input_file_id: Optional[str] = None
    completion_window: Optional[str] = None
    status: Optional[str] = None
    output_file_id: Optional[str] = None
    error_file_id: Optional[str] = None
    created_at: Optional[int] = None
    in_progress_at: Optional[int] = None
    expires_at: Optional[int] = None
    finalizing_at: Optional[int] = None
    completed_at: Optional[int] = None
    failed_at: Optional[int] = None
    expired_at: Optional[int] = None
    cancelling_at: Optional[int] = None
    cancelled_at: Optional[int] = None
    request_counts: Optional[Dict[str, Any]] = None

@router.get("/batches/{batch_id}/status", response_model=BatchStatusResponse)
def get_batch_status(batch_id: int, db: Session = Depends(get_db)):
    db_batch = db.query(Batch).filter(Batch.id == batch_id).first()
    if not db_batch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Batch with ID '{batch_id}' not found"
        )
    
    if not db_batch.open_ai_batch_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Batch {batch_id} does not have an OpenAI batch ID"
        )
    
    try:
        client = get_openai_client()
        openai_batch_id = db_batch.open_ai_batch_id
        batch = client.batches.retrieve(openai_batch_id)
        
        batch_dict = batch.model_dump() if hasattr(batch, 'model_dump') else batch.to_dict() if hasattr(batch, 'to_dict') else {}
        if not batch_dict:
            batch_dict = {k: getattr(batch, k, None) for k in dir(batch) if not k.startswith('_')}
        
        return BatchStatusResponse(
            id=batch_dict.get('id'),
            object=batch_dict.get('object'),
            endpoint=batch_dict.get('endpoint'),
            errors=batch_dict.get('errors'),
            input_file_id=batch_dict.get('input_file_id'),
            completion_window=batch_dict.get('completion_window'),
            status=batch_dict.get('status'),
            output_file_id=batch_dict.get('output_file_id'),
            error_file_id=batch_dict.get('error_file_id'),
            created_at=batch_dict.get('created_at'),
            in_progress_at=batch_dict.get('in_progress_at'),
            expires_at=batch_dict.get('expires_at'),
            finalizing_at=batch_dict.get('finalizing_at'),
            completed_at=batch_dict.get('completed_at'),
            failed_at=batch_dict.get('failed_at'),
            expired_at=batch_dict.get('expired_at'),
            cancelling_at=batch_dict.get('cancelling_at'),
            cancelled_at=batch_dict.get('cancelled_at'),
            request_counts=batch_dict.get('request_counts')
        )
    except Exception as e:
        import traceback
        error_detail = f"Error fetching batch status for OpenAI batch ID '{db_batch.open_ai_batch_id}': {str(e)}"
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_detail
        )

@router.get("/batches/{batch_id}/download")
def download_batch_output(batch_id: int, db: Session = Depends(get_db)):
    db_batch = db.query(Batch).filter(Batch.id == batch_id).first()
    if not db_batch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Batch with ID '{batch_id}' not found"
        )
    
    if not db_batch.open_ai_batch_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Batch {batch_id} does not have an OpenAI batch ID"
        )
    
    try:
        client = get_openai_client()
        
        batch = client.batches.retrieve(db_batch.open_ai_batch_id)
        
        if batch.status != 'completed':
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Batch is not completed. Current status: {batch.status}"
            )
        
        if not batch.output_file_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Batch output file ID not found"
            )
        
        file_content = client.files.retrieve_content(batch.output_file_id)
        
        filename = f"batch_{db_batch.open_ai_batch_id}_output.jsonl"
        
        return Response(
            content=file_content,
            media_type="application/x-ndjson",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error downloading batch output: {str(e)}"
        )

class PriorityBatchResponse(BaseModel):
    id: int
    website_id: int
    url: str
    website_url: str
    result: str
    model: str
    sync: bool = False
    sample: bool = False
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class PaginatedPriorityBatchesResponse(BaseModel):
    items: List[PriorityBatchResponse]
    total: int
    skip: int
    limit: int

@router.get("/priority-batches", response_model=PaginatedPriorityBatchesResponse)
def get_all_priority_batches(
    website_id: Optional[int] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db)
):
    query = db.query(PriorityBatch)
    
    if website_id:
        query = query.filter(PriorityBatch.website_id == website_id)
    
    total = query.count()
    priority_batches = query.order_by(PriorityBatch.created_at.desc()).offset(skip).limit(limit).all()
    
    return {
        "items": priority_batches,
        "total": total,
        "skip": skip,
        "limit": limit
    }

@router.get("/priority-batches/{priority_batch_id}", response_model=PriorityBatchResponse)
def get_priority_batch(priority_batch_id: int, db: Session = Depends(get_db)):
    db_priority_batch = db.query(PriorityBatch).filter(PriorityBatch.id == priority_batch_id).first()
    if not db_priority_batch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Priority batch with ID {priority_batch_id} not found"
        )
    return db_priority_batch


@router.post("/notifications/events")
def notifications_event(
    event: NotificationEvent,
    db: Session = Depends(get_db)
):
    email_content = build_notification_email(event.event_type, event.model_dump())
    send_notification_email(db, email_content["subject"], email_content["body"])
    return {"success": True}

class NodeLogCreate(BaseModel):
    instance_id: str
    message: str
    level: Optional[str] = "INFO"

class NodeLogResponse(BaseModel):
    id: int
    node_id: int
    message: str
    level: str
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True

@router.post("/nodes/logs", response_model=NodeLogResponse)
def create_node_log(log_data: NodeLogCreate, db: Session = Depends(get_db)):
    db_node = db.query(Node).filter(Node.instance_id == log_data.instance_id).first()
    if not db_node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Node with instance_id '{log_data.instance_id}' not found"
        )
    
    valid_levels = ['INFO', 'WARNING', 'ERROR', 'DEBUG']
    level = log_data.level.upper() if log_data.level else 'INFO'
    if level not in valid_levels:
        level = 'INFO'
    
    db_log = NodeLog(
        node_id=db_node.id,
        message=log_data.message,
        level=level,
        created_at=datetime.now(timezone.utc)
    )
    
    db.add(db_log)
    db.commit()
    db.refresh(db_log)
    
    return db_log

@router.get("/nodes/{node_id}/logs", response_model=List[NodeLogResponse])
def get_node_logs(
    node_id: int,
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of logs to retrieve"),
    db: Session = Depends(get_db)
):
    db_node = db.query(Node).filter(Node.id == node_id).first()
    if not db_node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Node with ID '{node_id}' not found"
        )
    
    logs = db.query(NodeLog).filter(
        NodeLog.node_id == node_id
    ).order_by(NodeLog.created_at.desc()).limit(limit).all()
    
    return logs

@router.get("/settings/sample-size")
def get_sample_size(db: Session = Depends(get_db)):
    setting = db.query(SystemSetting).filter(SystemSetting.key == 'sample_size').first()
    if setting:
        try:
            return {"sample_size": int(setting.value)}
        except ValueError:
            return {"sample_size": 100}  # Default
    return {"sample_size": 100}  # Default

@router.put("/settings/sample-size")
def update_sample_size(sample_size: int = Query(..., ge=1, le=1000), db: Session = Depends(get_db)):
    setting = db.query(SystemSetting).filter(SystemSetting.key == 'sample_size').first()
    if setting:
        setting.value = str(sample_size)
        setting.updated_at = datetime.now(timezone.utc)
    else:
        setting = SystemSetting(key='sample_size', value=str(sample_size))
        db.add(setting)
    
    db.commit()
    return {"sample_size": sample_size}

class SampleCompletionRequest(BaseModel):
    website_id: int
    instance_id: str
    sample_count: int

@router.post("/websites/sample-completion")
def notify_sample_completion(request: SampleCompletionRequest, db: Session = Depends(get_db)):
    db_website = db.query(Website).filter(Website.id == request.website_id).first()
    if not db_website:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Website with ID '{request.website_id}' not found"
        )
    
    db_website.status = 'paused'
    db_website.updated_at = datetime.now(timezone.utc)
    
    db_node = db.query(Node).filter(Node.instance_id == request.instance_id).first()
    if db_node:
        db_node.current_website_id = None
        db_node.status = 'dead'
    
    db.commit()
    
    if db_node:
        try:
            node_region = db_node.region or 'ap-south-1'
            terminate_instance(db_node.instance_id, region=node_region)
            print(f"Terminated node {db_node.instance_id} after sample completion")
        except Exception as e:
            print(f"Error terminating node after sample completion: {e}")
    
    def validate_samples():
        try:
            validate_db = SessionLocal()
            try:
                samples = validate_db.query(PriorityBatch).filter(
                    PriorityBatch.website_id == request.website_id,
                    PriorityBatch.sample == True
                ).all()
                
                if len(samples) >= request.sample_count * 0.9:
                    website = validate_db.query(Website).filter(Website.id == request.website_id).first()
                    if website and website.status == 'paused':
                        print(f"Sample validation completed for website {request.website_id}: {len(samples)} samples found")
                else:
                    print(f"Sample validation failed for website {request.website_id}: Only {len(samples)} samples found")
            finally:
                validate_db.close()
        except Exception as e:
            print(f"Error in sample validation: {e}")
    
    thread = threading.Thread(target=validate_samples)
    thread.daemon = True
    thread.start()
    
    return {
        "success": True,
        "message": f"Website {request.website_id} paused. {request.sample_count} sample products fetched. Node terminated.",
        "status": "paused"
    }

@router.post("/websites/{website_id}/resume")
def resume_website_scraping(website_id: int, db: Session = Depends(get_db)):
    db_website = db.query(Website).filter(Website.id == website_id).first()
    if not db_website:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Website with ID '{website_id}' not found"
        )
    
    if db_website.status != 'paused':
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Website is not in 'paused' status. Current status: {db_website.status}"
        )
    
    try:
        from utils.sqs_client import send_website_to_sqs
        from config.settings import AWS_SQS_URL_WEBSITES, AWS_SQS_URL_PRIORITY_WEBSITES
        
        sample_count = db.query(PriorityBatch).filter(
            PriorityBatch.website_id == website_id,
            PriorityBatch.sample == True
        ).delete()
        
        db_website.status = 'ready'
        db_website.updated_at = datetime.now(timezone.utc)
        db.commit()
        
        website_data = {
            'id': db_website.id,
            'url': db_website.url,
            'type': db_website.type,
            'validator': db_website.validator,
            'scrape_region': db_website.scrape_region or 'ap-south-1',
            'sample_needed': False
        }
        
        queue_url = AWS_SQS_URL_PRIORITY_WEBSITES if db_website.priority else AWS_SQS_URL_WEBSITES
        success = send_website_to_sqs(website_data, queue_url)
        
        if success:
            db_website.status = 'in_queue'
            db.commit()
        
        return {
            "success": True,
            "message": f"Resumed scraping. Deleted {sample_count} sample products. Website added to queue with no sample limit.",
            "status": "in_queue" if success else "ready"
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error resuming website: {str(e)}"
        )

@router.post("/websites/{website_id}/discard")
def discard_website(website_id: int, db: Session = Depends(get_db)):
    db_website = db.query(Website).filter(Website.id == website_id).first()
    if not db_website:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Website with ID '{website_id}' not found"
        )
    
    if db_website.status != 'paused':
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Website is not in 'paused' status. Current status: {db_website.status}"
        )
    
    try:
        sample_count = db.query(PriorityBatch).filter(
            PriorityBatch.website_id == website_id,
            PriorityBatch.sample == True
        ).delete()
        
        db_website.status = 'rejected'
        db_website.updated_at = datetime.now(timezone.utc)
        
        db_node = db.query(Node).filter(Node.current_website_id == website_id).first()
        node_terminated = False
        
        if db_node:
            try:
                node_region = db_node.region or 'ap-south-1'
                success = terminate_instance(db_node.instance_id, region=node_region)
                if success:
                    db_node.status = 'dead'
                    db_node.current_website_id = None
                    node_terminated = True
            except Exception as e:
                print(f"Error terminating node: {e}")
        
        db.commit()
        
        return {
            "success": True,
            "message": f"Discarded website {website_id}. Deleted {sample_count} sample products. Node terminated: {node_terminated}",
            "status": "rejected"
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error discarding website: {str(e)}"
        )

@router.post("/websites/{website_id}/manual-extraction")
def set_manual_extraction(website_id: int, db: Session = Depends(get_db)):
    db_website = db.query(Website).filter(Website.id == website_id).first()
    if not db_website:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Website with ID '{website_id}' not found"
        )
    
    if db_website.status != 'paused':
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Website is not in 'paused' status. Current status: {db_website.status}"
        )
    
    try:
        db_website.status = 'manual_extraction'
        db_website.updated_at = datetime.now(timezone.utc)
        db.commit()
        
        return {
            "success": True,
            "message": f"Website {website_id} set to manual extraction",
            "status": "manual_extraction"
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error setting manual extraction: {str(e)}"
        )

