from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import get_settings
from .routers import public, reports, staff_auth, staff_cases

settings = get_settings()

app = FastAPI(
    title="HakKöprü API",
    version="0.1.0",
    description="Sendika–çalışan başvuru ve vaka yönetimi (pilot).",
    docs_url="/api/docs" if settings.env != "prod" else None,
    redoc_url=None,
    openapi_url="/api/openapi.json" if settings.env != "prod" else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Frame-Options"] = "DENY"
    return response


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    # Kullanıcının girdiği değeri hata yanıtına geri yansıtmıyoruz (hassas olabilir).
    errors = []
    for e in exc.errors():
        msg = e.get("msg", "Geçersiz değer")
        if msg.startswith("Value error, "):
            msg = msg[len("Value error, "):]
        errors.append({"field": ".".join(str(x) for x in e.get("loc", [])[1:]), "message": msg})
    return JSONResponse(status_code=422, content={"detail": errors[0]["message"] if errors else "Geçersiz istek", "errors": errors})


@app.get("/api/health")
def health():
    return {"ok": True}


app.include_router(public.router)
app.include_router(staff_auth.router)
app.include_router(staff_cases.router)
app.include_router(reports.router)
