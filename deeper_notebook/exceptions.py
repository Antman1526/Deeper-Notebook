class DeeperNotebookError(Exception):
    """Base exception class for Deeper Notebook errors."""

    pass


OpenNotebookError = DeeperNotebookError
"""Deprecated public alias retained for existing integrations."""


class DatabaseOperationError(DeeperNotebookError):
    """Raised when a database operation fails."""

    pass


class UnsupportedTypeException(DeeperNotebookError):
    """Raised when an unsupported type is provided."""

    pass


class InvalidInputError(DeeperNotebookError):
    """Raised when invalid input is provided."""

    pass


class NotFoundError(DeeperNotebookError):
    """Raised when a requested resource is not found."""

    pass


class AuthenticationError(DeeperNotebookError):
    """Raised when there's an authentication problem."""

    pass


class ConfigurationError(DeeperNotebookError):
    """Raised when there's a configuration problem."""

    pass


class ExternalServiceError(DeeperNotebookError):
    """Raised when an external service (e.g., AI model) fails."""

    pass


class RateLimitError(DeeperNotebookError):
    """Raised when a rate limit is exceeded."""

    pass


class FileOperationError(DeeperNotebookError):
    """Raised when a file operation fails."""

    pass


class NetworkError(DeeperNotebookError):
    """Raised when a network operation fails."""

    pass


class NoTranscriptFound(DeeperNotebookError):
    """Raised when no transcript is found for a video."""

    pass
