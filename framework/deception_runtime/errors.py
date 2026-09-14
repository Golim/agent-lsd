"""
Custom error types for safe deception application failure.
"""


class DeceptionApplicationError(Exception):
    """Base exception for deception application errors."""

    def __init__(self, message: str, instance_id: str | None = None, safe: bool = True):
        """
        Initialize deception application error.

        Args:
            message: Error description
            instance_id: Optional instance ID that caused the error
            safe: Whether this error is safe to ignore (fail open)
        """
        super().__init__(message)
        self.message = message
        self.instance_id = instance_id
        self.safe = safe


class HTMLParsingError(DeceptionApplicationError):
    """Error parsing HTML content."""
    pass


class SelectorNotFoundError(DeceptionApplicationError):
    """Required selector not found in HTML."""
    pass


class InvalidPlacementError(DeceptionApplicationError):
    """Invalid placement configuration."""
    pass


class UnsupportedChannelError(DeceptionApplicationError):
    """Unsupported deception channel or surface."""
    pass


class DependencyMissingError(DeceptionApplicationError):
    """Required dependency not available."""

    def __init__(self, dependency: str, message: str | None = None):
        """
        Initialize dependency missing error.

        Args:
            dependency: Name of missing dependency
            message: Optional custom message
        """
        msg = message or f"Required dependency '{dependency}' is not available"
        super().__init__(msg, safe=False)
        self.dependency = dependency


class ContentTooLargeError(DeceptionApplicationError):
    """Response content exceeds maximum size."""
    pass
