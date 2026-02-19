#!/usr/bin/env python3
"""
Scan a Google Cloud Storage bucket folder structure and produce a CSV report
usable by `main.py` (it will include `table.csv` as an HTML table when sending).

Behavior:
- Scans a bucket under an optional prefix (defaults to 'sftp/').
- For each immediate child folder under the prefix, counts files in
  child/completed/ and child/errorFile/ and writes rows: item,processed,error,total
- Writes `table.csv` to the current working directory.
- Optionally invokes `main.py --send` to email the report.

Authentication:
- The script uses Application Default Credentials by default. To use a
  service account JSON key, pass --service-account /path/to/key.json.

Usage examples:
  python gcs_scan_and_send.py --bucket my-bucket --prefix sftp/ --send
  python gcs_scan_and_send.py --bucket my-bucket --prefix reports/ --service-account C:\keys\sa.json

"""
from __future__ import annotations

import argparse
import csv
import logging
import subprocess
import sys
from pathlib import Path
from typing import Dict, Optional

import json
import os
import time
import urllib.parse
import urllib.request


def _http_get(url: str, headers: dict | None = None, timeout: int = 20) -> dict:
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
        if not data:
            return {}
        return json.loads(data.decode("utf-8"))


def get_access_token() -> str:
    """Get an OAuth2 access token for GCS.

    Order:
      1. Try GCE metadata server (when running on GCP) at
         http://metadata/computeMetadata/v1/instance/service-accounts/default/token
      2. Use environment variable GCS_ACCESS_TOKEN
      3. Try `gcloud auth print-access-token` (if gcloud is available)

    This avoids third-party Python libraries; the token is used in Bearer header.
    """
    # 1) metadata server
    metadata_url = "http://metadata/computeMetadata/v1/instance/service-accounts/default/token"
    try:
        req = urllib.request.Request(metadata_url, headers={"Metadata-Flavor": "Google"})
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = resp.read()
            token_json = json.loads(data.decode("utf-8"))
            token = token_json.get("access_token")
            if token:
                return token
    except Exception:
        pass

    # 2) environment variable
    token = os.environ.get("GCS_ACCESS_TOKEN")
    if token:
        return token

    # 3) gcloud CLI
    try:
        out = subprocess.check_output(["gcloud", "auth", "print-access-token"], stderr=subprocess.DEVNULL, text=True, timeout=5)
        tok = out.strip()
        if tok:
            return tok
    except Exception:
        pass

    raise RuntimeError("No GCS access token available. Set GCS_ACCESS_TOKEN, run on GCP, or install and auth gcloud.")


def _list_prefixes(bucket_name: str, prefix: str, token: str) -> list[str]:
    """Return a list of immediate child prefixes under the given prefix using delimiter='/'"""
    prefixes: list[str] = []
    base = f"https://storage.googleapis.com/storage/v1/b/{urllib.parse.quote(bucket_name)}/o"
    params = {"prefix": prefix, "delimiter": "/", "fields": "prefixes,nextPageToken"}
    page_token = None
    headers = {"Authorization": f"Bearer {token}"}
    while True:
        if page_token:
            params["pageToken"] = page_token
        qs = urllib.parse.urlencode(params)
        url = base + "?" + qs
        resp = _http_get(url, headers=headers)
        pfxs = resp.get("prefixes") or []
        for p in pfxs:
            # p will be like 'sftp/foo/'
            rest = p[len(prefix) :] if prefix and p.startswith(prefix) else p
            child = rest.rstrip("/").split("/")[0]
            if child:
                prefixes.append(child)
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return prefixes


def _count_objects(bucket_name: str, prefix: str, token: str) -> int:
    """Count objects under the prefix using list API and pagination."""
    base = f"https://storage.googleapis.com/storage/v1/b/{urllib.parse.quote(bucket_name)}/o"
    params = {"prefix": prefix, "fields": "items/name,nextPageToken"}
    page_token = None
    headers = {"Authorization": f"Bearer {token}"}
    total = 0
    while True:
        if page_token:
            params["pageToken"] = page_token
        qs = urllib.parse.urlencode(params)
        url = base + "?" + qs
        resp = _http_get(url, headers=headers)
        items = resp.get("items") or []
        total += len(items)
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return total


