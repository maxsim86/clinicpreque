import json
import re
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import List, Optional

from fastapi import APIRouter, Request, Form, Depends, Response, BackgroundTasks
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_

from core.database import get_db
from models.queue import PatientQueue
from services.systmone_bot import trigger_systmone_ticket
from services.sse_manager import sse_manager

router = APIRouter(prefix="/counter", tags=["Counter"])
templates = Jinja2Templates(directory="templates")


def get_next_token(db: Session) -> str:
    """Menjana nombor token harian ringkas (cth: A0001)"""
    kl_tz = ZoneInfo("Asia/Kuala_Lumpur")
    today_start = datetime.now(kl_tz).replace(hour=0, minute=0, second=0, microsecond=0)

    last_patient = (
        db.query(PatientQueue)
        .filter(PatientQueue.created_at >= today_start)
        .order_by(PatientQueue.id.desc())
        .first()
    )

    next_num = 1
    if last_patient and last_patient.token_code:
        digits = re.sub(r"[^0-9]", "", last_patient.token_code)
        if digits:
            next_num = int(digits) + 1

    return f"A{next_num:04d}"


# ==========================================
# 0. PENDAFTARAN WALK-IN & EDIT TOKEN
# ==========================================


@router.post("/station/quick-walkin", response_class=HTMLResponse)
async def quick_walkin_register(
    request: Request,
    background_tasks: BackgroundTasks,
    full_name: str = Form(...),
    ic_passport: str = Form(...),
    phone_number: Optional[str] = Form("-"),
    address: Optional[str] = Form("-"),
    db: Session = Depends(get_db),
):
    clean_ic = ic_passport.strip().upper().replace("-", "")
    token = get_next_token(db)

    new_patient = PatientQueue(
        full_name=full_name.strip().upper(),
        ic_passport=clean_ic,
        phone_number=phone_number.strip() if phone_number else "-",
        address=address.strip() if address else "-",
        address_status="KEKAL",
        token_code=token,
        visit_purpose="OPD",
        is_served=False,
    )
    db.add(new_patient)
    db.commit()
    db.refresh(new_patient)

    # Siarkan ke stesen lain melalui SSE
    background_tasks.add_task(sse_manager.broadcast_refresh)

    card_html = templates.TemplateResponse(
        request=request,
        name="partials/active_patient_card.html",
        context={"p": new_patient, "patient": new_patient},
    ).body.decode("utf-8")

    # PASTIKAN ada "refreshQueue": True supaya stesen ini terus kemas kini senarai
    headers = {
        "HX-Trigger": json.dumps(
            {"refreshQueue": True, "playAudioSuccess": True, "closeWalkInModal": True}
        )
    }
    return HTMLResponse(content=card_html, headers=headers)


@router.get("/edit-token/{patient_id}", response_class=HTMLResponse)
def get_edit_token_form(
    request: Request, patient_id: int, db: Session = Depends(get_db)
):
    patient = db.query(PatientQueue).filter(PatientQueue.id == patient_id).first()
    if not patient:
        return HTMLResponse(
            "<span class='text-xs text-rose-500 font-bold'>Tiada</span>",
            status_code=404,
        )

    return templates.TemplateResponse(
        request=request,
        name="partials/token_edit_form.html",
        context={"patient": patient},
    )


@router.post("/update-token/{patient_id}", response_class=HTMLResponse)
async def update_patient_token(
    request: Request,
    background_tasks: BackgroundTasks,
    patient_id: int,
    new_token: str = Form(...),
    db: Session = Depends(get_db),
):
    patient = db.query(PatientQueue).filter(PatientQueue.id == patient_id).first()
    if patient:
        clean_token = new_token.strip().upper()
        patient.token_code = clean_token
        patient.systmone_queue_no = clean_token
        db.commit()
        background_tasks.add_task(sse_manager.broadcast_refresh)

    return templates.TemplateResponse(
        request=request, name="partials/token_badge.html", context={"patient": patient}
    )


