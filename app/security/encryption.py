import os
import base64
import logging
import threading
from typing import Dict, Any, Optional
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger(__name__)


class DataEncryption:
    def __init__(self, encryption_key: Optional[bytes] = None):
        if encryption_key is None:
            key_str = os.environ.get("ENCRYPTION_KEY")
            if key_str:
                encryption_key = base64.urlsafe_b64decode(key_str)
            else:
                encryption_key = Fernet.generate_key()
                encoded = base64.urlsafe_b64encode(encryption_key).decode()
                logger.warning(
                    f"未设置 ENCRYPTION_KEY 环境变量，已生成临时密钥。"
                    f"生产环境请设置该变量: {encoded}"
                )

        self.fernet = Fernet(encryption_key)

    def encrypt_field(self, plaintext: str) -> str:
        if not plaintext:
            return ""
        encrypted = self.fernet.encrypt(plaintext.encode())
        return base64.urlsafe_b64encode(encrypted).decode()

    def decrypt_field(self, ciphertext: str) -> str:
        if not ciphertext:
            return ""
        try:
            encrypted = base64.urlsafe_b64decode(ciphertext.encode())
            decrypted = self.fernet.decrypt(encrypted)
            return decrypted.decode()
        except Exception:
            logger.error("数据解密失败", exc_info=True)
            return ""

    def encrypt_sensitive_user_data(self, user_data: Dict) -> Dict:
        sensitive_fields = [
            "email",
            "phone",
            "real_name",
            "id_card",
            "address",
            "emergency_contact",
        ]

        encrypted_data = user_data.copy()
        for field in sensitive_fields:
            if field in encrypted_data and encrypted_data[field]:
                encrypted_data[field] = self.encrypt_field(
                    str(encrypted_data[field])
                )
                encrypted_data[f"{field}_encrypted"] = True

        return encrypted_data

    @staticmethod
    def hash_password(password: str) -> str:
        salt = os.urandom(16)
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=600000,
        )
        key = kdf.derive(password.encode())
        return base64.urlsafe_b64encode(salt + key).decode()

    @staticmethod
    def verify_password(hashed_password: str, password: str) -> bool:
        try:
            decoded = base64.urlsafe_b64decode(hashed_password)
            salt = decoded[:16]
            stored_key = decoded[16:]

            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=600000,
            )
            new_key = kdf.derive(password.encode())
            return stored_key == new_key
        except Exception:
            return False


_encryption_instance: Optional[DataEncryption] = None
_lock = threading.Lock()


def get_encryption() -> DataEncryption:
    global _encryption_instance
    if _encryption_instance is None:
        with _lock:
            if _encryption_instance is None:
                _encryption_instance = DataEncryption()
    return _encryption_instance