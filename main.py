import argparse
import csv
import getpass
import logging
import os
import smtplib
import sys
import time
from email.message import EmailMessage
from pathlib import Path
from typing import Optional


def load_dotenv(path: str = ".env") -> None:
    """Load a simple KEY=VALUE .env file into os.environ without overwriting existing values."""
    p = Path(path)
    if not p.exists():
        return
    try:
        with p.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except Exception:
        # Do not raise; silently ignore malformed .env in production usage
        return


def build_message(sender: str, receiver: str, subject: str, body: str, table_path: Optional[Path] = None) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = receiver
    msg["Subject"] = subject
    plain_body = body

    if table_path and table_path.exists():
        dialect = "excel" if table_path.suffix == ".csv" else "excel-tab"
        rows = []
        try:
            with table_path.open("r", newline="", encoding="utf-8") as fh:
                reader = csv.reader(fh, dialect=dialect)
                for r in reader:
                    rows.append(r)
        except Exception:
            rows = []

        if rows:
            cols = rows[0]
            html = ["<html><body>", f"<p>{body}</p>", '<table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse">']
            html.append("<thead><tr>")
            for c in cols:
                html.append(f"<th style=\"background:#eee\">{c}</th>")
            html.append("</tr></thead>")
            html.append("<tbody>")
            for row in rows[1:]:
                html.append("<tr>")
                for cell in row:
                    html.append(f"<td>{cell}</td>")
                html.append("</tr>")
            html.append("</tbody></table></body></html>")
            html_body = "\n".join(html)
            msg.set_content(plain_body)
            msg.add_alternative(html_body, subtype="html")
            return msg

    msg.set_content(plain_body)
    return msg


def send_email_from_env(subject: str, body: str, table_path: Optional[Path] = None, *, smtp_host: str = "smtp.gmail.com", smtp_port: int = 587, timeout: int = 20, max_retries: int = 3) -> None:
    """Send an email using credentials from environment variables.

    Required environment variables:
      - SENDER_EMAIL
      - RECEIVER_EMAIL
      - SMTP_PASSWORD (an App Password for Gmail when using Gmail)

    This function performs a small retry loop for transient failures and
    logs errors instead of printing sensitive information.
    """
    sender = os.environ.get("SENDER_EMAIL")
    receiver = os.environ.get("RECEIVER_EMAIL")
    password = os.environ.get("SMTP_PASSWORD") or os.environ.get("APP_PASSWORD")

    if not sender or not receiver:
        raise RuntimeError("SENDER_EMAIL and RECEIVER_EMAIL must be set in environment")
    if not password:
        # For non-interactive/automated runs we require password in env (use Secret Manager in prod)
        raise RuntimeError("SMTP_PASSWORD (App Password) must be set in environment for automated sending")

    msg = build_message(sender, receiver, subject, body, table_path)

    last_exc = None
    for attempt in range(1, max_retries + 1):
        try:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=timeout) as s:
                s.starttls()
                s.login(sender, password)
                s.send_message(msg)
            logging.info("Email sent to %s", receiver)
            return
        except smtplib.SMTPException as exc:
            last_exc = exc
            logging.warning("SMTP attempt %d failed: %s", attempt, exc)
            # simple backoff
            time.sleep(2 ** attempt)
        except Exception as exc:
            last_exc = exc
            logging.exception("Unexpected error while sending email: %s", exc)
            time.sleep(1)

    # If we get here, all retries failed
    raise RuntimeError("Failed to send email after retries") from last_exc


def _cli_main(argv: Optional[list[str]] = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Send a report email. Uses .env for credentials by default.")
    parser.add_argument("--send", action="store_true", help="Actually send the email (otherwise preview only)")
    parser.add_argument("--subject", help="Email subject (overrides SUBJECT env)")
    parser.add_argument("--body", help="Email body (overrides BODY env)")
    parser.add_argument("--table", help="Path to CSV/TSV table to attach (default: auto-detect)")
    args = parser.parse_args(argv)

    subject = args.subject or os.environ.get("SUBJECT", "Report from alerting_mail")
    body = args.body or os.environ.get("BODY", "Please find the attached report.")

    # choose table path: explicit, or detect table.csv/table.tsv in cwd
    table_path = None
    if args.table:
        table_path = Path(args.table)
    else:
        for candidate in ("table.csv", "table.tsv"):
            if Path(candidate).exists():
                table_path = Path(candidate)
                break

    print("\nPreview:")
    print("Subject:", subject)
    print(body)
    if not args.send:
        print("\nNo --send flag: not sending. Run with --send to actually send.")
        return 0

    send_email_from_env(subject, body, table_path)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        raise SystemExit(_cli_main())
    except Exception as e:
        logging.exception("Error: %s", e)
        raise
