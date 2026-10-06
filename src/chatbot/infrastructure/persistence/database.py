"""Infraestructura de persistencia PostgreSQL: pool, sonda y migrador.

Equivale a `database.ts` de los servicios NestJS (Kysely + `pg`), con psycopg 3.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field

from psycopg import AsyncConnection, sql
from psycopg_pool import AsyncConnectionPool

# Conexiones simultaneas del pool. Deliberadamente bajo: todos los servicios
# comparten el mismo motor en el nodo de datos (ADR-011), y si cada uno abriera
# un pool generoso PostgreSQL agotaria `max_connections` antes de que ningun
# servicio notara presion.
DEFAULT_MAX_CONNECTIONS = 5


def create_pool(
    connection_string: str, *, max_connections: int = DEFAULT_MAX_CONNECTIONS
) -> AsyncConnectionPool:
    """Crea el pool SIN abrirlo; lo abre el ciclo de vida de la aplicacion.

    La leccion de Sprint 2 (servicios con `pg` que morian al reiniciarse la
    base) se resuelve aqui de forma distinta pero con el mismo control en CI:

    - `min_size=0`: el pool no mantiene conexiones que el motor pueda cortar
      mientras esperan, ni reintenta en bucle contra una base caida.
    - `check`: cada conexion se comprueba al prestarla; una conexion rota se
      descarta y se abre otra, en vez de devolver un error al primer uso.
    - `connect_timeout` y `timeout`: sin limite, un motor caido dejaria las
      peticiones colgadas hasta el tiempo de espera HTTP, mucho mas largo.
    """
    return AsyncConnectionPool(
        conninfo=connection_string,
        min_size=0,
        max_size=max_connections,
        # Cerrar conexiones ociosas devuelve capacidad al motor compartido.
        max_idle=30,
        timeout=5,
        kwargs={"connect_timeout": 3},
        check=AsyncConnectionPool.check_connection,
        open=False,
        name="chatbot",
    )


async def ping_database(pool: AsyncConnectionPool) -> bool:
    """Readiness contra el motor. Devuelve `False` en lugar de lanzar: para la
    sonda, un motor inalcanzable es un resultado, no una excepcion."""
    try:
        async with pool.connection(timeout=5) as connection:
            await connection.execute("select 1")
    except Exception:
        return False
    return True


@dataclass(frozen=True)
class Migration:
    """Migracion declarada en codigo, no descubierta del sistema de ficheros.

    El nombre lleva prefijo numerico SECUENCIAL (`001-...`), nunca una fecha: una
    migracion fechada al escribirse y no al promoverse ya tumbo un servicio en
    produccion (Account, HU-66).
    """

    name: str
    sql: str


# Cada Historia de Usuario anade aqui su migracion, en orden de nombre.
MIGRATIONS: Sequence[Migration] = (
    Migration(
        "001-knowledge-entries",
        """
        create table knowledge_entries (
          id uuid primary key,
          intent text not null,
          language text not null,
          priority integer not null,
          answer text not null,
          variations jsonb not null,
          constraint knowledge_entries_idioma check (language in ('es', 'en')),
          constraint knowledge_entries_intencion
            check (intent ~ '^[a-z][a-z0-9_]{0,63}$'),
          constraint knowledge_entries_respuesta
            check (char_length(btrim(answer)) > 0 and char_length(answer) <= 8000),
          constraint knowledge_entries_variaciones check (
            jsonb_typeof(variations) = 'array' and jsonb_array_length(variations) >= 1
          )
        )
        """,
    ),
    Migration(
        "002-knowledge-entry-view",
        """
        alter table knowledge_entries
          add column view text,
          add constraint knowledge_entries_vista check (
            view is null or view ~ '^[a-z][a-z0-9_-]{0,39}$'
          )
        """,
    ),
    Migration(
        "003-model-versions",
        """
        create table model_versions (
          id uuid primary key,
          state text not null,
          accuracy double precision not null,
          macro_f1 double precision not null,
          report jsonb not null,
          artifact bytea not null,
          created_at timestamptz not null,
          constraint model_versions_estado check (state in ('CANDIDATE', 'ACTIVE'))
        );
        create unique index model_versions_one_active
          on model_versions (state) where state = 'ACTIVE';
        create table model_training_lease (
          id integer primary key,
          until timestamptz not null,
          constraint model_training_lease_unica check (id = 1)
        );
        insert into model_training_lease (id, until) values (1, '-infinity');
        """,
    ),
    Migration(
        "004-model-experiment",
        """
        alter table model_versions
          add column in_experiment boolean not null default false;
        create unique index model_versions_one_experiment
          on model_versions (in_experiment) where in_experiment;
        create table model_answer_outcomes (
          id uuid primary key default gen_random_uuid(),
          version_id uuid not null references model_versions (id),
          useful boolean,
          created_at timestamptz not null default now()
        );
        """,
    ),
)

MIGRATIONS_TABLE = sql.Identifier("_migrations")
# Clave del bloqueo consultivo que serializa dos migradores concurrentes.
_MIGRATION_LOCK_KEY = 7_220_022


@dataclass(frozen=True)
class MigrationOutcome:
    applied: list[str] = field(default_factory=list)
    error: Exception | None = None


class MigrationOrderError(Exception):
    pass


def _validate(migrations: Sequence[Migration]) -> None:
    names = [migration.name for migration in migrations]
    if len(set(names)) != len(names):
        raise MigrationOrderError("Hay migraciones con el mismo nombre.")
    if names != sorted(names):
        raise MigrationOrderError("Las migraciones deben declararse en orden de nombre.")


async def migrate_to_latest(
    connection: AsyncConnection, migrations: Sequence[Migration] = MIGRATIONS
) -> MigrationOutcome:
    """Lleva el esquema al ultimo estado conocido.

    No se ejecuta al arrancar el servicio: migrar desde el arranque deja un
    despliegue con una migracion rota en bucle de reinicio. Se invoca desde el
    contenedor `chatbot-migrate`, como paso explicito del despliegue.

    Todas las pendientes se aplican en UNA transaccion, como el migrador de
    Kysely en PostgreSQL: o entran todas o ninguna. Las migraciones se reciben
    como parametro para que la prueba contra motor real pueda ejercitar el
    camino de fallo sin anadir una migracion rota al producto.
    """
    try:
        _validate(migrations)
        async with connection.transaction():
            await connection.execute("select pg_advisory_xact_lock(%s)", (_MIGRATION_LOCK_KEY,))
            await connection.execute(
                sql.SQL(
                    "create table if not exists {} ("
                    " name text primary key,"
                    " applied_at timestamptz not null default now())"
                ).format(MIGRATIONS_TABLE)
            )
            cursor = await connection.execute(
                sql.SQL("select name from {}").format(MIGRATIONS_TABLE)
            )
            already = {str(row[0]) for row in await cursor.fetchall()}
            known = {migration.name for migration in migrations}
            unknown = sorted(already - known)
            if unknown:
                # La base esta por delante del codigo: una imagen anterior a la
                # que la migro. Seguir arrancaria con un esquema que no conoce.
                raise MigrationOrderError(
                    f"La base tiene migraciones que este codigo no declara: {', '.join(unknown)}."
                )
            applied: list[str] = []
            for migration in migrations:
                if migration.name in already:
                    continue
                await connection.execute(migration.sql.encode("utf-8"))
                await connection.execute(
                    sql.SQL("insert into {} (name) values (%s)").format(MIGRATIONS_TABLE),
                    (migration.name,),
                )
                applied.append(migration.name)
    except Exception as error:
        return MigrationOutcome(applied=[], error=error)
    return MigrationOutcome(applied=applied)
