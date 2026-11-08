# models/queue.py
import datetime
from zoneinfo import ZoneInfo
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text
from core.database import Base

def get_malaysia_now():
    return datetime.datetime.now(ZoneInfo("Asia/Kuala_Lumpur")).replace(tzinfo=None)

class PatientQueue(Base):
    __tablename__ = "patient_queue"

    id = Column(Integer, primary_key=True, index=True)
    ic_passport = Column(String(50), index=True, nullable=False)
    full_name = Column(String(150), nullable=False)
    phone_number = Column(String(20), nullable=False)
    visit_purpose = Column(String(50), nullable=False, default="SAKIT_BIASA")
    address_status = Column(String(20), default="KEKAL")
    address = Column(String(255), nullable=False)
    is_priority = Column(Boolean, default=False)  # Status Laluan Pantas / Keutamaan
    priority_reason = Column(String(50), nullable=True) # Cth: WARGA_EMAS, OKU, KERUSI_RODA, BAYI
    
    # --- MEDAN BAHARU UNTUK UJIAN MAKMAL / AMBIL DARAH ---
    is_blood_test = Column(Boolean, default=False)
    lab_tests = Column(String(255), nullable=True)     # Cth: "FBS, HBA1C, LIPID, RENAL"
    fasting_status = Column(String(20), nullable=True) # Cth: "PUASA (10 JAM)" atau "TIDAK PUASA"
    lab_notes = Column(Text, nullable=True)            # Nota tambahan (cth: "Ujian Ulangan / Bilik 5")
    
    systmone_queue_no = Column(String(20), nullable=True) # No tiket rasmi SystmOne
    token_code = Column(String(20), index=True, nullable=False)
    is_served = Column(Boolean, default=False)
    created_at = Column(DateTime, default=get_malaysia_now)
