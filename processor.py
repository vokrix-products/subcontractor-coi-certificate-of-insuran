import os
import io
import csv
import re
import datetime
from typing import Any, Dict, List, Optional

# Required for optional LLM extraction; kept available but not used by default
import openai
import pdfplumber
import openpyxl

VALID_STATUSES = {
    "missing:critical",
    "expired:critical",
    "expiring_soon:warning",
    "valid_compliant:good",
    "flagged:critical",
    "needs_review:warning",
    "blocked:critical",
}

_FIELD_SYNONYMS = {
    "subcontractor_legal_name": [
        "subcontractor legal name",
        "subcontractor",
        "insured",
        "named insured",
        "legal name",
        "company name",
        "vendor name",
        "supplier",
        "contractor name",
        "name",
    ],
    "certificate_holder_name": [
        "certificate holder name",
        "certificate holder",
    ],
    "primary_carrier_name": [
        "primary insurance carrier name",
        "primary carrier",
        "insurance carrier",
        "carrier name",
        "carrier",
    ],
    "additional_insured_status": [
        "additional insured status/endorsement",
        "additional insured status",
        "additional insured",
        "endorsement",
    ],
    "am_best_rating": [
        "am best financial strength rating",
        "am best rating",
        "am best",
    ],
    "policy_numbers": [
        "policy number(s) per coverage type",
        "policy numbers",
        "policy number",
        "policy no",
        "policy nos",
        "policy #",
    ],
    "coverage_types": [
        "coverage types",
        "coverage type",
        "type of insurance",
    ],
    "policy_effective_date": [
        "policy effective date",
        "effective date",
    ],
    "policy_expiration_date": [
        "policy expiration date",
        "expiration date",
    ],
    "certificate_issue_date": [
        "certificate issue date",
        "issue date",
    ],
    "insurance_limits_per_occurrence": [
        "insurance limits per occurrence",
        "limits per occurrence",
        "occurrence limit",
    ],
    "insurance_limits_aggregate": [
        "insurance limits aggregate",
        "aggregate limit",
    ],
    "waiver_of_subrogation": [
        "waiver of subrogation indicator",
        "waiver of subrogation",
    ],
    "issuing_agent_name": [
        "issuing agent/agency name",
        "issuing agent name",
        "agent name",
        "agency name",
    ],
    "issuing_agent_contact": [
        "issuing agent contact",
        "agent contact",
    ],
    "certificate_number": [
        "certificate number/document control number",
        "certificate number",
        "document control number",
    ],
    "uploaded_document_file_name": [
        "uploaded document file name",
        "file name",
        "filename",
    ],
    "last_verified_date": [
        "last verified date",
        "verified date",
    ],
}


def _safe_str(value) -> str:
    return "" if value is None else str(value).strip()


def _parse_date_obj(value) -> Optional[datetime.date]:
    if not value:
        return None
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value

    s = str(value).strip()

    if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        try:
            return datetime.datetime.strptime(s, "%Y-%m-%d").date()
        except ValueError:
            return None

    for fmt in ("%m/%d/%Y", "%m-%d-%Y", "%m/%d/%y", "%m-%d-%y", "%B %d, %Y", "%b %d, %Y", "%d %b %Y"):
        try:
            return datetime.datetime.strptime(s, fmt).date()
        except ValueError:
            pass

    return None


def _parse_date_iso(value) -> Optional[str]:
    d = _parse_date_obj(value)
    return d.isoformat() if d else None


def _decode_bytes(file_bytes: bytes) -> str:
    if file_bytes[:4] == b"%PDF":
        try:
            parts = []
            with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                for page in pdf.pages:
                    text = page.extract_text() or ""
                    parts.append(text)
            return "\n".join(parts)
        except Exception:
            return ""

    if file_bytes[:2] == b"PK":
        try:
            wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
            lines = []
            for ws in wb.worksheets:
                for row in ws.iter_rows(values_only=True):
                    lines.append("\t".join("" if c is None else str(c) for c in row))
            return "\n".join(lines)
        except Exception:
            return ""

    return file_bytes.decode("utf-8", errors="ignore")


def _parse_rows(text: str) -> List[List[str]]:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return []

    first = lines[0]
    delimiter = "\t" if "\t" in first else "," if "," in first else None
    if not delimiter:
        return []

    rows = []
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    for row in reader:
        if row and any(c.strip() for c in row):
            rows.append([c.strip() for c in row])
    return rows


def _looks_like_tabular(text: str) -> bool:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if len(lines) < 2:
        return False
    first = lines[0]
    return "\t" in first or "," in first


def _find_value(rowdict: Dict[str, Any], keys: List[str]) -> Any:
    for key in keys:
        for k, v in rowdict.items():
            if k.lower().strip() == key.lower().strip() and v:
                return v
    return ""


