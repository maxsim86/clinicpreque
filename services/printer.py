# services/printer.py
from escpos.printer import Win32Raw

def print_blood_test_ticket(patient_name: str, ic_no: str, systmone_queue: str, tests_list: list, fasting_status: str, notes: str = ""):
    """
    Mencetak tiket kombo (SystmOne Queue + Slip Pengambilan Darah)
    terus ke Bixolon SRP-350III
    """
    try:
        p = Win32Raw(printer_name="BIXOLON SRP-350III")
        
        # ================= BAHAGIAN 1: TIKET GILIRAN SYSTMONE =================
        p.set(align='center', font='a', width=1, height=1)
        p.text("KLINIK KESIHATAN PANDAMARAN\n")
        p.text("BILIK PENGAMBILAN DARAH / MAKMAL\n")
        p.text("--------------------------------\n")
        
        # Nombor Giliran SystmOne (Besar & Jelas)
        p.set(align='center', font='a', width=3, height=4, bold=True)
        p.text(f"{systmone_queue}\n\n")
        
        p.set(align='left', font='a', width=1, height=1, bold=False)
        p.text(f"Nama : {patient_name[:24]}\n")
        p.text(f"No.KP: {ic_no}\n")
        p.text("Sila tunggu nombor dipanggil ke Bilik Darah.\n")
        p.text("================================\n") # Garisan pemisah
        
        # ================= BAHAGIAN 2: SLIP NOTA UJIAN MAKMAL =================
        p.set(align='center', font='a', width=1, height=2, bold=True)
        p.text("SLIP ARAHAN UJIAN MAKMAL\n")
        
        p.set(align='left', font='a', width=1, height=1, bold=False)
        p.text(f"Status Puasa: [{fasting_status}]\n")
        p.text("Senarai Ujian Darah:\n")
        
        # Senaraikan ujian yang ditik
        p.set(align='left', font='a', width=1, height=1, bold=True)
        for t in tests_list:
            p.text(f" [X] {t}\n")
            
        if notes:
            p.set(align='left', font='a', width=1, height=1, bold=False)
            p.text(f"Catatan: {notes}\n")
            
        p.text("--------------------------------\n")
        p.set(align='center', font='a', width=1, height=1)
        p.text("Serahkan slip ini kepada petugas makmal\n\n\n")
        
        # Potong kertas
        p.cut()
        p.close()
        return True
    except Exception as e:
        print(f"Ralat cetak Bixolon: {e}")
        return False