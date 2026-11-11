"""Conciliação Inteligente — API (FastAPI)."""
import logging
import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from . import models  # noqa: F401  (registra as tabelas)
from .config import AUTO_CREATE_TABLES, IS_SQLITE, JWT_SECRET_ENV
from .db import Base, engine
from .parsers import ParseError
from .routers import auth, files, reconciliations, settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("conciliacao")

app = FastAPI(title="Conciliação Inteligente API", version="1.0.0", docs_url="/api/docs",
              openapi_url="/api/openapi.json", redoc_url=None)

_tables_ready = False


@app.middleware("http")
async def ensure_tables_and_log(request: Request, call_next):
    global _tables_ready
    if not _tables_ready and AUTO_CREATE_TABLES:
        Base.metadata.create_all(engine)
        _tables_ready = True
    t0 = time.perf_counter()
    response = await call_next(request)
    log.info("%s %s %s %.0fms", request.method, request.url.path, response.status_code,
             (time.perf_counter() - t0) * 1000)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(ParseError)
async def parse_error(_req, exc: ParseError):
    return JSONResponse({"detail": str(exc)}, status_code=422)


@app.exception_handler(RequestValidationError)
async def validation_error(_req, exc: RequestValidationError):
    campos = ", ".join(".".join(str(x) for x in e["loc"][1:]) for e in exc.errors())
    return JSONResponse({"detail": f"Dados inválidos na requisição: {campos}."}, status_code=422)


@app.exception_handler(Exception)
async def unexpected(_req, exc: Exception):
    if isinstance(exc, HTTPException):
        raise exc
    log.exception("Erro inesperado")
    return JSONResponse({"detail": "Erro interno ao processar a solicitação. Tente novamente ou contate o suporte."},
                        status_code=500)


@app.get("/api/health")
def health():
    return {"status": "ok", "database": "sqlite (temporário)" if IS_SQLITE else "postgresql",
            "jwt_secret": "variavel de ambiente" if JWT_SECRET_ENV else "gerado automaticamente no banco"}


for r in (auth.router, auth.users_router, files.router, reconciliations.router, settings.router):
    app.include_router(r)
