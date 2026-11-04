import io
import random
import string
import qrcode

def generate_purpose_token(purpose: str) -> str:
    prefixes = {
        "SAKIT_BIASA": "D",
        "TEMUJANJI": "A",
        "DRESSING": "P",
        "LAIN_LAIN": "U"
    }
    prefix = prefixes.get(purpose, "K")
    suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=3))
    return f"{prefix}-{suffix}"

def create_qr_buffer(data: str) -> io.BytesIO:
    qr = qrcode.QRCode(version=1, box_size=8, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf
