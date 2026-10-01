"""Read an uploaded file into a table of plain text.

Everything is read as text on purpose: a column of ID codes such as 00123 must stay 00123, and a date
must stay in whatever shape the file wrote it. Missing cells become the empty string.

    table, info = read_table(file_name, raw_bytes, sheet=None)

`info` describes what was found (format, delimiter, encoding, sheets, warnings) so the page can show it.
"""
import csv
import io
import json
import re
from pathlib import Path

import pandas as pd

MAX_BYTES = 25 * 1024 * 1024      # defaults suit the browser; the standalone app passes bigger limits
MAX_ROWS = 100_000
MAX_COLUMNS = 200
ENCODINGS = ["utf-8-sig", "utf-8", "cp1252", "latin-1"]
DELIMITERS = [",", ";", "\t", "|"]
EXCEL_SUFFIXES = {".xlsx", ".xlsm"}


class ReadError(Exception):
    """The file cannot be used; the message is written for the person who uploaded it."""


def _size(count):
    return f"{count / 1048576:.1f} MB" if count >= 1048576 else f"{count / 1024:.0f} KB"


def _decode(raw):
    for encoding in ENCODINGS:
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise ReadError("Could not work out the text encoding of this file.")


def _delimiter(text):
    lines = [line for line in text.splitlines()[:30] if line.strip()]
    if not lines:
        raise ReadError("The file is empty.")
    try:
        found = csv.Sniffer().sniff("\n".join(lines), delimiters="".join(DELIMITERS)).delimiter
        if found in DELIMITERS:
            return found
    except csv.Error:
        pass
    counts = {d: sum(line.count(d) for line in lines) for d in DELIMITERS}
    best = max(counts, key=counts.get)
    return best if counts[best] else ","


def _tidy(table, info, max_rows, max_columns):
    table = table.copy()
    table.columns = [str(c).strip() if str(c).strip() and not str(c).startswith("Unnamed:") else f"column_{i + 1}"
                     for i, c in enumerate(table.columns)]
    seen, names = {}, []
    for name in table.columns:
        count = seen.get(name, 0)
        seen[name] = count + 1
        names.append(name if count == 0 else f"{name}_{count + 1}")
    table.columns = names
    table = table.fillna("").astype(str)
    for column in table.columns:                       # an Excel date arrives as "2024-03-01 00:00:00"
        values = table[column]
        stamped = values.str.endswith(" 00:00:00")
        if stamped.any() and (stamped | (values == "")).all():
            table[column] = values.str.replace(" 00:00:00", "", regex=False)
    table = table.loc[~(table == "").all(axis=1)].reset_index(drop=True)
    if table.shape[1] > max_columns:
        raise ReadError(f"This file has {table.shape[1]} columns; the limit is {max_columns}.")
    if len(table) > max_rows:
        raise ReadError(f"This file has {len(table):,} rows; the limit here is {max_rows:,}. "
                        "The standalone app handles bigger files.")
    if table.empty or table.shape[1] == 0:
        raise ReadError("No data rows were found in this file.")
    info["rows"], info["columns"] = int(len(table)), int(table.shape[1])
    return table, info


def read_table(name, raw, sheet=None, max_bytes=MAX_BYTES, max_rows=MAX_ROWS, max_columns=MAX_COLUMNS):
    raw = bytes(raw)
    if len(raw) > max_bytes:
        raise ReadError(f"This file is {_size(len(raw))}; the limit here is {_size(max_bytes)}. "
                        "The standalone app handles bigger files.")
    suffix = Path(name).suffix.lower()
    info = {"file": name, "warnings": [], "sheets": [], "sheet": None}
    if suffix == ".xls":
        raise ReadError("Old .xls files are not supported. Save it as .xlsx or .csv and try again.")
    if suffix in EXCEL_SUFFIXES:
        try:
            book = pd.ExcelFile(io.BytesIO(raw))
        except Exception as error:
            raise ReadError(f"Could not open this Excel file ({error}).")
        info["format"], info["sheets"] = "excel", list(book.sheet_names)
        info["sheet"] = sheet if sheet in book.sheet_names else book.sheet_names[0]
        table = book.parse(info["sheet"], dtype=str, keep_default_na=False)
        return _tidy(table, info, max_rows, max_columns)
    text, info["encoding"] = _decode(raw)
    stripped = text.lstrip()
    if suffix == ".json" or stripped.startswith(("[", "{")):
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                lists = [v for v in data.values() if isinstance(v, list)]
                data = lists[0] if lists else [data]
            table = pd.json_normalize(data)
        except Exception as error:
            raise ReadError(f"Could not read this JSON file ({error}).")
        info["format"] = "json"
        return _tidy(table.astype(object).where(table.notna(), ""), info, max_rows, max_columns)
    delimiter = _delimiter(text)
    info["format"], info["delimiter"] = "text", delimiter
    try:
        table = pd.read_csv(io.StringIO(text), sep=delimiter, dtype=str, keep_default_na=False)
    except pd.errors.ParserError:
        table = pd.read_csv(io.StringIO(text), sep=delimiter, dtype=str, keep_default_na=False,
                            engine="python", on_bad_lines="skip")
        info["warnings"].append("Some lines had the wrong number of fields and were skipped.")
    if re.search(r"�", text):
        info["warnings"].append("Some characters could not be decoded cleanly.")
    return _tidy(table, info, max_rows, max_columns)
