import os
import time
import json
from datetime import datetime, timezone

import requests
import processor

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
PRODUCT_ID = os.environ["PRODUCT_ID"]
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

JOBS_URL = f"{SUPABASE_URL}/rest/v1/jobs"
RECORDS_URL = f"{SUPABASE_URL}/rest/v1/records"
NOTIFICATIONS_URL = "https://njyvnmczoydsaewvfhyq.supabase.co/rest/v1/notifications"


def headers():
    return {
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "apikey": SUPABASE_SERVICE_KEY,
        "Content-Type": "application/json",
    }


def download_file(bucket, file_path):
    if file_path.startswith(bucket + "/"):
        file_path = file_path[len(bucket) + 1:]
    url = f"{SUPABASE_URL}/storage/v1/object/{bucket}/{file_path}"
    resp = requests.get(url, headers={"Authorization": f"Bearer {SUPABASE_SERVICE_KEY}", "apikey": SUPABASE_SERVICE_KEY})
    resp.raise_for_status()
    return resp.content


def upload_result(job_id, content):
    filename = f"result_{job_id}.json"
    url = f"{SUPABASE_URL}/storage/v1/object/results/{filename}"
    resp = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
            "apikey": SUPABASE_SERVICE_KEY,
            "Content-Type": "application/json",
        },
        data=content,
    )
    resp.raise_for_status()
    return filename


def insert_notification(product_id, customer_id, title, body, notif_type):
    try:
        payload = {
            "product_id": product_id,
            "customer_id": customer_id,
            "title": title,
            "body": body,
            "type": notif_type,
            "read": False,
        }
        requests.post(NOTIFICATIONS_URL, headers=headers(), json=payload)
    except Exception as e:
        print(f"Notification failed: {e}")


def poll():
    while True:
        try:
            params = {
                "status": "eq.pending",
                "job_type": "eq.process_upload",
                "product_id": f"eq.{PRODUCT_ID}",
                "select": "*",
            }
            resp = requests.get(JOBS_URL, headers=headers(), params=params)
            resp.raise_for_status()
            jobs = resp.json()

            for job in jobs:
                job_id = job.get("id")
                customer_id = job.get("customer_id")
                input_file_path = job.get("input_file_path")
                if not input_file_path:
                    continue

                try:
                    file_bytes = download_file("uploads", input_file_path)
                    result = processor.process_file(file_bytes)
                    if isinstance(result, dict):
                        result_json = json.dumps(result, default=str)
                        details = result
                    else:
                        result_json = json.dumps({"data": result}, default=str)
                        details = {"data": result}

                    due_date = None
                    record_status = "pending"
                    if isinstance(result, dict):
                        due_date = result.get("due_date")
                        record_status = result.get("status", "pending")

                    record_payload = {
                        "product_id": PRODUCT_ID,
                        "customer_id": customer_id,
                        "title": result.get("title", "Uploaded document") if isinstance(result, dict) else "Uploaded document",
                        "status": record_status,
                        "details": details,
                        "source_file_path": input_file_path,
                        "due_date": due_date,
                    }

                    record_resp = requests.post(RECORDS_URL, headers=headers(), json=record_payload)
                    record_resp.raise_for_status()

                    output_file_path = upload_result(job_id, result_json)
                    completed_at = datetime.now(timezone.utc).isoformat()

                    update_payload = {
                        "status": "completed",
                        "output_file_path": output_file_path,
                        "result_summary": "Processing completed successfully",
                        "completed_at": completed_at,
                    }
                    requests.patch(f"{JOBS_URL}?id=eq.{job_id}", headers=headers(), json=update_payload).raise_for_status()
                    insert_notification(PRODUCT_ID, customer_id, "Processing complete", "Your upload has been processed successfully.", "success")

                except Exception as e:
                    failed_at = datetime.now(timezone.utc).isoformat()
                    update_payload = {
                        "status": "failed",
                        "result_summary": str(e),
                        "completed_at": failed_at,
                    }
                    try:
                        requests.patch(f"{JOBS_URL}?id=eq.{job_id}", headers=headers(), json=update_payload).raise_for_status()
                    except Exception:
                        pass
                    insert_notification(PRODUCT_ID, customer_id, "Processing failed", "There was an error processing your upload.", "error")
                    print(f"Job {job_id} failed: {e}")

        except Exception as e:
            print(f"Poll error: {e}")

        time.sleep(60)


if __name__ == "__main__":
    print("Poller started")
    poll()
