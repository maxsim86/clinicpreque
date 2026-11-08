import json, re
from typing import List, Optional

from fastapi import APIRouter, Request, Form, Depends, Response, BackgroundTasks
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
# FUNGSI 1: BATAL / GUGUR PESAKIT DARI SENARAI
# ==========================================

@router.post("/cancel-patient/{patient_id}")
def cancel_patient_queue(patient_id: int, db: Session = Depends(get_db)):
    """Menandakan pesakit sebagai terbatal/selesai supaya baris hilang dari senarai menunggu"""
    patient = db.query(PatientQueue).filter(PatientQueue.id == patient_id).first()
    if patient:
        patient.is_served = True  # Keluarkan dari paparan senarai menunggu
        patient.systmone_queue_no = "DIBATALKAN"
        db.commit()

    # Hantar maklum balas kosong bersama header untuk segarkan senarai & bersihkan kad jika pesakit aktif dibatalkan
    headers = {
        "HX-Trigger": json.dumps({
            "refreshQueue": True,
            "clearActivePatient": True
        })
    }
    return Response(content="", status_code=200, headers=headers)


# ==========================================
# FUNGSI 2: CETAK SEMULA TIKET TERAKHIR (REPRINT)
# ==========================================

@router.post("/reprint-last", response_class=HTMLResponse)
def reprint_last_ticket(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Mencari pesakit terakhir yang telah diproses dan cetak semula tiket / cetuskan SystmOne"""
    # Cari rekod terakhir yang telah diproses dan mempunyai no tiket
    last_patient = (
        db.query(PatientQueue)
        .filter(
            PatientQueue.is_served == True,
            PatientQueue.systmone_queue_no.isnot(None),
            PatientQueue.systmone_queue_no != "DIBATALKAN"
        )
        .order_by(PatientQueue.id.desc())
        .first()
    )

    if not last_patient:
        return HTMLResponse("""
            <div class="fixed bottom-5 right-5 bg-rose-600 text-white text-xs font-bold px-4 py-2.5 rounded-2xl shadow-xl animate-fade-in z-50 flex items-center gap-2">
                <span>⚠️ Tiada rekod tiket sedia ada untuk dicetak semula.</span>
            </div>
        """)

    # Cetus bot SystmOne atau hantar ke Bixolon di latar belakang
    # Kategori default boleh ditentukan dari no tiket (cth: prefix D -> OPD)
    cat = "OPD"
    if "M" in (last_patient.systmone_queue_no or ""):
        cat = "MCH"
    elif "S" in (last_patient.systmone_queue_no or ""):
        cat = "PAKAR"

    background_tasks.add_task(trigger_systmone_ticket, cat)

    # Contoh jika ada fungsi printer fizikal:
    # background_tasks.add_task(reprint_ticket_bixolon, last_patient)

    return HTMLResponse(f"""
        <div id="reprint-toast" class="fixed bottom-5 right-5 bg-slate-900 text-white text-xs font-bold px-4 py-3 rounded-2xl shadow-2xl animate-fade-in z-50 flex items-center gap-2 border border-slate-700">
            <span class="text-emerald-400 text-sm">🖨️</span>
            <span>Tiket terakhir <span class="text-blue-400 font-black">[{last_patient.systmone_queue_no}]</span> ({last_patient.full_name}) dihantar semula ke pencetak!</span>
        </div>
        <script>
            setTimeout(() => {{
                const toast = document.getElementById('reprint-toast');
                if (toast) toast.remove();
            }}, 3500);
        </script>
    """)




@router.get("/edit-token/{patient_id}", response_class=HTMLResponse)
def get_edit_token_form(request: Request, patient_id: int, db: Session = Depends(get_db)):
    patient = db.query(PatientQueue).filter(PatientQueue.id == patient_id).first()
    if not patient:
        return HTMLResponse("<span class='text-xs text-rose-500 font-bold'>Tiada</span>", status_code=404)
        
    return templates.TemplateResponse(
        request=request,
        name="partials/token_edit_form.html",
        context={"patient": patient}
    )


@router.post("/update-token/{patient_id}", response_class=HTMLResponse)
def update_patient_token(request: Request, patient_id: int, new_token: str = Form(...), db: Session = Depends(get_db)):
    patient = db.query(PatientQueue).filter(PatientQueue.id == patient_id).first()
    if patient:
        clean_token = new_token.strip().upper()
        patient.token_code = clean_token
        patient.systmone_queue_no = clean_token
        db.commit()

    # Pulangkan lencana badge terus menggantikan <form> (hx-target="this")
    return templates.TemplateResponse(
        request=request,
        name="partials/token_badge.html",
        context={"patient": patient}
    )


@router.get("/cancel-edit-token/{patient_id}", response_class=HTMLResponse)
def cancel_edit_token(request: Request, patient_id: int, db: Session = Depends(get_db)):
    patient = db.query(PatientQueue).filter(PatientQueue.id == patient_id).first()
    if not patient:
        return HTMLResponse("", status_code=404)
        
    return templates.TemplateResponse(
        request=request,
        name="partials/token_badge.html",
        context={"patient": patient}
    )


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
        context={
            "p": patient,
            "patient": patient  
        }
    )


@router.get("/station/scan-select/{scanned_code}", response_class=HTMLResponse)
def scan_select_patient(request: Request, scanned_code: str, db: Session = Depends(get_db)):
    """Dipanggil apabila pengimbas membaca QR atau No. KP pesakit"""
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
        context={
            "p": patient,
            "patient": patient  
        }
    )


@router.post("/station/process-ticket", response_class=HTMLResponse)
def process_station_ticket(
    request: Request,
    background_tasks: BackgroundTasks,
    patient_id: Optional[int] = Form(None),
    category: str = Form(...),
    prefix: str = Form(...),
    is_priority: Optional[bool] = Form(False),
    priority_reason: Optional[str] = Form(None),
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

    # 1. Panggil automasi SystmOne di latar belakang tanpa melengahkan UI web
    background_tasks.add_task(trigger_systmone_ticket, category)

    # 2. Format Nombor Giliran & Keutamaan Fast-Track
    if is_priority:
        effective_prefix = f"E-{prefix}"
        generated_ticket = f"{effective_prefix}-{patient.token_code.split('-')[-1]}"
    else:
        if patient.token_code.startswith(prefix):
            generated_ticket = patient.token_code
        else:
            generated_ticket = f"{prefix}-{patient.token_code}"

    # 3. Kemas kini data pesakit & tandakan sebagai selesai saringan
    patient.systmone_queue_no = generated_ticket
    patient.is_served = True
    patient.is_priority = bool(is_priority)
    patient.priority_reason = priority_reason if is_priority else None
    patient.is_blood_test = bool(is_blood_test)
    patient.lab_tests = ", ".join(test_type) if test_type else None
    patient.fasting_status = fasting if is_blood_test else None
    patient.lab_notes = lab_notes.strip() if lab_notes else None
    db.commit()

    priority_badge = ""
    if is_priority:
        priority_badge = f'<span class="bg-emerald-600 text-white text-[10px] font-black px-2 py-0.5 rounded ml-2">⚡ FAST-TRACK ({priority_reason})</span>'

    # 4. Maklum balas UI bersama HTMX Out-of-Band Swap untuk zon pesakit aktif
    response_html = f"""<div class="p-3.5 bg-emerald-50 border-2 border-emerald-300 rounded-2xl text-emerald-950 text-xs font-bold flex justify-between items-center shadow-sm animate-fade-in mb-3">
    <div class="flex items-center gap-2">
        <span class="text-lg">✓</span>
        <span>Tiket <span class="text-blue-700 underline font-black">[{generated_ticket}]</span> ({category}){priority_badge} siap diproses & dicetuskan ke SystmOne!</span>
    </div>
    <span class="text-[10px] text-emerald-700 font-semibold bg-emerald-100 px-2.5 py-1 rounded-full">Sedia Masuk</span>
</div>
<div id="active-patient-zone" hx-swap-oob="true">
    <div class="bg-white border-2 border-dashed border-slate-300 rounded-3xl p-8 text-center text-slate-400 shadow-sm animate-fade-in">
        <span class="text-4xl block mb-2">📷</span>
        <p class="font-extrabold text-sm text-slate-700">Sedia Menerima Imbasan Kod Bar / QR Pesakit</p>
        <p class="text-xs text-slate-400 mt-1">Imbas kod QR pada telefon pesakit atau klik pada senarai menunggu di sebelah kanan.</p>
    </div>
</div>"""

    headers = {
        "HX-Trigger": json.dumps({
            "refreshQueue": True
        })
    }
    return HTMLResponse(content=response_html, headers=headers)


# ==========================================
# 2. KAUNTER PENDAFTARAN UTAMA & POLING SENARAI
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
    # 1. Kira jumlah sebenar keseluruhan pesakit menunggu untuk lencana (cth: 900 orang)
    total_waiting = db.query(PatientQueue).filter(PatientQueue.is_served == False).count()
    query = db.query(PatientQueue).filter(PatientQueue.is_served == False)

    if purpose_filter and purpose_filter != "ALL":
        query = query.filter(PatientQueue.visit_purpose == purpose_filter)

    raw_search = search.strip()
    if raw_search:
        clean_digits = re.sub(r'[^0-9A-Za-z]', '', raw_search).upper()
        upper_search = raw_search.upper()
        conditions = []

        # A. Carian Token (cth: D0001, A0012)
        conditions.append(PatientQueue.token_code.like(f"%{upper_search}%"))

        # B. Carian No. KP:
        # Jika taip 4 digit -> padankan 4 digit belakang No. KP
        if clean_digits.isdigit() and len(clean_digits) == 4:
            conditions.append(PatientQueue.ic_passport.like(f"%{clean_digits}"))
        elif clean_digits.isdigit() and len(clean_digits) > 4:
            conditions.append(PatientQueue.ic_passport.like(f"%{clean_digits}%"))
        else:
            conditions.append(PatientQueue.ic_passport.like(f"%{upper_search}%"))

        # C. Carian Nama: Pecahkan setiap perkataan (multi-word match)
        name_words = [w for w in upper_search.split() if len(w) > 1]
        if name_words:
            for word in name_words:
                conditions.append(PatientQueue.full_name.like(f"%{word}%"))
        else:
            conditions.append(PatientQueue.full_name.like(f"%{upper_search}%"))

        query = query.filter(or_(*conditions))
        
        # Hadkan carian kepada 10 orang teratas supaya tindak balas carian serta-merta
        patients = query.order_by(PatientQueue.created_at.asc()).limit(10).all()
    else:
        # Paparan biasa: ambil 20 pesakit terawal sahaja supaya DOM kekal ringan dan laju
        patients = query.order_by(PatientQueue.created_at.asc()).limit(20).all()

    referer = request.headers.get("referer", "")
    is_station = station_mode or ("station" in referer)
    template_name = "partials/station_rows.html" if is_station else "partials/patient_rows.html"

    response = templates.TemplateResponse(
        request=request,
        name=template_name,
        context={"patients": patients}
    )
    
    # Hantar jumlah pesakit keseluruhan ke UI badge
    trigger_payload = {"value": total_waiting}
    
    # Jika hasil carian menghasilkan tepat 1 padanan pesakit, auto-select ke panel kiri
    if raw_search and len(patients) == 1 and is_station:
        trigger_payload["autoSelectPatientId"] = patients[0].id

    response.headers["HX-Trigger"] = json.dumps({
        "updateQueueCount": trigger_payload
    })
    
    return response

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