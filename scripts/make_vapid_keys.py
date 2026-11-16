"""Make the key pair for push alerts (VAPID), once.

  python scripts/make_vapid_keys.py

Prints two lines. The PUBLIC key goes into infra/main.dev.local.bicepparam
(param vapidPublicKey = '...'). The PRIVATE key goes into Key Vault as the secret
'vapid-private-key' and nowhere else: never into Git, never into a chat.
"""

from __future__ import annotations

import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def main() -> None:
    key = ec.generate_private_key(ec.SECP256R1())
    private = key.private_numbers().private_value.to_bytes(32, "big")
    public = key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    print(f"PUBLIC  {b64(public)}")
    print(f"PRIVATE {b64(private)}")


if __name__ == "__main__":
    main()
