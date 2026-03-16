"""Textual input validators for the Add mount form."""

from __future__ import annotations

from textual.validation import ValidationResult, Validator


class MountNameValidator(Validator):
    def validate(self, value: str) -> ValidationResult:
        if not value:
            return self.failure("Required")
        if any(c in value for c in (" ", "\t", "/")):
            return self.failure("No spaces or slashes")
        return self.success()


class AbsolutePathValidator(Validator):
    def validate(self, value: str) -> ValidationResult:
        if not value:
            return self.failure("Required")
        if not value.startswith("/"):
            return self.failure("Must be an absolute path")
        return self.success()


class PositiveIntValidator(Validator):
    def __init__(self, minimum: int = 1) -> None:
        super().__init__()
        self.minimum = minimum

    def validate(self, value: str) -> ValidationResult:
        try:
            if int(value) < self.minimum:
                return self.failure(f"Must be >= {self.minimum}")
            return self.success()
        except ValueError:
            return self.failure("Must be an integer")