@router.get("/cancel-edit-token/{patient_id}", response_class=HTMLResponse)
def cancel_edit_token(request: Request, patient_id: int, db: Session = Depends(get_db)):
    patient = db.query(PatientQueue).filter(PatientQueue.id == patient_id).first()
    if not patient:
        return HTMLResponse("", status_code=404)

    return templates.TemplateResponse(
        request=request, name="partials/token_badge.html", context={"patient": patient}
    )


# ==========================================
# 1. PENGURUSAN PESAKIT & CETAK SEMULA
# ==========================================


@router.post("/cancel-patient/{patient_id}")
async def cancel_patient_queue(
    patient_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)
):
    patient = db.query(PatientQueue).filter(PatientQueue.id == patient_id).first()
    if patient:
        patient.is_served = True
        patient.systmone_queue_no = "DIBATALKAN"
        db.commit()
        background_tasks.add_task(sse_manager.broadcast_refresh)

    headers = {"HX-Trigger": json.dumps({"clearActivePatient": True})}
    return Response(content="", status_code=200, headers=headers)


@router.post("/reprint-last", response_class=HTMLResponse)
def reprint_last_ticket(
    background_tasks: BackgroundTasks, db: Session = Depends(get_db)
):
    """Cetak semula tiket bagi pesakit terakhir yang diproses"""
    last_patient = (
        db.query(PatientQueue)
        .filter(
            PatientQueue.is_served == True,
            PatientQueue.systmone_queue_no.isnot(None),
            PatientQueue.systmone_queue_no != "DIBATALKAN",
        )
        .order_by(PatientQueue.id.desc())
        .first()
    )

    if not last_patient:
        return HTMLResponse("""
            <div id="reprint-toast" class="fixed bottom-5 right-5 bg-rose-600 text-white text-xs font-bold px-4 py-2.5 rounded-2xl shadow-xl animate-fade-in z-50 flex items-center gap-2">
                <span>⚠️ Tiada rekod tiket sedia ada untuk dicetak semula.</span>
            </div>
            <script>setTimeout(() => { const t = document.getElementById('reprint-toast'); if(t) t.remove(); }, 3500);</script>
        """)

    cat = "OPD"
    if "M" in (last_patient.systmone_queue_no or ""):
        cat = "MCH"
    elif "S" in (last_patient.systmone_queue_no or ""):
        cat = "PAKAR"

    background_tasks.add_task(trigger_systmone_ticket, cat)

    return HTMLResponse(f"""
        <div id="reprint-toast" class="fixed bottom-5 right-5 bg-slate-900 text-white text-xs font-bold px-4 py-3 rounded-2xl shadow-2xl animate-fade-in z-50 flex items-center gap-2 border border-slate-700">
            <span class="text-emerald-400 text-sm">🖨️</span>
            <span>Tiket terakhir <span class="text-blue-400 font-black">[{last_patient.systmone_queue_no}]</span> ({last_patient.full_name}) dihantar semula ke pencetak!</span>
        </div>
        <script>setTimeout(() => {{ const t = document.getElementById('reprint-toast'); if(t) t.remove(); }}, 3500);</script>
    """)


# ==========================================
# 2. STESEN PRA-GILIRAN (PRE-QUEUE STATION)
# ==========================================


@router.get("/station", response_class=HTMLResponse)
def get_prequeue_station(request: Request, db: Session = Depends(get_db)):
    """Memaparkan stesen saringan bersama senarai menunggu awal"""
    patients = (
        db.query(PatientQueue)
        .filter(PatientQueue.is_served == False)
        .order_by(PatientQueue.created_at.asc())
        .limit(15)
        .all()
    )
    return templates.TemplateResponse(
        request=request,
        name="prequeue_station.html",
        context={"request": request, "patients": patients},
    )


@router.get("/station/patient-card/{patient_id}", response_class=HTMLResponse)
def get_patient_card(request: Request, patient_id: int, db: Session = Depends(get_db)):
    patient = db.query(PatientQueue).filter(PatientQueue.id == patient_id).first()
    if not patient:
        return HTMLResponse(
            "<div class='p-4 text-xs text-rose-500 font-bold'>Pesakit tidak dijumpai.</div>"
        )

    return templates.TemplateResponse(
        request=request,
        name="partials/active_patient_card.html",
        context={"p": patient, "patient": patient},
    )


