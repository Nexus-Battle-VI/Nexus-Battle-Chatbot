"""Raiz de composicion.

Es el UNICO lugar donde se eligen implementaciones concretas, como
`app.module.ts` en los servicios NestJS. Los casos de uso son clases planas: se
construyen aqui y se entregan a los adaptadores, de modo que la capa de
aplicacion no conoce FastAPI.
"""

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI
from psycopg_pool import AsyncConnectionPool

from chatbot.adapters.inbound.http import health
from chatbot.adapters.inbound.http.auth.guards import AuthSettings, authenticate
from chatbot.adapters.inbound.http.errors import register_error_handlers
from chatbot.adapters.inbound.http.knowledge import knowledge_router
from chatbot.adapters.inbound.http.messages import messages_router
from chatbot.adapters.inbound.http.precision import precision_router
from chatbot.adapters.outbound.identity.cognito_token_verifier import (
    CognitoTokenVerifier,
    CognitoTokenVerifierOptions,
)
from chatbot.adapters.outbound.nlp.sklearn_intent import SklearnIntentModelFactory
from chatbot.adapters.outbound.persistence.empty_reviews import EmptyReviewedConversations
from chatbot.adapters.outbound.persistence.in_memory_knowledge import (
    InMemoryKnowledgeEntryRepository,
)
from chatbot.adapters.outbound.persistence.in_memory_versions import (
    InMemoryModelVersionRepository,
)
from chatbot.adapters.outbound.persistence.postgres_knowledge import (
    PostgresKnowledgeEntryRepository,
)
from chatbot.adapters.outbound.persistence.postgres_versions import (
    PostgresModelVersionRepository,
)
from chatbot.adapters.outbound.system.clock import SystemClock
from chatbot.adapters.outbound.system.fernet_cipher import FernetTextCipher
from chatbot.adapters.outbound.system.training_scheduler import TrainingScheduler
from chatbot.application.answer import AnswerQuestion
from chatbot.application.conversation import ConversationSession
from chatbot.application.knowledge import (
    CreateKnowledgeEntry,
    DeleteKnowledgeEntry,
    ListKnowledgeEntries,
    UpdateKnowledgeEntry,
)
from chatbot.application.ports.clock import ClockPort
from chatbot.application.ports.knowledge_entry_repository import KnowledgeEntryRepositoryPort
from chatbot.application.ports.model_version_repository import ModelVersionRepository
from chatbot.application.ports.token_verifier import TokenVerifierPort, VerifiedIdentity
from chatbot.application.precision import ReadModelPrecision
from chatbot.application.train_model import RetrainModel
from chatbot.infrastructure.config.env import AppConfig, AuthMode
from chatbot.infrastructure.health.health import ReadinessCheck
from chatbot.infrastructure.observability.logger import JsonLogger, Logger
from chatbot.infrastructure.persistence.database import ping_database

# Servicios autorizados a llamar a las rutas `@internal_only` de Chatbot.
#
# Es la lista de consumidores que ADR-022 declara: ninguno. Chatbot lee los datos
# del jugador con el testimonio del propio usuario (HU-48) y no ofrece rutas
# internas. Anadir uno es una decision de arquitectura, no de configuracion: por
# eso vive en codigo, donde cambiarla exige un Pull Request revisado.
INTERNAL_CALLERS: tuple[str, ...] = ()


class _UnconfiguredVerifier:
    """Con `AUTH_MODE=disabled` no hay verificador. No se devuelve uno que acepte
    cualquier cosa: el guard que lo usaria no se ejecuta en ese modo."""

    async def verify(self, token: str) -> VerifiedIdentity:
        del token  # Conserva la firma del puerto; nunca se examina.
        raise RuntimeError("No hay verificador de testimonios configurado.")


