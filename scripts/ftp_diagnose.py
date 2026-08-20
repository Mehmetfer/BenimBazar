#!/usr/bin/env python3
"""FTP hedef klasor teshisi."""
import hashlib
import json
from ftplib import FTP
from io import BytesIO
from pathlib import Path
import urllib.request

CREDS = Path(__file__).with_name("ftp-credentials.local.json")
LOCAL = Path(__file__).resolve().parents[1] / "php-site" / "test.php"

c = json.loads(CREDS.read_text())
ftp = FTP(c["host"], timeout=60)
ftp.set_pasv(True)
ftp.login(c["user"], c["password"])
print("FTP PWD:", ftp.pwd())

for p in ["", "changex.mehmetfer.com.tr", "public_html"]:
    try:
        ftp.cwd("/")
        for part in p.split("/"):
            if part:
                ftp.cwd(part)
        bio = BytesIO()
        ftp.retrbinary("RETR version.php", bio.write)
        md5 = hashlib.md5(bio.getvalue()).hexdigest()
        print(f"  {p or 'ROOT'} version.php md5={md5[:16]} size={bio.tell()}")
    except Exception as e:
        print(f"  {p or 'ROOT'} version.php MISSING:", e)

ftp.cwd("/")
bio = BytesIO()
ftp.retrbinary("RETR test.php", bio.write)
print("FTP ROOT test.php md5:", hashlib.md5(bio.getvalue()).hexdigest()[:16])
print("LOCAL test.php md5:", hashlib.md5(LOCAL.read_bytes()).hexdigest()[:16])
ftp.quit()

try:
    live = urllib.request.urlopen("http://changex.mehmetfer.com.tr/test.php", timeout=15).read(200)
    print("LIVE test starts:", live[:60])
    print("LIVE is HTML:", b"FTP Deploy Test" in live or b"<!DOCTYPE" in live)
except Exception as e:
    print("LIVE fetch fail:", e)
