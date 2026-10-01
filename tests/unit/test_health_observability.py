import json
from datetime import UTC, datetime

import pytest

from chatbot.adapters.outbound.system.clock import SystemClock
from chatbot.infrastructure.health.health import (
    ReadinessCheck,
    build_liveness,
    build_readiness,
    build_version,
)
from chatbot.infrastructure.observability.describe_error import describe_error
from chatbot.infrastructure.observability.logger import JsonLogger


async def _ok() -> bool:
    return True


async def _down() -> bool:
    return False


async def _explodes() -> bool:
    raise RuntimeError("motor caido")


def test_liveness_no_consulta_dependencias() -> None:
    assert build_liveness() == {"status": "ok", "checks": {}}


@pytest.mark.anyio
async def test_readiness_sana_con_todas_las_dependencias() -> None:
    report = await build_readiness([ReadinessCheck("database", _ok)])
    assert report == {"status": "ok", "checks": {"database": "ok"}}


@pytest.mark.anyio
async def test_readiness_falla_si_una_dependencia_falla_o_lanza() -> None:
    report = await build_readiness(
        [ReadinessCheck("a", _ok), ReadinessCheck("b", _down), ReadinessCheck("c", _explodes)]
    )
    assert report == {"status": "error", "checks": {"a": "ok", "b": "error", "c": "error"}}


def test_version() -> None:
    assert build_version("nexus-battle-chatbot", "0.1.0", "test") == {
        "service": "nexus-battle-chatbot",
        "version": "0.1.0",
        "environment": "test",
    }


def test_registro_json_con_el_formato_de_los_servicios_nestjs() -> None:
    lines: list[str] = []
    logger = JsonLogger(
        level="info",
        service="nexus-battle-chatbot",
        version="0.1.0",
        sink=lines.append,
        clock=lambda: datetime(2026, 9, 30, 12, 0, 0, 123456, tzinfo=UTC),
    )
    logger.debug("no_aparece")
    logger.info("arranque", {"port": 3011})
    logger.warn("aviso")
    logger.error("fallo", {"detail": "ñ"})

    assert len(lines) == 3
    first = json.loads(lines[0])
    assert first == {
        "timestamp": "2026-09-30T12:00:00.123Z",
        "level": "info",
        "service": "nexus-battle-chatbot",
        "version": "0.1.0",
        "message": "arranque",
        "port": 3011,
    }
    assert json.loads(lines[1])["level"] == "warn"
    assert "ñ" in lines[2]


def test_el_contexto_no_sobrescribe_los_campos_fijos() -> None:
    lines: list[str] = []
    logger = JsonLogger(
        level="info", service="nexus-battle-chatbot", version="0.1.0", sink=lines.append
    )
    logger.info("aceptada", {"service": "combat", "caller": "combat"})
    record = json.loads(lines[0])
    assert record["service"] == "nexus-battle-chatbot"
    assert record["caller"] == "combat"


def test_registro_por_defecto_escribe_en_la_salida(capsys: pytest.CaptureFixture[str]) -> None:
    JsonLogger(level="debug", service="s", version="v").debug("hola")
    assert '"message":"hola"' in capsys.readouterr().out


def test_describe_errores_sin_texto_inutil() -> None:
    assert describe_error(RuntimeError("sql invalido")) == "sql invalido"
    assert describe_error(RuntimeError()) == "RuntimeError"
    assert describe_error({"a": 1}) == "{'a': 1}"


def test_reloj_del_sistema_en_utc() -> None:
    assert SystemClock().now().tzinfo is UTC
