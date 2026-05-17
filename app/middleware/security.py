import re
import html
from typing import Any, Dict, List, Optional


XSS_PATTERNS = [
    re.compile(r"<\s*script[^>]*>", re.IGNORECASE),
    re.compile(r"<\s*iframe[^>]*>", re.IGNORECASE),
    re.compile(r"<\s*object[^>]*>", re.IGNORECASE),
    re.compile(r"<\s*embed[^>]*>", re.IGNORECASE),
    re.compile(r"<\s*form[^>]*>", re.IGNORECASE),
    re.compile(r"javascript\s*:", re.IGNORECASE),
    re.compile(r"vbscript\s*:", re.IGNORECASE),
    re.compile(r"on\w+\s*=", re.IGNORECASE),
    re.compile(r"<\s*img[^>]+on\w+\s*=", re.IGNORECASE),
    re.compile(r"<\s*a[^>]+on\w+\s*=", re.IGNORECASE),
    re.compile(r"<\s*svg[^>]*>", re.IGNORECASE),
    re.compile(r"<\s*math[^>]*>", re.IGNORECASE),
    re.compile(r"expression\s*\(", re.IGNORECASE),
    re.compile(r"url\s*\(", re.IGNORECASE),
]

SQL_INJECTION_PATTERNS = [
    re.compile(r"(\b(union)\b\s+\b(select)\b)", re.IGNORECASE),
    re.compile(r"(\b(select)\b\s+.*?\b(from)\b)", re.IGNORECASE),
    re.compile(r"(\b(insert)\b\s+\b(into)\b)", re.IGNORECASE),
    re.compile(r"(\b(delete)\b\s+\b(from)\b)", re.IGNORECASE),
    re.compile(r"(\b(drop)\b\s+\b(table|database)\b)", re.IGNORECASE),
    re.compile(r"(\b(update)\b\s+\w+\s+\b(set)\b)", re.IGNORECASE),
    re.compile(r"(\b(alter)\b\s+\b(table)\b)", re.IGNORECASE),
    re.compile(r"(--\s*$)", re.IGNORECASE | re.MULTILINE),
    re.compile(r"(;\s*(drop|delete|update|alter|insert)\b)", re.IGNORECASE),
    re.compile(r"('\s*(or|and)\s+\d)", re.IGNORECASE),
    re.compile(r"(\bexec\b\s*\()", re.IGNORECASE),
    re.compile(r"(\bexecute\b\s*\()", re.IGNORECASE),
]

PATH_TRAVERSAL_PATTERNS = [
    re.compile(r"\.\./"),
    re.compile(r"\.\.\\"),
    re.compile(r"\b/etc/passwd\b"),
    re.compile(r"\b/etc/shadow\b"),
    re.compile(r"\b\\windows\\system32\b", re.IGNORECASE),
]


class SecurityValidationError(Exception):
    def __init__(self, message: str, threat_type: str = "unknown"):
        self.message = message
        self.threat_type = threat_type
        super().__init__(self.message)


def sanitize_string(value: str, max_length: int = 50000) -> str:
    if not isinstance(value, str):
        value = str(value)

    if len(value) > max_length:
        value = value[:max_length]

    value = value.replace("\x00", "")

    return value


def detect_xss(value: str) -> Optional[str]:
    if not isinstance(value, str):
        return None
    for pattern in XSS_PATTERNS:
        match = pattern.search(value)
        if match:
            return match.group(0)
    return None


def detect_sql_injection(value: str) -> Optional[str]:
    if not isinstance(value, str):
        return None
    for pattern in SQL_INJECTION_PATTERNS:
        match = pattern.search(value)
        if match:
            return match.group(0)
    return None


def detect_path_traversal(value: str) -> Optional[str]:
    if not isinstance(value, str):
        return None
    for pattern in PATH_TRAVERSAL_PATTERNS:
        match = pattern.search(value)
        if match:
            return match.group(0)
    return None


def escape_html(value: str) -> str:
    if not isinstance(value, str):
        return value
    return html.escape(value, quote=True)


def validate_input(value: Any, field_name: str = "", max_length: int = 50000,
                   allow_html: bool = False, skip_sql_check: bool = False) -> Any:
    if value is None:
        return value

    if isinstance(value, str):
        value = sanitize_string(value, max_length)

        xss_match = detect_xss(value)
        if xss_match:
            raise SecurityValidationError(
                f"输入包含潜在的危险内容（XSS攻击特征）: {field_name}",
                threat_type="xss",
            )

        if not skip_sql_check:
            sql_match = detect_sql_injection(value)
            if sql_match:
                raise SecurityValidationError(
                    f"输入包含潜在的危险内容（SQL注入特征）: {field_name}",
                    threat_type="sql_injection",
                )

        path_match = detect_path_traversal(value)
        if path_match:
            raise SecurityValidationError(
                f"输入包含潜在的危险内容（路径遍历特征）: {field_name}",
                threat_type="path_traversal",
            )

        if not allow_html:
            value = escape_html(value)

        return value

    if isinstance(value, list):
        return [validate_input(item, f"{field_name}[{i}]", max_length, allow_html, skip_sql_check)
                for i, item in enumerate(value)]

    if isinstance(value, dict):
        return {k: validate_input(v, f"{field_name}.{k}", max_length, allow_html, skip_sql_check)
                for k, v in value.items()}

    return value


def validate_request_data(data: Dict[str, Any], max_length: int = 50000, skip_sql_check: bool = False) -> Dict[str, Any]:
    validated = {}
    for key, value in data.items():
        validated[key] = validate_input(value, field_name=key, max_length=max_length, skip_sql_check=skip_sql_check)
    return validated


def is_safe_image_data(data: str) -> bool:
    if not isinstance(data, str):
        return False

    if data.startswith("data:image/"):
        mime_part = data[:50]
        if not re.match(r"^data:image/(png|jpeg|jpg|gif|webp|bmp);base64,", mime_part):
            return False
        return True

    if re.match(r"^[A-Za-z0-9+/=\s]+$", data) and len(data) > 100:
        return True

    return False