def _extract_label_value(text: str, label: str) -> str:
    patterns = [
        r"(?im)^[ \t]*" + re.escape(label) + r"[ \t]*[:;-][ \t]*(.*?)[ \t]*$",
        r"(?im)^[ \t]*" + re.escape(label) + r"[ \t]+(.+?)[ \t]*$",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m and m.group(1).strip():
            return m.group(1).strip()

    lines = [ln.strip() for ln in text.splitlines()]
    for i, line in enumerate(lines):
        if label.lower() in line.lower():
            if ":" in line:
                val = line.split(":", 1)[1].strip()
                if val:
                    return val
            if i + 1 < len(lines) and lines[i + 1]:
                return lines[i + 1]
    return ""


def _extract_date_field(text: str, label: str) -> str:
    date_pat = r"([0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{2,4}|[0-9]{4}-[0-9]{2}-[0-9]{2})"
    m = re.search(r"(?im)" + re.escape(label) + r"[^\d]*" + date_pat, text)
    if m and m.group(1):
        return m.group(1).strip()
    return _extract_label_value(text, label)


def _title_from_text(text: str) -> str:
    skip_prefixes = (
        "certificate", "accord", "date", "insurer", "policy", "this",
        "limits", "description", "additional", "coverage", "waiver",
        "agent", "producer", "insured", "subcontractor", "named",
    )
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        lower = line.lower()
        if any(lower.startswith(p) for p in skip_prefixes):
            continue
        if len(line) <= 100:
            return line
    return "Unknown Subcontractor"


def _extract_coi_fields_from_text(text: str) -> Dict[str, Any]:
    label_map = {
        "subcontractor_legal_name": ["INSURED", "SUBCONTRACTOR", "NAMED INSURED", "LEGAL NAME", "COMPANY NAME"],
        "certificate_holder_name": ["CERTIFICATE HOLDER"],
        "primary_carrier_name": ["INSURER AFFORDING COVERAGE", "PRIMARY INSURANCE CARRIER", "INSURANCE CARRIER", "CARRIER"],
        "additional_insured_status": ["ADDITIONAL INSURED", "ADDITIONAL INSURED STATUS/ENDORSEMENT"],
        "am_best_rating": ["AM BEST"],
        "policy_numbers": ["POLICY NUMBER", "POLICY NO"],
        "coverage_types": ["COVERAGE TYPE", "TYPE OF INSURANCE"],
        "policy_effective_date": ["POLICY EFFECTIVE DATE", "EFFECTIVE DATE"],
        "policy_expiration_date": ["POLICY EXPIRATION DATE", "EXPIRATION DATE"],
        "certificate_issue_date": ["CERTIFICATE ISSUE DATE", "ISSUE DATE"],
        "insurance_limits_per_occurrence": ["LIMITS PER OCCURRENCE", "OCCURRENCE LIMIT"],
        "insurance_limits_aggregate": ["LIMITS AGGREGATE", "AGGREGATE LIMIT"],
        "waiver_of_subrogation": ["WAIVER OF SUBROGATION"],
        "issuing_agent_name": ["ISSUING AGENT", "AGENT/AGENCY NAME", "AGENT NAME"],
        "issuing_agent_contact": ["AGENT CONTACT", "ISSUING AGENT CONTACT"],
        "certificate_number": ["CERTIFICATE NUMBER", "DOCUMENT CONTROL NUMBER"],
        "last_verified_date": ["LAST VERIFIED DATE", "VERIFIED DATE"],
        "uploaded_document_file_name": ["UPLOADED DOCUMENT FILE NAME", "FILE NAME", "FILENAME"],
    }

    fields: Dict[str, Any] = {}

    for internal, labels in label_map.items():
        for label in labels:
            if "date" in internal:
                val = _extract_date_field(text, label)
            else:
                val = _extract_label_value(text, label)
            if val:
                fields[internal] = val
                break

    if not fields.get("subcontractor_legal_name"):
        fallback = _title_from_text(text)
        if fallback and fallback != "Unknown Subcontractor":
            fields["subcontractor_legal_name"] = fallback

    return fields


def _score_status(fields: Dict[str, Any]):
    exp = fields.get("policy_expiration_date") or ""
    exp_d = _parse_date_obj(exp)
    today = datetime.date.today()

    if not exp_d:
        if not fields.get("policy_numbers"):
            return "missing:critical", "No policy data found on certificate"
        return "needs_review:warning", "Expiration date missing"

    if exp_d < today:
        return "expired:critical", f"Policy expired on {exp_d.isoformat()}"

    days_left = (exp_d - today).days
    if days_left <= 30:
        return "expiring_soon:warning", f"Policy expires in {days_left} days"

    return "valid_compliant:good", f"Policy valid until {exp_d.isoformat()}"


def process_file(file_bytes: bytes) -> List[Dict[str, Any]]:
    text = _decode_bytes(file_bytes)
    records: List[Dict[str, Any]] = []

    if _looks_like_tabular(text):
        rows = _parse_rows(text)
        if rows and len(rows) > 1:
            header = [h.lower().strip() for h in rows[0]]
            for r in rows[1:]:
                if not any(c for c in r):
                    continue
                rowdict = dict(zip(header, r))
                fields: Dict[str, Any] = {}
                for internal, synonyms in _FIELD_SYNONYMS.items():
                    val = _find_value(rowdict, synonyms)
                    if val:
                        fields[internal] = val
                if not fields:
                    continue
                fields.setdefault("subcontractor_legal_name", _title_from_text(text))
                status, details = _score_status(fields)
                records.append({
                    "title": fields.get("subcontractor_legal_name") or "Unknown Subcontractor",
                    "status": status,
                    "details": details,
                    "due_date": _parse_date_iso(fields.get("policy_expiration_date")),
                })
            if records:
                return records

    fields = _extract_coi_fields_from_text(text)
    status, details = _score_status(fields)
    records.append({
        "title": fields.get("subcontractor_legal_name") or "Unknown Subcontractor",
        "status": status,
        "details": details,
        "due_date": _parse_date_iso(fields.get("policy_expiration_date")),
    })
    return records
