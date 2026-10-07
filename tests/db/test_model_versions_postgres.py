"""Las versiones y el arrendamiento contra PostgreSQL real."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool
from testcontainers.community.postgres import PostgresContainer

from chatbot.adapters.outbound.persistence.postgres_versions import PostgresModelVersionRepository
from chatbot.application.ports.model_version_repository import ModelVersion
from chatbot.domain.training_set import ValidationMetrics
from chatbot.infrastructure.persistence.database import create_pool, migrate_to_latest

pytestmark = [pytest.mark.db, pytest.mark.anyio]

_NOW = datetime(2026, 10, 5, tzinfo=UTC)


@pytest.fixture(scope="module")
def postgres_url() -> Iterator[str]:
    with PostgresContainer("postgres:17-alpine", driver=None) as container:
        yield container.get_connection_url()


def _version(suffix: str) -> ModelVersion:
    return ModelVersion(
        id=f"00000000-0000-4000-8000-0000000000{suffix}",
        state="CANDIDATE",
        accuracy=0.9,
        macro_f1=0.85,
        metrics=ValidationMetrics(
            0.9,
            0.85,
            (("es:cuenta", 0.85),),
            (("es:cuenta", "es:cuenta", 4),),
        ),
        single_example_labels=("es:sola",),
        artifact=b"modelo",
        created_at=_NOW,
    )


async def _repository(
    postgres_url: str,
) -> tuple[PostgresModelVersionRepository, AsyncConnectionPool]:
    async with await AsyncConnection.connect(postgres_url) as connection:
        await migrate_to_latest(connection)
    pool = create_pool(postgres_url)
    await pool.open()
    return PostgresModelVersionRepository(pool), pool


async def test_promover_deja_una_sola_activa(postgres_url: str) -> None:
    repository, pool = await _repository(postgres_url)
    try:
        first = _version("31")
        second = _version("32")
        await repository.add_candidate(first)
        assert await repository.promote(first.id) is True
        await repository.add_candidate(second)
        assert await repository.promote(second.id) is True
        active = await repository.active()
        assert active is not None
        assert active.id == second.id
        assert active.macro_f1 == 0.85
        assert active.single_example_labels == ("es:sola",)
        assert active.artifact == b"modelo"
    finally:
        await pool.close()


async def test_el_arrendamiento_impide_dos_entrenos_a_la_vez(postgres_url: str) -> None:
    repository, pool = await _repository(postgres_url)
    try:
        assert await repository.try_acquire(_NOW, _NOW + timedelta(minutes=15)) is True
        assert await repository.try_acquire(_NOW, _NOW + timedelta(minutes=15)) is False
        await repository.release()
        assert await repository.try_acquire(_NOW, _NOW + timedelta(minutes=15)) is True
    finally:
        await pool.close()


async def test_la_candidata_en_prueba_y_la_precision(postgres_url: str) -> None:
    repository, pool = await _repository(postgres_url)
    try:
        first = _version("41")
        second = _version("42")
        await repository.add_candidate(first)
        await repository.add_candidate(second)
        assert await repository.mark_experiment(first.id) is True
        assert await repository.mark_experiment(second.id) is True
        current = await repository.experiment_candidate()
        assert current is not None
        assert current.id == second.id
        await repository.record_answer(second.id, True)
        await repository.record_answer(second.id, None)
        counts = await repository.rating_counts()
        assert counts[second.id] == (1, 0)
    finally:
        await pool.close()