@router.get("/station/scan-select/{scanned_code}", response_class=HTMLResponse)
def scan_select_patient(
    request: Request, scanned_code: str, db: Session = Depends(get_db)
):
    clean_code = scanned_code.strip().upper().replace("-", "")

    patient = (
        db.query(PatientQueue)
        .filter(
            or_(
                PatientQueue.token_code == scanned_code.strip().upper(),
                PatientQueue.ic_passport.like(f"%{clean_code}%"),
            ),
            PatientQueue.is_served == False,
        )
        .order_by(PatientQueue.id.desc())
        .first()
    )

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
        context={"p": patient, "patient": patient},
    )


@router.post("/station/process-ticket", response_class=HTMLResponse)
async def process_station_ticket(
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
    db: Session = Depends(get_db),
):
    if not patient_id:
        return HTMLResponse(
            "<div class='p-3 bg-rose-50 border border-rose-200 rounded-xl text-rose-800 text-xs font-bold'>⚠️ Sila pilih pesakit terlebih dahulu!</div>"
        )

    patient = db.query(PatientQueue).filter(PatientQueue.id == patient_id).first()
    if not patient:
        return HTMLResponse(
            "<div class='p-3 bg-rose-50 border border-rose-200 rounded-xl text-rose-800 text-xs font-bold'>⚠️ Rekod tidak ditemui.</div>"
        )

    background_tasks.add_task(trigger_systmone_ticket, category)

    clean_num = re.sub(r"^[A-Za-z\-]+", "", patient.token_code)
    generated_ticket = (
        f"E-{prefix}-{clean_num}" if is_priority else f"{prefix}-{clean_num}"
    )

    patient.systmone_queue_no = generated_ticket
    patient.is_served = True
    patient.is_priority = bool(is_priority)
    patient.priority_reason = priority_reason if is_priority else None
    patient.is_blood_test = bool(is_blood_test)
    patient.lab_tests = ", ".join(test_type) if test_type else None
    patient.fasting_status = fasting if is_blood_test else None
    patient.lab_notes = lab_notes.strip() if lab_notes else None
    db.commit()

    # Siarkan kemas kini SSE kepada semua pelanggan
    background_tasks.add_task(sse_manager.broadcast_refresh)

    response_html = f"""<div class="p-3.5 bg-emerald-50 border-2 border-emerald-300 rounded-2xl text-emerald-950 text-xs font-bold flex justify-between items-center shadow-sm animate-fade-in mb-3">
        <span>Tiket <span class="text-blue-700 underline font-black">[{generated_ticket}]</span> ({category}) sedia diproses!</span>
    </div>
    <div id="active-patient-zone" hx-swap-oob="true">
        <div class="bg-white border-2 border-dashed border-slate-300 rounded-3xl p-8 text-center text-slate-400">
            <span class="text-4xl block mb-2">📷</span>
            <p class="font-extrabold text-sm text-slate-700">Sedia Menerima Imbasan Kod Bar / QR Seterusnya</p>
        </div>
    </div>"""

    return HTMLResponse(content=response_html)


# ==========================================
# 3. STREAM SSE & POLING SENARAI
# ==========================================


@router.get("/stream")
async def sse_queue_stream(request: Request):
    async def event_generator():
        q = await sse_manager.subscribe()
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    await asyncio.wait_for(q.get(), timeout=20.0)
                    # Pastikan nama event tepat: "queueUpdate"
                    yield {"event": "queueUpdate", "data": "refresh"}
                except asyncio.TimeoutError:
                    # Ping keep-alive untuk mengelakkan sambungan ditutup oleh pelayar
                    yield {"event": "ping", "data": "keep-alive"}
        finally:
            sse_manager.unsubscribe(q)

    return EventSourceResponse(event_generator())


