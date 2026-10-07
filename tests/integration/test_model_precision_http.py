"""La precisión por versión se consulta, y no la ve un jugador."""

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import ClassVar

import pytest
from fastapi.testclient import TestClient

from chatbot.application.ports.model_version_repository import ModelVersion
from chatbot.application.ports.token_verifier import Role, TokenVerificationError, VerifiedIdentity
from chatbot.domain.training_set import ValidationMetrics
from chatbot.infrastructure.bootstrap.app import create_app
from chatbot.infrastructure.config.env import load_config

PATH = "/api/v1/chatbot/admin/model-precision"
JWT_ENV = {
    "AUTH_MODE": "jwt",
    "COGNITO_USER_POOL_ID": "us-east-1_p",
    "COGNITO_CLIENT_ID": "c",
    "INTERNAL_SERVICE_AUTH_SECRET": "secreto-de-pruebas",
}


class FakeVerifier:
    IDENTITIES: ClassVar[dict[str, VerifiedIdentity]] = {
        "token-jugador": VerifiedIdentity("jugador", roles=frozenset({Role.PLAYER})),
        "token-admin": VerifiedIdentity("admin", roles=frozenset({Role.ADMINISTRATOR})),
    }

    async def verify(self, token: str) -> VerifiedIdentity:
        identity = self.IDENTITIES.get(token)
        if identity is None:
            raise TokenVerificationError()
        return identity


@pytest.fixture
def client() -> Iterator[TestClient]:
    config = load_config({"APP_ENV": "test", **JWT_ENV})
    app = create_app(config, token_verifier=FakeVerifier())
    version = ModelVersion(
        id="00000000-0000-4000-8000-0000000000b1",
        state="CANDIDATE",
        accuracy=1.0,
        macro_f1=1.0,
        metrics=ValidationMetrics(
            1.0,
            1.0,
            (("es:otro", 0.0), ("es:turno", 1.0)),
            (("es:turno", "es:otro", 1), ("es:turno", "es:turno", 2)),
        ),
        single_example_labels=(),
        artifact=b"activa",
        created_at=datetime(2026, 10, 5, tzinfo=UTC),
    )
    versions = app.state.model_versions
    asyncio.run(versions.add_candidate(version))
    asyncio.run(versions.promote(version.id))
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def test_un_jugador_no_consulta_la_precision(client: TestClient) -> None:
    assert client.get(PATH).status_code == 401
    denied = client.get(PATH, headers={"authorization": "Bearer token-jugador"})
    assert denied.status_code == 403


def test_el_administrador_puede_lanzar_el_reentrenamiento(client: TestClient) -> None:
    headers = {"authorization": "Bearer token-admin"}
    denied = client.post(
        "/api/v1/chatbot/admin/model-training",
        headers={"authorization": "Bearer token-jugador"},
    )
    assert denied.status_code == 403
    started = client.post("/api/v1/chatbot/admin/model-training", headers=headers)
    assert started.status_code == 200
    body = started.json()
    assert body["started"] is True
    assert body["promoted"] is False
    assert body["versionId"] is None
    assert "userId" not in body


def test_el_administrador_ve_la_precision_de_cada_version(client: TestClient) -> None:
    headers = {"authorization": "Bearer token-admin"}
    empty = client.get(PATH, headers=headers)
    assert empty.status_code == 200
    assert empty.json()[0]["precision"] is None
    versions = client.app.state.model_versions
    version_id = "00000000-0000-4000-8000-0000000000b1"
    asyncio.run(versions.record_answer(version_id, True))
    asyncio.run(versions.record_answer(version_id, False))
    body = client.get(PATH, headers=headers).json()
    assert body[0]["versionId"] == version_id
    assert body[0]["useful"] == 1
    assert body[0]["notUseful"] == 1
    assert body[0]["precision"] == 0.5
    assert body[0]["perIntentF1"] == [
        {"label": "es:otro", "score": 0.0},
        {"label": "es:turno", "score": 1.0},
    ]
    assert body[0]["confusion"] == [
        {"actual": "es:turno", "predicted": "es:otro", "count": 1},
        {"actual": "es:turno", "predicted": "es:turno", "count": 2},
    ]
