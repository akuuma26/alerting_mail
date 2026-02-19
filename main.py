import os
import sys
import smtplib
import getpass
from email.message import EmailMessage

# Load simple .env (KEY=VALUE) if present
if os.path.exists('.env'):
    try:
        with open('.env', 'r', encoding='utf-8') as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except Exception:
        pass

S = os.environ.get('SENDER_EMAIL') or input('Sender: ')
P = os.environ.get('SMTP_PASSWORD') or os.environ.get('APP_PASSWORD') or getpass.getpass('Password: ')
R = os.environ.get('RECEIVER_EMAIL') or input('Receiver: ')
SUB = os.environ.get('SUBJECT', 'Test email')
BODY = os.environ.get('BODY', 'Hello from Python')

msg = EmailMessage()
msg['From'], msg['To'], msg['Subject'] = S, R, SUB
plain_body = BODY

# If a table file exists (table.csv or table.tsv) include it in the message as HTML table
table_path = None
for candidate in ('table.csv', 'table.tsv'):
    if os.path.exists(candidate):
        table_path = candidate
        break

if table_path:
    # build a simple HTML table from the CSV/TSV
    import csv
    dialect = 'excel' if table_path.endswith('.csv') else 'excel-tab'
    rows = []
    try:
        with open(table_path, newline='', encoding='utf-8') as fh:
            reader = csv.reader(fh, dialect=dialect)
            for r in reader:
                rows.append(r)
    except Exception:
        rows = []

    if rows:
        # prepare HTML
        cols = rows[0]
        html = ['<html><body>', f'<p>{BODY}</p>', '<table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse">']
        # header
        html.append('<thead><tr>')
        for c in cols:
            html.append(f'<th style="background:#eee">{c}</th>')
        html.append('</tr></thead>')
        # body rows
        html.append('<tbody>')
        for row in rows[1:]:
            html.append('<tr>')
            for cell in row:
                html.append(f'<td>{cell}</td>')
            html.append('</tr>')
        html.append('</tbody></table></body></html>')
        html_body = '\n'.join(html)
        msg.set_content(plain_body)
        msg.add_alternative(html_body, subtype='html')
    else:
        msg.set_content(plain_body)
else:
    msg.set_content(plain_body)

print('\nPreview:')
print('From:', S)
print('To:  ', R)
print('Subject:', SUB)
print('\n' + BODY + '\n')

if '--send' not in sys.argv:
    print('No --send flag: not sending. Run with --send to actually send.')
    sys.exit(0)

try:
    with smtplib.SMTP('smtp.gmail.com', 587, timeout=20) as s:
        s.starttls()
        s.login(S, P)
        s.send_message(msg)
    print('Email sent')
except Exception as e:
    print('Send failed:', e)
    sys.exit(1)
