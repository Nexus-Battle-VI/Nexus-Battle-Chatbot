"""El historial sobrevive en PostgreSQL y el de otra persona no se lee."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool
from testcontainers.community.postgres import PostgresContainer

from chatbot.adapters.outbound.persistence.postgres_transcript import PostgresTranscriptRepository
from chatbot.application.ports.transcript_repository import StoredTurn
from chatbot.infrastructure.persistence.database import migrate_to_latest

pytestmark = [pytest.mark.db, pytest.mark.anyio]


@pytest.fixture(scope="module")
def postgres_url() -> Iterator[str]:
    with PostgresContainer("postgres:17-alpine", driver=None) as container:
        yield container.get_connection_url()


def _turn(turn_id: str | None = None) -> StoredTurn:
    return StoredTurn(
        id=turn_id or str(uuid.uuid4()),
        question="cifrado",
        answer=None,
        language="es",
        intent="regla_turno",
        model_version=None,
        useful=None,
        created_at=datetime(2026, 10, 5, tzinfo=UTC),
    )


async def test_el_historial_queda_y_no_se_mezcla(postgres_url: str) -> None:
    admin = await AsyncConnection.connect(postgres_url, autocommit=True)
    name = f"historial_{uuid.uuid4().hex}"
    await admin.execute(f'create database "{name}"')
    url = postgres_url.rsplit("/", 1)[0] + f"/{name}"
    connection = await AsyncConnection.connect(url)
    assert (await migrate_to_latest(connection)).error is None
    await connection.close()

    pool = AsyncConnectionPool(url, min_size=0, max_size=1, open=False)
    await pool.open(wait=True)
    try:
        repository = PostgresTranscriptRepository(pool)
        turn = _turn()
        await repository.add("player:uno", turn)
        await repository.remember_visitor("sesion-1")
        assert await repository.visitor_known("sesion-1") is True
        assert await repository.visitor_known("sesion-2") is False
        assert [item.id for item in await repository.list_active("player:uno")] == [turn.id]
        assert await repository.list_active("player:dos") == ()
        rated = await repository.set_useful("player:uno", turn.id, True)
        assert rated is not None
        assert rated.useful is True
        assert [item.id for item in await repository.list_rated()] == [turn.id]
        await repository.set_show_time("player:uno", False)
        assert await repository.show_time("player:uno") is False
        assert await repository.show_time("player:dos") is None
        await repository.clear("player:uno")
        assert await repository.list_active("player:uno") == ()
        assert await repository.list_rated() == ()
        assert await repository.get("player:uno", turn.id) is None
    finally:
        await pool.close()
        await admin.execute(f'drop database "{name}"')
        await admin.close()
