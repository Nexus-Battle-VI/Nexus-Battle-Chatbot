"""Rechazos de la conversacion que ocurren antes del clasificador."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from chatbot.infrastructure.bootstrap.app import create_app
from chatbot.infrastructure.config.env import load_config

PATH = "/api/v1/chatbot/messages"


@pytest.fixture
def client() -> Iterator[TestClient]:
    config = load_config({"APP_ENV": "test", "AUTH_MODE": "disabled"})
    app = create_app(config)
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def test_rechaza_una_inyeccion(client: TestClient) -> None:
    response = client.post(PATH, json={"text": "<script>alert(1)</script>"})
    assert response.status_code == 400
    assert response.json()["statusCode"] == 400


def test_rechaza_contenido_ofensivo(client: TestClient) -> None:
    response = client.post(PATH, json={"text": "eres un malparido"})
    assert response.status_code == 400


def test_limpiar_el_historial_de_un_visitante(client: TestClient) -> None:
    opened = client.get("/api/v1/chatbot/messages/history")
    assert opened.status_code == 200
    session_id = opened.json()["sessionId"]
    cleared = client.delete(
        "/api/v1/chatbot/messages/history",
        params={"sessionId": session_id},
    )
    assert cleared.status_code == 204
    history = client.get("/api/v1/chatbot/messages/history", params={"sessionId": session_id})
    assert history.status_code == 200
    assert history.json()["turns"] == []


def test_el_historial_conserva_el_camino_de_la_accion(client: TestClient) -> None:
    created = client.post(
        "/api/v1/chatbot/admin/knowledge",
        json={
            "intent": "mi_inventario",
            "language": "es",
            "priority": 1,
            "answer": "El inventario se consulta en el momento.",
            "variations": ["que tengo en el inventario"],
        },
    )
    assert created.status_code == 201
    opened = client.get("/api/v1/chatbot/messages/history")
    session_id = opened.json()["sessionId"]
    asked = client.post(
        PATH,
        json={"text": "que tengo en el inventario", "sessionId": session_id},
    )
    assert asked.status_code == 200
    assert asked.json()["assistedAction"] == {
        "name": "buscar_inventario",
        "path": "/inventory",
    }
    history = client.get("/api/v1/chatbot/messages/history", params={"sessionId": session_id})
    assert history.status_code == 200
    assert history.json()["turns"][0]["assistedAction"] == {
        "name": "buscar_inventario",
        "path": "/inventory",
    }
