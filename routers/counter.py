import json
from typing import List, Optional

from fastapi import APIRouter, Request, Form, Depends, Response
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import or_

from core.database import get_db
from models.queue import PatientQueue
from services.systmone_bot import trigger_systmone_ticket

router = APIRouter(prefix="/counter", tags=["Counter"])
templates = Jinja2Templates(directory="templates")


# ==========================================
# 0. FUNGSI PEMBANTU & EDIT TOKEN SEGERA
# ==========================================

def render_token_badge(patient: PatientQueue) -> str:
    """Fungsi pembantu menghasilkan badge berserta butang edit mesra skrin sentuh"""
    return f"""
    <div id="token-container-{patient.id}" class="flex items-center gap-1 group">
        <span class="inline-flex px-2 py-0.5 rounded-md text-[11px] font-black bg-blue-50 text-blue-700 border border-blue-200">
            {patient.token_code}
        </span>
        <button type="button" 
                hx-get="/counter/edit-token/{patient.id}" 
                hx-target="#token-container-{patient.id}" 
                hx-swap="outerHTML"
                class="opacity-60 hover:opacity-100 p-0.5 text-slate-500 hover:text-blue-600 rounded transition text-xs" 
                title="Edit Nombor Ikut SystmOne">
            ✏️
        </button>
    </div>
    """

@router.get("/edit-token/{patient_id}", response_class=HTMLResponse)
def get_edit_token_form(patient_id: int, db: Session = Depends(get_db)):
    """Memaparkan kotak input ringkas untuk menukar nombor token"""
    patient = db.query(PatientQueue).filter(PatientQueue.id == patient_id).first()
    if not patient:
        return HTMLResponse("<span class='text-xs text-rose-500 font-bold'>Tiada</span>", status_code=404)
        
    return HTMLResponse(f"""
        <form hx-post="/counter/update-token/{patient.id}" 
              hx-target="#token-container-{patient.id}" 
              hx-swap="outerHTML" 
              class="flex items-center gap-1">
            <input type="text" name="new_token" value="{patient.token_code}" 
                   class="w-24 px-1.5 py-0.5 text-xs font-black uppercase border-2 border-blue-500 rounded bg-white outline-none focus:ring-1 focus:ring-blue-400"
                   autofocus onfocus="this.select()">
            <button type="submit" class="px-1.5 py-0.5 bg-emerald-600 text-white text-[10px] font-bold rounded hover:bg-emerald-700">✓</button>
            <button type="button" 
                    hx-get="/counter/cancel-edit-token/{patient.id}" 
                    hx-target="#token-container-{patient.id}" 
                    hx-swap="outerHTML"
                    class="px-1.5 py-0.5 bg-slate-300 text-slate-700 text-[10px] font-bold rounded hover:bg-slate-400">✕</button>
        </form>
    """)

@router.post("/update-token/{patient_id}", response_class=HTMLResponse)
def update_patient_token(patient_id: int, new_token: str = Form(...), db: Session = Depends(get_db)):
    """Menyimpan nombor token baharu (sepadan dengan SystmOne)"""
    patient = db.query(PatientQueue).filter(PatientQueue.id == patient_id).first()
    if patient:
        clean_token = new_token.strip().upper()
        patient.token_code = clean_token
        patient.systmone_queue_no = clean_token
        db.commit()

    return HTMLResponse(render_token_badge(patient))

@router.get("/cancel-edit-token/{patient_id}", response_class=HTMLResponse)
def cancel_edit_token(patient_id: int, db: Session = Depends(get_db)):
    """Membatalkan mod edit dan kembali ke paparan badge asal"""
    patient = db.query(PatientQueue).filter(PatientQueue.id == patient_id).first()
    if not patient:
        return HTMLResponse("", status_code=404)
    return HTMLResponse(render_token_badge(patient))


# ==========================================
# 1. STESEN PRA-GILIRAN (PRE-QUEUE STATION)
# ==========================================

@router.get("/station", response_class=HTMLResponse)
def get_prequeue_station(request: Request, db: Session = Depends(get_db)):
    """Paparan skrin Stesen Pra-Giliran & Saringan Pantas (/counter/station)"""
    patients = (
        db.query(PatientQueue)
        .filter(PatientQueue.is_served == False)
        .order_by(PatientQueue.created_at.asc())
        .all()
    )
    return templates.TemplateResponse(
        request=request,
        name="prequeue_station.html",
        context={"patients": patients}
    )

@router.get("/station/patient-card/{patient_id}", response_class=HTMLResponse)
def get_patient_card(request: Request, patient_id: int, db: Session = Depends(get_db)):
    """Memuatkan kad butiran pesakit terpilih ke dalam zon aktif (#active-patient-zone)"""
    patient = db.query(PatientQueue).filter(PatientQueue.id == patient_id).first()
    if not patient:
        return HTMLResponse("<div class='p-4 text-xs text-rose-500 font-bold'>Pesakit tidak dijumpai.</div>")
    
    return templates.TemplateResponse(
        request=request,
        name="partials/active_patient_card.html",
        context={"p": patient}
    )