def create_app(
    config: AppConfig,
    *,
    logger: Logger | None = None,
    clock: ClockPort | None = None,
    token_verifier: TokenVerifierPort | None = None,
    pool: AsyncConnectionPool | None = None,
    internal_callers: tuple[str, ...] = INTERNAL_CALLERS,
    extra_routers: Sequence[APIRouter] = (),
) -> FastAPI:
    log = logger or JsonLogger(
        level=config.log_level, service=config.service_name, version=config.version
    )

    if pool is None:
        log.warn(
            "in_memory_persistence",
            {"detail": "PERSISTENCE_DRIVER=memory: el estado se pierde al reiniciar el servicio."},
        )

    app_clock = clock or SystemClock()
    verifier: TokenVerifierPort
    if token_verifier is not None:
        verifier = token_verifier
    elif config.cognito is not None:
        verifier = CognitoTokenVerifier(
            CognitoTokenVerifierOptions(config.cognito.user_pool_id, config.cognito.client_id)
        )
    else:
        log.warn(
            "authentication_disabled",
            {"detail": "AUTH_MODE=disabled: ninguna ruta verifica quien realiza la peticion."},
        )
        verifier = _UnconfiguredVerifier()

    entries: KnowledgeEntryRepositoryPort = (
        PostgresKnowledgeEntryRepository(pool)
        if pool is not None
        else InMemoryKnowledgeEntryRepository()
    )
    versions: ModelVersionRepository = (
        PostgresModelVersionRepository(pool)
        if pool is not None
        else InMemoryModelVersionRepository()
    )
    model_factory = SklearnIntentModelFactory()
    scheduler = (
        TrainingScheduler(
            RetrainModel(
                entries,
                EmptyReviewedConversations(),
                model_factory,
                versions,
                app_clock,
            ),
            config.training_interval_seconds,
            log,
        )
        if config.training_scheduler_enabled
        else None
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        # El esquema NO se migra aqui: es un paso explicito (`chatbot-migrate`).
        # `wait=False`: el servicio arranca aunque la base no responda todavia, y
        # la readiness lo dira con 503 en vez de impedir el arranque.
        if pool is not None:
            await pool.open(wait=False)
        if scheduler is not None:
            scheduler.start()
        try:
            yield
        finally:
            if scheduler is not None:
                await scheduler.stop()
            if pool is not None:
                await pool.close()

    prefix = f"/{config.global_prefix.strip('/')}"
    app = FastAPI(
        title="Nexus Battles VI — Chatbot",
        description="API del bounded context Chatbot.",
        version=config.version,
        lifespan=lifespan,
        # La identidad y el contrato interno se comprueban en TODA ruta: un
        # endpoint nuevo nace protegido y hay que abrirlo a proposito (`@public`).
        dependencies=[Depends(authenticate)],
        docs_url=f"{prefix}/docs" if config.swagger_enabled else None,
        openapi_url=f"{prefix}/docs/openapi.json" if config.swagger_enabled else None,
        redoc_url=None,
    )
    register_error_handlers(app)

    app.state.auth = AuthSettings(
        jwt_enabled=config.auth_mode is AuthMode.JWT,
        verifier=verifier,
        internal_secret=config.internal_service_auth_secret,
        internal_callers=internal_callers,
        clock=app_clock,
        logger=log,
    )
    app.state.version_info = {
        "service": config.service_name,
        "version": config.version,
        "environment": config.app_env,
    }

    readiness: list[ReadinessCheck] = []
    if pool is not None:
        connected_pool = pool

        async def database_ready() -> bool:
            return await ping_database(connected_pool)

        readiness.append(ReadinessCheck(name="database", check=database_ready))
    app.state.readiness_checks = readiness
    app.state.model_versions = versions

    app.include_router(health.router, prefix=prefix)
    # La ruta publica del contexto es /api/v1/chatbot* (ADR-022, Caddy). No
    # depende de GLOBAL_PREFIX, que las sondas siguen usando (`/api/health/*`).
    app.include_router(
        knowledge_router(
            create=CreateKnowledgeEntry(entries),
            update=UpdateKnowledgeEntry(entries),
            delete=DeleteKnowledgeEntry(entries),
            list_entries=ListKnowledgeEntries(entries),
        ),
        prefix="/api/v1/chatbot",
    )
    app.include_router(
        precision_router(ReadModelPrecision(versions)),
        prefix="/api/v1/chatbot",
    )
    app.include_router(
        messages_router(
            ConversationSession(
                AnswerQuestion(
                    entries,
                    model_factory,
                    versions,
                    model_factory,
                    config.ab_candidate_percent,
                ),
                app_clock,
                FernetTextCipher(FernetTextCipher.generate_key()),
            )
        ),
        prefix="/api/v1/chatbot",
    )
    for router in extra_routers:
        app.include_router(router, prefix=prefix)
    return app
