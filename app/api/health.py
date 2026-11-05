from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import __version__
from app.cache import cache
from app.db import get_db
from app.models import ImportBatch, Issue, Order

router = APIRouter(tags=["system"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@router.get("/ready")
def ready(db: Session = Depends(get_db)) -> dict[str, str]:
    db.execute(select(1))
    return {
        "status": "ready",
        "database": "ok",
        "cache": cache.backend,
        "cache_ok": "yes" if cache.ping() else "no",
    }


@router.get("/metrics", include_in_schema=False)
def metrics(db: Session = Depends(get_db)) -> str:
    orders = db.scalar(select(func.count()).select_from(Order)) or 0
    issues = db.scalar(select(func.count()).select_from(Issue)) or 0
    open_issues = db.scalar(select(func.count()).select_from(Issue).where(Issue.status == "open")) or 0
    imports = db.scalar(select(func.count()).select_from(ImportBatch)) or 0
    cache_stats = cache.stats()
    lines = [
        "# HELP orderhub_orders Number of canonical orders.",
        "# TYPE orderhub_orders gauge",
        f"orderhub_orders {orders}",
        "# HELP orderhub_issues Number of data-quality issues.",
        "# TYPE orderhub_issues gauge",
        f'orderhub_issues{{status="all"}} {issues}',
        f'orderhub_issues{{status="open"}} {open_issues}',
        "# HELP orderhub_imports Number of import batches.",
        "# TYPE orderhub_imports gauge",
        f"orderhub_imports {imports}",
        "# HELP orderhub_cache_hits Cache hits.",
        "# TYPE orderhub_cache_hits counter",
        f"orderhub_cache_hits {cache_stats['hits']}",
        "# HELP orderhub_cache_misses Cache misses.",
        "# TYPE orderhub_cache_misses counter",
        f"orderhub_cache_misses {cache_stats['misses']}",
        "# HELP orderhub_cache_backend Cache backend (1 = redis, 0 = memory).",
        "# TYPE orderhub_cache_backend gauge",
        f"orderhub_cache_backend {1 if cache_stats['backend'] == 'redis' else 0}",
    ]
    return "\n".join(lines) + "\n"
