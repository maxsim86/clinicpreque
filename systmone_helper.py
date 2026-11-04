import time
import pyautogui
import pyperclip
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
# Benarkan permintaan daripada domain/IP server FastAPI klinik
CORS(app)

# Konfigurasi kelajuan taipan pyautogui (selang masa kecil)
pyautogui.PAUSE = 0.08

def type_text(text):
    """
    Menggunakan clipboard paste untuk menyokong simbol/huruf besar 
    tanpa isu susunan papan kekunci
    """
    if not text:
        return
    pyperclip.copy(str(text))
    # Simulasi Ctrl + V
    pyautogui.hotkey('ctrl', 'v')
    time.sleep(0.05)

@app.route('/inject', methods=['POST'])
def inject_data():
    data = request.json
    ic_no = data.get('ic', '')
    name = data.get('name', '')
    phone = data.get('phone', '')
    address = data.get('address', '')
    
    # 1. Beri staf 2 saat untuk pastikan kursor berada dalam kotak pertama SystmOne
    time.sleep(2.0)

    # 2. Urutan suntikan kekunci (Sesuaikan dengan urutan Tab form SystmOne klinik anda)
    # Contoh urutan standard form carian/daftar SystmOne:
    
    # a. Isi No. KP (bersihkan sengkang)
    clean_ic = ic_no.replace("-", "").strip()
    type_text(clean_ic)
    pyautogui.press('tab')

    # b. Isi Nama Penuh
    type_text(name)
    pyautogui.press('tab')

    # c. Isi Nombor Telefon
    type_text(phone)
    pyautogui.press('tab')

    # d. Isi Alamat Penuh (jika ada kemaskini)
    if address and address != "KEKAL SEPERTI REKOD SEDIA ADA":
        type_text(address)
    
    return jsonify({"status": "success", "message": "Data berjaya disuntik ke SystmOne!"})

if __name__ == '__main__':
    # Berjalan di port setempat PC staf
    print("SystmOne Auto-Type Helper sedang berjalan di port 9999...")
    app.run(host='127.0.0.1', port=9999)
