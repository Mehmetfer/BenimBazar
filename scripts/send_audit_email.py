#!/usr/bin/env python3
"""Audit raporunu e-posta ile gonderir.

Gerekli ortam degiskenleri:
  SMTP_HOST (varsayilan: smtp.gmail.com)
  SMTP_PORT (varsayilan: 587)
  SMTP_USER (ornek: mehmetfer@gmail.com)
  SMTP_PASSWORD (Gmail icin uygulama sifresi)
  MAIL_TO (varsayilan: mehmetfer@gmail.com)
"""

from __future__ import annotations

import os
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "docs" / "BenimBazar-Rakip-Audit-2026-08-15.md"


def main() -> None:
    user = os.environ.get("SMTP_USER", "").strip()
    password = os.environ.get("SMTP_PASSWORD", "").strip()
    mail_to = os.environ.get("MAIL_TO", "mehmetfer@gmail.com").strip()
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com").strip()
    port = int(os.environ.get("SMTP_PORT", "587"))

    if not user or not password:
        raise SystemExit(
            "SMTP_USER ve SMTP_PASSWORD ortam degiskenleri gerekli.\n"
            "Gmail: Google Hesap > Guvenlik > 2FA > Uygulama sifreleri"
        )
    if not REPORT.is_file():
        raise SystemExit(f"Rapor bulunamadi: {REPORT}")

    body = REPORT.read_text(encoding="utf-8")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "BenimBazar Rakip UX Audit — 15 Agustos 2026"
    msg["From"] = user
    msg["To"] = mail_to
    msg.attach(MIMEText(body, "plain", "utf-8"))

    ctx = ssl.create_default_context()
    with smtplib.SMTP(host, port, timeout=60) as server:
        server.ehlo()
        server.starttls(context=ctx)
        server.ehlo()
        server.login(user, password)
        server.sendmail(user, [mail_to], msg.as_string())

    print(f"OK gonderildi: {mail_to}")


if __name__ == "__main__":
    main()
