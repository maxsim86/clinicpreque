import json
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POSTCODE_PATH = os.path.join(BASE_DIR, "postcodes.json")

POSTCODES = {}
if os.path.exists(POSTCODE_PATH):
    with open(POSTCODE_PATH, "r", encoding="utf-8") as f:
        POSTCODES = json.load(f)

def check_pandamaran_zone(postcode: str) -> dict:
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