def scan_bucket(bucket_name: str, prefix: str, service_account: Optional[str] = None) -> Dict[str, Dict[str, int]]:
    """Return mapping child -> counts, using raw HTTP calls to GCS JSON API.

    `service_account` is ignored for this minimal implementation; use GCS_ACCESS_TOKEN or run on GCP.
    """
    token = get_access_token()
    # normalize prefix
    if prefix and not prefix.endswith("/"):
        prefix = prefix + "/"

    counts: Dict[str, Dict[str, int]] = {}

    # collect children via prefixes
    try:
        seen_children = set(_list_prefixes(bucket_name, prefix, token))
    except Exception:
        # fallback to scanning object names (smaller buckets)
        seen_children = set()
        # reuse _count_objects with listing without delimiter: get all object names and parse
        base = f"https://storage.googleapis.com/storage/v1/b/{urllib.parse.quote(bucket_name)}/o"
        params = {"prefix": prefix, "fields": "items/name,nextPageToken"}
        page_token = None
        headers = {"Authorization": f"Bearer {token}"}
        while True:
            if page_token:
                params["pageToken"] = page_token
            qs = urllib.parse.urlencode(params)
            url = base + "?" + qs
            resp = _http_get(url, headers=headers)
            for item in resp.get("items", []):
                name = item.get("name", "")
                rest = name[len(prefix) :] if prefix and name.startswith(prefix) else name
                parts = rest.split("/")
                if parts and parts[0]:
                    seen_children.add(parts[0])
            page_token = resp.get("nextPageToken")
            if not page_token:
                break

    for child in sorted(seen_children):
        processed_prefix = f"{prefix}{child}/completed/" if prefix else f"{child}/completed/"
        error_prefix = f"{prefix}{child}/errorFile/" if prefix else f"{child}/errorFile/"

        processed_count = _count_objects(bucket_name, processed_prefix, token)
        error_count = _count_objects(bucket_name, error_prefix, token)
        total_count = processed_count + error_count
        counts[child] = {"processed": processed_count, "error": error_count, "total": total_count}

    return counts


def write_csv(path: Path, counts: Dict[str, Dict[str, int]]):
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["item", "processed", "error", "total"])
        for item, v in counts.items():
            writer.writerow([item, v.get("processed", 0), v.get("error", 0), v.get("total", 0)])


def main(argv: list[str] | None = None):
    p = argparse.ArgumentParser(description="Scan GCS bucket and create table.csv report")
    p.add_argument("--bucket", required=True, help="GCS bucket name (e.g. my-bucket)")
    p.add_argument("--prefix", default="sftp/", help="Prefix inside the bucket to scan (default: sftp/)")
    p.add_argument("--service-account", help="Path to service account JSON key (optional)")
    p.add_argument("--out", default="table.csv", help="Output CSV path (default: table.csv)")
    p.add_argument("--send", action="store_true", help="If set, send email after writing CSV")
    p.add_argument("--subject", help="Email subject to use when sending")
    p.add_argument("--body", help="Email body to use when sending")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO)

    logging.info("Scanning bucket: %s prefix: %s", args.bucket, args.prefix)
    try:
        counts = scan_bucket(args.bucket, args.prefix, args.service_account)
    except Exception as e:
        logging.error("Failed to scan bucket: %s", e)
        sys.exit(2)

    out_path = Path.cwd() / args.out
    write_csv(out_path, counts)
    logging.info("Wrote report to %s (%d rows)", out_path, len(counts))

    if args.send:
        # Try to call main.send_email_from_env directly for a cleaner, secure flow
        try:
            from main import send_email_from_env

            subject = args.subject or "Automated GCS report"
            body = args.body or "Please find the automated report generated from GCS."
            send_email_from_env(subject, body, out_path)
            logging.info("Email sent via main.send_email_from_env")
        except Exception as exc:
            logging.warning("Direct call to main.send_email_from_env failed: %s", exc)
            # Fallback to subprocess invocation (keeps original behavior)
            main_py = Path(__file__).parent / "main.py"
            if not main_py.exists():
                logging.error("Cannot find main.py to send the email. Please ensure main.py is in the same folder.")
                sys.exit(3)
            cmd = [sys.executable, str(main_py), "--send"]
            if args.subject:
                cmd += ["--subject", args.subject]
            if args.body:
                cmd += ["--body", args.body]
            logging.info("Invoking email sender subprocess: %s", " ".join(cmd))
            subprocess.run(cmd, check=False)


if __name__ == "__main__":
    main()
