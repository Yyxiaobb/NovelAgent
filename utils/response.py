from typing import Any

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

def response(*, code: int = 200, message: str = "success", data: Any = None, http_status: int = 200) -> JSONResponse:
    """统一响应封装"""
    content = {"code": code, "message": message, "data": data}
    return JSONResponse(content=jsonable_encoder(content), status_code=http_status)

def success_response(message: str = "success", data: Any = None) -> JSONResponse:
    return response(code=200, message=message, data=data)

def error_response(message: str = "error", code: int = 500, data: Any = None) -> JSONResponse:
    return response(code=code, message=message, data=data)