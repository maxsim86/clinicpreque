import io
import qrcode
from datetime import datetime
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session
from models.queue import PatientQueue

def generate_purpose_token(purpose: str, db: Session) -> str:
    """
    Menjana token giliran harian mengikut kategori (D00001, A00001, dll).
    Bermula semula dari 00001 setiap hari mengikut waktu tempatan Malaysia (Asia/Kuala_Lumpur).
    """
    prefixes = {
        "SAKIT_BIASA": "D",
        "TEMUJANJI": "A",
        "DRESSING": "P",
        "LAIN_LAIN": "U"
    }
    prefix = prefixes.get(purpose, "K")
    
    # 1. Tetapkan waktu permulaan hari ini (00:00:00) waktu Malaysia
    today_start = datetime.now(ZoneInfo("Asia/Kuala_Lumpur")).replace(
        hour=0, minute=0, second=0, microsecond=0, tzinfo=None
    )

    # 2. Dapatkan semua token hari ini yang sepadan dengan kategori ini
    existing_tokens = db.query(PatientQueue.token_code).filter(
        PatientQueue.token_code.like(f"{prefix}%"),
        PatientQueue.created_at >= today_start
    ).all()

    # 3. Cari nombor siri tertinggi bagi hari ini
    max_num = 0
    for (t_code,) in existing_tokens:
        if t_code:
            digits = ''.join(filter(str.isdigit, t_code))
            if digits:
                try:
                    num = int(digits)
                    if num > max_num:
                        max_num = num
                except ValueError:
                    pass

    # 4. Jana nombor turutan seterusnya (cth: D00001, D00002)
    next_number = max_num + 1
    return f"{prefix}{next_number:04d}"


def create_qr_buffer(data: str) -> io.BytesIO:
    """Menjana imej kod QR ke dalam bentuk buffer ingatan (In-Memory Buffer)"""
    qr = qrcode.QRCode(version=1, box_size=8, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf