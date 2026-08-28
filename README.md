# Subcontractor COI Auto-Tracker & Expiry Monitor

Backend extraction processor for certificates of insurance. Extracts policy data from PDF, Excel, CSV, or plain text and classifies each subcontractor COI with a status and due date.

## Quick Start

```bash
python3 run_demo.py   # runs hardcoded demo data and asserts extraction
python3 run_tests.py  # minimal self-tests for processor behavior
```

## Files

- `processor.py` — core extraction library
- `run_demo.py` — zero-argument demo runner
- `run_tests.py` — minimal self-tests
- `requirements.txt` — Python dependencies

## Expected Input

The poller passes raw file bytes (`bytes`) to `process_file(file_bytes)`, which returns a list of records:

```json
{
  "title": "Acme Drywall LLC",
  "status": "expired:critical",
  "details": "Policy expired on 2024-12-31",
  "due_date": "2024-12-31"
}
```

Supported statuses: `missing:critical`, `expired:critical`, `expiring_soon:warning`, `valid_compliant:good`, `flagged:critical`, `needs_review:warning`, `blocked:critical`.


Dashboard: https://subcontractor-coi-certificate-of-insuran.vokrix.co
Vercel: subcontractor-coi-certificate-of-insuran
Railway: subcontractor-coi-certificate-of-insuran
Cloudflare: subcontractor-coi-certificate-of-insuran.vokrix.co

Landing: https://vokrix.co/subcontractor-coi-certificate-of-insuran
