"""El clasificador elige la entrada y no inventa por debajo del umbral."""

from collections.abc import Iterator
from typing import ClassVar
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from chatbot.application.ports.token_verifier import Role, TokenVerificationError, VerifiedIdentity
from chatbot.domain.knowledge_entry import knowledge_entry
from chatbot.infrastructure.bootstrap.app import create_app
from chatbot.infrastructure.config.env import load_config

JWT_ENV = {
    "AUTH_MODE": "jwt",
    "COGNITO_USER_POOL_ID": "us-east-1_p",
    "COGNITO_CLIENT_ID": "c",
    "INTERNAL_SERVICE_AUTH_SECRET": "secreto-de-pruebas",
}
PATH = "/api/v1/chatbot/messages"
ADMIN = "/api/v1/chatbot/admin/knowledge"


class FakeVerifier:
    IDENTITIES: ClassVar[dict[str, VerifiedIdentity]] = {
        "token-jugador": VerifiedIdentity("jugador", roles=frozenset({Role.PLAYER})),
        "token-otro": VerifiedIdentity("otro", roles=frozenset({Role.PLAYER})),
        "token-admin": VerifiedIdentity("admin", roles=frozenset({Role.ADMINISTRATOR})),
    }

    async def verify(self, token: str) -> VerifiedIdentity:
        identity = self.IDENTITIES.get(token)
        if identity is None:
            raise TokenVerificationError()
        return identity


def _entry(
    intent: str, language: str, answer: str, variations: list[str], view: str | None = None
) -> dict[str, object]:
    return {
        "intent": intent,
        "language": language,
        "priority": 10,
        "answer": answer,
        "variations": variations,
        "view": view,
    }


@pytest.fixture
def client() -> Iterator[TestClient]:
    config = load_config({"APP_ENV": "test", **JWT_ENV})
    app = create_app(config, token_verifier=FakeVerifier())
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def _seed(client: TestClient) -> None:
    headers = {"authorization": "Bearer token-admin"}
    turns = _entry(
        "regla_turno",
        "es",
        "El combate es por turnos y cada turno dura 30 segundos.",
        [
            "como funciona el turno",
            "cuanto dura un turno",
            "que puedo hacer en mi turno",
            "cuanto dura la batalla",
            "en que orden se juega",
        ],
    )
    mission = _entry(
        "modo_mision",
        "es",
        "Una mision bloquea al heroe y usa tres rotaciones.",
        [
            "como funciona una mision",
            "que es una mision",
            "el heroe queda bloqueado",
            "que son las rotaciones",
            "que dificultades hay",
        ],
    )
    mission_view = _entry(
        "modo_mision",
        "es",
        "Estas en la vista de misiones: elige dificultad y rotaciones.",
        ["como funciona una mision en esta vista"],
        view="misiones",
    )
    assert client.post(ADMIN, json=turns, headers=headers).status_code == 201
    assert client.post(ADMIN, json=mission, headers=headers).status_code == 201
    assert client.post(ADMIN, json=mission_view, headers=headers).status_code == 201


def test_un_visitante_recibe_la_respuesta_del_diccionario(client: TestClient) -> None:
    _seed(client)
    response = client.post(PATH, json={"text": "cuanto dura un truno"})
    assert response.status_code == 200
    body = response.json()
    assert body["answered"] is True
    assert body["ticketId"] is None
    assert body["intent"] == "regla_turno"
    assert body["language"] == "es"
    assert body["confidence"] >= 0.55
    assert "30 segundos" in body["answer"]
    assert "subject" not in body
    listed = client.get(
        "/api/v1/chatbot/admin/tickets",
        headers={"authorization": "Bearer token-admin"},
    )
    assert listed.json() == []


def test_otra_formulacion_reconoce_la_misma_intencion(client: TestClient) -> None:
    _seed(client)
    response = client.post(PATH, json={"text": "En que orden se juega?"})
    assert response.json()["intent"] == "regla_turno"


