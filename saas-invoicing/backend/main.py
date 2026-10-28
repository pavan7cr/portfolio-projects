"""SaaS Invoicing backend (FastAPI + SQLAlchemy).

Auth (2026-10-28 rewrite, replacing the old token=user-id scheme):
- Passwords: bcrypt with a per-password salt (never SHA-256, never plaintext).
- Tokens: real JWT access tokens (30 min) + refresh tokens (7 days), signed
  with JWT_SECRET. Clients send ``Authorization: Bearer <access_token>``.
  An ``X-Token`` header containing the same JWT is also accepted so the
  React demo can send one header set; a bare user id is NOT a valid token
  and is rejected with 401.
- Roles: ``owner`` may create users and mark invoices paid. ``staff`` may
  create/list clients and invoices and view the dashboard, but may NOT
  create users or pay invoices (403).
- Tenant isolation: every client/invoice query is scoped by the caller's
  tenant_id, and cross-tenant access to a specific record returns 403.

Database: DATABASE_URL if set (PostgreSQL via psycopg2, e.g. a free
Neon/Supabase database, with ``postgres://`` normalised to
``postgresql://``), otherwise SQLite (``./saas_full.db``) for local
development and tests. No live Postgres database is required to run tests.

Stripe: NOT integrated here. ``pay`` only flips an invoice to ``paid``
locally and is idempotent (paying twice leaves one paid invoice and
does not change totals). See stripe_test.py for the separate test-mode
experiment; no Stripe key is used and no Stripe call is made.
Run: ~/workspace/projects/venv/bin/uvicorn backend.main:app --port 8000
from saas-invoicing/
"""
import os
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import FastAPI, Header, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, String, Integer, ForeignKey
from sqlalchemy.orm import sessionmaker, declarative_base, Session

JWT_SECRET = os.environ.get("JWT_SECRET", "dev-only-change-me")
JWT_ALGORITHM = "HS256"
ACCESS_MINUTES = 30
REFRESH_DAYS = 7

Base = declarative_base()


class Tenant(Base):
    __tablename__ = "tenants"
    id = Column(String, primary_key=True)
    name = Column(String)


class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True)
    tenant_id = Column(String, ForeignKey("tenants.id"))
    email = Column(String)
    role = Column(String)
    pw_hash = Column(String)


class Client(Base):
    __tablename__ = "clients"
    id = Column(String, primary_key=True)
    tenant_id = Column(String, ForeignKey("tenants.id"))
    name = Column(String)
    email = Column(String)


class Invoice(Base):
    __tablename__ = "invoices"
    id = Column(String, primary_key=True)
    tenant_id = Column(String, ForeignKey("tenants.id"))
    client_id = Column(String)
    status = Column(String, default="unpaid")
    total_cents = Column(Integer)


class Item(Base):
    __tablename__ = "items"
    id = Column(String, primary_key=True)
    invoice_id = Column(String)
    description = Column(String)
    amount_cents = Column(Integer)


def _database_url():
    url = os.environ.get("DATABASE_URL") or os.environ.get("SAAS_DATABASE_URL")
    if url:
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://"):]
        return url, {}
    return "sqlite:///./saas_full.db", {"check_same_thread": False}


_DB_URL, _CONNECT_ARGS = _database_url()
eng = create_engine(_DB_URL, connect_args=_CONNECT_ARGS)
SessionLocal = sessionmaker(bind=eng)
Base.metadata.create_all(eng)

app = FastAPI(title="SaaS Invoicing")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def get_db():
    d = SessionLocal()
    try:
        yield d
    finally:
        d.close()


def _hash(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _check(password: str, pw_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), pw_hash.encode())
    except Exception:
        return False


def _token(user: User, kind: str, delta: timedelta) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"sub": user.id, "tenant_id": user.tenant_id, "role": user.role,
         "type": kind, "iat": now, "exp": now + delta},
        JWT_SECRET, algorithm=JWT_ALGORITHM)


def _decode(token: str):
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except Exception:
        raise HTTPException(401, "invalid token")


def _optional_user(authorization: str = Header(None), x_token: str = Header(None, alias="X-Token"),
                   db: Session = Depends(get_db)):
    raw = None
    if authorization and authorization.startswith("Bearer "):
        raw = authorization[7:]
    elif x_token:
        raw = x_token
    if not raw:
        return None
    payload = _decode(raw)
    if payload.get("type") != "access":
        raise HTTPException(401, "invalid token type")
    user = db.query(User).filter(User.id == payload["sub"]).first()
    if not user or user.tenant_id != payload.get("tenant_id"):
        raise HTTPException(401, "invalid token")
    return user


def me(user: User = Depends(_optional_user)):
    if not user:
        raise HTTPException(401, "invalid token")
    return user


def require_owner(user: User = Depends(me)):
    if user.role != "owner":
        raise HTTPException(403, "owner role required")
    return user


class TenantIn(BaseModel):
    name: str


class UserIn(BaseModel):
    tenant_id: str
    email: str
    password: str
    role: str = "staff"


class LoginIn(BaseModel):
    email: str
    password: str


class RefreshIn(BaseModel):
    refresh_token: str


class ClientIn(BaseModel):
    name: str
    email: str


class ItemIn(BaseModel):
    description: str
    amount_cents: int


class InvoiceIn(BaseModel):
    client_id: str
    items: list[ItemIn]


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/tenants")
def create_tenant(d: TenantIn, db: Session = Depends(get_db)):
    t = Tenant(id=str(uuid.uuid4()), name=d.name)
    db.add(t)
    db.commit()
    return {"tenant_id": t.id}


