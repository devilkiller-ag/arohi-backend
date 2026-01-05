import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import health, auth, chat
from app.routers import websocket as ws_router

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown events."""
    # Startup: Start background scheduler (replaces Celery for free tier)
    use_scheduler = os.environ.get("USE_SCHEDULER", "true").lower() == "true"
    if use_scheduler:
        try:
            from app.scheduler import start_scheduler
            start_scheduler()
        except Exception as e:
            print(f"Warning: Could not start scheduler: {e}")
    yield
    # Shutdown: Stop scheduler
    if use_scheduler:
        try:
            from app.scheduler import stop_scheduler
            stop_scheduler()
        except Exception:
            pass


app = FastAPI(
    title="Arohi - Health Coach",
    description="Personal health coaching API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Configure CORS
origins = [origin.strip() for origin in settings.cors_origins.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router, prefix="/api", tags=["Health"])
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(chat.router, prefix="/api/chat", tags=["Chat"])
app.include_router(ws_router.router, prefix="/api", tags=["WebSocket"])


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "Welcome to Arohi - Health Coach API",
        "docs": "/docs",
        "health": "/api/health",
    }
