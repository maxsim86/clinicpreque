from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class PatientBase(BaseModel):
    ic_passport: str
    full_name: str
    phone_number: str
    address: str

class PatientCreate(PatientBase):
    pass

class PatientOut(PatientBase):
    id: int
    token_code: str
    queue_number: Optional[str] = None
    is_served: bool
    created_at: datetime

    class Config:
        from_attributes = True
