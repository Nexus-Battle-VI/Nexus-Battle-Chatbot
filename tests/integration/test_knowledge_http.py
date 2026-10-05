"""Alta, edicion, baja y listado del diccionario por HTTP."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from tests.integration.test_service_http import JWT_ENV, FakeVerifier

from chatbot.infrastructure.bootstrap.app import create_app
from chatbot.infrastructure.config.env import load_config

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
