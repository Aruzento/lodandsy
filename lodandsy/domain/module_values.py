from uuid import UUID


def validate_id(value):
    if not isinstance(value, str):
        raise ValueError("ID must be a canonical UUID")
    try:
        if str(UUID(value)) != value:
            raise ValueError("ID must be a canonical UUID")
    except (ValueError, AttributeError):
        raise ValueError("ID must be a canonical UUID") from None


def validate_title(value):
    if not isinstance(value, str) or not value.strip() or any(c in value for c in "\r\n\0"):
        raise ValueError("Название должно быть непустой строкой")
    return value.strip()
