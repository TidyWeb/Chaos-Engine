"""Work out what each column is, so the right kind of damage can be chosen for it.

    profile_table(table) -> list of column profiles (plain dicts, easy to show on a page and to override)

Roles: id, integer, decimal, date, bool, email, category, text, empty.
`already_messy` is set when a column already contains missing-value markers other than a blank cell.
"""
import re
from datetime import datetime

MISSING_LIKE = {"", "n/a", "na", "null", "none", "nan", "-", "--", "?"}
ROLES = ["id", "integer", "decimal", "date", "bool", "email", "category", "text", "empty"]
DATE_FORMATS = ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d", "%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y %H:%M", "%d %b %Y", "%d %B %Y", "%b %d, %Y", "%B %d, %Y", "%Y%m%d"]
BOOL_POSITIVE = {"yes", "y", "true", "t", "1"}
BOOL_NEGATIVE = {"no", "n", "false", "f", "0"}
INT_RE = re.compile(r"^[+-]?\d+$")
DEC_RE = re.compile(r"^[+-]?(\d+\.\d+|\.\d+)$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
ID_NAME_RE = re.compile(r"(^|[_\s\-])(id|uuid|guid|key|ref|reference|code|sku|no|number)$|^(id|uuid)([_\s\-]|$)", re.I)


def is_missing(value):
    return str(value).strip().lower() in MISSING_LIKE


def detect_date_format(values):
    sample = values[:300]
    if not sample:
        return None
    for fmt in DATE_FORMATS:
        try:                                        # cheap rejection first: most columns are not dates
            datetime.strptime(sample[0].strip(), fmt)
            datetime.strptime(sample[len(sample) // 2].strip(), fmt)
        except ValueError:
            continue
        ok = 0
        for value in sample:
            try:
                datetime.strptime(value.strip(), fmt)
                ok += 1
            except ValueError:
                pass
        if ok >= 0.95 * len(sample):
            return fmt
    return None


def _share(values, pattern):
    return sum(1 for v in values if pattern.match(v.strip())) / len(values)


def profile_column(name, series):
    values_all = [str(v) for v in series.tolist()]
    n = len(values_all)
    markers = sum(1 for v in values_all if v.strip() != "" and is_missing(v))
    values = [v for v in values_all if not is_missing(v)]
    result = {"name": name, "role": "empty", "detail": "", "missing": n - len(values), "marker_cells": markers,
              "unique": len(set(values)), "already_messy": markers > 0, "sample": values[:3]}
    if not values:
        return result
    unique_ratio = len(set(values)) / len(values)
    has_leading_zero = any(len(v) > 1 and v.startswith("0") and "." not in v for v in values if INT_RE.match(v))
    named_id = bool(ID_NAME_RE.search(name.strip()))

    if named_id and unique_ratio >= 0.98 and len(values) >= 5:
        result["role"] = "id"
    elif _share(values, INT_RE) >= 0.95 and not has_leading_zero:
        result["role"] = "integer"
        nums = sorted(int(v) for v in values if INT_RE.match(v.strip()))
        if len(nums) >= 20 and unique_ratio >= 0.99 and nums[-1] - nums[0] == len(nums) - 1:
            result["role"] = "id"                                  # 1, 2, 3 ... a row counter
    elif _share(values, INT_RE) + _share(values, DEC_RE) >= 0.95 and _share(values, DEC_RE) > 0:
        result["role"] = "decimal"
    elif has_leading_zero and _share(values, INT_RE) >= 0.95:
        result["role"] = "id" if unique_ratio >= 0.98 else "category"
        result["detail"] = "code with leading zeros"
    else:
        fmt = detect_date_format(values)
        lowered = {v.strip().lower() for v in values}
        if fmt:
            result["role"], result["detail"] = "date", fmt
        elif len(lowered) <= 2 and lowered <= (BOOL_POSITIVE | BOOL_NEGATIVE):
            result["role"] = "bool"
        elif _share(values, EMAIL_RE) >= 0.9:
            result["role"] = "email"
        elif len(set(values)) <= max(15, 0.05 * len(values)):
            result["role"] = "category"
        else:
            result["role"] = "text"
    if result["role"] in ("integer", "decimal"):
        decimals = [len(v.split(".")[1]) for v in values if "." in v]
        result["detail"] = f"{max(decimals)} decimal places" if decimals else "whole numbers"
    return result


def profile_table(table):
    return [profile_column(c, table[c]) for c in table.columns]


def apply_overrides(profile, overrides):
    """overrides: {column name: role}. Lets the person correct a wrong guess before chaos is made."""
    out = []
    for column in profile:
        role = overrides.get(column["name"])
        out.append({**column, "role": role, "overridden": True} if role in ROLES and role != column["role"] else column)
    return out