@app.post("/users")
def register(d: UserIn, caller: User = Depends(_optional_user), db: Session = Depends(get_db)):
    tenant = db.query(Tenant).filter(Tenant.id == d.tenant_id).first()
    if not tenant:
        raise HTTPException(404, "tenant not found")
    existing = db.query(User).filter(User.tenant_id == d.tenant_id).count()
    if existing:
        # Only an owner of the same tenant may add further users.
        if not caller or caller.tenant_id != d.tenant_id or caller.role != "owner":
            raise HTTPException(403, "owner role required")
        role = d.role if d.role in ("owner", "staff") else "staff"
    else:
        # Bootstrap: the first user of a tenant is always its owner.
        role = "owner"
    if db.query(User).filter(User.email == d.email).first():
        raise HTTPException(400, "email already registered")
    u = User(id=str(uuid.uuid4()), tenant_id=d.tenant_id, email=d.email,
             role=role, pw_hash=_hash(d.password))
    db.add(u)
    db.commit()
    return {"user_id": u.id,
            "access_token": _token(u, "access", timedelta(minutes=ACCESS_MINUTES)),
            "refresh_token": _token(u, "refresh", timedelta(days=REFRESH_DAYS)),
            "token_type": "bearer", "role": u.role, "tenant_id": u.tenant_id}


@app.post("/login")
def login(d: LoginIn, db: Session = Depends(get_db)):
    u = db.query(User).filter(User.email == d.email).first()
    if not u or not _check(d.password, u.pw_hash):
        raise HTTPException(401, "bad login")
    return {"access_token": _token(u, "access", timedelta(minutes=ACCESS_MINUTES)),
            "refresh_token": _token(u, "refresh", timedelta(days=REFRESH_DAYS)),
            "token_type": "bearer", "tenant_id": u.tenant_id, "role": u.role}


@app.post("/refresh")
def refresh(d: RefreshIn, db: Session = Depends(get_db)):
    payload = _decode(d.refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(401, "invalid token type")
    u = db.query(User).filter(User.id == payload["sub"]).first()
    if not u:
        raise HTTPException(401, "invalid token")
    return {"access_token": _token(u, "access", timedelta(minutes=ACCESS_MINUTES)),
            "token_type": "bearer", "tenant_id": u.tenant_id, "role": u.role}


@app.post("/clients")
def create_client(d: ClientIn, u: User = Depends(me), db: Session = Depends(get_db)):
    c = Client(id=str(uuid.uuid4()), tenant_id=u.tenant_id, name=d.name, email=d.email)
    db.add(c)
    db.commit()
    return {"client_id": c.id}


@app.get("/clients")
def list_clients(u: User = Depends(me), db: Session = Depends(get_db)):
    return [{"id": c.id, "name": c.name, "email": c.email}
            for c in db.query(Client).filter(Client.tenant_id == u.tenant_id)]


@app.post("/invoices")
def create_invoice(d: InvoiceIn, u: User = Depends(me), db: Session = Depends(get_db)):
    if not d.items:
        raise HTTPException(400, "invoice needs at least one item")
    if any(i.amount_cents < 0 for i in d.items):
        raise HTTPException(400, "item amounts must not be negative")
    cl = db.query(Client).filter(Client.id == d.client_id, Client.tenant_id == u.tenant_id).first()
    if not cl:
        raise HTTPException(403, "client does not belong to this tenant")
    inv = Invoice(id=str(uuid.uuid4()), tenant_id=u.tenant_id, client_id=d.client_id,
                  total_cents=sum(i.amount_cents for i in d.items))
    db.add(inv)
    for i in d.items:
        db.add(Item(id=str(uuid.uuid4()), invoice_id=inv.id,
                    description=i.description, amount_cents=i.amount_cents))
    db.commit()
    return {"invoice_id": inv.id, "total_cents": inv.total_cents}


@app.get("/invoices")
def list_invoices(u: User = Depends(me), db: Session = Depends(get_db)):
    return [{"id": i.id, "client_id": i.client_id, "status": i.status, "total_cents": i.total_cents}
            for i in db.query(Invoice).filter(Invoice.tenant_id == u.tenant_id)]


@app.post("/invoices/{iid}/pay")
def pay(iid: str, u: User = Depends(require_owner), db: Session = Depends(get_db)):
    inv_any = db.query(Invoice).filter(Invoice.id == iid).first()
    if not inv_any:
        raise HTTPException(404, "invoice not found")
    if inv_any.tenant_id != u.tenant_id:
        raise HTTPException(403, "invoice does not belong to this tenant")
    if inv_any.status == "paid":
        # Idempotent: paying twice returns the same paid invoice; totals
        # are sums over invoices, so they cannot double-count.
        return {"invoice_id": iid, "status": "paid", "already_paid": True}
    inv_any.status = "paid"
    db.commit()
    return {"invoice_id": iid, "status": "paid", "already_paid": False}


@app.get("/dashboard")
def dashboard(u: User = Depends(me), db: Session = Depends(get_db)):
    invs = db.query(Invoice).filter(Invoice.tenant_id == u.tenant_id).all()
    return {"paid_cents": sum(i.total_cents for i in invs if i.status == "paid"),
            "unpaid_cents": sum(i.total_cents for i in invs if i.status == "unpaid"),
            "invoice_count": len(invs)}
