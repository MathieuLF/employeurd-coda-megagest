from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ErrorDetail:
    code: str
    message: str
    line_number: int | None = None
    field: str | None = None

    def format(self) -> str:
        parts = [self.code]
        if self.line_number is not None:
            parts.append(f"ligne {self.line_number}")
        if self.field:
            parts.append(self.field)
        return f"{' / '.join(parts)}: {self.message}"


class ConversionError(Exception):
    """Base error for safe conversion failures."""


class ConfigurationError(ConversionError):
    """Raised when configuration is missing or invalid."""


class FileOperationError(ConversionError):
    """Raised when a file cannot be read or written safely."""


class ValidationFailed(ConversionError):
    """Raised when a blocking validation prevents MND generation."""

    def __init__(self, errors: list[ErrorDetail] | str):
        if isinstance(errors, str):
            errors = [ErrorDetail(code="validation_failed", message=errors)]
        self.errors = errors
        super().__init__("\n".join(error.format() for error in errors))
