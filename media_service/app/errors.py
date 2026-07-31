from __future__ import annotations


class MediaComponentError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def provider_error_code(component: str, error: Exception) -> str:
    if isinstance(error, TimeoutError):
        return f"{component.upper()}_TIMEOUT"
    return f"{component.upper()}_{type(error).__name__.upper()}"
