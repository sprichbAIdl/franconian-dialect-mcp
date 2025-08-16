class BDOApiError(Exception):
    """Custom exception for BDO API related errors."""
    
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
