"""Infraestructura de persistencia contra un PostgreSQL REAL (Testcontainers).

Lo que se comprueba no se puede comprobar con un doble: que el pool conecta,
que el migrador registra lo aplicado y no lo repite, que una migracion rota se
informa en vez de darse por buena, y que el servicio sobrevive a que el motor
corte sus conexiones.
"""

import uuid
from collections.abc import AsyncIterator, Iterator

import pytest
from psycopg import AsyncConnection
from testcontainers.community.postgres import PostgresContainer

from chatbot.infrastructure.persistence.database import (
    MIGRATIONS,
    Migration,
    MigrationOrderError,
    create_pool,
    migrate_to_latest,
    ping_database,
)

pytestmark = [pytest.mark.db, pytest.mark.anyio]


@pytest.fixture(scope="module")
def postgres_url() -> Iterator[str]:
    with PostgresContainer("postgres:17-alpine", driver=None) as container:
        yield container.get_connection_url()


@pytest.fixture
async def connection(postgres_url: str) -> AsyncIterator[AsyncConnection]:
    # Una base nueva por prueba: el registro de migraciones de una no debe
    # condicionar a la siguiente, ni su orden de ejecucion.
    name = f"prueba_{uuid.uuid4().hex}"
    admin = await AsyncConnection.connect(postgres_url, autocommit=True)
    await admin.execute(f'create database "{name}"')
    conn = await AsyncConnection.connect(postgres_url.rsplit("/", 1)[0] + f"/{name}")
    try:
        yield conn
    finally:
        await conn.close()
        await admin.execute(f'drop database "{name}"')
        await admin.close()


async def test_la_sonda_responde_contra_un_motor_disponible(postgres_url: str) -> None:
    pool = create_pool(postgres_url)
    await pool.open(wait=False)
    try:
        assert await ping_database(pool) is True
    finally:
        await pool.close()


async def test_la_sonda_falla_contra_un_motor_inalcanzable() -> None:
    # Control de la anterior: si la sonda devolviera siempre `True`, pasaria igual.
    pool = create_pool("postgresql://nadie:nada@127.0.0.1:1/ninguna")
    await pool.open(wait=False)
    try:
        assert await ping_database(pool) is False
    finally:
        await pool.close()


async def test_aplica_las_migraciones_del_producto_sin_error(connection: AsyncConnection) -> None:
    outcome = await migrate_to_latest(connection)
    assert outcome.error is None
    assert outcome.applied == [migration.name for migration in MIGRATIONS]


async def test_registra_las_migraciones_aplicadas_y_no_las_repite(
    connection: AsyncConnection,
) -> None:
    migrations = [Migration("900-prueba", "create table prueba (id text)")]

    assert (await migrate_to_latest(connection, migrations)).applied == ["900-prueba"]
    assert (await migrate_to_latest(connection, migrations)).applied == []

    cursor = await connection.execute("select to_regclass('public.prueba') is not null")
    row = await cursor.fetchone()
    assert row == (True,)


async def test_informa_una_migracion_rota_y_no_aplica_ninguna(
    connection: AsyncConnection,
) -> None:
    outcome = await migrate_to_latest(
        connection,
        [
            Migration("900-prueba", "create table prueba (id text)"),
            Migration("901-buena", "create table buena (id text)"),
            Migration("902-rota", "esto no es sql"),
        ],
    )
    assert outcome.applied == []
    assert outcome.error is not None
    # Todas las pendientes van en una transaccion: la buena tampoco quedo.
    cursor = await connection.execute("select to_regclass('public.buena') is null")
    assert await cursor.fetchone() == (True,)


async def test_se_niega_si_la_base_va_por_delante_del_codigo(connection: AsyncConnection) -> None:
    await migrate_to_latest(connection, [Migration("900-prueba", "select 1")])
    outcome = await migrate_to_latest(connection, [])
    assert isinstance(outcome.error, MigrationOrderError)


async def test_exige_orden_y_nombres_unicos(connection: AsyncConnection) -> None:
    desordenadas = [Migration("002-b", "select 1"), Migration("001-a", "select 1")]
    repetidas = [Migration("001-a", "select 1"), Migration("001-a", "select 1")]
    assert isinstance(
        (await migrate_to_latest(connection, desordenadas)).error, MigrationOrderError
    )
    assert isinstance((await migrate_to_latest(connection, repetidas)).error, MigrationOrderError)


async def test_sobrevive_a_que_el_motor_corte_las_conexiones_del_pool(postgres_url: str) -> None:
    """Reproduce lo que tumbaba los servicios con `pg` en Sprint 2.

    Se terminan desde fuera las conexiones del pool, como haria un reinicio del
    motor. La siguiente consulta debe abrir una conexion nueva y responder, sin
    que el proceso muera ni la sonda quede rota.
    """
    application = "prueba-conexion-cortada"
    pool = create_pool(f"{postgres_url}?application_name={application}")
    await pool.open(wait=False)
    try:
        assert await ping_database(pool) is True

        admin = await AsyncConnection.connect(postgres_url, autocommit=True)
        try:
            cursor = await admin.execute(
                "select count(*) from (select pg_terminate_backend(pid) from pg_stat_activity"
                " where application_name = %s) cortadas",
                (application,),
            )
            cortadas = await cursor.fetchone()
        finally:
            await admin.close()
        # Control: habia una conexion que cortar; si no, la prueba no demostraria nada.
        assert cortadas is not None
        assert cortadas[0] >= 1

        assert await ping_database(pool) is True
    finally:
        await pool.close()
