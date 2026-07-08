from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings
from app.utils.response import error_response

# Import routers
from app.api import auth, services, bookings, payments, provider, me, reviews, public, admin

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Python FastAPI rebuild of EndlessPath Services backend",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Global CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request Logger Middleware (similar to Express logger)
@app.middleware("http")
async def log_requests(request: Request, call_next):
    print(f"[{datetime.utcnow().isoformat()}] {request.method} {request.url.path}")
    response = await call_next(request)
    return response

from datetime import datetime

# Health check (matches TypeScript /health endpoint)
@app.get("/health")
async def health_check():
    return {
        "status": "OK", 
        "message": "Marketplace Server is running"
    }

# --- Unified Global Error Handlers ---

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return error_response(
        message=str(exc.detail),
        error_code="UNAUTHORIZED" if exc.status_code == 401 else "FORBIDDEN" if exc.status_code == 403 else "NOT_FOUND" if exc.status_code == 404 else "BAD_REQUEST",
        status_code=exc.status_code
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    # Construct a human-readable list of validation errors
    msgs = []
    for err in errors:
        loc = " -> ".join(str(l) for l in err.get("loc", []))
        msgs.append(f"[{loc}]: {err.get('msg')}")
    
    return error_response(
        message="Request validation failed: " + "; ".join(msgs),
        error_code="VALIDATION_ERROR",
        status_code=422
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    print(f"CRITICAL GLOBAL ERROR: {exc}")
    import traceback
    traceback.print_exc()
    return error_response(
        message="Internal server error occurred.",
        error_code="INTERNAL_SERVER_ERROR",
        status_code=500
    )


# --- Register API Routers ---
API_PREFIX = "/api"

app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(services.router, prefix=API_PREFIX)
app.include_router(bookings.router, prefix=API_PREFIX)
app.include_router(payments.router, prefix=API_PREFIX)
app.include_router(reviews.router, prefix=API_PREFIX)
app.include_router(provider.router, prefix=API_PREFIX)
app.include_router(admin.router, prefix=API_PREFIX)
app.include_router(me.router, prefix=API_PREFIX)
app.include_router(public.router, prefix=API_PREFIX)
