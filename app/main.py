from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api import api_router
from app.auth import seed_users
from app.config import settings
from app.db import SessionLocal, init_db
from app.errors import install_exception_handlers
from app.middleware import RequestIDMiddleware

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.auto_create_tables:
        init_db()
    if settings.seed_default_users:
        with SessionLocal() as db:
            seed_users(db)
            db.commit()
    yield


app = FastAPI(
    title=settings.app_name,
    version=__version__,
    description=(
        "Order hub for five legacy order sources: ingestion, normalization, "
        "entity resolution, golden records and a discrepancy registry.\n\n"
        "**Roles:** `admin` — full access, `analyst` — reconcile and resolve "
        "issues, `viewer` — read-only. Use `POST /api/v1/auth/token` to get "
        "access and refresh tokens."
    ),
    contact={"name": "Order Hub team", "email": "orderhub@example.ru"},
    license_info={"name": "MIT"},
    openapi_tags=[
        {"name": "auth", "description": "JWT access/refresh tokens and users"},
        {"name": "orders", "description": "Canonical orders, CRUD and export"},
        {"name": "issues", "description": "Data-quality issue registry"},
        {"name": "imports", "description": "Import batches and reconciliation runs"},
        {"name": "master-data", "description": "Customers, products and unit conversions"},
        {"name": "system", "description": "Health, readiness and metrics"},
    ],
    lifespan=lifespan,
)

app.add_middleware(RequestIDMiddleware)
install_exception_handlers(app)

if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(api_router)


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    return {"service": settings.app_name, "docs": "/docs", "health": "/health"}
