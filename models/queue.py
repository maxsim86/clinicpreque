import datetime
from sqlalchemy import Column, Integer, String, DateTime, Boolean
from core.database import Base

class PatientQueue(Base):
    __tablename__ = "patient_queue"

    id = Column(Integer, primary_key=True, index=True)
    ic_passport = Column(String(50), index=True, nullable=False)
    full_name = Column(String(150), nullable=False)
    phone_number = Column(String(20), nullable=False)
    visit_purpose = Column(String(50), nullable=False, default="SAKIT_BIASA")
    address_status = Column(String(20), default="KEKAL")
    address = Column(String(255), nullable=False)
    queue_number = Column(String(20), nullable=True)
    token_code = Column(String(10), unique=True, index=True)
    is_served = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
