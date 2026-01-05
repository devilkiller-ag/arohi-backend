# Free Deployment Guide

This guide covers deploying the Arohi Health Coach backend for free using Render.com and Upstash Redis.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        FREE TIER SETUP                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐         │
│  │ Render.com  │    │   Upstash   │    │    Neon     │         │
│  │ Web Service │───▶│   Redis     │    │ PostgreSQL  │         │
│  │ (Free)      │    │   (Free)    │    │   (Free)    │         │
│  │             │    │ 10K cmd/day │    │ 0.5GB       │         │
│  │ - FastAPI   │    └─────────────┘    └─────────────┘         │
│  │ - WebSocket │              │                │               │
│  │ - Scheduler │              └────────────────┘               │
│  └─────────────┘                      │                        │
│         │                             │                        │
│         └─────────────────────────────┘                        │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Free Tier Limitations:**
- Render web services spin down after 15 mins of inactivity
- First request after sleep takes 30-50 seconds (cold start)
- Upstash: 10,000 Redis commands per day
- Neon: 0.5GB storage, auto-suspend after 5 mins inactivity

---

## Step 1: Set Up Upstash Redis

1. Go to [upstash.com](https://upstash.com) and create an account
2. Click "Create Database"
3. Select:
   - Name: `arohi-redis`
   - Region: Choose closest to your users
   - Type: Regional (free)
4. Copy the Redis URL from the dashboard:
   ```
   rediss://default:xxxxx@xxx-xxxxx.upstash.io:6379
   ```

---

## Step 2: Replace Celery with APScheduler (For Free Tier)

Celery requires a separate worker process which isn't free on most platforms.
We'll use APScheduler instead, which runs in the same process.

### Install APScheduler

Add to `requirements.txt`:
```
apscheduler==3.10.4
```

### Create Scheduler Module

Create `app/scheduler.py`:

```python
"""Background scheduler for follow-up tasks (replaces Celery for free tier)."""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from contextlib import asynccontextmanager

scheduler = AsyncIOScheduler()


def process_scheduled_reminders_job():
    """Process pending follow-up messages."""
    from app.database import SessionLocal
    from app.services.followup_service import get_followup_service
    from app.services.llm_service import get_llm_service
    from app.services.memory_service import get_memory_service
    from app.services.profile_service import get_profile_service
    from app.models.message import Message, MessageStatus
    from datetime import datetime

    db = SessionLocal()
    try:
        followup_service = get_followup_service()
        pending = followup_service.get_pending_followups(db)

        for followup in pending:
            try:
                user = followup.user
                if not user:
                    continue

                # Generate follow-up message
                llm_service = get_llm_service()
                memory_service = get_memory_service()
                profile_service = get_profile_service()

                memories = memory_service.get_user_memories(user.id, db)
                profile_context = profile_service.get_profile_context_for_llm(user.id, db)
                if profile_context:
                    memories.append(profile_context)

                context = followup.context or "Check in with the user"
                prompt = f"Send a follow-up message. Context: {context}"

                response = llm_service.generate_response(
                    user_message=prompt,
                    user_memories=memories if memories else None,
                )

                # Save message
                message = Message(
                    user_id=user.id,
                    role="assistant",
                    content=response,
                    status=MessageStatus.DELIVERED.value,
                )
                db.add(message)
                followup_service.mark_followup_sent(followup.id, db)
                db.commit()
                print(f"Sent follow-up to user {user.id}")

            except Exception as e:
                print(f"Error processing follow-up {followup.id}: {e}")
                followup_service.mark_followup_failed(followup.id, db)

    finally:
        db.close()


def check_and_send_followups_job():
    """Check for users needing proactive follow-ups."""
    from app.database import SessionLocal
    from app.services.followup_service import get_followup_service

    db = SessionLocal()
    try:
        followup_service = get_followup_service()
        users = followup_service.get_users_needing_followup(db)

        for user_id, reason in users:
            try:
                context = followup_service.generate_followup_context(user_id, reason, db)
                followup_service.schedule_proactive_followup(
                    user_id=user_id,
                    followup_type=reason,
                    context=context,
                    db=db,
                )
                print(f"Scheduled follow-up for user {user_id}: {reason}")
            except Exception as e:
                print(f"Error scheduling follow-up for {user_id}: {e}")

    finally:
        db.close()


def start_scheduler():
    """Start the background scheduler."""
    # Process reminders every minute
    scheduler.add_job(
        process_scheduled_reminders_job,
        CronTrigger(minute="*"),
        id="process_reminders",
        replace_existing=True,
    )

    # Check for follow-ups every hour
    scheduler.add_job(
        check_and_send_followups_job,
        CronTrigger(minute=0),
        id="check_followups",
        replace_existing=True,
    )

    scheduler.start()
    print("Background scheduler started")


def stop_scheduler():
    """Stop the background scheduler."""
    if scheduler.running:
        scheduler.shutdown()
        print("Background scheduler stopped")
```

### Update main.py

Modify `app/main.py` to use the scheduler:

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import health, auth, chat
from app.routers.websocket import router as websocket_router

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    from app.scheduler import start_scheduler
    start_scheduler()
    yield
    # Shutdown
    from app.scheduler import stop_scheduler
    stop_scheduler()


app = FastAPI(
    title="Arohi Health Coach API",
    description="AI-powered health coaching assistant",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router, prefix="/api", tags=["Health"])
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(chat.router, prefix="/api/chat", tags=["Chat"])
app.include_router(websocket_router, prefix="/api", tags=["WebSocket"])


@app.get("/")
async def root():
    return {
        "message": "Arohi Health Coach API",
        "docs": "/docs",
        "health": "/api/health",
    }
```

---

## Step 3: Deploy to Render.com

### 3.1 Prepare Repository

1. Push your code to GitHub: https://github.com/devilkiller-ag/arohi-backend
2. Make sure these files exist:
   - `requirements.txt` (with all dependencies)
   - `.python-version` (specifies Python 3.11.9)
   - `Procfile` (already exists)

### 3.2 Create Render Web Service

1. Go to [render.com](https://render.com) and sign up
2. Click "New" → "Web Service"
3. Connect your GitHub repository
4. Configure:

| Setting | Value |
|---------|-------|
| Name | `arohi-backend` |
| Region | Singapore (or closest) |
| Branch | `main` |
| Runtime | Python 3 |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Instance Type | Free |

### 3.3 Add Environment Variables

In Render dashboard, go to "Environment" and add:

```
DATABASE_URL=postgresql://neondb_owner:xxx@xxx.neon.tech/neondb?sslmode=require
REDIS_URL=redis://default:xxx@xxx.upstash.io:6379
GOOGLE_API_KEY=your-gemini-api-key
JWT_SECRET_KEY=your-secure-random-string-at-least-32-chars
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440
DEBUG=false
CORS_ORIGINS=https://arohi-healthcoach.vercel.app
```

### 3.4 Deploy

Click "Create Web Service". Render will:
1. Clone your repository
2. Install dependencies
3. Start your application

Your API will be available at: `https://arohi-backend-3gno.onrender.com/api`

---

## Step 4: Update Frontend Environment

Update your Vercel frontend environment variables:

```
NEXT_PUBLIC_API_URL=https://arohi-backend-3gno.onrender.com/api
NEXT_PUBLIC_WS_URL=wss://arohi-backend-3gno.onrender.com/api
```

Note: Use `wss://` (secure WebSocket) for production.

---

## Alternative: Railway.app ($5 Free Credit)

Railway gives you $5 free credit per month, enough for light usage with separate services.

### Deploy on Railway

1. Go to [railway.app](https://railway.app)
2. Create new project from GitHub
3. Add services:
   - Web service (FastAPI)
   - Redis (from Railway templates)
4. Configure environment variables
5. Deploy

Railway supports multiple services, so you can run Celery worker separately:

**Procfile for Railway:**
```
web: uvicorn app.main:app --host 0.0.0.0 --port $PORT
worker: celery -A app.celery_app worker --loglevel=info
beat: celery -A app.celery_app beat --loglevel=info
```

---

## Alternative: Fly.io (Free Tier)

Fly.io offers 3 shared-cpu-1x VMs for free.

### Install Fly CLI

```bash
# Windows (PowerShell)
powershell -Command "iwr https://fly.io/install.ps1 -useb | iex"

# Or download from https://fly.io/docs/hands-on/install-flyctl/
```

### Deploy

```bash
fly auth login
fly launch
```

Create `fly.toml`:
```toml
app = "arohi-backend"
primary_region = "sin"  # Singapore

[build]
  builder = "paketobuildpacks/builder:base"

[env]
  PORT = "8080"

[http_service]
  internal_port = 8080
  force_https = true
  auto_stop_machines = true
  auto_start_machines = true

[[services]]
  internal_port = 8080
  protocol = "tcp"

  [[services.ports]]
    handlers = ["http"]
    port = 80

  [[services.ports]]
    handlers = ["tls", "http"]
    port = 443
```

Set secrets:
```bash
fly secrets set DATABASE_URL="postgresql://..."
fly secrets set REDIS_URL="rediss://..."
fly secrets set GOOGLE_API_KEY="..."
fly secrets set JWT_SECRET_KEY="..."
```

Deploy:
```bash
fly deploy
```

---

## Handling Cold Starts (Render Free Tier)

Free tier services sleep after 15 minutes. To minimize impact:

### Option 1: Health Check Ping (External Service)

Use [UptimeRobot](https://uptimerobot.com) (free) to ping your API every 14 minutes:

1. Sign up at uptimerobot.com
2. Add new monitor:
   - Monitor Type: HTTP(s)
   - URL: `https://arohi-backend.onrender.com/api/health`
   - Monitoring Interval: 14 minutes

This keeps your service warm but uses some of your free tier resources.

### Option 2: Accept Cold Starts

For a personal/demo project, cold starts (30-50 seconds) might be acceptable.

---

## WebSocket Considerations

WebSocket connections will disconnect when:
1. Service goes to sleep (15 min inactivity)
2. Service restarts (deployments)

The frontend already has auto-reconnect logic, so users will reconnect automatically.

---

## Monitoring

### Render Dashboard
- View logs in real-time
- Monitor memory/CPU usage
- Check deployment status

### Upstash Dashboard
- Monitor Redis commands usage (10K/day limit)
- View connection stats

### Neon Dashboard
- Monitor database connections
- Check storage usage

---

## Cost Summary

| Service | Free Tier Limits | Monthly Cost |
|---------|------------------|--------------|
| Render Web Service | 750 hours, sleeps after 15 min | $0 |
| Upstash Redis | 10K commands/day | $0 |
| Neon PostgreSQL | 0.5GB, auto-suspend | $0 |
| UptimeRobot | 50 monitors | $0 |
| **Total** | | **$0** |

---

## Upgrading Later

When you need better performance:

| Upgrade | Cost | Benefit |
|---------|------|---------|
| Render Starter | $7/month | No sleep, faster |
| Render Background Worker | $7/month | Separate Celery worker |
| Upstash Pro | $10/month | More commands |
| Railway Pro | $20/month | Multiple services |

---

## Quick Start Checklist

- [ ] Create Upstash Redis database
- [ ] Add `apscheduler` to requirements.txt
- [ ] Create `app/scheduler.py`
- [ ] Update `app/main.py` with lifespan handler
- [ ] Push to GitHub
- [ ] Create Render web service
- [ ] Add environment variables
- [ ] Deploy
- [ ] Update frontend environment variables
- [ ] (Optional) Set up UptimeRobot for keep-alive pings
