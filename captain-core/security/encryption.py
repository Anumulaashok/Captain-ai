"""AES-256-GCM local encryption for sensitive stored data."""
import base64
import logging
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

log = logging.getLogger(__name__)
KEY_KEYCHAIN_ID = "db_encryption_key"


class LocalEncryption:

    def _get_key(self) -> bytes:
        from security.keychain import keychain
        stored = keychain.retrieve(KEY_KEYCHAIN_ID)
        if stored:
            return base64.b64decode(stored)
        # Generate a new 256-bit key and store in Keychain
        key = AESGCM.generate_key(bit_length=256)
        keychain.store(KEY_KEYCHAIN_ID, base64.b64encode(key).decode())
        log.info("Generated new AES-256 encryption key stored in Keychain")
        return key

    def encrypt(self, plaintext: str) -> str:
        key = self._get_key()
        aesgcm = AESGCM(key)
        nonce = os.urandom(12)
        ct = aesgcm.encrypt(nonce, plaintext.encode(), None)
        return base64.b64encode(nonce + ct).decode()

    def decrypt(self, ciphertext: str) -> str:
        key = self._get_key()
        aesgcm = AESGCM(key)
        data = base64.b64decode(ciphertext)
        nonce, ct = data[:12], data[12:]
        return aesgcm.decrypt(nonce, ct, None).decode()


encryption = LocalEncryption()
