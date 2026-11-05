from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

from app.cache import cache
from app.models import Issue, Order, OrderLink


def _seed_order(db) -> None:
    order = Order(
        canonical_order_id="CO-TEST-0001",
        customer_id="CUST-TEST",
        customer_name="ООО «Тест»",
        order_date=date(2026, 1, 1),
        delivery_date=date(2026, 1, 10),
        status="new",
        total_rub=Decimal("100.00"),
        currency="RUB",
        match_confidence=Decimal("0.95"),
        issue_count=1,
    )
    db.add(order)
    db.flush()
    db.add(
        OrderLink(
            order_id=order.id,
            source_type="1c_orders",
            source_id="ORD-TEST-0001",
            match_method="exact_order_id",
            confidence=Decimal("1.00"),
            is_primary=True,
        )
    )
    db.add(
        Issue(
            issue_key="test-issue-key",
            issue_type="missing_customer",
            severity="high",
            source="1c_orders_export.csv",
            source_id="CO-TEST-0001",
            order_canonical_id="CO-TEST-0001",
            order_id=order.id,
            details="customer_id пусто",
            status="open",
        )
    )
    db.commit()


def _token(client, username: str = "admin", password: str = "test-admin-password") -> str:
    response = client.post("/api/v1/auth/token", data={"username": username, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


def test_list_filter_and_detail(client, db) -> None:
    _seed_order(db)
    response = client.get("/api/v1/orders")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["sources"] == ["1c_orders"]

    filtered = client.get("/api/v1/orders", params={"status": "new", "has_issues": True})
    assert filtered.json()["total"] == 1
    empty = client.get("/api/v1/orders", params={"status": "closed"})
    assert empty.json()["total"] == 0

    detail = client.get("/api/v1/orders/CO-TEST-0001")
    assert detail.status_code == 200
    body = detail.json()
    assert body["links"][0]["source_id"] == "ORD-TEST-0001"
    assert body["issues"][0]["issue_type"] == "missing_customer"
    assert client.get("/api/v1/orders/CO-404").status_code == 404


def test_export_csv(client, db) -> None:
    _seed_order(db)
    response = client.get("/api/v1/orders/export")
    assert response.status_code == 200
    lines = response.text.lstrip("﻿").strip().splitlines()
    assert lines[0].startswith("canonical_order_id;customer_id")
    assert lines[1].startswith("CO-TEST-0001;CUST-TEST")


def test_auth_and_patch(client, db) -> None:
    _seed_order(db)
    assert client.patch("/api/v1/orders/CO-TEST-0001", json={"status": "confirmed"}).status_code == 401

    token = _token(client)
    headers = {"Authorization": f"Bearer {token}"}
    response = client.patch(
        "/api/v1/orders/CO-TEST-0001",
        json={"status": "confirmed", "customer_name": "ООО «Тест 2»"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "confirmed"
    assert response.json()["customer_name"] == "ООО «Тест 2»"

    bad = client.post(
        "/api/v1/orders/CO-TEST-0001/status",
        json={"status": "new"},
        headers=headers,
    )
    assert bad.status_code == 409

    status = client.post(
        "/api/v1/orders/CO-TEST-0001/status",
        json={"status": "in_production"},
        headers=headers,
    )
    assert status.status_code == 200
    assert status.json()["status"] == "in_production"


def test_issue_actions(client, db) -> None:
    _seed_order(db)
    token = _token(client)
    headers = {"Authorization": f"Bearer {token}"}
    issue_id = db.query(Issue).one().id
    response = client.post(
        f"/api/v1/issues/{issue_id}/resolve",
        json={"note": "проверено вручную"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "resolved"
    assert response.json()["resolution_note"] == "проверено вручную"

    reopened = client.post(f"/api/v1/issues/{issue_id}/reopen", json={}, headers=headers)
    assert reopened.status_code == 200
    assert reopened.json()["status"] == "open"


def test_health_and_metrics(client, db) -> None:
    _seed_order(db)
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/ready").status_code == 200
    metrics = client.get("/metrics").text
    assert "orderhub_orders 1" in metrics


def test_create_and_delete_manual_order(client, db) -> None:
    token = _token(client)
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "customer_name": "ООО «Новый клиент»",
        "order_date": "2026-02-01",
        "delivery_date": "2026-02-10",
        "status": "new",
        "lines": [
            {
                "sku": "CBL-TEST-3x1,5",
                "product_name": "Кабель тестовый",
                "qty": "100",
                "unit": "м",
                "price_rub": "10.00",
            }
        ],
    }

    assert client.post("/api/v1/orders", json=payload).status_code == 401

    created = client.post("/api/v1/orders", json=payload, headers=headers)
    assert created.status_code == 201
    body = created.json()
    assert body["canonical_order_id"].startswith("CO-MAN-")
    assert body["is_manual"] is True
    assert body["total_rub"] == "1000.00"
    assert len(body["lines"]) == 1
    assert body["links"][0]["source_type"] == "manual"

    canonical_id = body["canonical_order_id"]
    assert client.get(f"/api/v1/orders/{canonical_id}").status_code == 200

    deleted = client.delete(f"/api/v1/orders/{canonical_id}", headers=headers)
    assert deleted.status_code == 204
    assert client.get(f"/api/v1/orders/{canonical_id}").status_code == 404


def test_generated_order_cannot_be_deleted(client, db) -> None:
    _seed_order(db)
    token = _token(client)
    response = client.delete(
        "/api/v1/orders/CO-TEST-0001",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 409


def test_openapi_contract(client) -> None:
    spec = client.get("/openapi.json").json()
    paths = spec["paths"]
    assert "/api/v1/orders" in paths
    assert {"get", "post"} <= set(paths["/api/v1/orders"])
    assert "delete" in paths["/api/v1/orders/{canonical_order_id}"]
    assert "OAuth2PasswordBearer" in spec["components"]["securitySchemes"]
    assert paths["/api/v1/orders"]["post"].get("security")
    assert "/api/v1/auth/refresh" in paths
    assert "/api/v1/auth/users" in paths
    params = {parameter["name"] for parameter in paths["/api/v1/orders"]["get"]["parameters"]}
    assert {"limit", "offset", "status", "source_type"} <= params


def test_token_refresh_and_me(client) -> None:
    response = client.post(
        "/api/v1/auth/token",
        data={"username": "admin", "password": "test-admin-password"},
    )
    assert response.status_code == 200
    token = response.json()
    assert {"access_token", "refresh_token", "expires_in", "refresh_expires_in"} <= set(token)

    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token['access_token']}"})
    assert me.status_code == 200
    assert me.json()["username"] == "admin"
    assert me.json()["roles"] == ["admin"]

    refreshed = client.post("/api/v1/auth/refresh", json={"refresh_token": token["refresh_token"]})
    assert refreshed.status_code == 200
    assert refreshed.json()["access_token"] != token["access_token"]

    wrong_type = client.post("/api/v1/auth/refresh", json={"refresh_token": token["access_token"]})
    assert wrong_type.status_code == 401


def test_invalid_token_rejected(client) -> None:
    response = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == 401
    assert response.headers["X-Request-ID"]


def test_role_enforcement(client, db) -> None:
    _seed_order(db)
    issue_id = db.query(Issue).one().id
    analyst = _token(client, "analyst", "test-analyst-password")
    viewer = _token(client, "viewer", "test-viewer-password")
    analyst_headers = {"Authorization": f"Bearer {analyst}"}
    viewer_headers = {"Authorization": f"Bearer {viewer}"}

    payload = {
        "customer_name": "ООО «Роль»",
        "order_date": "2026-02-01",
        "status": "new",
    }
    assert client.post("/api/v1/orders", json=payload, headers=analyst_headers).status_code == 403
    assert client.post("/api/v1/orders", json=payload, headers=viewer_headers).status_code == 403

    resolved = client.post(
        f"/api/v1/issues/{issue_id}/resolve",
        json={"note": "analyst resolved"},
        headers=analyst_headers,
    )
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved"

    denied = client.post(
        f"/api/v1/issues/{issue_id}/reopen",
        json={},
        headers=viewer_headers,
    )
    assert denied.status_code == 403

    admin = _token(client)
    created = client.post(
        "/api/v1/orders",
        json=payload,
        headers={"Authorization": f"Bearer {admin}"},
    )
    assert created.status_code == 201


def test_error_envelope(client) -> None:
    response = client.get("/api/v1/orders/CO-404")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == 404
    assert body["error"]["request_id"]
    assert response.headers["X-Request-ID"] == body["error"]["request_id"]

    bad_login = client.post(
        "/api/v1/auth/token",
        data={"username": "admin", "password": "wrong"},
    )
    assert bad_login.status_code == 401
    assert bad_login.json()["error"]["message"] == "Incorrect username or password"


def test_cache_headers_and_invalidation(client, db) -> None:
    _seed_order(db)
    cache.invalidate()
    first = client.get("/api/v1/orders")
    assert first.headers["X-Cache"] == "MISS"
    second = client.get("/api/v1/orders")
    assert second.headers["X-Cache"] == "HIT"

    token = _token(client)
    patched = client.patch(
        "/api/v1/orders/CO-TEST-0001",
        json={"customer_name": "ООО «Кэш»"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert patched.status_code == 200
    after = client.get("/api/v1/orders")
    assert after.headers["X-Cache"] == "MISS"


def test_status_history(client, db) -> None:
    _seed_order(db)
    token = _token(client)
    headers = {"Authorization": f"Bearer {token}"}

    changed = client.post(
        "/api/v1/orders/CO-TEST-0001/status",
        json={"status": "confirmed", "comment": "проверено"},
        headers=headers,
    )
    assert changed.status_code == 200
    history = changed.json()["status_history"]
    assert len(history) == 1
    assert history[0]["from_status"] == "new"
    assert history[0]["to_status"] == "confirmed"
    assert history[0]["actor"] == "admin"

    invalid = client.post(
        "/api/v1/orders/CO-TEST-0001/status",
        json={"status": "new"},
        headers=headers,
    )
    assert invalid.status_code == 409


def test_admin_user_management(client) -> None:
    admin = _token(client)
    admin_headers = {"Authorization": f"Bearer {admin}"}
    username = f"qa_{uuid4().hex[:8]}"
    created = client.post(
        "/api/v1/auth/users",
        json={"username": username, "password": "secret123", "roles": ["viewer"]},
        headers=admin_headers,
    )
    assert created.status_code == 201
    user_id = created.json()["id"]
    assert created.json()["roles"] == ["viewer"]

    analyst = _token(client, "analyst", "test-analyst-password")
    forbidden = client.post(
        "/api/v1/auth/users",
        json={"username": f"x_{uuid4().hex[:8]}", "password": "secret123", "roles": ["viewer"]},
        headers={"Authorization": f"Bearer {analyst}"},
    )
    assert forbidden.status_code == 403

    updated = client.patch(
        f"/api/v1/auth/users/{user_id}",
        json={"roles": ["analyst"], "password": "secret456"},
        headers=admin_headers,
    )
    assert updated.status_code == 200
    assert updated.json()["roles"] == ["analyst"]
    assert _token(client, username, "secret456")

    me = client.get("/api/v1/auth/me", headers=admin_headers).json()
    self_deactivate = client.patch(
        f"/api/v1/auth/users/{me['id']}",
        json={"is_active": False},
        headers=admin_headers,
    )
    assert self_deactivate.status_code == 409