@router.get("/station/scan-select/{scanned_code}", response_class=HTMLResponse)
def scan_select_patient(request: Request, scanned_code: str, db: Session = Depends(get_db)):
    """
    Dipanggil apabila staf mengimbas kod QR di telefon pesakit
    Menerima token_code (cth: A00015) atau No. KP (cth: 860118086111)
    """
    clean_code = scanned_code.strip().upper().replace("-", "")
    
    patient = db.query(PatientQueue).filter(
        or_(
            PatientQueue.token_code == scanned_code.strip().upper(),
            PatientQueue.ic_passport.like(f"%{clean_code}%")
        ),
        PatientQueue.is_served == False
    ).order_by(PatientQueue.id.desc()).first()

    if not patient:
        return HTMLResponse("""
            <div class="bg-rose-50 border-2 border-rose-300 rounded-3xl p-6 text-center text-rose-800 animate-fade-in">
                <span class="text-3xl block mb-1">⚠️</span>
                <p class="font-extrabold text-sm">Pesakit Tidak Ditemui!</p>
                <p class="text-xs text-rose-600 mt-1">Sila pastikan pesakit telah mengisi borang pra-pendaftaran di telefon.</p>
            </div>
        """)

    return templates.TemplateResponse(
        request=request,
        name="partials/active_patient_card.html",
        context={"p": patient}
    )

@router.post("/station/process-ticket", response_class=HTMLResponse)
def process_station_ticket(
    request: Request,
    patient_id: Optional[int] = Form(None),
    category: str = Form(...),       # Nilai 'OPD' atau 'MCH' dihantar dari butang
    prefix: str = Form(...),         # Nilai 'D' (OPD), 'M' (MCH), dll.
    is_blood_test: Optional[bool] = Form(False),
    fasting: Optional[str] = Form(None),
    test_type: Optional[List[str]] = Form([]),
    lab_notes: Optional[str] = Form(""),
    db: Session = Depends(get_db)
):
    if not patient_id:
        return HTMLResponse("""
            <div class="p-3 bg-rose-50 border border-rose-200 rounded-xl text-rose-800 text-xs font-bold animate-fade-in">
                ⚠️ Sila pilih pesakit daripada senarai terlebih dahulu sebelum memilih kategori tiket!
            </div>
        """)

    patient = db.query(PatientQueue).filter(PatientQueue.id == patient_id).first()
    if not patient:
        return HTMLResponse("""
            <div class="p-3 bg-rose-50 border border-rose-200 rounded-xl text-rose-800 text-xs font-bold">
                ⚠️ Rekod pesakit tidak ditemui dalam sistem.
            </div>
        """)

    # 1. PANGGIL SYSTMONE AUTOMATION (Tukar tab & cetak ikut kategori di latar belakang)
    trigger_systmone_ticket(category=category)

    # 2. Format Nombor Giliran (Mencegah awalan berulang seperti D-D00001)
    if patient.token_code.startswith(prefix):
        generated_ticket = patient.token_code
    else:
        generated_ticket = f"{prefix}-{patient.token_code}"
    
    # 3. Kemas kini data ujian makmal & status giliran
    patient.systmone_queue_no = generated_ticket
    patient.is_blood_test = bool(is_blood_test)
    patient.lab_tests = ", ".join(test_type) if test_type else None
    patient.fasting_status = fasting if is_blood_test else None
    patient.lab_notes = lab_notes.strip() if lab_notes else None
    db.commit()

    # 4. Panggilan Cetak Terma Bixolon SRP-350III (Slip Makmal / Tiket Fizikal)
    # from services.printer import print_blood_test_ticket
    # print_blood_test_ticket(
    #     patient_name=patient.full_name,
    #     ic_no=patient.ic_passport,
    #     systmone_queue=generated_ticket,
    #     tests_list=test_type,
    #     fasting_status=fasting or "TIADA",
    #     notes=lab_notes
    # )

    # 5. Maklum balas UI dan trigger HTMX
    response_html = f"""
    <div class="p-3.5 bg-emerald-50 border border-emerald-200 rounded-2xl text-emerald-900 text-xs font-bold flex justify-between items-center shadow-sm animate-fade-in">
        <div class="flex items-center gap-2">
            <span class="text-base">✓</span>
            <span>Tiket <span class="text-blue-700 underline font-black">[{generated_ticket}]</span> ({category}) berjaya diproses & dicetuskan ke SystmOne!</span>
        </div>
        <span class="text-[10px] text-emerald-700 font-semibold bg-emerald-100/70 px-2 py-0.5 rounded-full">Sedia ke Ruang Menunggu</span>
    </div>
    """
    
    headers = {
        "HX-Trigger": json.dumps({
            "refreshQueue": True,
            "clearActivePatient": True
        })
    }
    return HTMLResponse(content=response_html, headers=headers)


# ==========================================
# 2. KAUNTER PENDAFTARAN UTAMA (/counter)
# ==========================================

@router.get("", response_class=HTMLResponse)
def counter_dashboard(request: Request, db: Session = Depends(get_db)):
    """Papan pemuka kaunter utama staf (/counter)"""
    patients = (
        db.query(PatientQueue)
        .filter(PatientQueue.is_served == False)
        .order_by(PatientQueue.created_at.asc())
        .all()
    )
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
    station_mode: Optional[bool] = False,
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

    # Periksa sama ada panggilan datang dari /counter/station
    referer = request.headers.get("referer", "")
    if station_mode or ("station" in referer):
        return templates.TemplateResponse(
            request=request,
            name="partials/station_rows.html",
            context={"patients": patients}
        )

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

@router.get("/copy-field", response_class=HTMLResponse)
def copy_field(request: Request, text: str, label: str):
    clean_text = text.strip()
    if label in ["No. KP", "No. Tel", "No. Telefon"]:
        clean_text = "".join(filter(str.isalnum, clean_text))

    headers = {
        "HX-Trigger": json.dumps({
            "triggerCopy": clean_text
        })
    }

    return templates.TemplateResponse(
        request=request,
        name="partials/toast_notification.html",
        context={"label": label},
        headers=headers
    )

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
        "id": patient.id,
        "name": patient.full_name,
        "phone": patient.phone_number,
        "address": patient.address,
        "address_status": patient.address_status,
        "purpose": patient.visit_purpose,
        "token": patient.token_code,
        "systmone_queue": patient.systmone_queue_no
    }