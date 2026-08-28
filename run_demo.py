import sys
from processor import process_file

CSV_DATA = b"""subcontractor legal name,policy numbers,policy effective date,policy expiration date,status
Acme Drywall LLC,POL-100-2024,01/01/2024,12/31/2024,active
Bright Electric Co.,POL-200-2025,06/01/2025,07/15/2025,active
Cornerstone Framing,POL-300-2023,03/01/2023,03/15/2023,expired
"""


def main():
    records = process_file(CSV_DATA)
    assert isinstance(records, list)
    assert len(records) == 3
    for rec in records:
        assert "title" in rec and "status" in rec and "details" in rec and "due_date" in rec
        assert rec["status"] in {
            "missing:critical", "expired:critical", "expiring_soon:warning",
            "valid_compliant:good", "flagged:critical", "needs_review:warning", "blocked:critical",
        }
    assert [r["title"] for r in records] == ["Acme Drywall LLC", "Bright Electric Co.", "Cornerstone Framing"]
    assert records[0]["status"] == "expired:critical"
    print("DEMO PASSED")
    for rec in records:
        print(f"  {rec['title']} | {rec['status']} | {rec['details']} | due {rec['due_date']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