def test_por_debajo_del_umbral_no_inventa_y_sugiere(client: TestClient) -> None:
    _seed(client)
    response = client.post(PATH, json={"text": "????"})
    body = response.json()
    assert body["answered"] is False
    assert body["answer"] is None
    assert body["intent"] is None
    assert body["ticketId"] is not None
    listed = client.get(
        "/api/v1/chatbot/admin/tickets",
        headers={"authorization": "Bearer token-admin"},
    )
    assert listed.status_code == 200
    assert listed.json()[0]["question"] == "????"
    denied = client.get(
        "/api/v1/chatbot/admin/tickets",
        headers={"authorization": "Bearer token-jugador"},
    )
    assert denied.status_code == 403


def test_transferir_redacta_la_pregunta(client: TestClient) -> None:
    extra = client.post(
        "/api/v1/chatbot/tickets",
        json={"text": "password: secreto123", "userId": "otro"},
    )
    assert extra.status_code == 400
    opened = client.post("/api/v1/chatbot/tickets", json={"text": "password: secreto123"})
    assert opened.status_code == 200
    assert opened.json()["sessionId"]
    listed = client.get(
        "/api/v1/chatbot/admin/tickets",
        headers={"authorization": "Bearer token-admin"},
    )
    stored = listed.json()[0]
    assert stored["id"] == opened.json()["id"]
    assert stored["question"] == "[redactado]"
    assert stored["actor"].startswith("visitor:")
    offensive = client.post("/api/v1/chatbot/tickets", json={"text": "esto es una mierda"})
    assert offensive.status_code == 400
    assert (
        len(
            client.get(
                "/api/v1/chatbot/admin/tickets",
                headers={"authorization": "Bearer token-admin"},
            ).json()
        )
        == 1
    )


def test_la_vista_cambia_la_respuesta(client: TestClient) -> None:
    _seed(client)
    general = client.post(PATH, json={"text": "como funciona una mision"}).json()
    contextual = client.post(
        PATH, json={"text": "como funciona una mision", "view": "misiones"}
    ).json()
    assert "bloquea" in general["answer"]
    assert contextual["kind"] == "contextual"
    assert "vista de misiones" in contextual["answer"]


def test_un_token_invalido_responde_401_y_un_campo_de_mas_400(client: TestClient) -> None:
    assert (
        client.post(PATH, json={"text": "hola"}, headers={"authorization": "Bearer no"}).status_code
        == 401
    )
    assert client.post(PATH, json={"text": "hola", "userId": "otro"}).status_code == 400


def test_la_semilla_de_dominio_sigue_aceptando_la_entrada_sin_vista() -> None:
    entry = knowledge_entry(
        entry_id=str(uuid4()),
        intent="regla_turno",
        language="es",
        priority=1,
        answer="texto",
        variations=["pregunta"],
    )
    assert entry.view is None


def test_el_historial_queda_en_su_dueno_y_la_valoracion_no_cambia(client: TestClient) -> None:
    own = {"authorization": "Bearer token-jugador"}
    other = {"authorization": "Bearer token-otro"}
    asked = client.post(PATH, json={"text": "hola"}, headers=own)
    assert asked.status_code == 200
    turn_id = asked.json()["turnId"]
    history = client.get(f"{PATH}/history", headers=own)
    assert history.json()["turns"][0]["id"] == turn_id
    assert history.json()["turns"][0]["question"] == "hola"
    assert client.get(f"{PATH}/history", headers=other).json()["turns"] == []
    denied = client.post(f"{PATH}/{turn_id}/rating", json={"useful": True}, headers=other)
    assert denied.status_code == 404
    rated = client.post(f"{PATH}/{turn_id}/rating", json={"useful": True}, headers=own)
    assert rated.status_code == 200
    conflict = client.post(f"{PATH}/{turn_id}/rating", json={"useful": False}, headers=own)
    assert conflict.status_code == 409
    saved = client.put(
        "/api/v1/chatbot/preferences",
        json={"showTime": False},
        headers=own,
    )
    assert saved.json()["showTime"] is False
    assert client.get("/api/v1/chatbot/preferences", headers=other).json()["showTime"] is True
