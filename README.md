Quick guide — store credentials safely and run the script

Files created:
- `main.py` — the small sender script. It will automatically load a local `.env` file if present.
- `.env.example` — a template you can copy to `.env` and fill with your credentials.
- `.gitignore` — ignores `.env` so you don't accidentally commit secrets.

Steps to run (PowerShell)
1. Copy the example and edit it (DON'T commit `.env`):
   ```powershell
   copy .\.env.example .\.env
   notepad .\.env   # paste your real credentials here
   ```
2. Run preview (no email sent):
   ```powershell
   py .\main.py
   ```
3. Send the email for real:
   ```powershell
   py .\main.py --send
   ```
Notes
- For Gmail: use an App Password (create at https://myaccount.google.com/security under App passwords) if your account has 2FA enabled.
- The `.env` file should look like this (no quotes around values):
  SENDER_EMAIL=you@gmail.com
  SMTP_PASSWORD=your-app-password
  RECEIVER_EMAIL=target@example.com
  SUBJECT=Hi
  BODY=Hello

If you want, I can populate a `.env` for you now (but please paste your real credentials only if you understand the security risk).