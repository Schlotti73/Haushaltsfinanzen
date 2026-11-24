import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.pfade import betriebsart, version
from app.server_config import erlaubte_origins
from app.routers import (
    auth, buchungen, kategorien, konten, projekte, wiederkehrend,
    statistik, belege, generierung,
    empfaenger, import_pdf, import_regel,
    geschaeft, haushaltsbuch, einstellungen, datenbanken, gebaeude,
    vertraege, fahrzeuge, erinnerungen, update,
)


def _init_db() -> None:
    """Schema sicherstellen – migrieren nur, wenn es erlaubt ist.

    In der Entwicklung zieht jeder Start das Schema nach. In der Produktion
    setzt die Dienst-Konfiguration FINANZ_AUTO_MIGRATE=0: dann wird nur
    geprueft, und bei Abweichung bricht der Start mit einer Meldung ab, die
    sagt, was zu tun ist. Migrieren darf dort allein das Update-Skript, das
    vorher ein Pflicht-Backup anlegt – siehe docs/release-paket.md.
    """
    from app.database import engine
    from app.db_init import init_db_schema, pruefe_schema
    from app.pfade import auto_migration_erlaubt

    if auto_migration_erlaubt():
        init_db_schema(engine)
    else:
        revision = pruefe_schema(engine)
        print(f"Schema geprueft (Alembic-Revision: {revision}).")


@asynccontextmanager
async def lifespan(_: FastAPI):
    _init_db()
    yield


app = FastAPI(
    title="Haushaltsfinanz-API",
    version=version(),
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

# Im Betrieb liefert dasselbe uvicorn API und Frontend aus; CORS braucht es nur
# fuer die Dev-Ports, die in config/server.json stehen.
app.add_middleware(
    CORSMiddleware,
    allow_origins=erlaubte_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(konten.router, prefix="/api")
app.include_router(kategorien.router, prefix="/api")
app.include_router(projekte.router, prefix="/api")
app.include_router(buchungen.router, prefix="/api")
app.include_router(wiederkehrend.router, prefix="/api")
app.include_router(statistik.router, prefix="/api")
app.include_router(belege.router, prefix="/api")
app.include_router(generierung.router, prefix="/api")
app.include_router(empfaenger.router, prefix="/api")
app.include_router(import_pdf.router, prefix="/api")
app.include_router(import_regel.router, prefix="/api")
app.include_router(geschaeft.router, prefix="/api")
app.include_router(haushaltsbuch.router, prefix="/api")
app.include_router(einstellungen.router, prefix="/api")
app.include_router(datenbanken.router, prefix="/api")
app.include_router(gebaeude.router, prefix="/api")
app.include_router(vertraege.router, prefix="/api")
app.include_router(fahrzeuge.router, prefix="/api")
app.include_router(erinnerungen.router, prefix="/api")
app.include_router(update.router, prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/version")
def version_info():
    """Die Paketversion, damit das Frontend sie anzeigen kann.

    Bewusst ohne Anmeldung und als eigener Endpunkt: dieselbe Angabe steckt
    schon im oeffentlichen /api/openapi.json, und das Frontend soll sie nicht
    als eigene Konstante mitschleppen - sonst zeigt die Oberflaeche nach einem
    Update weiter die alte Nummer.

    Dieselbe Auskunft traegt die Betriebsart ("standard" oder "docker"). Die
    Oberflaeche richtet daran zwei Dinge aus, die sonst ins Leere liefen: den
    Update-Befehl und die Windows-Felder der Backup-Einstellungen. Sie steht
    hier, weil sie wie die Version zum laufenden Programm gehoert und keine
    Anmeldung braucht - sie verraet nichts, was ein Blick auf die Seite nicht
    ohnehin zeigt.
    """
    return {"version": version(), "betriebsart": betriebsart()}


# SPA-Frontend aus dem Build-Verzeichnis ausliefern (nur in Prod, wenn vorhanden).
#
# Das Verzeichnis ist backend/static, so wie frontend/vite.config.js es mit
# outDir: '../backend/static' festlegt. Frueher stand hier frontend/dist - ein
# Ordner, den der Build nie erzeugt: das Frontend wurde dadurch gar nicht
# ausgeliefert. Wer den Ort aendert, aendert beides zusammen, und ausserdem die
# Pruefung in scripts/prod/create_prod_zip.ps1.
_FRONTEND_DIST = Path(__file__).resolve().parent.parent / "static"

if _FRONTEND_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=str(_FRONTEND_DIST / "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path: str):
        # Statische Dateien direkt ausliefern (z.B. manifest.json, favicon.ico)
        candidate = _FRONTEND_DIST / full_path
        if candidate.is_file():
            return FileResponse(str(candidate))
        return FileResponse(str(_FRONTEND_DIST / "index.html"))
