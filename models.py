from sqlalchemy import Column, String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    google_id = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    name = Column(String)
    picture = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    analyses = relationship("Analysis", back_populates="user")

class Analysis(Base):
    __tablename__ = "analyses"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # Link to User (Optional for guest users)
    user_id = Column(String, ForeignKey("users.id"), nullable=True)
    user = relationship("User", back_populates="analyses")

    resume_hash = Column(String, nullable=False)
    job_hash = Column(String, nullable=False)

    analysis_json = Column(Text, nullable=False)

    is_paid = Column(Boolean, default=False)

    payment_reference = Column(String, nullable=True) # Will store Txn ID if entered
    payment_screenshot = Column(String, nullable=True) # Path to saved screenshot
    screenshot_hash = Column(String, nullable=True, index=True) # SHA256 of screenshot
    payment_status = Column(String, default="unpaid") # unpaid, pending, paid

    created_at = Column(DateTime(timezone=True), server_default=func.now())
