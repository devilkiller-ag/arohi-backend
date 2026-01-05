# Arohi Health Coach - Backend API

A production-ready health coaching API that provides personalized health guidance through conversational AI. Built with FastAPI, PostgreSQL, and Google Gemini AI.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Features](#features)
- [Database Schema](#database-schema)
- [API Reference](#api-reference)
- [WebSocket Protocol](#websocket-protocol)
- [Background Tasks](#background-tasks)
- [Configuration](#configuration)
- [Installation](#installation)
- [Deployment](#deployment)

---

## Overview

Arohi is an AI-powered health coach designed to provide personalized health guidance through natural conversation. The system features:

- Real-time messaging with WhatsApp-like delivery status
- Multilingual support (English, Hindi, Hinglish)
- Intelligent follow-up scheduling
- Progressive user profiling through conversation
- Long-term memory for personalization

---

## Architecture

### High-Level Architecture

```
                                    +------------------+
                                    |   PostgreSQL     |
                                    |   (Neon Cloud)   |
                                    +--------+---------+
                                             |
+-------------+     +---------------+        |        +---------------+
|   Frontend  |<--->|   FastAPI     |<-------+------->|    Redis      |
|  (Next.js)  |     |   (Uvicorn)   |                 | (Msg Broker)  |
+-------------+     +-------+-------+                 +-------+-------+
      ^                     |                                 |
      |              WebSocket                                |
      |              REST API                                 v
      |                     |                         +---------------+
      +---------------------+                         | Celery Worker |
                                                      | (Background)  |
                                                      +---------------+
                                                              |
                                                              v
                                                      +---------------+
                                                      |  Google Gemini|
                                                      |  (AI Model)   |
                                                      +---------------+
```

### Request Flow

1. **Authentication**: JWT tokens validate all requests
2. **WebSocket Connection**: Real-time bidirectional communication
3. **Message Processing**: User message saved, AI response generated
4. **Context Injection**: Memories, profile data, and protocols added to LLM context
5. **Background Processing**: Memory extraction, profile updates, follow-up scheduling

### Service Layer Architecture

```
+------------------+     +------------------+     +------------------+
|   LLM Service    |     | Memory Service   |     | Profile Service  |
|  (AI Response)   |     | (Fact Storage)   |     | (Health Data)    |
+--------+---------+     +--------+---------+     +--------+---------+
         |                        |                        |
         v                        v                        v
+------------------------------------------------------------------+
|                        WebSocket Handler                          |
|                    (Message Orchestration)                        |
+------------------------------------------------------------------+
         |                        |                        |
         v                        v                        v
+------------------+     +------------------+     +------------------+
| Protocol Service |     | FollowUp Service |     |Onboarding Service|
| (Guidelines)     |     | (Scheduling)     |     | (New Users)      |
+------------------+     +------------------+     +------------------+
```

---

## Tech Stack

| Category | Technology | Version | Purpose |
|----------|------------|---------|---------|
| Framework | FastAPI | 0.109.0 | Web framework with async support |
| Server | Uvicorn | 0.27.0 | ASGI server |
| Database | PostgreSQL | 15+ | Primary data store |
| ORM | SQLAlchemy | 2.0.25 | Database operations |
| Migrations | Alembic | 1.13.1 | Schema migrations |
| Task Queue | Celery | 5.3.6 | Background job processing |
| Message Broker | Redis | 5.0.1 | Celery broker and result backend |
| AI Model | Google Gemini 2.0 Flash | - | Conversational AI |
| AI SDK | google-generativeai | - | Gemini API client |
| Auth | PyJWT | 3.3.0 | JWT token handling |
| Password | Passlib + bcrypt | 1.7.4 | Password hashing |
| Validation | Pydantic | 2.5.3 | Request/response validation |

---

## Project Structure

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                 # Application entry point
│   ├── config.py               # Configuration management
│   ├── database.py             # Database session management
│   ├── celery_app.py           # Celery configuration
│   │
│   ├── auth/                   # Authentication module
│   │   ├── jwt.py              # Token creation/validation
│   │   ├── password.py         # Password hashing
│   │   └── dependencies.py     # FastAPI dependencies
│   │
│   ├── models/                 # SQLAlchemy models
│   │   ├── user.py             # User authentication
│   │   ├── message.py          # Chat messages
│   │   ├── memory.py           # Long-term memories
│   │   ├── followup.py         # Scheduled follow-ups
│   │   ├── protocol.py         # Health protocols
│   │   └── user_profile.py     # User health profiles
│   │
│   ├── routers/                # API endpoints
│   │   ├── auth.py             # Authentication routes
│   │   ├── chat.py             # REST chat endpoints
│   │   ├── websocket.py        # WebSocket endpoint
│   │   └── health.py           # Health check
│   │
│   ├── schemas/                # Pydantic schemas
│   │   ├── auth.py             # Auth request/response
│   │   ├── message.py          # Message schemas
│   │   └── user.py             # User schemas
│   │
│   ├── services/               # Business logic
│   │   ├── llm_service.py      # Gemini AI integration
│   │   ├── memory_service.py   # Memory management
│   │   ├── protocol_service.py # Protocol matching
│   │   ├── connection_manager.py # WebSocket connections
│   │   ├── onboarding_service.py # New user onboarding
│   │   ├── followup_service.py # Follow-up scheduling
│   │   └── profile_service.py  # User profile management
│   │
│   ├── tasks/                  # Celery tasks
│   │   └── followup_tasks.py   # Background follow-up processing
│   │
│   └── scripts/                # Utility scripts
│       └── seed_protocols.py   # Protocol seeding
│
├── alembic/                    # Database migrations
│   ├── env.py
│   └── versions/               # Migration files
│
├── .env.example                # Environment template
├── alembic.ini                 # Alembic configuration
├── Procfile                    # Deployment configuration
└── requirements.txt            # Python dependencies
```

---

## Features

### 1. Real-Time Messaging

**Implementation**: WebSocket with message status tracking

The chat system implements WhatsApp-like messaging with visual delivery indicators:

- **SENDING**: Message queued for sending (clock icon)
- **SENT**: Server received message (single checkmark)
- **DELIVERED**: Server processed message (double checkmark)
- **FAILED**: Message delivery failed (error icon)

**Technical Details**:
- WebSocket endpoint at `/ws/chat?token=JWT`
- Fresh database sessions per operation to prevent connection timeouts
- Typing indicators with realistic delays based on response length
- Automatic reconnection handling on client side

```python
# Message flow timing
1. User sends message → MESSAGE_SENT (0ms)
2. Processing delay → MESSAGE_DELIVERED (300-600ms)
3. Reading simulation → TYPING_START (800-1500ms)
4. Response generation → AI processes with context
5. Typing simulation → Delay based on response length (1.5-5s)
6. Response delivery → ASSISTANT_MESSAGE
```

### 2. AI-Powered Health Coaching

**Implementation**: Google Gemini 2.0 Flash with structured output

The LLM service provides:

- **Persona**: Arohi, a female health coach from Bangalore with 5 years experience
- **Tone**: Warm, professional, conversational (like texting a knowledgeable friend)
- **Format**: Short messages (2-3 sentences), one question at a time
- **Safety**: RED FLAG detection for critical symptoms requiring medical attention

**Structured Output Schema**:
```python
CHAT_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "message": {"type": "string"},
        "scheduling": {
            "type": "object",
            "nullable": True,
            "properties": {
                "requested": {"type": "boolean"},
                "minutes_from_now": {"type": "integer"},
                "reason": {"type": "string"}
            }
        }
    }
}
```

**Context Injection**:
- User memories (extracted facts)
- User profile data (health information)
- Relevant protocols (medical guidelines)
- Chat history (last 20 messages)

### 3. Long-Term Memory System

**Implementation**: Pattern-based extraction with database persistence

The memory service extracts and stores facts from conversations:

**Categories**:
- `health`: Medical conditions, symptoms, medications
- `preference`: Diet preferences, exercise preferences
- `personal`: Name, age, location
- `lifestyle`: Sleep patterns, work schedule, stress factors

**Extraction Patterns**:
```python
# Age detection
"I am 25 years old" → Memory: "User is 25 years old" (personal)

# Health conditions
"I have diabetes" → Memory: "User has diabetes" (health)

# Diet preferences
"I'm vegetarian" → Memory: "User follows vegetarian diet" (preference)
```

### 4. User Profile System

**Implementation**: LLM-based extraction with progressive onboarding

The profile system collects 40+ data points across 9 categories:

**Onboarding Stages**:
1. NOT_STARTED → BASIC_INFO (age, gender, occupation)
2. BASIC_INFO → HEALTH_GOALS (primary goal, motivation)
3. HEALTH_GOALS → LIFESTYLE (sleep, stress, work)
4. LIFESTYLE → DIET_HABITS (diet type, meals, water)
5. DIET_HABITS → PHYSICAL_ACTIVITY (exercise, activity level)
6. PHYSICAL_ACTIVITY → HEALTH_HISTORY (conditions, medications)
7. HEALTH_HISTORY → COMPLETED

**LLM-Based Extraction**:
```python
# Supports multiple languages
"I'm 23" → age: 23
"Main veg hun" (Hindi) → diet_type: "vegetarian"
"Desk job hai meri" (Hinglish) → work_type: "desk_job"
```

### 5. Intelligent Follow-Up System

**Implementation**: Celery scheduled tasks with engagement tracking

**Follow-Up Types**:

| Type | Trigger | Purpose |
|------|---------|---------|
| USER_REQUESTED | User asks for reminder | Honor explicit requests |
| INACTIVITY | 24+ hours no message | Re-engage inactive users |
| PLAN_CHECKIN | 48+ hours with active plan | Track goal progress |
| DAILY_CHECKIN | Scheduled daily | Routine health check-in |
| MOTIVATION | Scheduled | Encouragement messages |

**Scheduling Detection**:
```python
# Detected phrases (any language)
"Remind me in 2 hours" → 120 minutes
"Kal baat karte hain" → 1440 minutes (tomorrow)
"2 ghante baad message karna" → 120 minutes
```

**Engagement Tracking**:
- Last message timestamp
- Total messages count
- Preferred contact time (hour most active)
- Average response time
- Follow-up preferences

### 6. Protocol/Guidelines System

**Implementation**: Keyword-based matching with priority scoring

Protocols are medical/health guidelines injected into LLM context when relevant:

```python
# Protocol matching
User: "How should I manage my diabetes?"
→ Matches: diabetes_management protocol (keywords: diabetes, blood sugar, insulin)
→ Protocol content added to LLM context
```

**Scoring Algorithm**:
```python
score = keyword_matches * 10 + protocol.priority
# Top 3 protocols by score included in context
```

### 7. Authentication System

**Implementation**: JWT with bcrypt password hashing

**Security Features**:
- Bcrypt password hashing with automatic salting
- JWT tokens with HS256 algorithm
- 24-hour token expiration (configurable)
- Separate validation for REST and WebSocket

**Token Structure**:
```json
{
  "sub": "user-uuid",
  "exp": 1234567890,
  "type": "access"
}
```

---

## Database Schema

### Entity Relationship Diagram

```
+------------------+       +------------------+       +------------------+
|      users       |       |     messages     |       |     memories     |
+------------------+       +------------------+       +------------------+
| id (PK)          |<──┬──>| id (PK)          |       | id (PK)          |
| email            |   │   | user_id (FK)     |       | user_id (FK)     |
| password_hash    |   │   | role             |       | content          |
| name             |   │   | content          |       | category         |
| created_at       |   │   | status           |       | created_at       |
| updated_at       |   │   | created_at       |       +------------------+
+------------------+   │   +------------------+              │
        │              │                                     │
        │              │   +------------------+              │
        │              │   | user_profiles    |              │
        │              │   +------------------+              │
        │              └──>| id (PK)          |              │
        │                  | user_id (FK)     |<─────────────┘
        │                  | onboarding_stage |
        │                  | age, gender, ... |
        │                  | (40+ fields)     |
        │                  +------------------+
        │
        │              +------------------+       +------------------+
        │              |scheduled_followups|      | user_engagements |
        │              +------------------+       +------------------+
        └─────────────>| id (PK)          |      | id (PK)          |
                       | user_id (FK)     |      | user_id (FK)     |
                       | scheduled_at     |      | last_message_at  |
                       | followup_type    |      | total_messages   |
                       | status           |      | preferred_time   |
                       | context          |      | followup_enabled |
                       +------------------+      +------------------+
```

### Key Tables

**users**: Core authentication and identity
```sql
- id: UUID PRIMARY KEY
- email: VARCHAR UNIQUE NOT NULL
- password_hash: VARCHAR NOT NULL
- name: VARCHAR
- created_at, updated_at: TIMESTAMP
```

**messages**: Conversation history with status tracking
```sql
- id: UUID PRIMARY KEY
- user_id: UUID FOREIGN KEY
- role: VARCHAR ('user' | 'assistant')
- content: TEXT
- status: VARCHAR ('sending' | 'sent' | 'delivered' | 'read' | 'failed')
- created_at: TIMESTAMP (indexed)
```

**user_profiles**: Comprehensive health data (40+ fields)
```sql
- Onboarding: stage, started_at, completed_at, questions_asked
- Basic: age, gender, location, occupation, work_type
- Goals: primary_goal, secondary_goals, timeline, motivation
- Lifestyle: work_hours, sleep_hours, sleep_quality, stress_level
- Diet: diet_type, meals_per_day, water_intake, allergies
- Activity: activity_level, current_exercise, gym_access
- Health: conditions, medications, supplements, family_history
- Metrics: height_cm, current_weight_kg, target_weight_kg
```

---

## API Reference

### Authentication Endpoints

#### POST /api/auth/register
Register a new user account.

**Request**:
```json
{
  "email": "user@example.com",
  "password": "securepass123",
  "name": "John Doe"
}
```

**Response** (201):
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer"
}
```

#### POST /api/auth/login
Authenticate existing user.

**Request**:
```json
{
  "email": "user@example.com",
  "password": "securepass123"
}
```

**Response** (200):
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer"
}
```

#### GET /api/auth/me
Get current user information.

**Headers**: `Authorization: Bearer {token}`

**Response** (200):
```json
{
  "id": "uuid",
  "email": "user@example.com",
  "name": "John Doe",
  "created_at": "2024-01-01T00:00:00Z"
}
```

### Chat Endpoints

#### GET /api/chat/messages
Fetch paginated message history.

**Headers**: `Authorization: Bearer {token}`

**Query Parameters**:
- `before` (optional): Message ID cursor for pagination
- `limit` (optional): Messages per page (1-50, default 20)

**Response** (200):
```json
{
  "messages": [
    {
      "id": "uuid",
      "role": "user",
      "content": "Hello",
      "status": "delivered",
      "created_at": "2024-01-01T00:00:00Z"
    }
  ],
  "has_more": true,
  "next_cursor": "uuid"
}
```

#### POST /api/chat/messages
Send a message and receive AI response.

**Headers**: `Authorization: Bearer {token}`

**Request**:
```json
{
  "content": "How can I improve my sleep?"
}
```

**Response** (201):
```json
{
  "user_message": {
    "id": "uuid",
    "role": "user",
    "content": "How can I improve my sleep?",
    "status": "delivered",
    "created_at": "2024-01-01T00:00:00Z"
  },
  "assistant_message": {
    "id": "uuid",
    "role": "assistant",
    "content": "Sleep is so important...",
    "status": "delivered",
    "created_at": "2024-01-01T00:00:01Z"
  }
}
```

### Health Check

#### GET /api/health
Check service health.

**Response** (200):
```json
{
  "status": "healthy",
  "service": "arohi-health-coach"
}
```

---

## WebSocket Protocol

### Connection

```
ws://localhost:8000/api/ws/chat?token=JWT_TOKEN
```

### Message Types

#### Client to Server

**USER_MESSAGE**: Send a chat message
```json
{
  "type": "user_message",
  "data": {
    "content": "Hello Arohi"
  }
}
```

#### Server to Client

**MESSAGE_SENT**: Message received by server
```json
{
  "type": "message_sent",
  "data": {
    "message_id": "uuid",
    "status": "sent"
  }
}
```

**MESSAGE_DELIVERED**: Message processed
```json
{
  "type": "message_delivered",
  "data": {
    "message_id": "uuid",
    "status": "delivered"
  }
}
```

**TYPING_START**: Assistant is typing
```json
{
  "type": "typing_start",
  "data": {}
}
```

**ASSISTANT_MESSAGE**: AI response
```json
{
  "type": "assistant_message",
  "data": {
    "message": {
      "id": "uuid",
      "role": "assistant",
      "content": "Hi! How can I help you today?",
      "status": "delivered",
      "created_at": "2024-01-01T00:00:00Z"
    }
  }
}
```

**ONBOARDING**: Welcome message for new users
```json
{
  "type": "onboarding",
  "data": {
    "message": {
      "id": "uuid",
      "role": "assistant",
      "content": "Hi John! I'm Arohi...",
      "status": "delivered",
      "created_at": "2024-01-01T00:00:00Z"
    }
  }
}
```

**ERROR**: Error occurred
```json
{
  "type": "error",
  "data": {
    "message": "Something went wrong..."
  }
}
```

---

## Background Tasks

### Celery Configuration

**Broker**: Redis
**Result Backend**: Redis
**Task Acknowledgment**: After completion (reliable delivery)

### Scheduled Tasks (Celery Beat)

| Task | Schedule | Description |
|------|----------|-------------|
| `process_scheduled_reminders` | Every minute | Process pending follow-ups |
| `check_and_send_followups` | Every hour | Identify users needing follow-ups |

### Task Definitions

#### send_followup_message
Sends a scheduled follow-up message to a user.

**Process**:
1. Fetch follow-up record and user
2. Determine message context based on follow-up type
3. Gather user memories and profile
4. Generate message via Gemini
5. Save message to database
6. Update follow-up status

#### schedule_user_reminder
Schedules a user-requested reminder.

**Parameters**:
- `user_id`: Target user UUID
- `minutes_from_now`: Delay in minutes
- `context`: Reason for follow-up

### Running Celery

```bash
# Start worker
celery -A app.celery_app worker --loglevel=info --pool=solo

# Start beat scheduler
celery -A app.celery_app beat --loglevel=info
```

---

## Configuration

### Environment Variables

```env
# Database (required)
DATABASE_URL=postgresql://user:password@host:5432/dbname

# Redis (required for Celery)
REDIS_URL=redis://localhost:6379/0

# Google AI (required)
GOOGLE_API_KEY=your-gemini-api-key

# JWT Authentication (required)
JWT_SECRET_KEY=your-secret-key-minimum-32-characters
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440

# Application
DEBUG=false
CORS_ORIGINS=http://localhost:3000

# Follow-up Settings (optional)
FOLLOWUP_CHECK_INTERVAL_HOURS=4
FOLLOWUP_INACTIVITY_HOURS=24
FOLLOWUP_PLAN_CHECKIN_HOURS=48
```

### Settings Class

Settings are loaded via Pydantic's BaseSettings with environment variable support:

```python
from app.config import get_settings

settings = get_settings()
print(settings.database_url)
```

---

## Installation

### Prerequisites

- Python 3.11+
- PostgreSQL 15+
- Redis 7+
- Google Cloud account with Gemini API access

### Setup

1. **Clone and navigate**:
```bash
cd backend
```

2. **Create virtual environment**:
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows
```

3. **Install dependencies**:
```bash
pip install -r requirements.txt
```

4. **Configure environment**:
```bash
cp .env.example .env
# Edit .env with your values
```

5. **Run migrations**:
```bash
alembic upgrade head
```

6. **Seed protocols** (optional):
```bash
python -m app.scripts.seed_protocols
```

7. **Start the server**:
```bash
uvicorn app.main:app --reload --port 8000
```

8. **Start Celery** (separate terminal):
```bash
celery -A app.celery_app worker --loglevel=info --pool=solo
celery -A app.celery_app beat --loglevel=info
```

---

## Deployment

### Production Checklist

- [ ] Set `DEBUG=false`
- [ ] Use strong `JWT_SECRET_KEY` (32+ characters)
- [ ] Configure production database URL
- [ ] Set up Redis for Celery
- [ ] Configure CORS origins for production domain
- [ ] Enable HTTPS
- [ ] Set up monitoring and logging

### Procfile (Render/Heroku)

```
web: uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

### Docker (Example)

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## Support

For issues and feature requests, contact the development team.
