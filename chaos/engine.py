"""Chaos Engine: damage a table the way real data gets damaged, and keep a key of every change.

    messy, key = make_chaos(table, profile, seed, intensity="realistic")

`table` is all text (see reader.py), `profile` comes from profile.py. The same table, profile, seed and
intensity always give the same result. Every change is listed in the answer key, so the damage can be
undone exactly. Rates are per affected column; "intensity" scales every rate and the overall budget.
"""
import re
from datetime import datetime

import numpy as np
import pandas as pd

from .profile import BOOL_POSITIVE, DATE_FORMATS, detect_date_format, is_missing

KEY_COLUMNS = ["row", "column", "problem", "original", "messy", "note"]
MISSING_MARKERS = ["", "N/A", "null", "-", "?", "n/a", "NaN"]
BOOL_STYLES = [("Yes", "No"), ("Y", "N"), ("1", "0"), ("true", "false"), ("TRUE", "FALSE"), ("yes", "no")]
OUTPUT_DATES = ["%d/%m/%Y", "%m-%d-%Y", "%d %b %Y", "%Y%m%d", "%b %d, %Y", "%d.%m.%Y"]
OUTPUT_DATETIMES = ["%Y-%m-%dT%H:%M:%S", "%d/%m/%Y %H:%M", "%m/%d/%Y %I:%M %p"]
MONEY_WORDS = re.compile(r"price|amount|cost|revenue|salary|fee|total|spend|income|value|balance|wage", re.I)
INTENSITY = {"light": 0.5, "realistic": 1.0, "heavy": 1.8}
CELL_BUDGET = 0.14      # at "realistic", about this share of all cells is hit by the cell-level faults


def _decimals(text):
    return len(text.split(".")[1]) if "." in text else 0


def _number(text):
    text = text.strip()
    return int(text) if re.fullmatch(r"[+-]?\d+", text) else float(text)


def _format_like(value, decimals):
    return str(int(value)) if decimals == 0 else f"{value:.{decimals}f}"


