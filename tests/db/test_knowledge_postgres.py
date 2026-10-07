"""El diccionario sobre PostgreSQL real: la base impone lo que el dominio ya exige."""

import uuid
from collections.abc import Iterator

import pytest
from psycopg import AsyncConnection
from psycopg.errors import CheckViolation
from psycopg_pool import AsyncConnectionPool
from testcontainers.community.postgres import PostgresContainer

from chatbot.adapters.outbound.persistence.postgres_knowledge import (
    PostgresKnowledgeEntryRepository,
)
from chatbot.domain.knowledge_entry import KnowledgeEntry, knowledge_entry
from chatbot.infrastructure.persistence.database import migrate_to_latest

pytestmark = [pytest.mark.db, pytest.mark.anyio]


@pytest.fixture(scope="module")
def postgres_url() -> Iterator[str]:
    with PostgresContainer("postgres:17-alpine", driver=None) as container:
        yield container.get_connection_url()


def _entry(**overrides: object) -> KnowledgeEntry:
    base: dict[str, object] = {
        "entry_id": str(uuid.uuid4()),
        "intent": "regla_turno",
        "language": "es",
        "priority": 10,
        "answer": "El combate es por turnos.",
        "variations": ["como funciona el turno"],
    }
    base.update(overrides)
    return knowledge_entry(**base)  # type: ignore[arg-type]


async def test_alta_listado_edicion_y_baja(postgres_url: str) -> None:
    admin = await AsyncConnection.connect(postgres_url, autocommit=True)
    name = f"diccionario_{uuid.uuid4().hex}"
    await admin.execute(f'create database "{name}"')
    url = postgres_url.rsplit("/", 1)[0] + f"/{name}"
    connection = await AsyncConnection.connect(url)
    outcome = await migrate_to_latest(connection)
    await connection.close()
    assert outcome.error is None

    pool = AsyncConnectionPool(url, min_size=0, max_size=1, open=False)
    await pool.open(wait=True)
    try:
        repository = PostgresKnowledgeEntryRepository(pool)
        created = _entry()
        await repository.add(created)
        listed = await repository.list_all()
        assert [entry.id for entry in listed] == [created.id]
        assert listed[0].variations == ("como funciona el turno",)

        changed = _entry(entry_id=created.id, answer="30 segundos.", priority=1)
        assert await repository.save(changed) is True
        stored = await repository.get(created.id)
        assert stored is not None
        assert stored.answer == "30 segundos."
        assert await repository.remove(created.id) is True
        assert await repository.get(created.id) is None
        assert await repository.remove(created.id) is False
    finally:
        await pool.close()
        await admin.execute(f'drop database "{name}"')
        await admin.close()


async def test_la_base_rechaza_un_idioma_que_el_dominio_no_conoce(postgres_url: str) -> None:
    admin = await AsyncConnection.connect(postgres_url, autocommit=True)
    name = f"diccionario_{uuid.uuid4().hex}"
    await admin.execute(f'create database "{name}"')
    url = postgres_url.rsplit("/", 1)[0] + f"/{name}"
    connection = await AsyncConnection.connect(url)
    assert (await migrate_to_latest(connection)).error is None
    with pytest.raises(CheckViolation):
        await connection.execute(
            "insert into knowledge_entries"
            " (id, intent, language, priority, answer, variations)"
            " values (%s, 'regla_turno', 'fr', 1, 'texto', '[\"pregunta\"]'::jsonb)",
            (str(uuid.uuid4()),),
        )
    await connection.close()
    await admin.execute(f'drop database "{name}"')
    await admin.close()