@router.get("", response_class=HTMLResponse)
def counter_dashboard(request: Request, db: Session = Depends(get_db)):
    patients = (
        db.query(PatientQueue)
        .filter(PatientQueue.is_served == False)
        .order_by(PatientQueue.created_at.asc())
        .limit(30)
        .all()
    )
    return templates.TemplateResponse(
        request=request, name="staff_dashboard.html", context={"patients": patients}
    )


@router.get("/queue-rows", response_class=HTMLResponse)
def get_queue_rows(
    request: Request,
    search: str = "",
    purpose_filter: str = "ALL",
    station_mode: Optional[bool] = False,
    db: Session = Depends(get_db),
):
    total_waiting = (
        db.query(PatientQueue).filter(PatientQueue.is_served == False).count()
    )
    query = db.query(PatientQueue).filter(PatientQueue.is_served == False)

    if purpose_filter and purpose_filter != "ALL":
        query = query.filter(PatientQueue.visit_purpose == purpose_filter)

    raw_search = search.strip()
    if raw_search:
        clean_digits = re.sub(r"[^0-9A-Za-z]", "", raw_search).upper()
        upper_search = raw_search.upper()
        conditions = []

        conditions.append(PatientQueue.token_code.like(f"%{upper_search}%"))

        if clean_digits.isdigit() and len(clean_digits) == 4:
            conditions.append(PatientQueue.ic_passport.like(f"%{clean_digits}"))
        elif clean_digits.isdigit() and len(clean_digits) > 4:
            conditions.append(PatientQueue.ic_passport.like(f"%{clean_digits}%"))
        else:
            conditions.append(PatientQueue.ic_passport.like(f"%{upper_search}%"))

        name_words = [w for w in upper_search.split() if len(w) > 1]
        if name_words:
            for word in name_words:
                conditions.append(PatientQueue.full_name.like(f"%{word}%"))
        else:
            conditions.append(PatientQueue.full_name.like(f"%{upper_search}%"))

        query = query.filter(or_(*conditions))
        patients = query.order_by(PatientQueue.created_at.asc()).limit(10).all()
    else:
        patients = query.order_by(PatientQueue.created_at.asc()).limit(15).all()

    referer = request.headers.get("referer", "")
    is_station = station_mode or ("station" in referer)
    template_name = (
        "partials/station_rows.html" if is_station else "partials/patient_rows.html"
    )

    response = templates.TemplateResponse(
        request=request, name=template_name, context={"patients": patients}
    )

    trigger_payload = {"value": total_waiting}
    if raw_search and len(patients) == 1 and is_station:
        trigger_payload["autoSelectPatientId"] = patients[0].id

    response.headers["HX-Trigger"] = json.dumps({"updateQueueCount": trigger_payload})

    return response


@router.post("/serve/{patient_id}")
async def mark_served(
    patient_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)
):
    patient = db.query(PatientQueue).filter(PatientQueue.id == patient_id).first()
    if patient:
        patient.is_served = True
        db.commit()
        background_tasks.add_task(sse_manager.broadcast_refresh)
    return Response(content="", status_code=200)


@router.get("/copy-field", response_class=HTMLResponse)
def copy_field(request: Request, text: str, label: str):
    clean_text = text.strip()
    if label in ["No. KP", "No. Tel", "No. Telefon"]:
        clean_text = "".join(filter(str.isalnum, clean_text))

    headers = {"HX-Trigger": json.dumps({"triggerCopy": clean_text})}

    return templates.TemplateResponse(
        request=request,
        name="partials/toast_notification.html",
        context={"label": label},
        headers=headers,
    )


@router.get("/api/get-patient/{ic_passport}")
def api_get_patient(ic_passport: str, db: Session = Depends(get_db)):
    patient = (
        db.query(PatientQueue)
        .filter(
            PatientQueue.ic_passport == ic_passport.strip().upper(),
            PatientQueue.is_served == False,
        )
        .first()
    )

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
        "systmone_queue": patient.systmone_queue_no,
    }
