from sqlalchemy import Column, String, Boolean, DateTime, Text
from sqlalchemy.sql import func
import uuid

from database import Base

class Analysis(Base):
    __tablename__ = "analyses"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    resume_hash = Column(String, nullable=False)
    job_hash = Column(String, nullable=False)

    analysis_json = Column(Text, nullable=False)

    is_paid = Column(Boolean, default=False)

    payment_reference = Column(String, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
