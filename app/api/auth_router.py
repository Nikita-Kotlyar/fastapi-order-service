from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import (
    UserContext,
    authenticate,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    require_admin,
)
from app.db import get_db
from app.models import AuditEvent, User
from app.schemas import Page, RefreshRequest, Token, UserCreate, UserOut, UserPatch
from app.security import hash_password

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

ALLOWED_ROLES = {"admin", "analyst", "viewer"}


def _validate_roles(roles: list[str]) -> list[str]:
    normalized = sorted({role.strip().lower() for role in roles if role.strip()})
    unknown = set(normalized) - ALLOWED_ROLES
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown roles: {sorted(unknown)}")
    if not normalized:
        raise HTTPException(status_code=422, detail="At least one role is required")
    return normalized


def _to_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        username=user.username,
        roles=user.role_list,
        is_active=user.is_active,
        created_at=user.created_at,
    )


@router.post("/token", response_model=Token)
def issue_token(
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> Token:
    user = authenticate(db, form.username, form.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user.last_login_at = datetime.now(UTC)
    access_token, expires_in = create_access_token(user)
    refresh_token, refresh_expires_in = create_refresh_token(user)
    db.add(
        AuditEvent(
            actor=user.username,
            action="auth.login",
            entity="user",
            entity_id=str(user.id),
            payload={"roles": user.role_list},
        )
    )
    db.commit()
    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
        refresh_expires_in=refresh_expires_in,
    )


@router.post("/refresh", response_model=Token)
def refresh_token(payload: RefreshRequest, db: Session = Depends(get_db)) -> Token:
    claims = decode_token(payload.refresh_token, "refresh")
    user = db.scalar(select(User).where(User.username == claims["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User is inactive or missing")
    access_token, expires_in = create_access_token(user)
    new_refresh, refresh_expires_in = create_refresh_token(user)
    return Token(
        access_token=access_token,
        refresh_token=new_refresh,
        expires_in=expires_in,
        refresh_expires_in=refresh_expires_in,
    )


@router.get("/me", response_model=UserOut)
def me(user: UserContext = Depends(get_current_user), db: Session = Depends(get_db)) -> UserOut:
    db_user = db.get(User, user.user_id)
    if db_user is None:
        raise HTTPException(status_code=401, detail="User is missing")
    return _to_out(db_user)


@router.get("/users", response_model=Page[UserOut])
def list_users(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _admin: UserContext = Depends(require_admin),
) -> Page[UserOut]:
    stmt = select(User)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = list(db.scalars(stmt.order_by(User.id).offset(offset).limit(limit)))
    return Page[UserOut](
        items=[_to_out(user) for user in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    admin: UserContext = Depends(require_admin),
) -> UserOut:
    if db.scalar(select(User).where(User.username == payload.username)) is not None:
        raise HTTPException(status_code=409, detail="Username already exists")
    roles = _validate_roles(payload.roles)
    user = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        roles=",".join(roles),
        is_active=True,
    )
    db.add(user)
    db.flush()
    db.add(
        AuditEvent(
            actor=admin.username,
            action="user.create",
            entity="user",
            entity_id=str(user.id),
            payload={"username": user.username, "roles": roles},
        )
    )
    db.commit()
    return _to_out(user)


@router.patch("/users/{user_id}", response_model=UserOut)
def patch_user(
    user_id: int,
    payload: UserPatch,
    db: Session = Depends(get_db),
    admin: UserContext = Depends(require_admin),
) -> UserOut:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    changes = payload.model_dump(exclude_unset=True)
    if "roles" in changes and changes["roles"] is not None:
        changes["roles"] = _validate_roles(changes["roles"])
    new_roles = changes.get("roles")
    new_active = changes.get("is_active", user.is_active)
    losing_admin = "admin" in user.role_list and (
        (new_roles is not None and "admin" not in new_roles) or new_active is False
    )
    if losing_admin:
        active_admins = db.scalar(
            select(func.count()).select_from(User).where(User.is_active.is_(True), User.roles.like("%admin%"))
        )
        if (active_admins or 0) <= 1:
            raise HTTPException(status_code=409, detail="At least one active admin is required")
    if user_id == admin.user_id and new_active is False:
        raise HTTPException(status_code=409, detail="You cannot deactivate your own account")

    if "password" in changes and changes["password"]:
        user.password_hash = hash_password(changes["password"])
    if new_roles is not None:
        user.roles = ",".join(new_roles)
    if "is_active" in changes and changes["is_active"] is not None:
        user.is_active = changes["is_active"]
    db.add(
        AuditEvent(
            actor=admin.username,
            action="user.patch",
            entity="user",
            entity_id=str(user.id),
            payload={key: str(value) for key, value in changes.items() if key != "password"},
        )
    )
    db.commit()
    return _to_out(user)
