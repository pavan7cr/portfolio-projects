"""Deterministic synthetic sales generator for the scheduled/batch pipeline.

Default output is 50,000 rows in:
  46,000 unique valid orders
  + 2,500 duplicate order_id rows (copies of earlier orders, amount present)
  + 1,500 rows with a unique order_id but an empty amount (null rows)
so the expected clean count is exactly 46,000 rows, before any
pipeline code runs. Dates span 2026-09-01..2026-09-30, amounts $10-$500.
Usage: python3 generate_sales.py [--rows 50000] [--out sales_large.csv]
"""
import argparse
import csv
import random
import sys

CUSTOMERS = ["Acme", "Beta", "Gamma", "Delta", "Echo"]


def generate(path, total=50000, seed=42):
    rng = random.Random(seed)
    nulls = int(total * 0.03)
    dups = int(total * 0.05)
    valid = total - nulls - dups
    rows = []
    for i in range(valid):
        day = rng.randint(1, 30)
        rows.append({"order_id": f"S{i+1:06d}", "order_date": f"2026-09-{day:02d}",
                     "amount": f"{rng.uniform(10, 500):.2f}",
                     "customer": CUSTOMERS[i % len(CUSTOMERS)]})
    for j in range(dups):
        src = rows[rng.randrange(valid)]
        rows.append({"order_id": src["order_id"], "order_date": src["order_date"],
                     "amount": src["amount"], "customer": src["customer"]})
    for k in range(nulls):
        day = rng.randint(1, 30)
        rows.append({"order_id": f"N{k+1:06d}", "order_date": f"2026-09-{day:02d}",
                     "amount": "", "customer": CUSTOMERS[k % len(CUSTOMERS)]})
    rng.shuffle(rows)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["order_id", "order_date", "amount", "customer"])
        w.writeheader()
        w.writerows(rows)
    return {"rows_in": total, "valid": valid, "duplicates": dups, "nulls": nulls}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=50000)
    ap.add_argument("--out", default="sales_large.csv")
    a = ap.parse_args()
    print(generate(a.out, a.rows))
    sys.exit(0)
