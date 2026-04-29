"""AES-GCM and handshake helpers; OOP facade :class:`CTAPCrypto`."""

import base64
import binascii
import hashlib
import hmac
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

FIXED_AES_KEY_HEX = (
    "000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f"
)
HANDSHAKE_SECRET = "CTAP-GLOVE-AUTH-2026"


class CTAPCrypto:
    """Symmetric crypto + handshake verification for CTAP wire format."""

    __slots__ = ("_aesgcm",)

    def __init__(self, key_hex: str = FIXED_AES_KEY_HEX) -> None:
        key = binascii.unhexlify(key_hex)
        self._aesgcm = AESGCM(key)

    def decrypt_payload(self, payload: dict) -> str:
        try:
            nonce = base64.b64decode(payload["nonce"])
            ciphertext = base64.b64decode(payload["ciphertext"])
            plaintext_bytes = self._aesgcm.decrypt(nonce, ciphertext, None)
            return plaintext_bytes.decode("utf-8")
        except Exception as e:
            return f"[DECRYPTION FAILED] {e}"

    def verify_handshake_hash(self, challenge: str, response_hash: str) -> bool:
        if not response_hash or len(response_hash) != 64:
            return False
        if not all(c in "0123456789abcdefABCDEF" for c in response_hash):
            return False
        expected = hashlib.sha256(
            (challenge + HANDSHAKE_SECRET).encode("utf-8")
        ).hexdigest()
        try:
            return hmac.compare_digest(
                expected.lower().encode("ascii"),
                response_hash.lower().encode("ascii"),
            )
        except Exception:
            return False

    @staticmethod
    def generate_challenge() -> str:
        return os.urandom(16).hex()

    @staticmethod
    def generate_hash(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()


_default_crypto = CTAPCrypto()


def decrypt_payload(payload: dict) -> str:
    return _default_crypto.decrypt_payload(payload)


def verify_handshake_hash(challenge: str, response_hash: str) -> bool:
    return _default_crypto.verify_handshake_hash(challenge, response_hash)


def generate_challenge() -> str:
    return CTAPCrypto.generate_challenge()


def generate_hash(content: str) -> str:
    return CTAPCrypto.generate_hash(content)
