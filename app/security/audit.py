import logging
import json
import os
import threading
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional


class AuditLogger:
    def __init__(self, log_file: str = "logs/audit.log"):
        os.makedirs(os.path.dirname(log_file), exist_ok=True)

        self.logger = logging.getLogger("audit")
        self.logger.setLevel(logging.INFO)

        if not self.logger.handlers:
            handler = logging.FileHandler(log_file, encoding="utf-8")
            formatter = logging.Formatter(
                "%(asctime)s | %(levelname)s | %(message)s"
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

    def log_access(
        self,
        user_id: str,
        resource_type: str,
        resource_id: str,
        action: str,
        ip_address: str = "",
        user_agent: str = "",
    ):
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": "DATA_ACCESS",
            "user_id": user_id,
            "resource": f"{resource_type}:{resource_id}",
            "action": action,
            "ip": ip_address,
            "user_agent": user_agent[:100] if user_agent else "",
        }
        self.logger.info(json.dumps(log_entry, ensure_ascii=False))

    def log_modification(
        self,
        user_id: str,
        resource_type: str,
        resource_id: str,
        old_value: Dict,
        new_value: Dict,
        changed_fields: List[str],
    ):
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": "DATA_MODIFICATION",
            "user_id": user_id,
            "resource": f"{resource_type}:{resource_id}",
            "changed_fields": changed_fields,
            "old_value": self._sanitize(old_value),
            "new_value": self._sanitize(new_value),
        }
        self.logger.warning(json.dumps(log_entry, ensure_ascii=False))

    def log_deletion(
        self,
        user_id: str,
        resource_type: str,
        resource_id: str,
        reason: str = "",
    ):
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": "DATA_DELETION",
            "user_id": user_id,
            "resource": f"{resource_type}:{resource_id}",
            "reason": reason,
        }
        self.logger.critical(json.dumps(log_entry, ensure_ascii=False))

    def log_export(
        self,
        user_id: str,
        export_type: str,
        record_count: int,
        filters_applied: Optional[Dict] = None,
    ):
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": "DATA_EXPORT",
            "user_id": user_id,
            "export_type": export_type,
            "record_count": record_count,
            "filters": filters_applied,
        }
        self.logger.warning(json.dumps(log_entry, ensure_ascii=False))

    def log_login(
        self,
        user_id: str,
        success: bool,
        ip_address: str = "",
        reason: str = "",
    ):
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": "LOGIN_ATTEMPT",
            "user_id": user_id,
            "success": success,
            "ip": ip_address,
            "reason": reason,
        }
        level = logging.INFO if success else logging.WARNING
        self.logger.log(level, json.dumps(log_entry, ensure_ascii=False))

    def _sanitize(self, data: Dict) -> Dict:
        sensitive_keys = {
            "password",
            "password_hash",
            "token",
            "secret",
            "key",
            "api_key",
        }
        sanitized = {}
        for k, v in data.items():
            if k in sensitive_keys:
                sanitized[k] = "***REDACTED***"
            elif isinstance(v, dict):
                sanitized[k] = self._sanitize(v)
            else:
                sanitized[k] = v
        return sanitized

    def close(self):
        for handler in self.logger.handlers[:]:
            handler.close()
            self.logger.removeHandler(handler)


_audit_logger: Optional[AuditLogger] = None
_lock = threading.Lock()


def get_audit_logger() -> AuditLogger:
    global _audit_logger
    if _audit_logger is None:
        with _lock:
            if _audit_logger is None:
                _audit_logger = AuditLogger()
    return _audit_logger