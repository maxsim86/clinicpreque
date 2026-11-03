import json
import os
import random
import string
from fastapi import FastAPI, Depends, Form, Request, HTTPException
from fastapi.responses import HTMLResponse, Response, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database import engine, Base, get_db
import models

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Pre-Queue Clinic System (Fast-Verification)")
templates = Jinja2Templates(directory="templates")

# Muat turun data poskod ke memori
POSTCODES = {}
if os.path.exists("postcodes.json"):
    with open("postcodes.json", "r", encoding="utf-8") as f:
        POSTCODES = json.load(f)

def generate_token():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))

# 1. Borang Utama
@app.get("/register", response_class=HTMLResponse)
def get_patient_form(request: Request):
    return templates.TemplateResponse(request=request, name="patient_form.html")

# 2. HTMX Semakan Pesakit Berulang Berdasarkan No. KP
@app.get("/check-ic", response_class=HTMLResponse)
def check_returning_patient(request: Request, ic_passport: str = "", db: Session = Depends(get_db)):
    clean_ic = ic_passport.strip().upper()
    if len(clean_ic) < 8:
        return Response(content="", status_code=200)

    # Cari rekod terkini pesakit ini dalam pangkalan data
    patient = db.query(models.PatientQueue).filter(
        models.PatientQueue.ic_passport == clean_ic
    ).order_by(models.PatientQueue.id.desc()).first()

    if patient:
        return templates.TemplateResponse(
            request=request,
            name="partials/returning_patient.html",
            context={"patient": patient}
        )
    return Response(content="", status_code=200)

@app.get("/api/lookup-postcode/{postcode}")
def lookup_postcode(postcode: str):
    clean_code = postcode.strip()
    info = POSTCODES.get(clean_code)
    
    if info:
        return {
            "found": True,
            "in_zone": info.get("in_zone", False),
            "city": info["city"],
            "state": info["state"],
            "area": info["area"],
            "nearest_kk": info.get("nearest_kk", "")
        }
    
    return {
        "found": False,
        "in_zone": False,
        "message": "Poskod di luar kawasan operasi KK Pandamaran."
    }


# 4. Hantar Maklumat & Jana Kad Token (Inline CSS Mesra Offline / Intranet)
@app.post("/submit-patient", response_class=HTMLResponse)
def submit_patient(
    ic_passport: str = Form(...),
    full_name: str = Form(...),
    phone_number: str = Form(...),
    address_status: str = Form("KEKAL"),
    address: str = Form("KEKAL SEPERTI REKOD SEDIA ADA"),
    db: Session = Depends(get_db)
):
    token = generate_token()
    
    # Tetapkan alamat mengikut status
    final_address = address.strip().upper() if address_status == "DIKEMASKINI" else "KEKAL SEPERTI REKOD SEDIA ADA"

    record = models.PatientQueue(
        ic_passport=ic_passport.strip().upper(),
        full_name=full_name.strip().upper(),
        phone_number=phone_number.strip(),
        address_status=address_status,
        address=final_address,
        token_code=token
    )
    db.add(record)
    db.commit()

    return HTMLResponse(content=f"""
    <div id="form-container" style="
        background: #ffffff; 
        max-width: 480px; 
        width: 100%; 
        border-radius: 16px; 
        padding: 32px 24px; 
        text-align: center; 
        border-top: 8px solid #059669; 
        box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.1);
        margin: auto;
    ">
        <!-- Ikon Tanda Right Hijau -->
        <div style="
            width: 64px; 
            height: 64px; 
            background-color: #d1fae5; 
            color: #059669; 
            border-radius: 50%; 
            display: flex; 
            align-items: center; 
            justify-content: center; 
            margin: 0 auto 16px auto; 
            font-size: 32px; 
            font-weight: 900;
        ">✓</div>

        <h2 style="margin: 0 0 6px 0; font-size: 24px; font-weight: 800; color: #1e293b;">Pendaftaran Berjaya!</h2>
        <p style="margin: 0; font-size: 13px; color: #64748b;">Kod Rujukan Anda:</p>
        
        <!-- Kotak Token Rujukan -->
        <div style="
            margin: 20px 0; 
            background-color: #eff6ff; 
            border: 2px dashed #3b82f6; 
            padding: 16px; 
            border-radius: 12px;
        ">
            <span style="
                font-size: 44px; 
                font-weight: 900; 
                letter-spacing: 6px; 
                color: #1d4ed8; 
                font-family: monospace;
            ">{token}</span>
        </div>

        <p style="margin: 0; font-size: 14px; font-weight: 600; color: #334155; line-height: 1.4;">
            Sila ambil tiket nombor giliran anda di mesin <strong>pre-queue</strong> sekarang.
        </p>
    </div>
    """)

# 5. Papan Pemuka Kaunter & Polling (Kekal Berfungsi Seperti Asal)
@app.get("/counter", response_class=HTMLResponse)
def counter_dashboard(request: Request, db: Session = Depends(get_db)):
    patients = db.query(models.PatientQueue).filter(
        models.PatientQueue.is_served == False
    ).order_by(models.PatientQueue.created_at.asc()).all()
    
    return templates.TemplateResponse(
        request=request,
        name="staff_dashboard.html",
        context={"patients": patients}
    )

@app.get("/counter/queue-rows", response_class=HTMLResponse)
def get_queue_rows(request: Request, db: Session = Depends(get_db)):
    patients = db.query(models.PatientQueue).filter(
        models.PatientQueue.is_served == False
    ).order_by(models.PatientQueue.created_at.asc()).all()

    return templates.TemplateResponse(
        request=request,
        name="partials/patient_rows.html",
        context={"patients": patients}
    )

@app.post("/serve-patient/{patient_id}")
def mark_served(patient_id: int, db: Session = Depends(get_db)):
    patient = db.query(models.PatientQueue).filter(models.PatientQueue.id == patient_id).first()
    if patient:
        patient.is_served = True
        db.commit()
    return Response(content="", status_code=200)

@app.get("/api/get-patient-by-ic/{ic_passport}")
def api_get_patient(ic_passport: str, db: Session = Depends(get_db)):
    patient = db.query(models.PatientQueue).filter(
        models.PatientQueue.ic_passport == ic_passport.strip().upper(),
        models.PatientQueue.is_served == False
    ).first()
    if not patient:
        return {"found": False}
    return {
        "found": True,
        "name": patient.full_name,
        "phone": patient.phone_number,
        "address": patient.address,
        "token": patient.token_code
    }