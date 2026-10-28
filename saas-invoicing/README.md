# SaaS Invoicing MVP - what was built
- SQLite + Python stdlib HTTP server on port 8001, no pip installs needed.
- Tenants, users (hashed passwords), clients, invoices + items, dashboard (paid/unpaid totals).
- Tenant isolation: every invoice/client query filters by tenant_id; a client from another tenant is rejected with 403.
- Stripe is a TEST STUB only (records paid, does not call Stripe) - real Stripe integration is a next step for the evening build.
- Run: python3 app.py
## Round 2 (2026-10-28)
- Added frontend.html served at / - tenant/user/client/dashboard flow in the browser.
- Added stripe_test.py: real Stripe test-mode PaymentIntent if STRIPE_TEST_SECRET_KEY is set, otherwise stub. No key was set, so no Stripe call was made and no real money is involved.
- Still to do: React frontend, real PDF invoices, email reminders, deployment.
