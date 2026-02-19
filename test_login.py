# test_login.py - small debug helper (prints SMTP protocol debug)
import os, smtplib, getpass

S = os.environ.get('SENDER_EMAIL') or input('Sender: ')
P = os.environ.get('SMTP_PASSWORD') or getpass.getpass('Password: ')

try:
    with smtplib.SMTP('smtp.gmail.com', 587, timeout=20) as s:
        s.set_debuglevel(1)     # shows SMTP protocol exchange
        s.starttls()
        s.login(S, P)
    print('Login OK')
except Exception as e:
    print('Login failed:', repr(e))