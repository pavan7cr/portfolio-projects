"""Real Stripe test-mode integration point.
If STRIPE_TEST_SECRET_KEY is set (sk_test_...), this creates a real
test-mode PaymentIntent via Stripe's API. Without a key it returns the
same stub behaviour as app.py, so nothing charges real money.
Set the key in the environment, never in code or in the repo.
"""
import os, requests
def create_payment_intent(amount_cents, currency="usd"):
    key = os.environ.get("STRIPE_TEST_SECRET_KEY")
    if not key:
        return {"mode": "test-stub", "amount_cents": amount_cents, "note": "No STRIPE_TEST_SECRET_KEY set - no Stripe call made"}
    r = requests.post("https://api.stripe.com/v1/payment_intents",
        auth=(key, ""), data={"amount": amount_cents, "currency": currency, "payment_method_types[]": "card"}, timeout=20)
    return {"mode": "stripe-test", "status": r.status_code, "body": r.json()}
