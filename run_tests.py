import sys
from processor import process_file

CSV = b"""subcontractor legal name,policy numbers,policy expiration date
Valid Co,POL-1,12/31/2099
Expired Co,POL-2,01/01/2020
"""

def main():
    records = process_file(CSV)
    assert isinstance(records, list)
    assert len(records) == 2
    for rec in records:
        assert {"title", "status", "details", "due_date"} <= set(rec.keys())
        assert isinstance(rec["due_date"], str)
    statuses = [r["status"] for r in records]
    assert statuses[0] == "valid_compliant:good", statuses
    assert statuses[1] == "expired:critical", statuses
    print("TESTS PASSED")
    return 0

if __name__ == "__main__":
    sys.exit(main())
