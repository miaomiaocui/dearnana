"""DearNana exception types."""


class DataFetchError(Exception):
    """Raised when a remote data source cannot be reached after retries.

    Carries a user-facing message suitable for direct display.
    """
