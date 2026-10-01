import pytest


@pytest.fixture
def anyio_backend() -> str:
    # Solo asyncio: es el bucle con el que corre uvicorn en produccion.
    return "asyncio"
