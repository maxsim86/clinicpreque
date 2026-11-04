from fastapi import FastAPI
from core.database import engine, Base
from routers import patient, counter

# Cipta jadual pangkalan data secara automatik
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Sistem Pra-Giliran KK Pandamaran",
    description="Sistem pendaftaran pantas bersepadu kaunter & triage",
    version="2.0.0"
)

# Daftarkan Router Modul
app.include_router(patient.router)
app.include_router(counter.router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
