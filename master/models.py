from sqlalchemy import Column, Integer, String, Enum, DateTime, ForeignKey, Float, Boolean, Text
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import JSONB

Base = declarative_base()

class Website(Base):
    __tablename__ = 'websites'
    
    id = Column(Integer, primary_key=True, index=True)
    url = Column(String, unique=True, nullable=False)
    status = Column(
        Enum('pending_validator', 'ready', 'in_queue', 'processing', 'paused', 'completed', 'terminated', 'rejected', 'manual_extraction', name='website_status'), 
        default='pending_validator',
        nullable=False
    )
    validator = Column(String, nullable=True)
    type = Column(Enum('retailer', 'brand', name='website_type'), nullable=True)
    priority = Column(Boolean, default=False, nullable=False)
    country_info = Column(JSONB, nullable=True)
    scrape_region = Column(String, nullable=True, default='ap-south-1')
    reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    batches = relationship("Batch", back_populates="website")
    tasks = relationship("Task", back_populates="website")


class Batch(Base):
    __tablename__ = 'batches'
    
    id = Column(Integer, primary_key=True, index=True)
    website_id = Column(Integer, ForeignKey('websites.id'), nullable=False)
    batch_name = Column(String, nullable=False)
    open_ai_batch_id = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    website = relationship("Website", back_populates="batches")


class Node(Base):
    __tablename__ = 'nodes'
    
    id = Column(Integer, primary_key=True, index=True)
    instance_id = Column(String, unique=True, nullable=False)
    ip_address = Column(String, nullable=False)
    region = Column(String, nullable=True, default='ap-south-1')
    status = Column(Enum('alive', 'processing', 'dead', name='node_status'), default='alive', nullable=False)
    last_seen = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    cpu_usage = Column(Float, nullable=True)
    memory_usage = Column(Float, nullable=True)
    current_website_id = Column(Integer, ForeignKey('websites.id'), nullable=True)
    null_heartbeat_count = Column(Integer, default=0, nullable=False)
    resume_command = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    tasks = relationship("Task", back_populates="node")
    current_website = relationship("Website", foreign_keys=[current_website_id])


class Task(Base):
    __tablename__ = 'tasks'
    
    id = Column(Integer, primary_key=True, index=True)
    node_id = Column(Integer, ForeignKey('nodes.id'), nullable=False)
    website_id = Column(Integer, ForeignKey('websites.id'), nullable=False)
    status = Column(Enum('processing', 'completed', name='task_status'), default='processing', nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    node = relationship("Node", back_populates="tasks")
    website = relationship("Website", back_populates="tasks")


class PriorityBatch(Base):
    __tablename__ = 'priority_batches'
    
    id = Column(Integer, primary_key=True, index=True)
    website_id = Column(Integer, ForeignKey('websites.id'), nullable=False)
    url = Column(String, nullable=False)
    website_url = Column(String, nullable=False)
    result = Column(Text, nullable=False)
    model = Column(String, nullable=False)
    sync = Column(Boolean, default=False, nullable=False)
    sample = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class NodeLog(Base):
    __tablename__ = 'node_logs'
    
    id = Column(Integer, primary_key=True, index=True)
    node_id = Column(Integer, ForeignKey('nodes.id'), nullable=False)
    message = Column(Text, nullable=False)
    level = Column(String, default='INFO', nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    node = relationship("Node", backref="logs")


class NotificationSetting(Base):
    __tablename__ = 'notification_settings'

    id = Column(Integer, primary_key=True, index=True)
    emails = Column(JSONB, nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SystemSetting(Base):
    __tablename__ = 'system_settings'

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, nullable=False)
    value = Column(Text, nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AutomatedScrapingConfig(Base):
    __tablename__ = 'automated_scraping_configs'
    
    id = Column(Integer, primary_key=True, index=True)
    website = Column(String, nullable=False)  # Domain like www.abc.com
    country = Column(String, nullable=False)
    currency = Column(String, nullable=True)
    name_selector = Column(Text, nullable=True)  # CSS selector for product name
    description_selector = Column(Text, nullable=True)  # CSS selector for product description
    price_selector = Column(Text, nullable=True)  # CSS selector for product price
    images_container_selector = Column(Text, nullable=True)  # CSS selector for images container
    status = Column(
        Enum('ready', 'in_queue', 'completed', 'blocked', name='scraping_status'),
        default='ready',
        nullable=False
    )
    reason = Column(Text, nullable=True)  # Reason if blocked
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

