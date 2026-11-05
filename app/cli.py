from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from sqlalchemy import select

from app.auth import seed_users
from app.config import settings
from app.db import SessionLocal
from app.ingestion.master_data import seed_master_data
from app.models import User
from app.security import hash_password
from app.services.reconciliation import ReconciliationService


def _seed(source_dir: Path) -> None:
    with SessionLocal() as session:
        seed_master_data(session, source_dir)
        created = seed_users(session)
        session.commit()
    print(f"Master data seeded from {source_dir}; users created: {created}")


def _create_user(username: str, password: str, roles: str) -> None:
    with SessionLocal() as session:
        if session.scalar(select(User).where(User.username == username)) is not None:
            raise SystemExit(f"User {username!r} already exists")
        session.add(
            User(
                username=username,
                password_hash=hash_password(password),
                roles=roles,
                is_active=True,
            )
        )
        session.commit()
    print(f"User {username!r} created with roles: {roles}")


def _reconcile(source_dir: Path, profile: str, dry_run: bool, run_date: str | None) -> None:
    with SessionLocal() as session:
        service = ReconciliationService(session)
        result = service.run(
            source_dir,
            profile=profile,
            dry_run=dry_run,
            run_date=date.fromisoformat(run_date) if run_date else None,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


def main() -> None:
    parser = argparse.ArgumentParser(prog="orderhub", description="Order hub CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    seed_parser = subparsers.add_parser("seed", help="Seed customers, products and unit conversions")
    seed_parser.add_argument("--source-dir", type=Path, default=settings.source_dir)

    reconcile_parser = subparsers.add_parser("reconcile", help="Run ingestion + matching + DQ")
    reconcile_parser.add_argument("--source-dir", type=Path, default=settings.source_dir)
    reconcile_parser.add_argument("--profile", choices=["reference", "full"], default="full")
    reconcile_parser.add_argument("--dry-run", action="store_true")
    reconcile_parser.add_argument("--run-date", default=None)

    user_parser = subparsers.add_parser("create-user", help="Create a user with roles")
    user_parser.add_argument("--username", required=True)
    user_parser.add_argument("--password", required=True)
    user_parser.add_argument("--roles", default="viewer", help="Comma-separated: admin,analyst,viewer")

    serve_parser = subparsers.add_parser("serve", help="Run the API with uvicorn")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8080)
    serve_parser.add_argument("--reload", action="store_true")

    args = parser.parse_args()
    if args.command == "seed":
        _seed(args.source_dir)
    elif args.command == "reconcile":
        _reconcile(args.source_dir, args.profile, args.dry_run, args.run_date)
    elif args.command == "create-user":
        _create_user(args.username, args.password, args.roles)
    elif args.command == "serve":
        import uvicorn

        uvicorn.run("app.main:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
