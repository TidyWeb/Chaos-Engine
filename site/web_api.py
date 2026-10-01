"""The functions the web page calls (in the browser, through Pyodide). Every function returns JSON text or bytes.

The uploaded table and the latest chaos result are kept here between calls, so a big file is sent once.
"""
import io
import json
import re
import secrets

from chaos.engine import make_chaos, summarise
from chaos.profile import apply_overrides, profile_table
from chaos.reader import MAX_BYTES, MAX_COLUMNS, MAX_ROWS, ReadError, read_table

PREVIEW_ROWS = 200
_state = {"table": None, "profile": None, "info": None, "messy": None, "key": None, "seed": None, "name": "data"}
_NUMBER = re.compile(r"^-?(0|[1-9]\d*)(\.\d+)?$")
_ROW_FAULTS = ("duplicate_row", "near_duplicate_row", "conflicting_duplicate_id", "repeated_header_row", "blank_row")


def _bytes(data):
    return data.to_py().tobytes() if hasattr(data, "to_py") else bytes(data)


def _stem(name):
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", name.rsplit(".", 1)[0]).strip("_") or "data"


def limits():
    return json.dumps({"max_mb": MAX_BYTES // 1048576, "max_rows": MAX_ROWS, "max_columns": MAX_COLUMNS})


def load(name, data, sheet=""):
    """Read an uploaded file. Returns what was found, the guessed column types and a preview."""
    try:
        table, info = read_table(name, _bytes(data), sheet=sheet or None)
    except ReadError as error:
        return json.dumps({"ok": False, "error": str(error)})
    except Exception as error:                              # an unexpected file shape: say so, do not crash the page
        return json.dumps({"ok": False, "error": f"This file could not be read ({type(error).__name__}: {error})."})
    profile = profile_table(table)
    _state.update(table=table, profile=profile, info=info, messy=None, key=None, seed=None, name=_stem(name))
    return json.dumps({
        "ok": True, "info": info, "profile": profile,
        "columns": list(table.columns), "rows": table.head(PREVIEW_ROWS).values.tolist(), "total": int(len(table)),
    })


def chaos(seed, intensity, overrides_json="{}"):
    table = _state["table"]
    if table is None:
        return json.dumps({"ok": False, "error": "Load a file first."})
    profile = apply_overrides(_state["profile"], json.loads(overrides_json or "{}"))
    seed = int(seed) if str(seed).strip() != "" else secrets.randbelow(1_000_000_000)
    messy, key = make_chaos(table, profile, seed, intensity)
    _state.update(messy=messy, key=key, seed=seed)

    shown = messy.head(PREVIEW_ROWS)
    marks, row_marks, header_marks = {}, {}, {}
    original_columns = list(table.columns)
    for row, column, problem, original, new, note in key.itertuples(index=False):
        if row == 0:
            header_marks[str(original_columns.index(column))] = {"problem": problem, "was": original}
        elif row > PREVIEW_ROWS:
            continue
        elif problem in _ROW_FAULTS:
            row_marks[str(row - 1)] = {"problem": problem, "note": note}
        else:
            marks[f"{row - 1},{original_columns.index(column)}"] = {"problem": problem, "was": original}
    return json.dumps({
        "ok": True, "seed": seed, "columns": list(messy.columns), "rows": shown.values.tolist(),
        "total": int(len(messy)), "summary": summarise(key), "changes": int(len(key)),
        "marks": marks, "row_marks": row_marks, "header_marks": header_marks,
        "csv_name": f"{_state['name']}_chaos_seed{seed}.csv",
        "xlsx_name": f"{_state['name']}_chaos_seed{seed}.xlsx",
        "key_name": f"{_state['name']}_chaos_seed{seed}_answer_key.csv",
    })


def make_csv():
    return _state["messy"].to_csv(index=False).encode("utf-8")


def make_key():
    return _state["key"].to_csv(index=False).encode("utf-8")


def make_xlsx():
    """Excel file: cells that are clean numbers become real numbers; everything else stays text, as in a real export."""
    from openpyxl import Workbook
    book = Workbook(write_only=True)
    sheet = book.create_sheet("data")
    messy = _state["messy"]
    sheet.append(list(messy.columns))
    for row in messy.itertuples(index=False):
        out = []
        for value in row:
            text = "" if value is None else str(value)
            if _NUMBER.match(text):
                out.append(float(text) if "." in text else int(text))
            else:
                out.append(text if text != "" else None)
        sheet.append(out)
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()
