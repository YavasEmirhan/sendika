"""Demo hesapları için anlık TOTP kodlarını yazdırır (yalnızca yerel geliştirme).

Gerçek kullanımda kodlar personelin telefonundaki doğrulayıcı uygulamadan gelir.
"""
import json
import time

import pyotp

from scripts.seed import MFA_FILE


def main() -> None:
    if not MFA_FILE.exists():
        print("Önce demo verisini oluşturun: python -m scripts.seed")
        return
    secrets = json.loads(MFA_FILE.read_text())
    remaining = 30 - int(time.time()) % 30
    print(f"Kodlar {remaining} saniye daha geçerli:\n")
    for email, secret in secrets.items():
        print(f"  {pyotp.TOTP(secret).now()}   {email}")


if __name__ == "__main__":
    main()
