"""Scan a local sftp-style folder and send a table email.

Usage:
    - Put your folder structure under the project, e.g. c:/Users/HP/alerting_mail/sftp/item/completed etc.
    - Ensure `main.py` credentials are set (via .env) so the email can be sent.
    - Run:
            py .\scan_and_send.py        # preview and generate table.csv
            py .\scan_and_send.py --send # generate table.csv and send email (calls main.py --send)

What it does:
    - Scans immediate child directories of the base folder (default './sftp').
    - For each child (e.g. item, promotion, item_price) counts files under:
             <child>/completed  -> counted as processed
             <child>/errorFile  -> counted as error
    - Writes c:/Users/HP/alerting_mail/table.csv with columns: item,processed,error,total
    - Optionally calls main.py --send to send the email (main.py will include the table.csv automatically)
"""

import os
import csv
import argparse
import subprocess
from pathlib import Path


def count_files(folder: Path) -> int:
    if not folder.exists() or not folder.is_dir():
        return 0
    # count only files (not directories)
    return sum(1 for p in folder.iterdir() if p.is_file())


def scan(base_path: Path):
    rows = []
    if not base_path.exists() or not base_path.is_dir():
        print(f"Base folder not found: {base_path.resolve()}")
        return rows

    for child in sorted(base_path.iterdir()):
        if not child.is_dir():
            continue
        processed = count_files(child / 'completed')
        error = count_files(child / 'errorFile')
        total = processed + error
        rows.append((child.name, str(processed), str(error), str(total)))

    return rows


def write_table_csv(path: Path, rows):
    with path.open('w', newline='', encoding='utf-8') as fh:
        writer = csv.writer(fh)
        writer.writerow(['item', 'processed', 'error', 'total'])
        for r in rows:
            writer.writerow(r)
    print(f'Wrote table to {path}')


def main():
    p = argparse.ArgumentParser(description='Scan sftp folders and generate table.csv, then optionally send email')
    p.add_argument('--base', default='sftp', help='Base folder to scan (default: sftp)')
    p.add_argument('--send', action='store_true', help='Call main.py --send after generating table.csv')
    args = p.parse_args()

    base = Path(args.base)
    rows = scan(base)
    if not rows:
        print('No child folders found or base path missing. Expected structure: sftp/<name>/(completed|errorFile)')
        return

    table_path = Path('table.csv')
    write_table_csv(table_path, rows)

    # Print a quick preview
    print('\nPreview table:')
    for r in rows:
        print(f'{r[0]:<15} processed={r[1]:>3}  error={r[2]:>3}  total={r[3]:>3}')

    if args.send:
        # call main.py to send the email
        print('\nCalling main.py --send to deliver the email...')
        # Use the py launcher on Windows; fallback to python if py fails
        cmd = ['py', '.\\main.py', '--send']
        try:
            subprocess.check_call(cmd)
        except FileNotFoundError:
            cmd[0] = 'python'
            subprocess.check_call(cmd)


if __name__ == '__main__':
    main()
