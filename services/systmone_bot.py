# services/systmone_bot.py
import sys
import time

# Semak sama ada sistem operasi semasa ialah Windows
IS_WINDOWS = sys.platform.startswith("win")

if IS_WINDOWS:
    try:
        from pywinauto import Application
    except ImportError:
        Application = None
else:
    Application = None


def trigger_systmone_ticket(category: str) -> bool:
    """
    Menghantar arahan cetak tiket ke SystmOne mengikut kategori (OPD atau MCH).
    Di Linux: Mencetak simulasi ke terminal.
    Di Windows: Mengawal tetingkap SystmOne melalui pywinauto.
    """
    if not IS_WINDOWS or Application is None:
        # Mod Pembangunan di Linux / MacOS
        print(f"[DEV MOCK] Mengeluarkan tiket SystmOne bagi kategori: [{category}] (Bukan di persekitaran Windows)")
        return True

    # Mod Sebenar di PC Kaunter Klinik (Windows OS)
    try:
        app = Application(backend="win32").connect(title_re=".*SystmOne.*")
        main_window = app.top_window()

        if category == "OPD":
            # Tukar ke Tab OPD (Ctrl+1) lalu tekan butang cetak (F5)
            main_window.type_keys("^1")
            time.sleep(0.15)
            main_window.type_keys("{F5}")

        elif category == "MCH":
            # Tukar ke Tab MCH (Ctrl+2) lalu tekan butang cetak (F6)
            main_window.type_keys("^2")
            time.sleep(0.15)
            main_window.type_keys("{F6}")

        return True

    except Exception as e:
        print(f"[RALAT] Gagal menghantar arahan ke SystmOne ({category}): {e}")
        return False