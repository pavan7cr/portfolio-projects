"""SaaS tests. Run from saas-invoicing/: venv/bin/pytest backend/test_main.py -v
Uses an isolated SQLite file (not saas_full.db) set before importing main.
"""
import os
import sys
import tempfile

os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tempfile.mkdtemp(), "saas_test.db")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi.testclient import TestClient  # noqa: E402
from main import app, SessionLocal, User  # noqa: E402

client = TestClient(app)


def auth(token):
    return {"Authorization": f"Bearer {token}", "X-Token": token}


def setup_tenant(email_prefix):
    t = client.post("/tenants", json={"name": "Tenant " + email_prefix}).json()["tenant_id"]
    r = client.post("/users", json={"tenant_id": t, "email": f"{email_prefix}@test.com",
                                    "password": "pw123456", "role": "staff"})
    assert r.status_code == 200, r.text
    # Bootstrap user is always owner, even if "staff" was requested.
    assert r.json()["role"] == "owner"
    return t, r.json()["access_token"], r.json()["refresh_token"]


def test_bad_token_and_bare_user_id_rejected():
    r = client.get("/clients", headers=auth("not-a-jwt"))
    assert r.status_code == 401
    t, token, _ = setup_tenant("badtoken")
    user = SessionLocal().query(User).filter(User.tenant_id == t).first()
    r = client.get("/clients", headers=auth(user.id))  # old scheme: user id as token
    assert r.status_code == 401


def test_password_is_bcrypt_not_plaintext():
    t, _, _ = setup_tenant("bcrypt")
    user = SessionLocal().query(User).filter(User.tenant_id == t).first()
    assert user.pw_hash != "pw123456"
    assert user.pw_hash.startswith("$2b$")


def test_login_and_refresh():
    t, _, refresh = setup_tenant("login")
    r = client.post("/login", json={"email": "login@test.com", "password": "pw123456"})
    assert r.status_code == 200 and r.json()["token_type"] == "bearer"
    assert client.post("/login", json={"email": "login@test.com", "password": "wrong"}).status_code == 401
    r = client.post("/refresh", json={"refresh_token": refresh})
    assert r.status_code == 200
    assert client.get("/clients", headers=auth(r.json()["access_token"])).status_code == 200


def test_role_enforcement():
    t, owner_token, _ = setup_tenant("roles")
    r = client.post("/users", json={"tenant_id": t, "email": "staff@test.com",
                                    "password": "pw123456", "role": "staff"},
                    headers=auth(owner_token))
    assert r.status_code == 200, r.text
    staff_token = r.json()["access_token"]
    # Staff may create a client but may NOT create users or pay invoices.
    c = client.post("/clients", json={"name": "C", "email": "c@test.com"}, headers=auth(staff_token))
    assert c.status_code == 200
    r = client.post("/users", json={"tenant_id": t, "email": "x@test.com",
                                    "password": "pw123456", "role": "staff"},
                    headers=auth(staff_token))
    assert r.status_code == 403
    inv = client.post("/invoices", json={"client_id": c.json()["client_id"],
                                         "items": [{"description": "Work", "amount_cents": 50000}]},
                      headers=auth(staff_token)).json()
    r = client.post(f"/invoices/{inv['invoice_id']}/pay", headers=auth(staff_token))
    assert r.status_code == 403
    r = client.post(f"/invoices/{inv['invoice_id']}/pay", headers=auth(owner_token))
    assert r.status_code == 200 and r.json()["status"] == "paid"


def test_tenant_isolation_and_totals_and_idempotent_pay():
    t1, tok1, _ = setup_tenant("tenant1")
    t2, tok2, _ = setup_tenant("tenant2")
    c1 = client.post("/clients", json={"name": "A", "email": "a@test.com"}, headers=auth(tok1)).json()
    # Tenant 2 cannot invoice tenant 1's client, cannot list tenant 1's clients.
    r = client.post("/invoices", json={"client_id": c1["client_id"],
                                       "items": [{"description": "X", "amount_cents": 100}]},
                    headers=auth(tok2))
    assert r.status_code == 403
    assert client.get("/clients", headers=auth(tok2)).json() == []
    inv = client.post("/invoices", json={"client_id": c1["client_id"],
                                         "items": [{"description": "Design", "amount_cents": 30000},
                                                 {"description": "Hosting", "amount_cents": 20000}]},
                      headers=auth(tok1)).json()
    assert inv["total_cents"] == 50000
    # Cross-tenant pay is 403, not a silent success.
    assert client.post(f"/invoices/{inv['invoice_id']}/pay", headers=auth(tok2)).status_code == 403
    assert client.post(f"/invoices/{inv['invoice_id']}/pay", headers=auth(tok1)).status_code == 200
    dash1 = client.get("/dashboard", headers=auth(tok1)).json()
    assert dash1 == {"paid_cents": 50000, "unpaid_cents": 0, "invoice_count": 1}
    # Paying twice does not double-count.
    r = client.post(f"/invoices/{inv['invoice_id']}/pay", headers=auth(tok1))
    assert r.status_code == 200 and r.json()["already_paid"] is True
    assert client.get("/dashboard", headers=auth(tok1)).json() == dash1
    assert client.get("/dashboard", headers=auth(tok2)).json()["invoice_count"] == 0
