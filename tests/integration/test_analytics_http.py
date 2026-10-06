"""El administrador lee agregados. Un jugador no. El periodo inválido se rechaza."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import ClassVar

import pytest
from fastapi.testclient import TestClient

from chatbot.application.ports.token_verifier import Role, TokenVerificationError, VerifiedIdentity
from chatbot.infrastructure.bootstrap.app import create_app
from chatbot.infrastructure.config.env import load_config

PATH = "/api/v1/chatbot/admin/analytics"


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
    config = load_config(
        {
            "APP_ENV": "test",
            "AUTH_MODE": "jwt",
            "COGNITO_USER_POOL_ID": "us-east-1_p",
            "COGNITO_CLIENT_ID": "c",
            "INTERNAL_SERVICE_AUTH_SECRET": "secreto-de-pruebas",
        }
    )
    app = create_app(config, token_verifier=FakeVerifier())
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def _period() -> dict[str, str]:
    now = datetime.now(UTC)
    return {
        "from": (now - timedelta(hours=1)).isoformat(),
        "to": (now + timedelta(hours=1)).isoformat(),
    }


def test_el_administrador_ve_la_consulta_y_el_escalamiento(client: TestClient) -> None:
    asked = client.post(
        "/api/v1/chatbot/messages",
        json={"text": "cuanto dura un turno"},
        headers={"authorization": "Bearer token-jugador"},
    )
    assert asked.status_code == 200
    denied = client.get(PATH, params=_period(), headers={"authorization": "Bearer token-jugador"})
    assert denied.status_code == 403
    report = client.get(PATH, params=_period(), headers={"authorization": "Bearer token-admin"})
    assert report.status_code == 200
    body = report.json()
    assert body["conversationsStarted"] == 1
    assert body["escalations"] == 1
    assert body["resolutionRate"] == 0
    assert body["satisfaction"] is None
    assert body["averageResponseMs"] is not None
    assert "actor" not in body
    assert any(item["text"] == "turno" for item in body["keywords"])
    assert len(body["trend"]) >= 1


def test_rechaza_un_periodo_invalido(client: TestClient) -> None:
    headers = {"authorization": "Bearer token-admin"}
    naive = client.get(
        PATH,
        params={"from": "2026-10-06T00:00:00", "to": "2026-10-06T01:00:00"},
        headers=headers,
    )
    assert naive.status_code == 400
    wide = client.get(
        PATH,
        params={"from": "2020-01-01T00:00:00Z", "to": "2026-01-01T00:00:00Z"},
        headers=headers,
    )
    assert wide.status_code == 400
    now = datetime.now(UTC)
    response = client.get(
        PATH,
        params={
            "from": (now + timedelta(hours=1)).isoformat(),
            "to": now.isoformat(),
        },
        headers={"authorization": "Bearer token-admin"},
    )
    assert response.status_code == 400
