from typing import Any
from fastapi.responses import JSONResponse

def success_response(message: str, data: Any = None, status_code: int = 200) -> JSONResponse:
    content = {
        "success": True,
        "message": message,
        "data": data
    }
    return JSONResponse(content=content, status_code=status_code)

def error_response(message: str, error_code: str = "BAD_REQUEST", status_code: int = 400) -> JSONResponse:
    content = {
        "success": False,
        "message": message,
        "error": error_code,
        "data": None
    }
    return JSONResponse(content=content, status_code=status_code)
