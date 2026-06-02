"""macOS Keychain integration via the `keyring` library."""
import logging
import keyring

log = logging.getLogger(__name__)
SERVICE_NAME = "CaptainAI"


class KeychainStore:

    def store(self, key: str, value: str) -> None:
        keyring.set_password(SERVICE_NAME, key, value)
        log.debug(f"Stored secret: {key}")

    def retrieve(self, key: str) -> str | None:
        return keyring.get_password(SERVICE_NAME, key)

    def delete(self, key: str) -> None:
        try:
            keyring.delete_password(SERVICE_NAME, key)
        except keyring.errors.PasswordDeleteError:
            pass

    def store_if_absent(self, key: str, value: str) -> None:
        if not self.retrieve(key):
            self.store(key, value)


keychain = KeychainStore()
