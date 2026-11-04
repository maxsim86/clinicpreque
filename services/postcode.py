import json
import os

# Cari fail postcodes.json di folder utama projek
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
POSTCODE_PATH = os.path.join(PROJECT_ROOT, "postcodes.json")

# Muat data poskod
POSTCODES = {}
if os.path.exists(POSTCODE_PATH):
    try:
        with open(POSTCODE_PATH, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
            # Pastikan semua kunci dijadikan String
            POSTCODES = {str(k).strip(): v for k, v in raw_data.items()}
    except Exception as e:
        print(f"Ralat membaca postcodes.json: {e}")
else:
    print(f"Amaran: Fail postcodes.json TIDAK DIJUMPAI di: {POSTCODE_PATH}")

def check_pandamaran_zone(postcode: str) -> dict:
    clean_code = str(postcode).strip().replace(" ", "")
    info = POSTCODES.get(clean_code)
    
    if info:
        return {
            "found": True,
            "in_zone": info.get("in_zone", False),
            "city": info.get("city", "KLANG"),
            "state": info.get("state", "SELANGOR"),
            "area": info.get("area", "Klang"),
            "nearest_kk": info.get("nearest_kk", "")
        }
    
    return {
        "found": False,
        "in_zone": False,
        "message": "Poskod di luar kawasan operasi KK Pandamaran."
    }
