"""Los tickets quedan en PostgreSQL y la base rechaza una pregunta vacía."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from psycopg import AsyncConnection
from psycopg.errors import CheckViolation
from psycopg_pool import AsyncConnectionPool
from testcontainers.community.postgres import PostgresContainer

from chatbot.adapters.outbound.persistence.postgres_tickets import PostgresSupportTicketRepository
from chatbot.domain.support_ticket import SupportTicket
from chatbot.infrastructure.persistence.database import migrate_to_latest

pytestmark = [pytest.mark.db, pytest.mark.anyio]


@pytest.fixture(scope="module")
def postgres_url() -> Iterator[str]:
    with PostgresContainer("postgres:17-alpine", driver=None) as container:
        yield container.get_connection_url()


def _ticket(**overrides: object) -> SupportTicket:
    base: dict[str, object] = {
        "id": str(uuid.uuid4()),
        "actor": "visitor:sesion",
        "question": "no entiendo el turno",
        "view": "misiones",
        "created_at": datetime(2026, 10, 5, tzinfo=UTC),
    }
    base.update(overrides)
    return SupportTicket(**base)  # type: ignore[arg-type]


async def test_guarda_y_lista_en_orden(postgres_url: str) -> None:
    admin = await AsyncConnection.connect(postgres_url, autocommit=True)
    name = f"tickets_{uuid.uuid4().hex}"
    await admin.execute(f'create database "{name}"')
    url = postgres_url.rsplit("/", 1)[0] + f"/{name}"
    connection = await AsyncConnection.connect(url)
    assert (await migrate_to_latest(connection)).error is None
    await connection.close()

    pool = AsyncConnectionPool(url, min_size=0, max_size=1, open=False)
    await pool.open(wait=True)
    try:
        repository = PostgresSupportTicketRepository(pool)
        first = _ticket()
        second = _ticket(
            question="sigue sin quedar claro",
            created_at=datetime(2026, 10, 6, tzinfo=UTC),
            view=None,
        )
        await repository.add(first)
        await repository.add(second)
        listed = await repository.list_all()
        assert [ticket.id for ticket in listed] == [first.id, second.id]
        assert listed[1].view is None
    finally:
        await pool.close()
        await admin.execute(f'drop database "{name}"')
        await admin.close()


async def test_la_base_rechaza_una_pregunta_vacia(postgres_url: str) -> None:
    admin = await AsyncConnection.connect(postgres_url, autocommit=True)
    name = f"tickets_{uuid.uuid4().hex}"
    await admin.execute(f'create database "{name}"')
    url = postgres_url.rsplit("/", 1)[0] + f"/{name}"
    connection = await AsyncConnection.connect(url)
    assert (await migrate_to_latest(connection)).error is None
    with pytest.raises(CheckViolation):
        await connection.execute(
            "insert into support_tickets (id, actor, question, view, created_at)"
            " values (%s, %s, %s, %s, %s)",
            (uuid.uuid4(), "visitor:sesion", "   ", None, datetime.now(UTC)),
        )
    await connection.close()
    await admin.execute(f'drop database "{name}"')
    await admin.close()
