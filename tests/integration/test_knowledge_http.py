"""Alta, edicion, baja y listado del diccionario por HTTP."""

from collections.abc import Iterator
from typing import ClassVar

import pytest
from fastapi.testclient import TestClient

from chatbot.application.ports.token_verifier import (
    Role,
    TokenVerificationError,
    VerifiedIdentity,
)
from chatbot.infrastructure.bootstrap.app import create_app
from chatbot.infrastructure.config.env import load_config

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
        "token-super": VerifiedIdentity("super", roles=frozenset({Role.SUPER_ADMINISTRATOR})),
    }

    async def verify(self, token: str) -> VerifiedIdentity:
        identity = self.IDENTITIES.get(token)
        if identity is None:
            raise TokenVerificationError()
        return identity


PATH = "/api/v1/chatbot/admin/knowledge"
BODY = {
    "intent": "regla_turno",
    "language": "es",
    "priority": 10,
    "answer": "El combate es por turnos.",
    "variations": ["como funciona el turno", "cuanto dura un turno"],
}


@pytest.fixture
def client() -> Iterator[TestClient]:
    config = load_config({"APP_ENV": "test", **JWT_ENV})
    app = create_app(config, token_verifier=FakeVerifier())
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def test_sin_testimonio_responde_401(client: TestClient) -> None:
    assert client.post(PATH, json=BODY).status_code == 401


def test_un_jugador_no_modifica_el_diccionario(client: TestClient) -> None:
    response = client.post(PATH, json=BODY, headers={"authorization": "Bearer token-jugador"})
    assert response.status_code == 403


def test_el_administrador_crea_edita_lista_y_borra(client: TestClient) -> None:
    headers = {"authorization": "Bearer token-admin"}
    created = client.post(PATH, json=BODY, headers=headers)
    assert created.status_code == 201
    entry_id = created.json()["id"]
    assert created.json()["variations"] == BODY["variations"]

    listed = client.get(PATH, headers=headers)
    assert listed.status_code == 200
    assert listed.json()[0]["intent"] == "regla_turno"

    updated = client.put(
        f"{PATH}/{entry_id}",
        json={**BODY, "answer": "Cada turno dura 30 segundos.", "priority": 2},
        headers=headers,
    )
    assert updated.status_code == 200
    assert updated.json()["answer"] == "Cada turno dura 30 segundos."
    assert updated.json()["id"] == entry_id

    assert client.delete(f"{PATH}/{entry_id}", headers=headers).status_code == 204
    assert client.get(PATH, headers=headers).json() == []


def test_el_super_administrador_tambien_puede_crear(client: TestClient) -> None:
    response = client.post(
        PATH,
        json=BODY,
        headers={"authorization": "Bearer token-super"},
    )
    assert response.status_code == 201


def test_rechaza_un_campo_ajeno_y_una_entrada_invalida(client: TestClient) -> None:
    headers = {"authorization": "Bearer token-admin"}
    extra = client.post(PATH, json={**BODY, "subject": "otro"}, headers=headers)
    assert extra.status_code == 400
    invalid = client.post(PATH, json={**BODY, "language": "fr"}, headers=headers)
    assert invalid.status_code == 400


def test_editar_o_borrar_una_entrada_ausente_responde_404(client: TestClient) -> None:
    headers = {"authorization": "Bearer token-admin"}
    missing = "00000000-0000-4000-8000-000000000001"
    assert client.put(f"{PATH}/{missing}", json=BODY, headers=headers).status_code == 404
    assert client.delete(f"{PATH}/{missing}", headers=headers).status_code == 404


def test_importa_la_semilla_y_no_duplica_al_repetirla(client: TestClient) -> None:
    headers = {"authorization": "Bearer token-admin"}
    document = {
        "schemaVersion": 1,
        "description": "recorte",
        "entries": [
            {
                "intent": "regla_turno",
                "language": "es",
                "priority": 10,
                "liveData": None,
                "question": "¿Cuánto dura un turno?",
                "variations": ["cuanto dura un turno"],
                "answer": "Cada turno dura 30 segundos.",
            },
            {
                "intent": "regla_turno",
                "language": "en",
                "priority": 10,
                "question": "How long is a turn?",
                "variations": ["turn length"],
                "answer": "Each turn lasts 30 seconds.",
            },
        ],
    }
    denied = client.post(
        f"{PATH}/import", json=document, headers={"authorization": "Bearer token-jugador"}
    )
    assert denied.status_code == 403
    imported = client.post(f"{PATH}/import", json=document, headers=headers)
    assert imported.status_code == 200
    assert imported.json() == {"created": 2, "skipped": 0, "reinforced": 0}
    again = client.post(f"{PATH}/import", json=document, headers=headers)
    assert again.json() == {"created": 0, "skipped": 2, "reinforced": 0}
    exported = client.get(f"{PATH}/export", headers=headers)
    assert exported.status_code == 200
    assert exported.json()["schemaVersion"] == 1
    spanish = next(item for item in exported.json()["entries"] if item["language"] == "es")
    assert spanish["question"] == "¿Cuánto dura un turno?"
    assert spanish["variations"] == ["cuanto dura un turno"]
    broken = client.post(
        f"{PATH}/import",
        json={
            "schemaVersion": 1,
            "entries": [
                {**document["entries"][0], "intent": "nueva"},
                {**document["entries"][1], "language": "fr"},
            ],
        },
        headers=headers,
    )
    assert broken.status_code == 400
    assert len(client.get(PATH, headers=headers).json()) == 2
    assert (
        client.post(
            f"{PATH}/import", json={"schemaVersion": 2, "entries": []}, headers=headers
        ).status_code
        == 400
    )
