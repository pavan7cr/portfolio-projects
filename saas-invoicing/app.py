"""Multi-tenant SaaS invoicing MVP - stdlib only, so it runs without pip installs.
Run: python3 app.py  (then POST to http://localhost:8001 - see README)
Tenant isolation rule: EVERY query filters by tenant_id, and every
request must carry X-Tenant-Id + X-User-Id belonging to that tenant.
There is no cross-tenant read path in this code - that is the point.
"""
import hashlib, json, sqlite3, uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

DB = "saas.db"

def db():
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row; return c

def init():
    c = db()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS tenants(id TEXT PRIMARY KEY, name TEXT);
    CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, tenant_id TEXT, email TEXT, role TEXT, pw_hash TEXT);
    CREATE TABLE IF NOT EXISTS clients(id TEXT PRIMARY KEY, tenant_id TEXT, name TEXT, email TEXT);
    CREATE TABLE IF NOT EXISTS invoices(id TEXT PRIMARY KEY, tenant_id TEXT, client_id TEXT, status TEXT, total_cents INTEGER);
    CREATE TABLE IF NOT EXISTS invoice_items(id TEXT PRIMARY KEY, invoice_id TEXT, description TEXT, amount_cents INTEGER);
    """)
    c.commit(); c.close()

def hash_pw(pw): return hashlib.sha256(pw.encode()).hexdigest()

def check_tenant(headers):
    """Return (tenant_id, user_id) or None. User must belong to the tenant."""
    tid = headers.get("X-Tenant-Id"); uid = headers.get("X-User-Id")
    if not tid or not uid: return None
    c = db(); row = c.execute("SELECT * FROM users WHERE id=? AND tenant_id=?", (uid, tid)).fetchone(); c.close()
    return (tid, uid) if row else None

class H(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}") if n else {}
    def do_POST(self):
        p = urlparse(self.path).path
        if p == "/tenants":
            d = self._body(); tid = str(uuid.uuid4())
            c = db(); c.execute("INSERT INTO tenants VALUES (?,?)", (tid, d["name"])); c.commit(); c.close()
            return self._send(201, {"tenant_id": tid})
        d = self._body()
        if p == "/users" and self.headers.get("X-Tenant-Id"):
            # Bootstrap: first user of a tenant may be created with just the tenant id
            c0 = db(); n0 = c0.execute("SELECT COUNT(*) FROM users WHERE tenant_id=?", (self.headers["X-Tenant-Id"],)).fetchone()[0]; c0.close()
            if n0 == 0:
                uid = str(uuid.uuid4()); c = db()
                c.execute("INSERT INTO users VALUES (?,?,?,?,?)", (uid, self.headers["X-Tenant-Id"], d["email"], d.get("role", "owner"), hash_pw(d["password"])))
                c.commit(); c.close(); return self._send(201, {"user_id": uid})
        auth = check_tenant(self.headers)
        if not auth: return self._send(401, {"error": "missing or invalid tenant/user headers"})
        tid, _ = auth; c = db()
        if p == "/users":
            uid = str(uuid.uuid4())
            c.execute("INSERT INTO users VALUES (?,?,?,?,?)", (uid, tid, d["email"], d.get("role", "staff"), hash_pw(d["password"])))
            c.commit(); c.close(); return self._send(201, {"user_id": uid})
        if p == "/clients":
            cid = str(uuid.uuid4())
            c.execute("INSERT INTO clients VALUES (?,?,?,?)", (cid, tid, d["name"], d["email"]))
            c.commit(); c.close(); return self._send(201, {"client_id": cid})
        if p == "/invoices":
            # client must belong to this tenant - enforced, not assumed
            row = c.execute("SELECT id FROM clients WHERE id=? AND tenant_id=?", (d["client_id"], tid)).fetchone()
            if not row: c.close(); return self._send(403, {"error": "client does not belong to this tenant"})
            iid = str(uuid.uuid4()); total = sum(i["amount_cents"] for i in d["items"])
            c.execute("INSERT INTO invoices VALUES (?,?,?,?,?)", (iid, tid, d["client_id"], "unpaid", total))
            for i in d["items"]:
                c.execute("INSERT INTO invoice_items VALUES (?,?,?,?)", (str(uuid.uuid4()), iid, i["description"], i["amount_cents"]))
            c.commit(); c.close(); return self._send(201, {"invoice_id": iid, "total_cents": total})
        if p == "/invoices/pay":
            # Stripe TEST-MODE STUB: records a payment, does not call Stripe.
            row = c.execute("SELECT * FROM invoices WHERE id=? AND tenant_id=?", (d["invoice_id"], tid)).fetchone()
            if not row: c.close(); return self._send(404, {"error": "invoice not found in this tenant"})
            c.execute("UPDATE invoices SET status='paid' WHERE id=?", (d["invoice_id"],)); c.commit(); c.close()
            return self._send(200, {"invoice_id": d["invoice_id"], "status": "paid", "stripe_mode": "test-stub"})
        return self._send(404, {"error": "unknown route"})
    def do_GET(self):
        p = urlparse(self.path).path
        if p == "/":
            body = open("frontend.html", "rb").read()
            self.send_response(200); self.send_header("Content-Type", "text/html"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body); return
        auth = check_tenant(self.headers)
        if not auth: return self._send(401, {"error": "missing or invalid tenant/user headers"})
        tid, _ = auth; c = db()
        if p == "/dashboard":
            rev = c.execute("SELECT COALESCE(SUM(total_cents),0) FROM invoices WHERE tenant_id=? AND status='paid'", (tid,)).fetchone()[0]
            overdue = c.execute("SELECT COALESCE(SUM(total_cents),0) FROM invoices WHERE tenant_id=? AND status='unpaid'", (tid,)).fetchone()[0]
            n = c.execute("SELECT COUNT(*) FROM invoices WHERE tenant_id=?", (tid,)).fetchone()[0]
            c.close(); return self._send(200, {"tenant_id": tid, "paid_cents": rev, "unpaid_cents": overdue, "invoice_count": n})
        if p == "/invoices":
            rows = c.execute("SELECT * FROM invoices WHERE tenant_id=?", (tid,)).fetchall(); c.close()
            return self._send(200, [dict(r) for r in rows])
        return self._send(404, {"error": "unknown route"})
    def log_message(self, *a): pass

if __name__ == "__main__":
    init(); print("SaaS invoicing MVP on http://localhost:8001")
    HTTPServer(("localhost", 8001), H).serve_forever()
