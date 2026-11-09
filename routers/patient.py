from fastapi import APIRouter, Request, Form, Depends, BackgroundTasks
from fastapi.responses import HTMLResponse, StreamingResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from core.database import get_db
from core.config import TRANSLATIONS
from models.queue import PatientQueue
from services.qr import generate_purpose_token, create_qr_buffer
from services.postcode import check_pandamaran_zone
from services.sse_manager import sse_manager

router = APIRouter(tags=["Patient"])
templates = Jinja2Templates(directory="templates")


@router.get("/register", response_class=HTMLResponse)
def get_patient_form(request: Request, lang: str = "bm", elderly: str = "false"):
    is_elderly = elderly.lower() in ["true", "1", "yes"]
    texts = TRANSLATIONS.get(lang, TRANSLATIONS["bm"])
    return templates.TemplateResponse(
        request=request,
        name="patient_form.html",
        context={"t": texts, "lang": lang, "elderly": is_elderly},
    )


@router.get("/get-form-content", response_class=HTMLResponse)
def get_form_content(request: Request, lang: str = "bm", elderly: str = "false"):
    is_elderly = elderly.lower() in ["true", "1", "yes"]
    texts = TRANSLATIONS.get(lang, TRANSLATIONS["bm"])
    return templates.TemplateResponse(
        request=request,
        name="partials/form_content.html",
        context={"t": texts, "lang": lang, "elderly": is_elderly},
    )


@router.get("/api/lookup-postcode/{postcode}")
def api_lookup_postcode(postcode: str):
    return check_pandamaran_zone(postcode)


@router.get("/qr/{token_code}")
def get_qr_image(token_code: str):
    buf = create_qr_buffer(token_code)
    return StreamingResponse(buf, media_type="image/png")


@router.get("/check-ic", response_class=HTMLResponse)
def check_returning_patient(
    request: Request, ic_passport: str = "", db: Session = Depends(get_db)
):
    clean_ic = ic_passport.strip().upper()
    if len(clean_ic) < 8:
        return Response(content="", status_code=200)

    patient = (
        db.query(PatientQueue)
        .filter(PatientQueue.ic_passport == clean_ic)
        .order_by(PatientQueue.id.desc())
        .first()
    )

    if patient:
        return templates.TemplateResponse(
            request=request,
            name="partials/returning_patient.html",
            context={"patient": patient},
        )
    return Response(content="", status_code=200)


@router.post("/submit-patient", response_class=HTMLResponse)
async def submit_patient(
    request: Request,
    background_tasks: BackgroundTasks,
    ic_passport: str = Form(...),
    full_name: str = Form(...),
    phone_number: str = Form(...),
    visit_purpose: str = Form("SAKIT_BIASA"),
    address_status: str = Form("KEKAL"),
    address: str = Form("KEKAL SEPERTI REKOD SEDIA ADA"),
    db: Session = Depends(get_db),
):
    token = generate_purpose_token(visit_purpose, db)
    final_address = (
        address.strip().upper()
        if address_status == "DIKEMASKINI"
        else "KEKAL SEPERTI REKOD SEDIA ADA"
    )

    record = PatientQueue(
        ic_passport=ic_passport.strip().upper(),
        full_name=full_name.strip().upper(),
        phone_number=phone_number.strip(),
        visit_purpose=visit_purpose,
        address_status=address_status,
        address=final_address,
        token_code=token,
        is_served=False,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    # WAJIB: Siarkan isyarat SSE kepada semua skrin kaunter & station serta-merta
    background_tasks.add_task(sse_manager.broadcast_refresh)

    return templates.TemplateResponse(
        request=request,
        name="partials/success_token.html",
        context={"token": token, "patient": record},
    )
