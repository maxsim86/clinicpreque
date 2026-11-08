# main.py
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from brotli_asgi import BrotliMiddleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.responses import Response

from routers import counter, patient

app = FastAPI(title="KK Pandamaran Pre-Queue")

# 1. Aktifkan Pemampatan Brotli & GZip (Pilih format terbaik mengikut sokongan pelayar)
# Brotli sangat berkesan memampatkan teks HTML/CSS/JS (sehingga 80% pengurangan saiz)
app.add_middleware(BrotliMiddleware, quality=5, minimum_size=500)
app.add_middleware(GZipMiddleware, minimum_size=500)


# 2. Custom StaticFiles untuk dayakan HTTP Cache-Control (Cache selama 30 hari / 1 tahun)
class CachedStaticFiles(StaticFiles):
    def file_response(self, *args, **kwargs) -> Response:
        response = super().file_response(*args, **kwargs)
        # 2592000 saat = 30 hari
        response.headers["Cache-Control"] = "public, max-age=2592000, immutable"
        return response

app.mount("/static", CachedStaticFiles(directory="static"), name="static")

# Masukkan router
app.include_router(counter.router)
app.include_router(patient.router)