import io
import json
import os
import random
import string
import qrcode

from fastapi import FastAPI, Depends, Form, Request, HTTPException
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import or_

from database import engine, Base, get_db
import models

# Cipta jadual pangkalan data jika belum wujud
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Pre-Queue Clinic System (KK Pandamaran)")
templates = Jinja2Templates(directory="templates")

# Kamus Terjemahan Dwi-Bahasa
TRANSLATIONS = {
    "bm": {
        "title": "Daftar Pra-Giliran KK Pandamaran",
        "subtitle": "Sila isi sebelum mengambil nombor giliran di kaunter.",
        "ic_label": "No. Kad Pengenalan / Pasport",
        "name_label": "Nama Penuh",
        "phone_label": "Nombor Telefon Bimbit",
        "purpose_title": "Tujuan Kehadiran Hari Ini",
        "p1_title": "Sakit Biasa / Demam / Batuk",
        "p1_desc": "Bilik Saringan / Pesakit Luar (OPD)",
        "p2_title": "Ada Temujanji Klinik",
        "p2_desc": "Darah tinggi, kencing manis, ibu mengandung, anak",
        "p3_title": "Cuci Luka / Dressing / Suntikan",
        "p3_desc": "Bilik Rawatan & Prosedur",
        "p4_title": "Lain-lain / Ambil Ubat",
        "p4_desc": "Urusan farmasi, surat rujukan, atau lain-lain",
        "addr_title": "Status Alamat & Tempat Tinggal",
        "addr_same": "Tiada Perubahan",
        "addr_same_desc": "Alamat sama seperti ic.",
        "addr_change": "Tukar Alamat",
        "addr_change_desc": "Pindah rumah / alamat baharu.",
        "submit_btn": "Hantar Maklumat",
        "elderly_mode": "Mod Warga Emas (Tulisan Besar)"
    },
    "en": {
        "title": "KK Pandamaran Pre-Queue Registration",
        "subtitle": "Please complete before taking queue number at counter.",
        "ic_label": "IC Number / Passport",
        "name_label": "Full Name",
        "phone_label": "Mobile Phone Number",
        "purpose_title": "Purpose of Visit",
        "p1_title": "Common Illness / Fever / Cough",
        "p1_desc": "Fever Triage / Outpatient Clinic (OPD)",
        "p2_title": "Clinic Appointment",
        "p2_desc": "Hypertension, diabetes, maternal & child checkup",
        "p3_title": "Wound Dressing / Injection",
        "p3_desc": "Treatment & Procedure Room",
        "p4_title": "Others / Medicine Refill",
        "p4_desc": "Pharmacy refill, medical report, inquiry",
        "addr_title": "Address & Residence Status",
        "addr_same": "No Changes",
        "addr_same_desc": "Address remains the same as in clinic records.",
        "addr_change": "Change Address",
        "addr_change_desc": "Relocated / new residential address.",
        "submit_btn": "Submit Details",
        "elderly_mode": "Senior Citizen Mode (Large Text)"
    }
}

# Muat data poskod dari direktori fail ini
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
POSTCODE_PATH = os.path.join(BASE_DIR, "postcodes.json")
POSTCODES = {}
if os.path.exists(POSTCODE_PATH):
    with open(POSTCODE_PATH, "r", encoding="utf-8") as f:
        POSTCODES = json.load(f)

# Penjana Kod Token mengikut Aliran Bilik
def generate_purpose_token(purpose: str):
    prefixes = {
        "SAKIT_BIASA": "D",    # Demam / Sakit
        "TEMUJANJI": "A",      # Appointment
        "DRESSING": "P",       # Prosedur / Dressing
        "LAIN_LAIN": "U"       # Ubat / Lain-lain
    }
    prefix = prefixes.get(purpose, "K")
    suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=3))
    return f"{prefix}-{suffix}"

# 1. Halaman Pendaftaran Utama (Menghantar konteks t, lang, elderly)
@app.get("/register", response_class=HTMLResponse)
def get_patient_form(request: Request, lang: str = "bm", elderly: bool = False):
    texts = TRANSLATIONS.get(lang, TRANSLATIONS["bm"])
    return templates.TemplateResponse(
        request=request,
        name="patient_form.html",
        context={"t": texts, "lang": lang, "elderly": elderly}
    )

# 2. Endpoint HTMX Tukar Bahasa / Mod Warga Emas Secara Serta-Merta
@app.get("/get-form-content", response_class=HTMLResponse)
def get_form_content(request: Request, lang: str = "bm", elderly: bool = False):
    texts = TRANSLATIONS.get(lang, TRANSLATIONS["bm"])
    return templates.TemplateResponse(
        request=request,
        name="partials/form_content.html",  # Pulangkan partial serpihan kad sahaja
        context={"t": texts, "lang": lang, "elderly": elderly}
    )

