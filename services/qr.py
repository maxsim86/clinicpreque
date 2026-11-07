import io
import qrcode
from datetime import datetime
from sqlalchemy.orm import Session
from models.queue import PatientQueue

def generate_purpose_token(purpose: str, db: Session) -> str:
    """
    Menjana nombor giliran bersiri harian mengikut kategori:
    Contoh: D00001, A00001, P00001, U00001
    """
    prefixes = {
        "SAKIT_BIASA": "D",
        "TEMUJANJI": "A",
        "DRESSING": "P",
        "LAIN_LAIN": "U"
    }
    prefix = prefixes.get(purpose, "K")
    
    # Kira bilangan pesakit kategori ini untuk hari ini
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    count_today = db.query(PatientQueue).filter(
        PatientQueue.token_code.like(f"{prefix}%"),
        PatientQueue.created_at >= today_start
    ).count()

    next_number = count_today + 1
    # Format 5 digit: D00001 (atau tukar :04d jika mahu D0001)
    return f"{prefix}{next_number:05d}"

def create_qr_buffer(data: str) -> io.BytesIO:
    qr = qrcode.QRCode(version=1, box_size=8, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf