class MCPDomainError(RuntimeError):
    def __init__(self, code: str, message: str, data: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data or {}

    def as_dict(self) -> dict:
        return {"error": self.code, "message": self.message, **self.data}
