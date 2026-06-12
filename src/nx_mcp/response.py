from dataclasses import dataclass

@dataclass
class ToolResult:
    message: str
    def __str__(self): return f"OK: {self.message}"
    def is_ok(self): return True

@dataclass
class ToolError:
    error: str
    def __str__(self): return f"ERROR: {self.error}"
    def is_ok(self): return False