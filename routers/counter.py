from fastapi import APIRouter, Request, Depends, Response
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import or_

from core.database import get_db
from models.queue import PatientQueue

router = APIRouter(prefix="/counter", tags=["Counter"])
templates = Jinja2Templates(directory="templates")

@router.get("", response_class=HTMLResponse)
def counter_dashboard(request: Request, db: Session = Depends(get_db)):
    patients = db.query(PatientQueue).filter(PatientQueue.is_served == False).order_by(PatientQueue.created_at.asc()).all()
    return templates.TemplateResponse(
        request=request,
        name="staff_dashboard.html",
        context={"patients": patients}
    )

@router.get("/queue-rows", response_class=HTMLResponse)
def get_queue_rows(
    request: Request, 
    search: str = "", 
    purpose_filter: str = "ALL", 
    db: Session = Depends(get_db)
):
    query = db.query(PatientQueue).filter(PatientQueue.is_served == False)

    if purpose_filter and purpose_filter != "ALL":
        query = query.filter(PatientQueue.visit_purpose == purpose_filter)

    if search:
        search_term = f"%{search.strip().upper()}%"
        query = query.filter(
            or_(
                PatientQueue.ic_passport.like(search_term),
                PatientQueue.full_name.like(search_term),
                PatientQueue.token_code.like(search_term),
                PatientQueue.phone_number.like(search_term)
            )
        )

    patients = query.order_by(PatientQueue.created_at.asc()).all()
    return templates.TemplateResponse(
        request=request,
        name="partials/patient_rows.html",
        context={"patients": patients}
    )

@router.post("/serve/{patient_id}")
def mark_served(patient_id: int, db: Session = Depends(get_db)):
    patient = db.query(PatientQueue).filter(PatientQueue.id == patient_id).first()
    if patient:
        patient.is_served = True
        db.commit()
    return Response(content="", status_code=200)

@router.get("/api/get-patient/{ic_passport}")
def api_get_patient(ic_passport: str, db: Session = Depends(get_db)):
    patient = db.query(PatientQueue).filter(
        PatientQueue.ic_passport == ic_passport.strip().upper(),
        PatientQueue.is_served == False
    ).first()
    if not patient:
        return {"found": False}
    return {
        "found": True,
        "name": patient.full_name,
        "phone": patient.phone_number,
        "address": patient.address,
        "purpose": patient.visit_purpose,
        "token": patient.token_code
    }
