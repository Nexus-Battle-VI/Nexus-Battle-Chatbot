"""Cifrado del historial de la sesion. La clave no sale del proceso."""

from cryptography.fernet import Fernet


class FernetTextCipher:
    def __init__(self, key: bytes) -> None:
        self._fernet = Fernet(key)

    @staticmethod
    def generate_key() -> bytes:
        return Fernet.generate_key()

    def encrypt(self, text: str) -> str:
        return self._fernet.encrypt(text.encode()).decode()

    def decrypt(self, token: str) -> str:
        return self._fernet.decrypt(token.encode()).decode()
