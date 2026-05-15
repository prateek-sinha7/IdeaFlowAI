"use client";

import { AppBuilderPreview, ParsedFile } from "@/components/preview/AppBuilderPreview";

const MOCK_FILES: ParsedFile[] = [
  {
    path: "README.md",
    name: "README.md",
    ext: "md",
    language: "markdown",
    content: `# Hotel Management System

A full-stack hotel management platform built with FastAPI and Next.js 14.

## Features

- **Room Management** — track room types, availability, and pricing
- **Guest Profiles** — store guest contact info and stay history
- **Reservations** — create, update, cancel bookings with conflict detection
- **Dashboard** — real-time occupancy stats and revenue metrics
- **REST API** — fully documented OpenAPI/Swagger interface
- **Auth** — JWT-based authentication with role-based access control

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 14, TypeScript, Tailwind CSS |
| Backend | FastAPI, Python 3.11, SQLAlchemy 2 |
| Database | PostgreSQL 15 |
| Cache | Redis 7 |
| Auth | JWT (python-jose) |
| Testing | pytest, React Testing Library |
| CI/CD | GitHub Actions |
| Deploy | Render (backend + frontend) |

## Quick Start

\`\`\`bash
# 1. Clone the repo
git clone https://github.com/your-org/hotel-management.git
cd hotel-management

# 2. Copy env files
cp .env.example .env

# 3. Start all services
docker compose up -d

# 4. Run migrations
make migrate

# 5. Open the app
open http://localhost:3000
\`\`\`

## Project Structure

\`\`\`
hotel-management/
├── backend/
│   ├── app/
│   │   ├── api/          # FastAPI routers
│   │   ├── core/         # Config, security
│   │   ├── models/       # SQLAlchemy models
│   │   └── services/     # Business logic
│   ├── alembic/          # DB migrations
│   └── tests/
├── frontend/
│   └── src/
│       ├── app/          # Next.js App Router pages
│       └── components/   # Reusable UI components
├── docs/
├── docker-compose.yml
└── Makefile
\`\`\`

## License

MIT
`,
  },
  {
    path: "SETUP.md",
    name: "SETUP.md",
    ext: "md",
    language: "markdown",
    content: `# Local Development Setup

## Prerequisites

- Python 3.11+
- Node.js 18+
- Docker & Docker Compose
- PostgreSQL 15 (or use Docker)
- Redis 7 (or use Docker)

## Backend Setup

\`\`\`bash
cd backend

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate

# Install dependencies
pip install -r requirements.txt

# Copy env file
cp ../.env.example .env
# Edit .env with your local values

# Run migrations
alembic upgrade head

# Start dev server
uvicorn app.main:app --reload --port 8000
\`\`\`

API docs available at http://localhost:8000/docs

## Frontend Setup

\`\`\`bash
cd frontend

# Install dependencies
npm install

# Copy env file
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local

# Start dev server
npm run dev
\`\`\`

App available at http://localhost:3000

## Database Setup

\`\`\`bash
# Using Docker
docker run -d \\
  --name hotel-db \\
  -e POSTGRES_DB=hotel \\
  -e POSTGRES_USER=hotel \\
  -e POSTGRES_PASSWORD=secret \\
  -p 5432:5432 \\
  postgres:15-alpine

# Run migrations
cd backend && alembic upgrade head
\`\`\`

## Running Tests

\`\`\`bash
# Backend tests
cd backend && pytest -v

# Frontend tests
cd frontend && npm test
\`\`\`
`,
  },
  {
    path: "CONTRIBUTING.md",
    name: "CONTRIBUTING.md",
    ext: "md",
    language: "markdown",
    content: `# Contributing Guide

Thank you for contributing to Hotel Management System!

## Branching Strategy

We use **GitHub Flow**:

- \`main\` — production-ready code, protected
- \`feature/<ticket>-short-description\` — new features
- \`fix/<ticket>-short-description\` — bug fixes
- \`chore/<description>\` — maintenance tasks

\`\`\`bash
# Start a new feature
git checkout main && git pull
git checkout -b feature/HMS-42-add-room-pricing
\`\`\`

## Commit Format

We follow [Conventional Commits](https://www.conventionalcommits.org/):

\`\`\`
<type>(<scope>): <short summary>

[optional body]

[optional footer]
\`\`\`

Types: \`feat\`, \`fix\`, \`docs\`, \`style\`, \`refactor\`, \`test\`, \`chore\`

Examples:
\`\`\`
feat(reservations): add conflict detection on overlapping dates
fix(auth): handle expired JWT tokens gracefully
docs(api): update reservation endpoint examples
\`\`\`

## Pull Request Process

1. Ensure all tests pass: \`make test\`
2. Ensure linting passes: \`make lint\`
3. Update docs if needed
4. Fill in the PR template
5. Request review from at least one team member
6. Squash and merge after approval

## Code Style

- **Python**: Black formatter, isort, flake8 (see \`pyproject.toml\`)
- **TypeScript**: ESLint + Prettier (see \`.eslintrc.json\`)
- Run \`make lint\` before pushing

## Reporting Issues

Use GitHub Issues with the appropriate label:
- \`bug\` — something is broken
- \`enhancement\` — new feature request
- \`documentation\` — docs improvement
`,
  },
  {
    path: "docs/DEPLOYMENT.md",
    name: "DEPLOYMENT.md",
    ext: "md",
    language: "markdown",
    content: `# Deployment Guide — Render

## Overview

The application is deployed on [Render](https://render.com) using:
- **Web Service** — FastAPI backend (Docker)
- **Static Site** — Next.js frontend
- **PostgreSQL** — Managed Render database
- **Redis** — Managed Render Redis instance

## Environment Variables

Set these in the Render dashboard for the backend service:

| Variable | Description |
|----------|-------------|
| \`DATABASE_URL\` | PostgreSQL connection string (auto-set by Render) |
| \`REDIS_URL\` | Redis connection string (auto-set by Render) |
| \`SECRET_KEY\` | JWT signing secret (generate with \`openssl rand -hex 32\`) |
| \`ALLOWED_ORIGINS\` | Comma-separated frontend URLs |
| \`ENVIRONMENT\` | \`production\` |

## Deploy Steps

### Backend

1. Connect your GitHub repo to Render
2. Create a new **Web Service**
3. Set **Runtime** to Docker
4. Set **Dockerfile Path** to \`./Dockerfile\`
5. Add environment variables
6. Deploy

### Frontend

1. Create a new **Static Site**
2. Set **Build Command**: \`cd frontend && npm ci && npm run build\`
3. Set **Publish Directory**: \`frontend/.next\`
4. Add \`NEXT_PUBLIC_API_URL\` pointing to your backend URL
5. Deploy

## Database Migrations

Migrations run automatically on deploy via the Dockerfile \`CMD\`:

\`\`\`dockerfile
CMD alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT
\`\`\`

## Rollback

\`\`\`bash
# Roll back one migration
alembic downgrade -1

# Roll back to specific revision
alembic downgrade 0001
\`\`\`

## Health Checks

- Backend: \`GET /health\` → \`{"status": "ok"}\`
- Render auto-restarts if health check fails 3 times
`,
  },
  {
    path: "docs/ARCHITECTURE.md",
    name: "ARCHITECTURE.md",
    ext: "md",
    language: "markdown",
    content: `# Architecture

## System Diagram

\`\`\`
┌─────────────────────────────────────────────────────────┐
│                        Internet                          │
└──────────────────────┬──────────────────────────────────┘
                       │
          ┌────────────▼────────────┐
          │   Next.js Frontend      │
          │   (Render Static Site)  │
          └────────────┬────────────┘
                       │ HTTPS / REST
          ┌────────────▼────────────┐
          │   FastAPI Backend       │
          │   (Render Web Service)  │
          └──────┬──────────┬───────┘
                 │          │
    ┌────────────▼──┐  ┌────▼──────────┐
    │  PostgreSQL   │  │    Redis       │
    │  (Render DB)  │  │  (Render KV)  │
    └───────────────┘  └───────────────┘
\`\`\`

## Key Design Decisions

### ADR-001: FastAPI over Django REST Framework

**Status**: Accepted

**Context**: Need a Python API framework for the hotel backend.

**Decision**: Use FastAPI with async SQLAlchemy.

**Rationale**: FastAPI provides automatic OpenAPI docs, native async support, and Pydantic validation out of the box. Performance benchmarks show 3-5x throughput vs DRF for I/O-bound workloads.

### ADR-002: Next.js App Router

**Status**: Accepted

**Context**: Frontend framework selection.

**Decision**: Next.js 14 with App Router.

**Rationale**: Server Components reduce client bundle size. Built-in routing, image optimization, and Vercel/Render deployment support.

### ADR-003: PostgreSQL for primary storage

**Status**: Accepted

**Context**: Database selection.

**Decision**: PostgreSQL 15.

**Rationale**: ACID compliance required for reservation transactions. Rich JSON support for flexible guest preferences. Excellent SQLAlchemy integration.

## Data Flow — Create Reservation

\`\`\`
Client → POST /api/reservations
  → Auth middleware (JWT validation)
  → ReservationRouter.create()
  → ReservationService.create_reservation()
    → Check room availability (DB query with row lock)
    → Validate guest exists
    → Insert reservation row
    → Invalidate Redis cache
  → Return 201 with reservation JSON
\`\`\`
`,
  },
  {
    path: "docs/RUNBOOK.md",
    name: "RUNBOOK.md",
    ext: "md",
    language: "markdown",
    content: `# Operations Runbook

## On-Call Contacts

| Role | Name | Contact |
|------|------|---------|
| Backend Lead | Jane Smith | @jane on Slack |
| Frontend Lead | Bob Jones | @bob on Slack |
| DevOps | Alice Chen | @alice on Slack |

## Common Incidents

### High Error Rate on /api/reservations

1. Check Render logs: Dashboard → Backend Service → Logs
2. Look for \`ConflictError\` or \`DatabaseError\` patterns
3. Check DB connections: \`SELECT count(*) FROM pg_stat_activity;\`
4. If connection pool exhausted, restart the service
5. Escalate to Backend Lead if unresolved in 15 min

### Database Connection Failures

\`\`\`bash
# Test connectivity
psql $DATABASE_URL -c "SELECT 1;"

# Check active connections
psql $DATABASE_URL -c "SELECT count(*) FROM pg_stat_activity WHERE state = 'active';"

# Kill idle connections older than 10 minutes
psql $DATABASE_URL -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE state = 'idle' AND query_start < NOW() - INTERVAL '10 minutes';"
\`\`\`

### Redis Cache Issues

\`\`\`bash
# Check Redis connectivity
redis-cli -u $REDIS_URL ping

# Flush cache (use with caution)
redis-cli -u $REDIS_URL FLUSHDB
\`\`\`

### Rollback Deployment

1. Go to Render Dashboard → Backend Service → Deploys
2. Find the last stable deploy
3. Click "Rollback to this deploy"
4. Monitor health check endpoint: \`GET /health\`

## Monitoring

- **Uptime**: Render built-in health checks
- **Errors**: Check Render log stream
- **DB**: Render PostgreSQL metrics dashboard
- **Alerts**: Configured in Render notification settings
`,
  },
  {
    path: "backend/app/main.py",
    name: "main.py",
    ext: "py",
    language: "python",
    content: `from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.models.database import engine, Base
from app.api import reservations, rooms, guests, auth


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create tables if they don't exist (migrations handle prod)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    # Shutdown: dispose connection pool
    await engine.dispose()


app = FastAPI(
    title="Hotel Management API",
    version="1.0.0",
    description="REST API for the Hotel Management System",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(rooms.router, prefix="/api/rooms", tags=["rooms"])
app.include_router(reservations.router, prefix="/api/reservations", tags=["reservations"])
app.include_router(guests.router, prefix="/api/guests", tags=["guests"])


@app.get("/health", tags=["health"])
async def health_check():
    return {"status": "ok", "version": "1.0.0"}
`,
  },
  {
    path: "backend/app/core/config.py",
    name: "config.py",
    ext: "py",
    language: "python",
    content: `from functools import lru_cache
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # App
    app_name: str = "Hotel Management API"
    environment: str = "development"
    debug: bool = False

    # Database
    database_url: str = "postgresql+asyncpg://hotel:secret@localhost:5432/hotel"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Security
    secret_key: str = "change-me-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # CORS
    allowed_origins: List[str] = ["http://localhost:3000"]

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
`,
  },
  {
    path: "backend/app/models/room.py",
    name: "room.py",
    ext: "py",
    language: "python",
    content: `import enum
from datetime import datetime
from sqlalchemy import Column, Integer, String, Numeric, Boolean, DateTime, Enum as SAEnum
from sqlalchemy.orm import relationship
from app.models.database import Base


class RoomType(str, enum.Enum):
    SINGLE = "single"
    DOUBLE = "double"
    SUITE = "suite"
    PENTHOUSE = "penthouse"


class RoomStatus(str, enum.Enum):
    AVAILABLE = "available"
    OCCUPIED = "occupied"
    MAINTENANCE = "maintenance"
    CLEANING = "cleaning"


class Room(Base):
    __tablename__ = "rooms"

    id = Column(Integer, primary_key=True, index=True)
    number = Column(String(10), unique=True, nullable=False, index=True)
    floor = Column(Integer, nullable=False)
    room_type = Column(SAEnum(RoomType), nullable=False, default=RoomType.SINGLE)
    status = Column(SAEnum(RoomStatus), nullable=False, default=RoomStatus.AVAILABLE)
    price_per_night = Column(Numeric(10, 2), nullable=False)
    max_occupancy = Column(Integer, nullable=False, default=2)
    has_ocean_view = Column(Boolean, default=False)
    has_balcony = Column(Boolean, default=False)
    description = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    reservations = relationship("Reservation", back_populates="room")

    def __repr__(self) -> str:
        return f"<Room {self.number} ({self.room_type.value})>"
`,
  },
  {
    path: "backend/app/models/guest.py",
    name: "guest.py",
    ext: "py",
    language: "python",
    content: `from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Date
from sqlalchemy.orm import relationship
from app.models.database import Base


class Guest(Base):
    __tablename__ = "guests"

    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    phone = Column(String(20), nullable=True)
    date_of_birth = Column(Date, nullable=True)
    nationality = Column(String(100), nullable=True)
    passport_number = Column(String(50), nullable=True)
    address_line1 = Column(String(255), nullable=True)
    address_city = Column(String(100), nullable=True)
    address_country = Column(String(100), nullable=True)
    loyalty_points = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    reservations = relationship("Reservation", back_populates="guest")

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    def __repr__(self) -> str:
        return f"<Guest {self.full_name} ({self.email})>"
`,
  },
  {
    path: "backend/app/models/reservation.py",
    name: "reservation.py",
    ext: "py",
    language: "python",
    content: `import enum
from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import Column, Integer, ForeignKey, Date, DateTime, Numeric, String, Enum as SAEnum, Text
from sqlalchemy.orm import relationship
from app.models.database import Base


class ReservationStatus(str, enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CHECKED_IN = "checked_in"
    CHECKED_OUT = "checked_out"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"


class Reservation(Base):
    __tablename__ = "reservations"

    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(Integer, ForeignKey("rooms.id"), nullable=False, index=True)
    guest_id = Column(Integer, ForeignKey("guests.id"), nullable=False, index=True)
    check_in_date = Column(Date, nullable=False)
    check_out_date = Column(Date, nullable=False)
    status = Column(SAEnum(ReservationStatus), nullable=False, default=ReservationStatus.PENDING)
    num_guests = Column(Integer, nullable=False, default=1)
    total_price = Column(Numeric(10, 2), nullable=False)
    special_requests = Column(Text, nullable=True)
    confirmation_code = Column(String(20), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    room = relationship("Room", back_populates="reservations")
    guest = relationship("Guest", back_populates="reservations")

    @property
    def nights(self) -> int:
        return (self.check_out_date - self.check_in_date).days

    def __repr__(self) -> str:
        return f"<Reservation {self.confirmation_code} ({self.status.value})>"
`,
  },
  {
    path: "backend/app/api/reservations.py",
    name: "reservations.py",
    ext: "py",
    language: "python",
    content: `from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db, get_current_user
from app.models.schemas import (
    ReservationCreate, ReservationUpdate, ReservationResponse, ReservationListResponse
)
from app.services.reservation_service import ReservationService

router = APIRouter()


@router.get("/", response_model=ReservationListResponse)
async def list_reservations(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    guest_id: Optional[int] = None,
    room_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    service = ReservationService(db)
    reservations, total = await service.list_reservations(
        page=page, page_size=page_size, status=status,
        guest_id=guest_id, room_id=room_id
    )
    return ReservationListResponse(
        items=reservations, total=total, page=page, page_size=page_size
    )


@router.post("/", response_model=ReservationResponse, status_code=status.HTTP_201_CREATED)
async def create_reservation(
    payload: ReservationCreate,
    db: AsyncSession = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    service = ReservationService(db)
    try:
        reservation = await service.create_reservation(payload)
        return reservation
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.get("/{reservation_id}", response_model=ReservationResponse)
async def get_reservation(
    reservation_id: int,
    db: AsyncSession = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    service = ReservationService(db)
    reservation = await service.get_reservation(reservation_id)
    if not reservation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reservation not found")
    return reservation


@router.patch("/{reservation_id}", response_model=ReservationResponse)
async def update_reservation(
    reservation_id: int,
    payload: ReservationUpdate,
    db: AsyncSession = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    service = ReservationService(db)
    try:
        reservation = await service.update_reservation(reservation_id, payload)
        if not reservation:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reservation not found")
        return reservation
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.delete("/{reservation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_reservation(
    reservation_id: int,
    db: AsyncSession = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    service = ReservationService(db)
    cancelled = await service.cancel_reservation(reservation_id)
    if not cancelled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reservation not found")
`,
  },
  {
    path: "backend/app/api/rooms.py",
    name: "rooms.py",
    ext: "py",
    language: "python",
    content: `from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db, get_current_user
from app.models.schemas import RoomCreate, RoomUpdate, RoomResponse
from app.models.room import RoomType, RoomStatus
from app.services.room_service import RoomService

router = APIRouter()


@router.get("/", response_model=List[RoomResponse])
async def list_rooms(
    room_type: Optional[RoomType] = None,
    status: Optional[RoomStatus] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    db: AsyncSession = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    service = RoomService(db)
    return await service.list_rooms(
        room_type=room_type, status=status,
        min_price=min_price, max_price=max_price
    )


@router.post("/", response_model=RoomResponse, status_code=status.HTTP_201_CREATED)
async def create_room(
    payload: RoomCreate,
    db: AsyncSession = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    service = RoomService(db)
    try:
        return await service.create_room(payload)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/{room_id}", response_model=RoomResponse)
async def get_room(
    room_id: int,
    db: AsyncSession = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    service = RoomService(db)
    room = await service.get_room(room_id)
    if not room:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room not found")
    return room


@router.patch("/{room_id}", response_model=RoomResponse)
async def update_room(
    room_id: int,
    payload: RoomUpdate,
    db: AsyncSession = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    service = RoomService(db)
    room = await service.update_room(room_id, payload)
    if not room:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room not found")
    return room


@router.delete("/{room_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_room(
    room_id: int,
    db: AsyncSession = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    service = RoomService(db)
    deleted = await service.delete_room(room_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room not found")
`,
  },
  {
    path: "backend/app/services/reservation_service.py",
    name: "reservation_service.py",
    ext: "py",
    language: "python",
    content: `import random
import string
from datetime import date
from typing import List, Optional, Tuple
from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.reservation import Reservation, ReservationStatus
from app.models.room import Room, RoomStatus
from app.models.schemas import ReservationCreate, ReservationUpdate


def _generate_confirmation_code() -> str:
    return "HMS-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=8))


class ReservationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _check_room_availability(
        self,
        room_id: int,
        check_in: date,
        check_out: date,
        exclude_reservation_id: Optional[int] = None,
    ) -> bool:
        """Return True if the room is available for the given date range."""
        query = select(Reservation).where(
            and_(
                Reservation.room_id == room_id,
                Reservation.status.notin_([ReservationStatus.CANCELLED, ReservationStatus.NO_SHOW]),
                or_(
                    and_(Reservation.check_in_date <= check_in, Reservation.check_out_date > check_in),
                    and_(Reservation.check_in_date < check_out, Reservation.check_out_date >= check_out),
                    and_(Reservation.check_in_date >= check_in, Reservation.check_out_date <= check_out),
                ),
            )
        )
        if exclude_reservation_id:
            query = query.where(Reservation.id != exclude_reservation_id)

        result = await self.db.execute(query)
        return result.first() is None

    async def create_reservation(self, payload: ReservationCreate) -> Reservation:
        # Validate dates
        if payload.check_out_date <= payload.check_in_date:
            raise ValueError("Check-out date must be after check-in date")

        # Check room exists and is not in maintenance
        room_result = await self.db.execute(select(Room).where(Room.id == payload.room_id))
        room = room_result.scalar_one_or_none()
        if not room:
            raise ValueError(f"Room {payload.room_id} not found")
        if room.status == RoomStatus.MAINTENANCE:
            raise ValueError(f"Room {room.number} is under maintenance")

        # Check availability
        available = await self._check_room_availability(
            payload.room_id, payload.check_in_date, payload.check_out_date
        )
        if not available:
            raise ValueError(
                f"Room {room.number} is not available from {payload.check_in_date} to {payload.check_out_date}"
            )

        # Calculate total price
        nights = (payload.check_out_date - payload.check_in_date).days
        total_price = float(room.price_per_night) * nights

        reservation = Reservation(
            room_id=payload.room_id,
            guest_id=payload.guest_id,
            check_in_date=payload.check_in_date,
            check_out_date=payload.check_out_date,
            num_guests=payload.num_guests,
            special_requests=payload.special_requests,
            total_price=total_price,
            confirmation_code=_generate_confirmation_code(),
            status=ReservationStatus.CONFIRMED,
        )
        self.db.add(reservation)
        await self.db.commit()
        await self.db.refresh(reservation)
        return reservation

    async def get_reservation(self, reservation_id: int) -> Optional[Reservation]:
        result = await self.db.execute(
            select(Reservation)
            .options(selectinload(Reservation.room), selectinload(Reservation.guest))
            .where(Reservation.id == reservation_id)
        )
        return result.scalar_one_or_none()

    async def list_reservations(
        self,
        page: int = 1,
        page_size: int = 20,
        status: Optional[str] = None,
        guest_id: Optional[int] = None,
        room_id: Optional[int] = None,
    ) -> Tuple[List[Reservation], int]:
        query = select(Reservation).options(
            selectinload(Reservation.room), selectinload(Reservation.guest)
        )
        if status:
            query = query.where(Reservation.status == status)
        if guest_id:
            query = query.where(Reservation.guest_id == guest_id)
        if room_id:
            query = query.where(Reservation.room_id == room_id)

        count_result = await self.db.execute(select(func.count()).select_from(query.subquery()))
        total = count_result.scalar_one()

        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await self.db.execute(query)
        return result.scalars().all(), total

    async def update_reservation(
        self, reservation_id: int, payload: ReservationUpdate
    ) -> Optional[Reservation]:
        reservation = await self.get_reservation(reservation_id)
        if not reservation:
            return None

        update_data = payload.model_dump(exclude_unset=True)

        if "check_in_date" in update_data or "check_out_date" in update_data:
            new_check_in = update_data.get("check_in_date", reservation.check_in_date)
            new_check_out = update_data.get("check_out_date", reservation.check_out_date)
            available = await self._check_room_availability(
                reservation.room_id, new_check_in, new_check_out,
                exclude_reservation_id=reservation_id
            )
            if not available:
                raise ValueError("Room is not available for the updated dates")

        for field, value in update_data.items():
            setattr(reservation, field, value)

        await self.db.commit()
        await self.db.refresh(reservation)
        return reservation

    async def cancel_reservation(self, reservation_id: int) -> bool:
        reservation = await self.get_reservation(reservation_id)
        if not reservation:
            return False
        reservation.status = ReservationStatus.CANCELLED
        await self.db.commit()
        return True
`,
  },
  {
    path: "backend/tests/test_reservations.py",
    name: "test_reservations.py",
    ext: "py",
    language: "python",
    content: `import pytest
from datetime import date, timedelta
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.models.reservation import ReservationStatus


@pytest.fixture
def tomorrow():
    return date.today() + timedelta(days=1)


@pytest.fixture
def next_week():
    return date.today() + timedelta(days=7)


@pytest.mark.asyncio
async def test_create_reservation_success(client: AsyncClient, room, guest, tomorrow, next_week):
    response = await client.post("/api/reservations/", json={
        "room_id": room.id,
        "guest_id": guest.id,
        "check_in_date": tomorrow.isoformat(),
        "check_out_date": next_week.isoformat(),
        "num_guests": 2,
    })
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == ReservationStatus.CONFIRMED
    assert data["confirmation_code"].startswith("HMS-")
    assert data["total_price"] > 0


@pytest.mark.asyncio
async def test_create_reservation_conflict(client: AsyncClient, room, guest, tomorrow, next_week):
    # Create first reservation
    await client.post("/api/reservations/", json={
        "room_id": room.id,
        "guest_id": guest.id,
        "check_in_date": tomorrow.isoformat(),
        "check_out_date": next_week.isoformat(),
        "num_guests": 1,
    })

    # Attempt overlapping reservation
    response = await client.post("/api/reservations/", json={
        "room_id": room.id,
        "guest_id": guest.id,
        "check_in_date": (tomorrow + timedelta(days=2)).isoformat(),
        "check_out_date": (next_week + timedelta(days=2)).isoformat(),
        "num_guests": 1,
    })
    assert response.status_code == 409
    assert "not available" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_create_reservation_invalid_dates(client: AsyncClient, room, guest, tomorrow):
    response = await client.post("/api/reservations/", json={
        "room_id": room.id,
        "guest_id": guest.id,
        "check_in_date": tomorrow.isoformat(),
        "check_out_date": tomorrow.isoformat(),  # same day
        "num_guests": 1,
    })
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_cancel_reservation(client: AsyncClient, reservation):
    response = await client.delete(f"/api/reservations/{reservation.id}")
    assert response.status_code == 204

    # Verify cancelled
    get_response = await client.get(f"/api/reservations/{reservation.id}")
    assert get_response.json()["status"] == ReservationStatus.CANCELLED


@pytest.mark.asyncio
async def test_get_reservation_not_found(client: AsyncClient):
    response = await client.get("/api/reservations/99999")
    assert response.status_code == 404
`,
  },
  {
    path: "backend/tests/test_rooms.py",
    name: "test_rooms.py",
    ext: "py",
    language: "python",
    content: `import pytest
from httpx import AsyncClient
from app.models.room import RoomType, RoomStatus


@pytest.mark.asyncio
async def test_list_rooms(client: AsyncClient, room):
    response = await client.get("/api/rooms/")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1


@pytest.mark.asyncio
async def test_create_room_success(client: AsyncClient):
    response = await client.post("/api/rooms/", json={
        "number": "301",
        "floor": 3,
        "room_type": RoomType.SUITE,
        "price_per_night": 299.99,
        "max_occupancy": 4,
        "has_ocean_view": True,
        "has_balcony": True,
    })
    assert response.status_code == 201
    data = response.json()
    assert data["number"] == "301"
    assert data["room_type"] == RoomType.SUITE
    assert data["status"] == RoomStatus.AVAILABLE


@pytest.mark.asyncio
async def test_create_room_duplicate_number(client: AsyncClient, room):
    response = await client.post("/api/rooms/", json={
        "number": room.number,
        "floor": 1,
        "room_type": RoomType.SINGLE,
        "price_per_night": 99.99,
        "max_occupancy": 2,
    })
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_get_room(client: AsyncClient, room):
    response = await client.get(f"/api/rooms/{room.id}")
    assert response.status_code == 200
    assert response.json()["id"] == room.id


@pytest.mark.asyncio
async def test_get_room_not_found(client: AsyncClient):
    response = await client.get("/api/rooms/99999")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_filter_rooms_by_type(client: AsyncClient, room):
    response = await client.get(f"/api/rooms/?room_type={room.room_type}")
    assert response.status_code == 200
    data = response.json()
    assert all(r["room_type"] == room.room_type for r in data)


@pytest.mark.asyncio
async def test_update_room_status(client: AsyncClient, room):
    response = await client.patch(f"/api/rooms/{room.id}", json={
        "status": RoomStatus.MAINTENANCE
    })
    assert response.status_code == 200
    assert response.json()["status"] == RoomStatus.MAINTENANCE
`,
  },
  {
    path: "frontend/src/app/layout.tsx",
    name: "layout.tsx",
    ext: "tsx",
    language: "typescript",
    content: `import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Hotel Management System",
  description: "Full-stack hotel management platform",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className={inter.className}>
        {children}
      </body>
    </html>
  );
}
`,
  },
  {
    path: "frontend/src/app/(dashboard)/dashboard/page.tsx",
    name: "page.tsx",
    ext: "tsx",
    language: "typescript",
    content: `import { StatsCard } from "@/components/dashboard/StatsCard";
import { BedDouble, Users, CalendarCheck, DollarSign } from "lucide-react";

async function getDashboardStats() {
  // In production this would fetch from the API
  return {
    totalRooms: 48,
    occupiedRooms: 31,
    totalGuests: 1284,
    activeReservations: 31,
    monthlyRevenue: 94250,
    occupancyRate: 64.6,
  };
}

export default async function DashboardPage() {
  const stats = await getDashboardStats();

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-gray-900">Dashboard</h1>
        <p className="text-sm text-gray-500 mt-1">
          Overview of hotel operations
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatsCard
          title="Occupancy Rate"
          value={\`\${stats.occupancyRate}%\`}
          subtitle={\`\${stats.occupiedRooms} of \${stats.totalRooms} rooms\`}
          icon={BedDouble}
          trend={{ value: 4.2, direction: "up" }}
        />
        <StatsCard
          title="Active Reservations"
          value={stats.activeReservations}
          subtitle="Checked in today"
          icon={CalendarCheck}
          trend={{ value: 2, direction: "up" }}
        />
        <StatsCard
          title="Total Guests"
          value={stats.totalGuests.toLocaleString()}
          subtitle="All time"
          icon={Users}
          trend={{ value: 12.5, direction: "up" }}
        />
        <StatsCard
          title="Monthly Revenue"
          value={\`$\${stats.monthlyRevenue.toLocaleString()}\`}
          subtitle="This month"
          icon={DollarSign}
          trend={{ value: 8.1, direction: "up" }}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <h2 className="text-sm font-semibold text-gray-700 mb-4">
            Recent Check-ins
          </h2>
          <p className="text-sm text-gray-400">No recent check-ins to display.</p>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <h2 className="text-sm font-semibold text-gray-700 mb-4">
            Upcoming Check-outs
          </h2>
          <p className="text-sm text-gray-400">No upcoming check-outs.</p>
        </div>
      </div>
    </div>
  );
}
`,
  },
  {
    path: "frontend/src/app/(dashboard)/reservations/page.tsx",
    name: "page.tsx",
    ext: "tsx",
    language: "typescript",
    content: `"use client";

import { useState, useEffect } from "react";
import { ReservationTable } from "@/components/reservations/ReservationTable";
import { Plus, Search } from "lucide-react";

interface Reservation {
  id: number;
  confirmation_code: string;
  guest: { first_name: string; last_name: string; email: string };
  room: { number: string; room_type: string };
  check_in_date: string;
  check_out_date: string;
  status: string;
  total_price: number;
}

export default function ReservationsPage() {
  const [reservations, setReservations] = useState<Reservation[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");

  useEffect(() => {
    async function fetchReservations() {
      try {
        const res = await fetch(
          \`\${process.env.NEXT_PUBLIC_API_URL}/api/reservations/\`,
          { credentials: "include" }
        );
        if (res.ok) {
          const data = await res.json();
          setReservations(data.items ?? []);
        }
      } finally {
        setLoading(false);
      }
    }
    fetchReservations();
  }, []);

  const filtered = reservations.filter((r) => {
    const q = search.toLowerCase();
    return (
      r.confirmation_code.toLowerCase().includes(q) ||
      r.guest.last_name.toLowerCase().includes(q) ||
      r.room.number.includes(q)
    );
  });

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">Reservations</h1>
          <p className="text-sm text-gray-500 mt-1">
            {reservations.length} total reservations
          </p>
        </div>
        <button className="flex items-center gap-2 bg-[#1B2A4A] text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-[#243660] transition-colors">
          <Plus className="w-4 h-4" />
          New Reservation
        </button>
      </div>

      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
        <input
          type="text"
          placeholder="Search by code, guest, or room..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full pl-9 pr-4 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-[#1B2A4A]/20"
        />
      </div>

      <ReservationTable reservations={filtered} loading={loading} />
    </div>
  );
}
`,
  },
  {
    path: "frontend/src/app/(dashboard)/rooms/page.tsx",
    name: "page.tsx",
    ext: "tsx",
    language: "typescript",
    content: `"use client";

import { useState, useEffect } from "react";
import { BedDouble, Plus } from "lucide-react";

interface Room {
  id: number;
  number: string;
  floor: number;
  room_type: string;
  status: string;
  price_per_night: number;
  max_occupancy: number;
  has_ocean_view: boolean;
  has_balcony: boolean;
}

const STATUS_COLORS: Record<string, string> = {
  available: "bg-green-100 text-green-700",
  occupied: "bg-blue-100 text-blue-700",
  maintenance: "bg-red-100 text-red-700",
  cleaning: "bg-yellow-100 text-yellow-700",
};

export default function RoomsPage() {
  const [rooms, setRooms] = useState<Room[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<string>("all");

  useEffect(() => {
    async function fetchRooms() {
      try {
        const url = filter === "all"
          ? \`\${process.env.NEXT_PUBLIC_API_URL}/api/rooms/\`
          : \`\${process.env.NEXT_PUBLIC_API_URL}/api/rooms/?status=\${filter}\`;
        const res = await fetch(url, { credentials: "include" });
        if (res.ok) setRooms(await res.json());
      } finally {
        setLoading(false);
      }
    }
    fetchRooms();
  }, [filter]);

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">Rooms</h1>
          <p className="text-sm text-gray-500 mt-1">{rooms.length} rooms total</p>
        </div>
        <button className="flex items-center gap-2 bg-[#1B2A4A] text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-[#243660] transition-colors">
          <Plus className="w-4 h-4" />
          Add Room
        </button>
      </div>

      <div className="flex gap-2">
        {["all", "available", "occupied", "maintenance", "cleaning"].map((s) => (
          <button
            key={s}
            onClick={() => setFilter(s)}
            className={\`px-3 py-1.5 rounded-lg text-xs font-medium capitalize transition-colors \${
              filter === s
                ? "bg-[#1B2A4A] text-white"
                : "bg-white border border-gray-200 text-gray-600 hover:bg-gray-50"
            }\`}
          >
            {s}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="h-40 bg-gray-100 rounded-xl animate-pulse" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
          {rooms.map((room) => (
            <div
              key={room.id}
              className="bg-white border border-gray-200 rounded-xl p-4 hover:shadow-md transition-shadow cursor-pointer"
            >
              <div className="flex items-start justify-between mb-3">
                <div className="w-10 h-10 bg-[#F0F4FF] rounded-lg flex items-center justify-center">
                  <BedDouble className="w-5 h-5 text-[#1B2A4A]" />
                </div>
                <span className={\`text-[10px] font-semibold px-2 py-0.5 rounded-full capitalize \${STATUS_COLORS[room.status] ?? "bg-gray-100 text-gray-600"}\`}>
                  {room.status}
                </span>
              </div>
              <p className="text-lg font-bold text-gray-900">Room {room.number}</p>
              <p className="text-xs text-gray-500 capitalize">{room.room_type} · Floor {room.floor}</p>
              <p className="text-sm font-semibold text-[#1B2A4A] mt-2">
                \${Number(room.price_per_night).toFixed(0)}<span className="text-xs font-normal text-gray-400">/night</span>
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
`,
  },
  {
    path: "frontend/src/components/dashboard/StatsCard.tsx",
    name: "StatsCard.tsx",
    ext: "tsx",
    language: "typescript",
    content: `import { LucideIcon, TrendingUp, TrendingDown } from "lucide-react";

interface StatsCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  icon: LucideIcon;
  trend?: {
    value: number;
    direction: "up" | "down";
  };
}

export function StatsCard({ title, value, subtitle, icon: Icon, trend }: StatsCardProps) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5">
      <div className="flex items-start justify-between">
        <div className="w-10 h-10 bg-[#F0F4FF] rounded-lg flex items-center justify-center flex-shrink-0">
          <Icon className="w-5 h-5 text-[#1B2A4A]" />
        </div>
        {trend && (
          <div
            className={\`flex items-center gap-1 text-xs font-medium \${
              trend.direction === "up" ? "text-green-600" : "text-red-500"
            }\`}
          >
            {trend.direction === "up" ? (
              <TrendingUp className="w-3.5 h-3.5" />
            ) : (
              <TrendingDown className="w-3.5 h-3.5" />
            )}
            {trend.value}%
          </div>
        )}
      </div>
      <div className="mt-3">
        <p className="text-2xl font-bold text-gray-900">{value}</p>
        <p className="text-xs font-medium text-gray-500 mt-0.5">{title}</p>
        {subtitle && (
          <p className="text-xs text-gray-400 mt-0.5">{subtitle}</p>
        )}
      </div>
    </div>
  );
}
`,
  },
  {
    path: "frontend/src/components/reservations/ReservationTable.tsx",
    name: "ReservationTable.tsx",
    ext: "tsx",
    language: "typescript",
    content: `"use client";

interface Reservation {
  id: number;
  confirmation_code: string;
  guest: { first_name: string; last_name: string; email: string };
  room: { number: string; room_type: string };
  check_in_date: string;
  check_out_date: string;
  status: string;
  total_price: number;
}

interface ReservationTableProps {
  reservations: Reservation[];
  loading?: boolean;
}

const STATUS_STYLES: Record<string, string> = {
  confirmed: "bg-blue-50 text-blue-700 border-blue-200",
  checked_in: "bg-green-50 text-green-700 border-green-200",
  checked_out: "bg-gray-50 text-gray-600 border-gray-200",
  cancelled: "bg-red-50 text-red-600 border-red-200",
  pending: "bg-yellow-50 text-yellow-700 border-yellow-200",
  no_show: "bg-orange-50 text-orange-600 border-orange-200",
};

function formatDate(dateStr: string) {
  return new Date(dateStr).toLocaleDateString("en-US", {
    month: "short", day: "numeric", year: "numeric"
  });
}

export function ReservationTable({ reservations, loading }: ReservationTableProps) {
  if (loading) {
    return (
      <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="h-14 border-b border-gray-100 animate-pulse bg-gray-50" />
        ))}
      </div>
    );
  }

  if (reservations.length === 0) {
    return (
      <div className="bg-white border border-gray-200 rounded-xl p-12 text-center">
        <p className="text-gray-400 text-sm">No reservations found</p>
      </div>
    );
  }

  return (
    <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-100 bg-gray-50">
            <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Code</th>
            <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Guest</th>
            <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Room</th>
            <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Check-in</th>
            <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Check-out</th>
            <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Status</th>
            <th className="text-right px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Total</th>
          </tr>
        </thead>
        <tbody>
          {reservations.map((r) => (
            <tr key={r.id} className="border-b border-gray-50 hover:bg-gray-50 transition-colors cursor-pointer">
              <td className="px-4 py-3 font-mono text-xs text-gray-600">{r.confirmation_code}</td>
              <td className="px-4 py-3">
                <p className="font-medium text-gray-900">{r.guest.first_name} {r.guest.last_name}</p>
                <p className="text-xs text-gray-400">{r.guest.email}</p>
              </td>
              <td className="px-4 py-3">
                <p className="font-medium text-gray-900">Room {r.room.number}</p>
                <p className="text-xs text-gray-400 capitalize">{r.room.room_type}</p>
              </td>
              <td className="px-4 py-3 text-gray-600">{formatDate(r.check_in_date)}</td>
              <td className="px-4 py-3 text-gray-600">{formatDate(r.check_out_date)}</td>
              <td className="px-4 py-3">
                <span className={\`inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium border capitalize \${STATUS_STYLES[r.status] ?? "bg-gray-50 text-gray-600 border-gray-200"}\`}>
                  {r.status.replace("_", " ")}
                </span>
              </td>
              <td className="px-4 py-3 text-right font-semibold text-gray-900">
                \${Number(r.total_price).toFixed(2)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
`,
  },
  {
    path: "frontend/src/components/layout/Sidebar.tsx",
    name: "Sidebar.tsx",
    ext: "tsx",
    language: "typescript",
    content: `"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  BedDouble,
  CalendarCheck,
  Users,
  Settings,
  LogOut,
  Hotel,
} from "lucide-react";

const NAV_ITEMS = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/reservations", label: "Reservations", icon: CalendarCheck },
  { href: "/rooms", label: "Rooms", icon: BedDouble },
  { href: "/guests", label: "Guests", icon: Users },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-56 bg-[#1B2A4A] flex flex-col h-full">
      {/* Logo */}
      <div className="flex items-center gap-2.5 px-5 py-5 border-b border-white/10">
        <div className="w-8 h-8 bg-white/10 rounded-lg flex items-center justify-center">
          <Hotel className="w-4.5 h-4.5 text-white" />
        </div>
        <div>
          <p className="text-white text-sm font-semibold leading-tight">HotelMS</p>
          <p className="text-white/40 text-[10px]">Management System</p>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-4 space-y-0.5">
        {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
          const active = pathname === href || pathname.startsWith(href + "/");
          return (
            <Link
              key={href}
              href={href}
              className={\`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors \${
                active
                  ? "bg-white/10 text-white font-medium"
                  : "text-white/60 hover:text-white hover:bg-white/5"
              }\`}
            >
              <Icon className="w-4 h-4 flex-shrink-0" />
              {label}
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="px-3 py-4 border-t border-white/10">
        <button className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm text-white/60 hover:text-white hover:bg-white/5 transition-colors w-full">
          <LogOut className="w-4 h-4" />
          Sign out
        </button>
      </div>
    </aside>
  );
}
`,
  },
  {
    path: "backend/alembic/versions/0001_initial_schema.sql",
    name: "0001_initial_schema.sql",
    ext: "sql",
    language: "sql",
    content: `-- Hotel Management System — Initial Schema
-- PostgreSQL 15

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ─── Rooms ────────────────────────────────────────────────────────────────────

CREATE TYPE room_type AS ENUM ('single', 'double', 'suite', 'penthouse');
CREATE TYPE room_status AS ENUM ('available', 'occupied', 'maintenance', 'cleaning');

CREATE TABLE rooms (
    id               SERIAL PRIMARY KEY,
    number           VARCHAR(10)    NOT NULL UNIQUE,
    floor            INTEGER        NOT NULL,
    room_type        room_type      NOT NULL DEFAULT 'single',
    status           room_status    NOT NULL DEFAULT 'available',
    price_per_night  NUMERIC(10, 2) NOT NULL,
    max_occupancy    INTEGER        NOT NULL DEFAULT 2,
    has_ocean_view   BOOLEAN        NOT NULL DEFAULT FALSE,
    has_balcony      BOOLEAN        NOT NULL DEFAULT FALSE,
    description      VARCHAR(500),
    created_at       TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ    NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_rooms_status    ON rooms (status);
CREATE INDEX idx_rooms_room_type ON rooms (room_type);
CREATE INDEX idx_rooms_floor     ON rooms (floor);

-- ─── Guests ───────────────────────────────────────────────────────────────────

CREATE TABLE guests (
    id              SERIAL PRIMARY KEY,
    first_name      VARCHAR(100)  NOT NULL,
    last_name       VARCHAR(100)  NOT NULL,
    email           VARCHAR(255)  NOT NULL UNIQUE,
    phone           VARCHAR(20),
    date_of_birth   DATE,
    nationality     VARCHAR(100),
    passport_number VARCHAR(50),
    address_line1   VARCHAR(255),
    address_city    VARCHAR(100),
    address_country VARCHAR(100),
    loyalty_points  INTEGER       NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_guests_email     ON guests (email);
CREATE INDEX idx_guests_last_name ON guests (last_name);

-- ─── Reservations ─────────────────────────────────────────────────────────────

CREATE TYPE reservation_status AS ENUM (
    'pending', 'confirmed', 'checked_in', 'checked_out', 'cancelled', 'no_show'
);

CREATE TABLE reservations (
    id                SERIAL PRIMARY KEY,
    room_id           INTEGER            NOT NULL REFERENCES rooms(id),
    guest_id          INTEGER            NOT NULL REFERENCES guests(id),
    check_in_date     DATE               NOT NULL,
    check_out_date    DATE               NOT NULL,
    status            reservation_status NOT NULL DEFAULT 'pending',
    num_guests        INTEGER            NOT NULL DEFAULT 1,
    total_price       NUMERIC(10, 2)     NOT NULL,
    special_requests  TEXT,
    confirmation_code VARCHAR(20)        NOT NULL UNIQUE,
    created_at        TIMESTAMPTZ        NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ        NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_dates CHECK (check_out_date > check_in_date),
    CONSTRAINT chk_num_guests CHECK (num_guests >= 1)
);

CREATE INDEX idx_reservations_room_id    ON reservations (room_id);
CREATE INDEX idx_reservations_guest_id   ON reservations (guest_id);
CREATE INDEX idx_reservations_status     ON reservations (status);
CREATE INDEX idx_reservations_check_in   ON reservations (check_in_date);
CREATE INDEX idx_reservations_check_out  ON reservations (check_out_date);
CREATE INDEX idx_reservations_code       ON reservations (confirmation_code);

-- Partial index for active reservations (most common query)
CREATE INDEX idx_reservations_active ON reservations (room_id, check_in_date, check_out_date)
    WHERE status NOT IN ('cancelled', 'no_show');

-- ─── Updated-at trigger ───────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_rooms_updated_at
    BEFORE UPDATE ON rooms
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_guests_updated_at
    BEFORE UPDATE ON guests
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_reservations_updated_at
    BEFORE UPDATE ON reservations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
`,
  },
  {
    path: "Dockerfile",
    name: "Dockerfile",
    ext: "dockerfile",
    language: "dockerfile",
    content: `# ─── Stage 1: Builder ─────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \\
    gcc libpq-dev \\
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies into a virtual environment
COPY backend/requirements.txt .
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip && \\
    pip install --no-cache-dir -r requirements.txt

# ─── Stage 2: Runtime ─────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

WORKDIR /app

# Runtime system deps only
RUN apt-get update && apt-get install -y --no-install-recommends \\
    libpq5 curl \\
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application code
COPY backend/ .

# Non-root user for security
RUN useradd -m -u 1001 appuser && chown -R appuser:appuser /app
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \\
    CMD curl -f http://localhost:\${PORT:-8000}/health || exit 1

EXPOSE 8000

# Run migrations then start server
CMD alembic upgrade head && \\
    uvicorn app.main:app --host 0.0.0.0 --port \${PORT:-8000} --workers 2
`,
  },
  {
    path: "docker-compose.yml",
    name: "docker-compose.yml",
    ext: "yml",
    language: "yaml",
    content: `version: "3.9"

services:
  db:
    image: postgres:15-alpine
    restart: unless-stopped
    environment:
      POSTGRES_DB: hotel
      POSTGRES_USER: hotel
      POSTGRES_PASSWORD: secret
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U hotel -d hotel"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    restart: unless-stopped
    command: redis-server --appendonly yes
    volumes:
      - redis_data:/data
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  backend:
    build:
      context: .
      dockerfile: Dockerfile
      target: runtime
    restart: unless-stopped
    environment:
      DATABASE_URL: postgresql+asyncpg://hotel:secret@db:5432/hotel
      REDIS_URL: redis://redis:6379/0
      SECRET_KEY: dev-secret-change-in-production
      ALLOWED_ORIGINS: '["http://localhost:3000"]'
      ENVIRONMENT: development
    ports:
      - "8000:8000"
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    restart: unless-stopped
    environment:
      NEXT_PUBLIC_API_URL: http://localhost:8000
    ports:
      - "3000:3000"
    depends_on:
      backend:
        condition: service_healthy

volumes:
  postgres_data:
  redis_data:
`,
  },
  {
    path: ".github/workflows/ci.yml",
    name: "ci.yml",
    ext: "yml",
    language: "yaml",
    content: `name: CI

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  backend:
    name: Backend Tests
    runs-on: ubuntu-latest

    services:
      postgres:
        image: postgres:15-alpine
        env:
          POSTGRES_DB: hotel_test
          POSTGRES_USER: hotel
          POSTGRES_PASSWORD: secret
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

      redis:
        image: redis:7-alpine
        ports:
          - 6379:6379
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python 3.11
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip
          cache-dependency-path: backend/requirements.txt

      - name: Install dependencies
        run: |
          cd backend
          pip install -r requirements.txt

      - name: Run linting
        run: |
          cd backend
          pip install flake8 black isort
          black --check .
          isort --check-only .
          flake8 .

      - name: Run tests
        env:
          DATABASE_URL: postgresql+asyncpg://hotel:secret@localhost:5432/hotel_test
          REDIS_URL: redis://localhost:6379/0
          SECRET_KEY: test-secret-key
        run: |
          cd backend
          pytest -v --tb=short --cov=app --cov-report=xml

      - name: Upload coverage
        uses: codecov/codecov-action@v4
        with:
          file: backend/coverage.xml
          flags: backend

  frontend:
    name: Frontend Tests
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Set up Node.js 18
        uses: actions/setup-node@v4
        with:
          node-version: "18"
          cache: npm
          cache-dependency-path: frontend/package-lock.json

      - name: Install dependencies
        run: cd frontend && npm ci

      - name: Type check
        run: cd frontend && npm run type-check

      - name: Lint
        run: cd frontend && npm run lint

      - name: Run tests
        run: cd frontend && npm test -- --coverage --watchAll=false

      - name: Build
        run: cd frontend && npm run build
        env:
          NEXT_PUBLIC_API_URL: http://localhost:8000
`,
  },
  {
    path: "Makefile",
    name: "Makefile",
    ext: "txt",
    language: "plaintext",
    content: `.PHONY: install dev build test lint migrate docker-up docker-down clean

# ─── Setup ────────────────────────────────────────────────────────────────────

install:
	@echo "Installing backend dependencies..."
	cd backend && pip install -r requirements.txt
	@echo "Installing frontend dependencies..."
	cd frontend && npm ci
	@echo "Done."

# ─── Development ──────────────────────────────────────────────────────────────

dev:
	@echo "Starting development servers..."
	@make -j2 dev-backend dev-frontend

dev-backend:
	cd backend && uvicorn app.main:app --reload --port 8000

dev-frontend:
	cd frontend && npm run dev

# ─── Build ────────────────────────────────────────────────────────────────────

build:
	@echo "Building frontend..."
	cd frontend && npm run build
	@echo "Building Docker image..."
	docker build -t hotel-management:latest .

# ─── Testing ──────────────────────────────────────────────────────────────────

test:
	@make test-backend
	@make test-frontend

test-backend:
	@echo "Running backend tests..."
	cd backend && pytest -v --tb=short

test-frontend:
	@echo "Running frontend tests..."
	cd frontend && npm test -- --watchAll=false

# ─── Linting ──────────────────────────────────────────────────────────────────

lint:
	@make lint-backend
	@make lint-frontend

lint-backend:
	@echo "Linting backend..."
	cd backend && black . && isort . && flake8 .

lint-frontend:
	@echo "Linting frontend..."
	cd frontend && npm run lint

# ─── Database ─────────────────────────────────────────────────────────────────

migrate:
	@echo "Running database migrations..."
	cd backend && alembic upgrade head

migrate-down:
	@echo "Rolling back last migration..."
	cd backend && alembic downgrade -1

migrate-create:
	@echo "Creating new migration: $(name)"
	cd backend && alembic revision --autogenerate -m "$(name)"

# ─── Docker ───────────────────────────────────────────────────────────────────

docker-up:
	docker compose up -d
	@echo "Services started. API: http://localhost:8000 | App: http://localhost:3000"

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f

# ─── Cleanup ──────────────────────────────────────────────────────────────────

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	cd frontend && rm -rf .next node_modules/.cache
`,
  },
  {
    path: ".env.example",
    name: ".env.example",
    ext: "env",
    language: "bash",
    content: `# ─── Application ──────────────────────────────────────────────────────────────
APP_NAME="Hotel Management System"
ENVIRONMENT=development          # development | staging | production
DEBUG=false

# ─── Database ─────────────────────────────────────────────────────────────────
# PostgreSQL connection string
# Format: postgresql+asyncpg://user:password@host:port/dbname
DATABASE_URL=postgresql+asyncpg://hotel:secret@localhost:5432/hotel

# ─── Redis ────────────────────────────────────────────────────────────────────
# Redis connection string for caching and session storage
REDIS_URL=redis://localhost:6379/0

# ─── Security ─────────────────────────────────────────────────────────────────
# Generate with: openssl rand -hex 32
SECRET_KEY=change-me-to-a-random-secret-in-production

# JWT settings
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60

# ─── CORS ─────────────────────────────────────────────────────────────────────
# Comma-separated list of allowed frontend origins
ALLOWED_ORIGINS=["http://localhost:3000","https://your-frontend.onrender.com"]

# ─── Frontend ─────────────────────────────────────────────────────────────────
# Backend API URL (used by Next.js)
NEXT_PUBLIC_API_URL=http://localhost:8000

# ─── Email (optional) ─────────────────────────────────────────────────────────
# SMTP settings for reservation confirmation emails
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password
EMAIL_FROM=noreply@hotelms.com

# ─── Sentry (optional) ────────────────────────────────────────────────────────
# Error tracking
SENTRY_DSN=
`,
  },
  {
    path: "frontend/package.json",
    name: "package.json",
    ext: "json",
    language: "json",
    content: `{
  "name": "hotel-management-frontend",
  "version": "1.0.0",
  "private": true,
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "lint": "next lint",
    "type-check": "tsc --noEmit",
    "test": "jest --passWithNoTests"
  },
  "dependencies": {
    "next": "14.2.5",
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "lucide-react": "^0.395.0",
    "clsx": "^2.1.1",
    "tailwind-merge": "^2.3.0",
    "@tanstack/react-query": "^5.45.1",
    "axios": "^1.7.2",
    "date-fns": "^3.6.0",
    "react-hook-form": "^7.52.1",
    "zod": "^3.23.8",
    "@hookform/resolvers": "^3.6.0"
  },
  "devDependencies": {
    "@types/node": "^20.14.9",
    "@types/react": "^18.3.3",
    "@types/react-dom": "^18.3.0",
    "typescript": "^5.5.3",
    "tailwindcss": "^3.4.4",
    "postcss": "^8.4.39",
    "autoprefixer": "^10.4.19",
    "eslint": "^8.57.0",
    "eslint-config-next": "14.2.5",
    "jest": "^29.7.0",
    "@testing-library/react": "^16.0.0",
    "@testing-library/jest-dom": "^6.4.6",
    "jest-environment-jsdom": "^29.7.0"
  }
}
`,
  },
  {
    path: "backend/requirements.txt",
    name: "requirements.txt",
    ext: "txt",
    language: "plaintext",
    content: `# ─── Web Framework ────────────────────────────────────────────────────────────
fastapi==0.111.0
uvicorn[standard]==0.30.1
python-multipart==0.0.9

# ─── Database ─────────────────────────────────────────────────────────────────
sqlalchemy==2.0.31
asyncpg==0.29.0
alembic==1.13.2
psycopg2-binary==2.9.9

# ─── Settings & Validation ────────────────────────────────────────────────────
pydantic==2.8.2
pydantic-settings==2.3.4

# ─── Auth ─────────────────────────────────────────────────────────────────────
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4

# ─── Cache ────────────────────────────────────────────────────────────────────
redis==5.0.7

# ─── HTTP Client ──────────────────────────────────────────────────────────────
httpx==0.27.0

# ─── Testing ──────────────────────────────────────────────────────────────────
pytest==8.2.2
pytest-asyncio==0.23.7
pytest-cov==5.0.0
anyio==4.4.0

# ─── Linting / Formatting ─────────────────────────────────────────────────────
black==24.4.2
isort==5.13.2
flake8==7.1.0
`,
  },
  {
    path: ".gitignore",
    name: ".gitignore",
    ext: "gitignore",
    language: "bash",
    content: `# ─── Python ───────────────────────────────────────────────────────────────────
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg
MANIFEST

# Virtual environments
.venv/
venv/
ENV/
env/

# pytest
.pytest_cache/
.coverage
coverage.xml
htmlcov/

# mypy
.mypy_cache/
.dmypy.json
dmypy.json

# ─── Node / Next.js ───────────────────────────────────────────────────────────
node_modules/
.next/
out/
.nuxt/
dist/
.cache/
*.tsbuildinfo
next-env.d.ts

# ─── Environment files ────────────────────────────────────────────────────────
.env
.env.local
.env.development.local
.env.test.local
.env.production.local
backend/.env

# ─── IDE ──────────────────────────────────────────────────────────────────────
.vscode/settings.json
.idea/
*.swp
*.swo
.DS_Store
Thumbs.db

# ─── Docker ───────────────────────────────────────────────────────────────────
.dockerignore

# ─── Logs ─────────────────────────────────────────────────────────────────────
*.log
logs/
npm-debug.log*
yarn-debug.log*
yarn-error.log*

# ─── Database ─────────────────────────────────────────────────────────────────
*.sqlite
*.db

# ─── Misc ─────────────────────────────────────────────────────────────────────
*.bak
*.tmp
.terraform/
terraform.tfstate*
`,
  },
];

export default function TestPreviewPage() {
  return (
    <div className="h-screen flex flex-col">
      <div className="bg-[#1B2A4A] text-white px-4 py-2 text-[11px] font-medium flex items-center gap-3 flex-shrink-0">
        <span className="bg-yellow-400 text-yellow-900 px-2 py-0.5 rounded text-[9px] font-bold uppercase tracking-wide">Test</span>
        <span>App Builder Preview — {MOCK_FILES.length} mock files · Hotel Management System · <code className="bg-white/10 px-1.5 py-0.5 rounded font-mono">/test-preview</code></span>
        <span className="ml-auto text-white/50 text-[10px]">Mirrors full 15-agent pipeline output: docs · backend · frontend · db · infra · tests · CI/CD</span>
      </div>
      <div className="flex-1 min-h-0">
        <AppBuilderPreview
          files={MOCK_FILES}
          projectName="Hotel Management System"
          onRevise={(instruction) => alert(`Revision requested:\n\n"${instruction}"\n\n(This would trigger the app_builder_revision pipeline)`)}
        />
      </div>
    </div>
  );
}