def make_chaos(table, profile, seed, intensity="realistic"):
    scale = INTENSITY.get(intensity, 1.0)
    rng = np.random.default_rng([int(seed), 7919])
    columns = list(table.columns)
    n = len(table)
    roles = {p["name"]: p["role"] for p in profile}
    details = {p["name"]: p.get("detail", "") for p in profile}
    for c in columns:                                               # a role the person set by hand may lack detail
        if roles[c] == "date":
            fmt = details[c] if "%" in details[c] else detect_date_format([v for v in table[c] if not is_missing(v)])
            if fmt:
                details[c] = fmt
            else:
                roles[c] = "text"
    data = {c: table[c].astype(str).tolist() for c in columns}
    used, cells = set(), []                                         # cells: (source row, column, problem, original, messy, note)
    state = {"budget": max(2, int(round(CELL_BUDGET * scale * n * len(columns))))}

    def rate(low, high):
        return min(0.6, float(rng.uniform(low, high)) * scale)

    def eligible(*wanted):
        return [c for c in columns if roles[c] in wanted]

    def choose_columns(pool, low, high):
        if not pool:
            return []
        k = max(1, int(round(float(rng.integers(low, high + 1)) * min(scale, 1.5))))
        return [str(c) for c in rng.choice(pool, size=min(k, len(pool)), replace=False)]

    def choose_rows(column, share):
        free = [i for i in range(n) if (i, column) not in used and not is_missing(data[column][i])]
        count = min(max(1, int(round(share * n))), len(free), state["budget"])
        if count <= 0:
            return []
        return [int(i) for i in rng.choice(free, size=count, replace=False)]

    def hit(i, column, problem, new, note=""):
        if new == data[column][i]:
            return
        cells.append((i, column, problem, data[column][i], new, note))
        data[column][i] = new
        used.add((i, column))
        state["budget"] -= 1

    def missing_values():                       # 3-8% of cells in 2-4 non-ID columns
        pool = [c for c in columns if roles[c] not in ("id", "empty")]
        for c in choose_columns(pool, 2, 4):
            markers = [str(m) for m in rng.choice(MISSING_MARKERS, size=2, replace=False)]
            for i in choose_rows(c, rate(0.03, 0.08)):
                hit(i, c, "missing_value", str(rng.choice(markers)))

    def numbers_as_text():                      # 4-8% of cells in 1-2 numeric columns
        for c in choose_columns(eligible("integer", "decimal"), 1, 2):
            money = bool(MONEY_WORDS.search(c))
            for i in choose_rows(c, rate(0.04, 0.08)):
                text = data[c][i].strip()
                v = _number(text)
                options = [f"{text} "]
                if roles[c] == "integer" and abs(v) >= 1000:
                    options.append(f"{v:,}")
                if roles[c] == "decimal":
                    options += [text.replace(".", ","), f"{v:,.{_decimals(text)}f}"] if abs(v) >= 1000 else [text.replace(".", ",")]
                if money:
                    options += [f"£{text}", f"${text}"]
                hit(i, c, "number_stored_as_text", str(rng.choice(options)))

    def wrong_dates():                          # 20-40% of rows in 1-2 date columns, plus 1-2% invalid
        for c in choose_columns(eligible("date"), 1, 2):
            fmt = details[c]
            pool = OUTPUT_DATETIMES if "%H" in fmt else OUTPUT_DATES
            pool = [f for f in pool if f != fmt]
            for i in choose_rows(c, rate(0.01, 0.02)):
                stamp = datetime.strptime(data[c][i].strip(), fmt)
                hit(i, c, "invalid_date", str(rng.choice([f"31/02/{stamp.year}", "TBC", "00/00/0000", "unknown"])))
            for i in choose_rows(c, rate(0.20, 0.40)):
                try:
                    stamp = datetime.strptime(data[c][i].strip(), fmt)
                except ValueError:
                    continue
                hit(i, c, "date_format", stamp.strftime(str(rng.choice(pool))))

    def text_damage():                          # casing 5-10%, stray spaces 3-6%, typos 1-3% in 1-2 text columns
        for c in choose_columns(eligible("category", "text", "email"), 1, 2):
            for i in choose_rows(c, rate(0.05, 0.10)):
                v = data[c][i]
                options = [o for o in (v.upper(), v.lower(), v.title(), v.swapcase()) if o != v]
                if options:
                    hit(i, c, "inconsistent_case", str(rng.choice(options)))
            for i in choose_rows(c, rate(0.03, 0.06)):
                v = data[c][i]
                hit(i, c, "stray_spaces", str(rng.choice([f" {v}", f"{v} ", f" {v} "])))
            if roles[c] == "email":
                for i in choose_rows(c, rate(0.01, 0.03)):
                    v = data[c][i]
                    hit(i, c, "invalid_email", str(rng.choice([v.replace("@", ""), v.replace(".", "", 1), v.replace("@", " at ")])))
            else:
                for i in choose_rows(c, rate(0.01, 0.03)):
                    v = data[c][i]
                    if len(v.strip()) < 4:
                        continue
                    p = int(rng.integers(0, len(v) - 1))
                    typo = v[:p] + v[p + 1] + v[p] + v[p + 2:] if (rng.random() < 0.5 and v[p] != v[p + 1]) else v[:p] + v[p + 1:]
                    hit(i, c, "typo", typo)

    def mixed_booleans():                       # 15-30% of rows in one Boolean column
        for c in choose_columns(eligible("bool"), 1, 1):
            for i in choose_rows(c, rate(0.15, 0.30)):
                pair = BOOL_STYLES[int(rng.integers(len(BOOL_STYLES)))]
                hit(i, c, "mixed_boolean", pair[0] if data[c][i].strip().lower() in BOOL_POSITIVE else pair[1])

    def outliers():                             # 0.5-1.5% of cells in 1-2 numeric columns
        for c in choose_columns(eligible("integer", "decimal"), 1, 2):
            non_negative = all(not v.strip().startswith("-") for v in data[c] if not is_missing(v))
            for i in choose_rows(c, rate(0.005, 0.015)):
                text = data[c][i].strip()
                v, d = _number(text), _decimals(text)
                ops = ["x10", "x100", "sentinel"] + (["negative"] if non_negative and v != 0 else [])
                op = str(rng.choice(ops))
                new = v * 10 if op == "x10" else v * 100 if op == "x100" else -abs(v) if op == "negative" else int(rng.choice([999999, -1, 9999]))
                hit(i, c, "outlier", _format_like(new, d if op != "sentinel" else 0))

    faults = [missing_values, numbers_as_text, wrong_dates, text_damage, mixed_booleans, outliers]
    for index in rng.permutation(len(faults)):
        faults[int(index)]()

    # ---- headers -----------------------------------------------------------------------------
    def words(s):
        return [w for w in re.split(r"[\s_\-]+", s.strip()) if w]

    styles = [lambda s: s, lambda s: s, lambda s: s,
              lambda s: " ".join(w.title() for w in words(s)),
              lambda s: s.upper(),
              lambda s: "_".join(w.lower() for w in words(s)),
              lambda s: (lambda p: p[0].lower() + "".join(w.title() for w in p[1:]))(words(s)),
              lambda s: s + " "]
    headers = {c: styles[int(rng.integers(len(styles)))](c) or c for c in columns}
    if all(headers[c] == c for c in columns):
        headers[columns[0]] = columns[0].upper() if columns[0].upper() != columns[0] else columns[0] + " "
    if len(set(headers.values())) < len(columns):
        headers = {c: c for c in columns}
        headers[columns[0]] = columns[0] + " "
    final_headers = [headers[c] for c in columns]

    # ---- structural faults: duplicates, near-duplicates, conflicting IDs, stray rows ---------------
    order = [("src", i) for i in range(n)]

    def insert(item):
        order.insert(int(rng.integers(1, len(order) + 1)), item)

    def count(low, high):
        return min(n, max(1, int(round(float(rng.uniform(low, high)) * scale * n))))

    for i in rng.choice(n, size=count(0.01, 0.03), replace=False):
        insert(("dup", int(i)))
    text_cols = eligible("category", "text")
    if text_cols and n >= 10:
        column = text_cols[int(rng.integers(len(text_cols)))]
        pool = [int(i) for i in range(n) if not is_missing(data[column][i])]
        for i in rng.choice(pool, size=min(len(pool), count(0.005, 0.015)), replace=False) if pool else []:
            v = data[column][int(i)]
            insert(("near", int(i), column, str(rng.choice([v.upper(), f"{v} ", v.lower()]))))
    id_cols, number_cols = eligible("id"), eligible("integer", "decimal")
    if id_cols and number_cols and n >= 10:
        column = number_cols[int(rng.integers(len(number_cols)))]
        for i in rng.choice(n, size=count(0.005, 0.01), replace=False):
            text = table[column].iloc[int(i)].strip()           # the original value, not one already damaged
            if is_missing(text) or not re.fullmatch(r"[+-]?\d*\.?\d+", text):
                continue
            v, d = _number(text), _decimals(text)
            new = _format_like(round(v * 1.1) + 1 if d == 0 else v * 1.1 + 0.01, d)
            if new != text:
                insert(("conflict", int(i), column, new))
    insert(("header",))
    insert(("blank",))

    rows, key, source_row = [], [], {}
    for position, item in enumerate(order, start=1):
        if item[0] == "src":
            source_row[item[1]] = position
    for position, item in enumerate(order, start=1):
        kind = item[0]
        if kind in ("src", "dup"):
            rows.append([data[c][item[1]] for c in columns])
            if kind == "dup":
                key.append((position, "", "duplicate_row", "", "", f"exact copy of row {source_row[item[1]]}"))
        elif kind == "near":
            row = [data[c][item[1]] for c in columns]
            row[columns.index(item[2])] = item[3]
            rows.append(row)
            key.append((position, item[2], "near_duplicate_row", "", "", f"copy of row {source_row[item[1]]} with {item[2]} written differently"))
        elif kind == "conflict":
            row = [data[c][item[1]] for c in columns]
            row[columns.index(item[2])] = item[3]
            rows.append(row)
            key.append((position, item[2], "conflicting_duplicate_id", "", "",
                        f"same {id_cols[0]} as row {source_row[item[1]]} but {item[2]} is {item[3]}"))
        elif kind == "header":
            rows.append(list(final_headers))
            key.append((position, "", "repeated_header_row", "", "", "the column names appear again as a data row"))
        else:
            rows.append([""] * len(columns))
            key.append((position, "", "blank_row", "", "", "an empty row"))
    for i, column, problem, original, messy, note in cells:
        key.append((source_row[i], column, problem, original, messy, note))
    for c in columns:
        if headers[c] != c:
            key.append((0, c, "messy_header", c, headers[c], "row 0 is the header line"))

    key_table = pd.DataFrame(key, columns=KEY_COLUMNS).sort_values(["row", "column"], kind="stable")
    messy = pd.DataFrame(rows, columns=final_headers, dtype=object)
    return messy, key_table.reset_index(drop=True)


def summarise(key):
    """Counts of each problem type, for the page."""
    return {str(k): int(v) for k, v in key["problem"].value_counts().items()}


def undo(messy, key, original_columns):
    """Rebuild the original table from the messy one and its key. Used by the tests to prove the key is exact."""
    structural = {"duplicate_row", "near_duplicate_row", "conflicting_duplicate_id", "repeated_header_row", "blank_row"}
    drop = set(key.loc[key["problem"].isin(structural), "row"].astype(int))
    cell_fixes = key[~key["problem"].isin(structural | {"messy_header"})]
    rows = messy.reset_index(drop=True)
    table = rows.copy()
    table.columns = original_columns
    table.index = range(1, len(table) + 1)
    for _, fix in cell_fixes.iterrows():
        table.at[int(fix["row"]), fix["column"]] = fix["original"]
    table = table.drop(index=sorted(drop & set(table.index)))
    return table.reset_index(drop=True)
