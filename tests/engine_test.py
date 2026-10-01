"""Engine tests: python tests/engine_test.py   (needs numpy, pandas, openpyxl)"""
import io
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from chaos.engine import make_chaos, summarise, undo
from chaos.profile import profile_table
from chaos.reader import ReadError, read_table

failures = []


def check(condition, message):
    print(("ok   " if condition else "FAIL ") + message)
    if not condition:
        failures.append(message)


def sample(rows=300, seed=1):
    r = np.random.default_rng(seed)
    cities = ["Leeds", "York", "Bristol", "Cardiff", "Glasgow", "Norwich"]
    dates = pd.to_datetime("2023-01-01") + pd.to_timedelta(r.integers(0, 700, rows), unit="D")
    return pd.DataFrame({
        "customer_id": range(1000, 1000 + rows),
        "full_name": [f"{r.choice(['Ann', 'Ben', 'Cara', 'Dev', 'Elif'])} {r.choice(['Smith', 'Jones', 'Patel', 'Okafor'])}" for _ in range(rows)],
        "email": [f"user{i}@example.com" for i in range(rows)],
        "city": r.choice(cities, rows),
        "signup_date": dates.strftime("%Y-%m-%d"),
        "order_total": np.round(r.uniform(5, 900, rows), 2),
        "items": r.integers(1, 12, rows),
        "is_member": r.choice(["Yes", "No"], rows),
        "notes": [f"order note {i} about delivery and packaging" for i in range(rows)],
    })


def same(a, b):
    return list(a.columns) == list(b.columns) and a.astype(object).values.tolist() == b.astype(object).values.tolist()


def roundtrip(name, raw, seed=42, intensity="realistic", **kw):
    table, info = read_table(name, raw, **kw)
    profile = profile_table(table)
    messy, key = make_chaos(table, profile, seed, intensity)
    back = undo(messy, key, list(table.columns))
    return table, info, profile, messy, key, back


# --- 1. a clean CSV: types are found, damage is plausible and exactly reversible ----------------------
clean = sample()
table, info, profile, messy, key, back = roundtrip("sales.csv", clean.to_csv(index=False).encode())
roles = {p["name"]: p["role"] for p in profile}
check(roles["customer_id"] == "id" and roles["order_total"] == "decimal" and roles["items"] == "integer", "numeric roles found")
check(roles["signup_date"] == "date" and roles["email"] == "email" and roles["is_member"] == "bool", "date, email, bool found")
check(roles["city"] == "category" and roles["notes"] == "text", "category and text found")
check(same(back, table), "answer key reverses every change exactly")
share = (key["row"] > 0).sum() / (len(messy) * len(messy.columns))
check(0.01 < share < 0.30, f"damage share is realistic ({share:.1%} of cells)")
check(len(summarise(key)) >= 8, f"many fault types used ({len(summarise(key))})")
messy2, key2 = make_chaos(table, profile, 42)
check(same(messy, messy2) and same(key, key2), "same seed gives identical output")
messy3, _ = make_chaos(table, profile, 43)
check(not same(messy, messy3), "different seed gives different output")
check(all(table[c].tolist() == clean[c].astype(str).tolist() for c in ("customer_id", "order_total")), "reader keeps text exactly")

# --- 2. intensity scales the damage --------------------------------------------------------------------
sizes = {i: len(make_chaos(table, profile, 7, i)[1]) for i in ("light", "realistic", "heavy")}
check(sizes["light"] < sizes["realistic"] < sizes["heavy"], f"intensity ordering {sizes}")
for level in ("light", "heavy"):
    t, _, p, m, k, b = roundtrip("sales.csv", clean.to_csv(index=False).encode(), intensity=level)
    check(same(b, t), f"{level}: reversible")

# --- 3. awkward text files ----------------------------------------------------------------------------
semi = clean.assign(city=clean.city.replace({"York": "Zürich"})).to_csv(index=False, sep=";").encode("cp1252")
t, info, *_ = roundtrip("data.txt", semi)
check(info["delimiter"] == ";" and info["encoding"] == "cp1252" and "Zürich" in set(t.city), "semicolon + cp1252 detected")
t, info, *_ = roundtrip("data.tsv", clean.to_csv(index=False, sep="\t").encode("utf-8-sig"))
check(info["delimiter"] == "\t" and list(t.columns)[0] == "customer_id", "tab + BOM detected, BOM removed")
zeros = pd.DataFrame({"zip": [f"0{i:04d}" for i in range(100)], "n": range(100)})
t, _, p, *_ = roundtrip("z.csv", zeros.to_csv(index=False).encode())
check(t.zip[5] == "00005" and {c["name"]: c["role"] for c in p}["zip"] == "id", "leading zeros kept, code not treated as number")

# --- 4. Excel with two sheets, and JSON ---------------------------------------------------------------
buffer = io.BytesIO()
with pd.ExcelWriter(buffer) as writer:
    clean.assign(signup_date=pd.to_datetime(clean.signup_date)).to_excel(writer, sheet_name="Orders", index=False)
    pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]}).to_excel(writer, sheet_name="Small", index=False)
t, info, p, m, k, b = roundtrip("book.xlsx", buffer.getvalue())
check(info["sheets"] == ["Orders", "Small"] and info["sheet"] == "Orders", "first sheet chosen, both listed")
check({c["name"]: c["role"] for c in p}["signup_date"] == "date" and same(b, t), "Excel dates profiled, reversible")
t, info, *_ = roundtrip("book.xlsx", buffer.getvalue(), sheet="Small")
check(info["sheet"] == "Small" and list(t.columns) == ["a", "b"], "sheet selection works")
records = clean.head(50).to_dict("records")
t, info, p, m, k, b = roundtrip("d.json", json.dumps(records, default=str).encode())
check(info["format"] == "json" and len(t) == 50 and same(b, t), "JSON records read and reversible")

# --- 5. a file that is already messy, a tiny file, a wide file ----------------------------------------
dirty = clean.copy()
dirty.loc[::7, "city"] = "N/A"
t, _, p, m, k, b = roundtrip("dirty.csv", dirty.to_csv(index=False).encode())
check({c["name"]: c["role"] for c in p}["city"] == "category" and {c["name"]: c for c in p}["city"]["already_messy"], "existing N/A markers flagged, column still category")
check(same(b, t), "already-messy file reversible")
tiny = clean.head(6)
t, _, p, m, k, b = roundtrip("tiny.csv", tiny.to_csv(index=False).encode())
check(same(b, t) and len(k) > 0, "6-row file survives")
wide = pd.DataFrame(np.random.default_rng(3).integers(0, 100, (200, 60)), columns=[f"v{i}" for i in range(60)])
t, _, p, m, k, b = roundtrip("wide.csv", wide.to_csv(index=False).encode())
check(same(b, t), "60-column file reversible")

# --- 6. limits and errors say something useful ---------------------------------------------------------
for label, call in {
    "too many rows": lambda: read_table("x.csv", clean.to_csv(index=False).encode(), max_rows=10),
    "too many bytes": lambda: read_table("x.csv", clean.to_csv(index=False).encode(), max_bytes=100),
    "old xls": lambda: read_table("x.xls", b"abc"),
    "empty file": lambda: read_table("x.csv", b""),
}.items():
    try:
        call()
        check(False, f"{label} should raise ReadError")
    except ReadError as error:
        check("standalone" in str(error) or "xls" in str(error) or "empty" in str(error).lower() or "No data" in str(error), f"{label}: '{str(error)[:60]}'")

print("\nFAILED: %d" % len(failures) if failures else "\nall tests passed")
sys.exit(1 if failures else 0)