# 3. Jana Imej Kod QR Dinamik
@app.get("/qr/{token_code}")
def get_qr_image(token_code: str):
    qr = qrcode.QRCode(version=1, box_size=8, border=2)
    qr.add_data(token_code)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")

# 4. Semakan Pesakit Berulang Berdasarkan No. KP
@app.get("/check-ic", response_class=HTMLResponse)
def check_returning_patient(request: Request, ic_passport: str = "", db: Session = Depends(get_db)):
    clean_ic = ic_passport.strip().upper()
    if len(clean_ic) < 8:
        return Response(content="", status_code=200)

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

# 5. Semakan Poskod Khusus KK Pandamaran
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

# 6. Hantar Borang Pesakit & Paparkan Kad QR
@app.post("/submit-patient", response_class=HTMLResponse)
def submit_patient(
    ic_passport: str = Form(...),
    full_name: str = Form(...),
    phone_number: str = Form(...),
    visit_purpose: str = Form("SAKIT_BIASA"),
    address_status: str = Form("KEKAL"),
    address: str = Form("KEKAL SEPERTI REKOD SEDIA ADA"),
    db: Session = Depends(get_db)
):
    token = generate_purpose_token(visit_purpose)
    final_address = address.strip().upper() if address_status == "DIKEMASKINI" else "KEKAL SEPERTI REKOD SEDIA ADA"

    record = models.PatientQueue(
        ic_passport=ic_passport.strip().upper(),
        full_name=full_name.strip().upper(),
        phone_number=phone_number.strip(),
        visit_purpose=visit_purpose,
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
        padding: 28px 20px; 
        text-align: center; 
        border-top: 8px solid #059669; 
        box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.1);
        margin: auto;
    ">
        <div style="
            width: 56px; 
            height: 56px; 
            background-color: #d1fae5; 
            color: #059669; 
            border-radius: 50%; 
            display: flex; 
            align-items: center; 
            justify-content: center; 
            margin: 0 auto 12px auto; 
            font-size: 28px; 
            font-weight: 900;
        ">✓</div>

        <h2 style="margin: 0 0 4px 0; font-size: 22px; font-weight: 800; color: #1e293b;">Pendaftaran Berjaya!</h2>
        <p style="margin: 0; font-size: 13px; color: #64748b;">Tunjukkan kod QR ini kepada staf di kaunter:</p>
        
        <div style="margin: 16px auto; display: inline-block; padding: 10px; background: #fff; border: 2px solid #e2e8f0; border-radius: 12px;">
            <img src="/qr/{token}" alt="QR Kod Pesakit" style="width: 180px; height: 180px; display: block; margin: auto;">
        </div>

        <div style="margin-bottom: 16px;">
            <span style="font-size: 12px; color: #64748b; display: block;">No. Rujukan Token:</span>
            <span style="font-size: 32px; font-weight: 900; letter-spacing: 3px; color: #1d4ed8; font-family: monospace;">{token}</span>
        </div>

        <p style="margin: 0; font-size: 13px; font-weight: 600; color: #334155; line-height: 1.4;">
            Sila ke kaunter panggilan atau kiosk tiket untuk imbasan.
        </p>
    </div>
    """)

# 7. Papan Pemuka Staf Kaunter
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

# 8. Carian Live & Polling Baris Giliran Kaunter
@app.get("/counter/queue-rows", response_class=HTMLResponse)
def get_queue_rows(
    request: Request, 
    search: str = "", 
    purpose_filter: str = "ALL", 
    db: Session = Depends(get_db)
):
    query = db.query(models.PatientQueue).filter(models.PatientQueue.is_served == False)

    if purpose_filter and purpose_filter != "ALL":
        query = query.filter(models.PatientQueue.visit_purpose == purpose_filter)

    if search:
        search_term = f"%{search.strip().upper()}%"
        query = query.filter(
            or_(
                models.PatientQueue.ic_passport.like(search_term),
                models.PatientQueue.full_name.like(search_term),
                models.PatientQueue.token_code.like(search_term),
                models.PatientQueue.phone_number.like(search_term)
            )
        )

    patients = query.order_by(models.PatientQueue.created_at.asc()).all()

    return templates.TemplateResponse(
        request=request,
        name="partials/patient_rows.html",
        context={"patients": patients}
    )

# 9. Selesai Daftar Pesakit
@app.post("/serve-patient/{patient_id}")
def mark_served(patient_id: int, db: Session = Depends(get_db)):
    patient = db.query(models.PatientQueue).filter(models.PatientQueue.id == patient_id).first()
    if patient:
        patient.is_served = True
        db.commit()
    return Response(content="", status_code=200)

# 10. API Semakan Pesakit Melalui No. KP (Untuk SystmOne / Kiosk)
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
        "purpose": patient.visit_purpose,
        "token": patient.token_code
    }