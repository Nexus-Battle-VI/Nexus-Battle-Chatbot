"""Forma de las respuestas de error, igual que en los servicios NestJS.

Web y los demas consumidores reciben `{statusCode, message, error}` de cualquier
servicio. FastAPI respondia `{detail}` por defecto, y una validacion fallida con
422 donde NestJS responde 400: dos diferencias que el cliente tendria que
conocer por servicio.
"""

from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


def _body(status_code: int, message: object) -> dict[str, object]:
    return {
        "statusCode": status_code,
        "message": message,
        "error": HTTPStatus(status_code).phrase,
    }


async def _http_error(_request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, StarletteHTTPException)  # noqa: S101 - registrado solo para este tipo
    return JSONResponse(
        _body(error.status_code, error.detail),
        status_code=error.status_code,
        headers=error.headers,
    )


async def _validation_error(_request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, RequestValidationError)  # noqa: S101 - registrado solo para este tipo
    messages = [
        f"{'.'.join(str(part) for part in item.get('loc', ()))}: {item.get('msg', '')}"
        for item in error.errors()
    ]
    return JSONResponse(_body(400, messages), status_code=400)


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
