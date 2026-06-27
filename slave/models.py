from sqlalchemy import Column, Integer, String, Enum, DateTime, ForeignKey
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.sql import func

Base = declarative_base()

class Website(Base):
    __tablename__ = 'websites'
    
    id = Column(Integer, primary_key=True, index=True)
    url = Column(String, unique=True, nullable=False)
    status = Column(
        Enum('pending_validator', 'processing', 'completed', 'ready', name='website_status'), 
        default='pending_validator',
        nullable=False
    )
    validator = Column(String, nullable=True)
    type = Column(Enum('retailer', 'brand', name='website_type'), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    batches = relationship("Batch", back_populates="website")

class Batch(Base):
    __tablename__ = 'batches'
    
    id = Column(Integer, primary_key=True, index=True)
    website_id = Column(Integer, ForeignKey('websites.id'), nullable=False)
    batch_name = Column(String, nullable=False)
    open_ai_batch_id = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    website = relationship("Website", back_populates="batches")

