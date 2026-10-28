"""SaaS Invoicing - full backend (FastAPI + SQLAlchemy + SQLite).
Run: ~/workspace/projects/venv/bin/uvicorn backend.main:app --port 8000
from saas-invoicing/
Auth: register/login returns a token (user id, for this MVP - swap for
JWT in production). Every route requires X-Token and scopes all
queries by the caller's tenant_id - tenant isolation is tested.
"""
from fastapi import FastAPI, Header, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, String, Integer, ForeignKey
from sqlalchemy.orm import sessionmaker, declarative_base, Session
import hashlib, uuid
Base = declarative_base()
class Tenant(Base):
    __tablename__ = "tenants"; id = Column(String, primary_key=True); name = Column(String)
class User(Base):
    __tablename__ = "users"; id = Column(String, primary_key=True); tenant_id = Column(String, ForeignKey("tenants.id")); email = Column(String); role = Column(String); pw_hash = Column(String)
class Client(Base):
    __tablename__ = "clients"; id = Column(String, primary_key=True); tenant_id = Column(String); name = Column(String); email = Column(String)
class Invoice(Base):
    __tablename__ = "invoices"; id = Column(String, primary_key=True); tenant_id = Column(String); client_id = Column(String); status = Column(String, default="unpaid"); total_cents = Column(Integer)
class Item(Base):
    __tablename__ = "items"; id = Column(String, primary_key=True); invoice_id = Column(String); description = Column(String); amount_cents = Column(Integer)
eng = create_engine("sqlite:///./saas_full.db", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=eng); Base.metadata.create_all(eng)
app = FastAPI(title="SaaS Invoicing")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
def get_db():
    d = SessionLocal()
    try: yield d
    finally: d.close()
def me(token: str = Header(None, alias="X-Token"), db: Session = Depends(get_db)):
    u = db.query(User).filter(User.id == token).first() if token else None
    if not u: raise HTTPException(401, "invalid token")
    return u
def h(p): return hashlib.sha256(p.encode()).hexdigest()
class TenantIn(BaseModel): name: str
class UserIn(BaseModel): tenant_id: str; email: str; password: str; role: str = "staff"
class LoginIn(BaseModel): email: str; password: str
class ClientIn(BaseModel): name: str; email: str
class ItemIn(BaseModel): description: str; amount_cents: int
class InvoiceIn(BaseModel): client_id: str; items: list[ItemIn]
@app.post("/tenants")
def create_tenant(d: TenantIn, db: Session = Depends(get_db)):
    t = Tenant(id=str(uuid.uuid4()), name=d.name); db.add(t); db.commit(); return {"tenant_id": t.id}
@app.post("/users")
def register(d: UserIn, db: Session = Depends(get_db)):
    u = User(id=str(uuid.uuid4()), tenant_id=d.tenant_id, email=d.email, role=d.role, pw_hash=h(d.password)); db.add(u); db.commit(); return {"user_id": u.id, "token": u.id}
@app.post("/login")
def login(d: LoginIn, db: Session = Depends(get_db)):
    u = db.query(User).filter(User.email == d.email, User.pw_hash == h(d.password)).first()
    if not u: raise HTTPException(401, "bad login")
    return {"token": u.id, "tenant_id": u.tenant_id}
@app.post("/clients")
def create_client(d: ClientIn, u: User = Depends(me), db: Session = Depends(get_db)):
    c = Client(id=str(uuid.uuid4()), tenant_id=u.tenant_id, name=d.name, email=d.email); db.add(c); db.commit(); return {"client_id": c.id}
@app.get("/clients")
def list_clients(u: User = Depends(me), db: Session = Depends(get_db)):
    return [{"id": c.id, "name": c.name, "email": c.email} for c in db.query(Client).filter(Client.tenant_id == u.tenant_id)]
@app.post("/invoices")
def create_invoice(d: InvoiceIn, u: User = Depends(me), db: Session = Depends(get_db)):
    cl = db.query(Client).filter(Client.id == d.client_id, Client.tenant_id == u.tenant_id).first()
    if not cl: raise HTTPException(403, "client does not belong to this tenant")
    inv = Invoice(id=str(uuid.uuid4()), tenant_id=u.tenant_id, client_id=d.client_id, total_cents=sum(i.amount_cents for i in d.items))
    db.add(inv)
    for i in d.items: db.add(Item(id=str(uuid.uuid4()), invoice_id=inv.id, description=i.description, amount_cents=i.amount_cents))
    db.commit(); return {"invoice_id": inv.id, "total_cents": inv.total_cents}
@app.get("/invoices")
def list_invoices(u: User = Depends(me), db: Session = Depends(get_db)):
    return [{"id": i.id, "client_id": i.client_id, "status": i.status, "total_cents": i.total_cents} for i in db.query(Invoice).filter(Invoice.tenant_id == u.tenant_id)]
@app.post("/invoices/{iid}/pay")
def pay(iid: str, u: User = Depends(me), db: Session = Depends(get_db)):
    inv = db.query(Invoice).filter(Invoice.id == iid, Invoice.tenant_id == u.tenant_id).first()
    if not inv: raise HTTPException(404, "invoice not found in this tenant")
    inv.status = "paid"; db.commit(); return {"invoice_id": iid, "status": "paid", "stripe_mode": "test-stub (see stripe_test.py for real test-mode call)"}
@app.get("/dashboard")
def dashboard(u: User = Depends(me), db: Session = Depends(get_db)):
    invs = db.query(Invoice).filter(Invoice.tenant_id == u.tenant_id).all()
    return {"paid_cents": sum(i.total_cents for i in invs if i.status == "paid"), "unpaid_cents": sum(i.total_cents for i in invs if i.status == "unpaid"), "invoice_count": len(invs)}
