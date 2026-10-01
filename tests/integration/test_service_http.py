"""Servicio completo por HTTP: guards, sondas, forma de los errores y contrato interno.

Usa rutas de sonda declaradas aqui, como `test/integration/service-http.spec.ts`
en los servicios NestJS: el andamiaje no tiene rutas de negocio.
"""

import json
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import ClassVar

import anyio
import pytest
from fastapi import APIRouter, Depends
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict

from chatbot.adapters.inbound.http.auth.guards import current_identity, require_roles
from chatbot.adapters.inbound.http.auth.markers import internal_only, public
from chatbot.adapters.outbound.identity.internal_signature import (
    CanonicalRequest,
    sign_internal_request,
)
from chatbot.application.ports.token_verifier import (
    Role,
    TokenVerificationError,
    VerifiedIdentity,
)
from chatbot.infrastructure.bootstrap.app import INTERNAL_CALLERS, create_app
from chatbot.infrastructure.config.env import load_config

SECRET = "secreto-de-pruebas"
NOW = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)


class FixedClock:
    def now(self) -> datetime:
        return NOW


class FakeVerifier:
    IDENTITIES: ClassVar[dict[str, VerifiedIdentity]] = {
        "token-jugador": VerifiedIdentity("jugador", roles=frozenset({Role.PLAYER})),
        "token-admin": VerifiedIdentity("admin", roles=frozenset({Role.ADMINISTRATOR})),
        "token-super": VerifiedIdentity("super", roles=frozenset({Role.SUPER_ADMINISTRATOR})),
    }

    async def verify(self, token: str) -> VerifiedIdentity:
        if token == "token-red-caida":
            raise ConnectionError("JWKS inalcanzable")
        identity = self.IDENTITIES.get(token)
        if identity is None:
            raise TokenVerificationError()
        return identity


class Mensaje(BaseModel):
    model_config = ConfigDict(extra="forbid")
    texto: str


def probe_router() -> APIRouter:
    router = APIRouter(prefix="/probe")

    @router.get("/publica")
    @public
    async def publica() -> dict[str, str]:
        return {"ok": "si"}

    @router.get("/protegida")
    async def protegida(
        identity: VerifiedIdentity = Depends(current_identity),  # noqa: B008
    ) -> dict[str, str]:
        return {"sujeto": identity.subject}

    @router.get("/administracion", dependencies=[Depends(require_roles(Role.ADMINISTRATOR))])
    async def administracion() -> dict[str, str]:
        return {"ok": "si"}

    @router.get("/raiz", dependencies=[Depends(require_roles(Role.SUPER_ADMINISTRATOR))])
    async def raiz() -> dict[str, str]:
        return {"ok": "si"}

    @router.post("/validada")
    @public
    async def validada(mensaje: Mensaje) -> dict[str, str]:
        return {"texto": mensaje.texto}

    @router.post("/interna", status_code=201)
    @internal_only()
    async def interna(cuerpo: dict[str, object]) -> dict[str, object]:
        return {"recibido": cuerpo}

    @router.post("/interna-acotada", status_code=201)
    @internal_only("combat")
    async def interna_acotada(cuerpo: dict[str, object]) -> dict[str, object]:
        return {"recibido": cuerpo}

    return router


def _client(env: dict[str, str], **overrides: object) -> TestClient:
    config = load_config({"APP_ENV": "test", **env})
    app = create_app(
        config,
        clock=FixedClock(),
        token_verifier=FakeVerifier(),
        extra_routers=[probe_router()],
        **overrides,  # type: ignore[arg-type]
    )
    return TestClient(app, raise_server_exceptions=False)


JWT_ENV = {
    "AUTH_MODE": "jwt",
    "COGNITO_USER_POOL_ID": "us-east-1_p",
    "COGNITO_CLIENT_ID": "c",
    "INTERNAL_SERVICE_AUTH_SECRET": SECRET,
}


@pytest.fixture
def client() -> Iterator[TestClient]:
    with _client(JWT_ENV, internal_callers=("combat", "missions")) as test_client:
        yield test_client


def _signed(client: TestClient, path: str, service: str, body: object, **changes: str) -> object:
    timestamp = changes.get("timestamp", str(int(NOW.timestamp() * 1000)))
    signature = changes.get(
        "signature",
        sign_internal_request(
            SECRET,
            CanonicalRequest(
                service=service, method="POST", path=path, timestamp=timestamp, body=body
            ),
        ),
    )
    return client.post(
        path,
        content=json.dumps(body),
        headers={
            "content-type": "application/json",
            "x-internal-service": service,
            "x-internal-timestamp": timestamp,
            "x-internal-signature": signature,
        },
    )


class TestIdentidad:
    def test_las_sondas_responden_sin_testimonio(self, client: TestClient) -> None:
        assert client.get("/api/health/live").json() == {"status": "ok", "checks": {}}
        ready = client.get("/api/health/ready")
        # Sin pool (persistencia en memoria) no hay dependencias que comprobar.
        assert (ready.status_code, ready.json()["status"]) == (200, "ok")
        assert client.get("/api/version").json()["service"] == "nexus-battle-chatbot"

    def test_una_ruta_publica_responde_sin_testimonio(self, client: TestClient) -> None:
        assert client.get("/api/probe/publica").status_code == 200

    def test_toda_ruta_nace_protegida(self, client: TestClient) -> None:
        response = client.get("/api/probe/protegida")
        assert response.status_code == 401
        # Misma forma de error que los servicios NestJS.
        assert response.json() == {
            "statusCode": 401,
            "message": "Falta el testimonio de identidad.",
            "error": "Unauthorized",
        }

    def test_la_identidad_sale_del_testimonio_verificado(self, client: TestClient) -> None:
        response = client.get(
            "/api/probe/protegida", headers={"authorization": "Bearer token-jugador"}
        )
        assert response.json() == {"sujeto": "jugador"}

    @pytest.mark.parametrize(
        "header",
        ["Bearer token-falso", "Bearer token-jugador sobra", "Basic token-jugador", "Bearer "],
    )
    def test_rechaza_testimonios_invalidos_o_mal_formados(
        self, client: TestClient, header: str
    ) -> None:
        response = client.get("/api/probe/protegida", headers={"authorization": header})
        assert response.status_code == 401

    def test_un_fallo_de_red_no_se_disfraza_de_401(self, client: TestClient) -> None:
        response = client.get(
            "/api/probe/protegida", headers={"authorization": "Bearer token-red-caida"}
        )
        assert response.status_code == 500


class TestRoles:
    def test_el_jugador_no_satisface_la_exigencia_de_administrador(
        self, client: TestClient
    ) -> None:
        response = client.get(
            "/api/probe/administracion", headers={"authorization": "Bearer token-jugador"}
        )
        assert response.status_code == 403

    def test_el_administrador_si(self, client: TestClient) -> None:
        response = client.get(
            "/api/probe/administracion", headers={"authorization": "Bearer token-admin"}
        )
        assert response.status_code == 200

    def test_el_super_administrador_satisface_la_exigencia_de_administrador(
        self, client: TestClient
    ) -> None:
        response = client.get(
            "/api/probe/administracion", headers={"authorization": "Bearer token-super"}
        )
        assert response.status_code == 200

    def test_el_administrador_no_satisface_la_de_super_administrador(
        self, client: TestClient
    ) -> None:
        # La jerarquia es de un solo sentido.
        admin = client.get("/api/probe/raiz", headers={"authorization": "Bearer token-admin"})
        super_ = client.get("/api/probe/raiz", headers={"authorization": "Bearer token-super"})
        assert (admin.status_code, super_.status_code) == (403, 200)


class TestContratoInterno:
    def test_acepta_a_un_consumidor_declarado_sin_testimonio(self, client: TestClient) -> None:
        response = _signed(client, "/api/probe/interna", "combat", {"operationId": "op-1"})
        assert response.status_code == 201  # type: ignore[attr-defined]
        assert response.json() == {"recibido": {"operationId": "op-1"}}  # type: ignore[attr-defined]

    @pytest.mark.parametrize(
        ("caso", "service", "changes"),
        [
            ("servicio no autorizado", "catalog", {}),
            ("sello fuera de ventana", "combat", {"timestamp": str(int(time.time() * 1000))}),
            ("firma que no corresponde", "combat", {"signature": "f" * 64}),
        ],
    )
    def test_rechaza(
        self, client: TestClient, caso: str, service: str, changes: dict[str, str]
    ) -> None:
        response = _signed(client, "/api/probe/interna", service, {"a": 1}, **changes)
        assert response.status_code == 401  # type: ignore[attr-defined]

    def test_rechaza_una_peticion_sin_firma(self, client: TestClient) -> None:
        assert client.post("/api/probe/interna", json={"a": 1}).status_code == 401

    def test_rechaza_un_cuerpo_que_no_es_json(self, client: TestClient) -> None:
        timestamp = str(int(NOW.timestamp() * 1000))
        response = client.post(
            "/api/probe/interna",
            content=b"{no json",
            headers={
                "x-internal-service": "combat",
                "x-internal-timestamp": timestamp,
                "x-internal-signature": "f" * 64,
            },
        )
        assert response.status_code == 401

    def test_la_ruta_acotada_admite_solo_a_su_servicio(self, client: TestClient) -> None:
        # Control: el mismo servicio global con firma valida pasa en la ruta general.
        assert _signed(client, "/api/probe/interna", "missions", {}).status_code == 201  # type: ignore[attr-defined]
        acotada = _signed(client, "/api/probe/interna-acotada", "missions", {})
        assert acotada.status_code == 401  # type: ignore[attr-defined]
        assert _signed(client, "/api/probe/interna-acotada", "combat", {}).status_code == 201  # type: ignore[attr-defined]

    def test_toma_la_primera_cabecera_cuando_llega_repetida(self, client: TestClient) -> None:
        timestamp = str(int(NOW.timestamp() * 1000))
        signature = sign_internal_request(
            SECRET,
            CanonicalRequest("combat", "POST", "/api/probe/interna", timestamp, {}),
        )
        response = client.post(
            "/api/probe/interna",
            content=b"{}",
            headers=[
                ("content-type", "application/json"),
                ("x-internal-service", "combat"),
                ("x-internal-service", "catalog"),
                ("x-internal-timestamp", timestamp),
                ("x-internal-signature", signature),
            ],
        )
        assert response.status_code == 201

    def test_sin_secreto_niega_con_503(self) -> None:
        env = {k: v for k, v in JWT_ENV.items() if k != "INTERNAL_SERVICE_AUTH_SECRET"}
        with _client(env, internal_callers=("combat",)) as test_client:
            assert _signed(test_client, "/api/probe/interna", "combat", {}).status_code == 503  # type: ignore[attr-defined]

    def test_el_producto_no_declara_consumidores_internos(self) -> None:
        # ADR-022: Chatbot no ofrece rutas internas. Con la lista del producto, una
        # firma valida de cualquier servicio se rechaza; el control de que una firma
        # correcta SI se acepta es `test_acepta_a_un_consumidor_declarado...`.
        assert INTERNAL_CALLERS == ()
        with _client(JWT_ENV) as test_client:
            assert _signed(test_client, "/api/probe/interna", "combat", {}).status_code == 401  # type: ignore[attr-defined]


class TestErrores:
    def test_una_ruta_desconocida_responde_404_en_json(self, client: TestClient) -> None:
        response = client.get("/api/v1/chatbot/no-existe")
        assert response.status_code == 404
        assert response.json()["statusCode"] == 404

    def test_rechaza_campos_no_declarados_con_400(self, client: TestClient) -> None:
        # Equivale a `forbidNonWhitelisted` de NestJS: un cliente no fija datos que
        # el contrato no contempla.
        response = client.post("/api/probe/validada", json={"texto": "hola", "importe": 5})
        assert response.status_code == 400
        assert response.json()["error"] == "Bad Request"
        assert client.post("/api/probe/validada", json={"texto": "hola"}).status_code == 200

    def test_la_documentacion_solo_se_expone_si_se_habilita(self) -> None:
        with _client({**JWT_ENV, "SWAGGER_ENABLED": "true"}) as abierto:
            assert abierto.get("/api/docs").status_code == 200
        with _client({**JWT_ENV, "SWAGGER_ENABLED": "false"}) as cerrado:
            assert cerrado.get("/api/docs").status_code == 404


class TestSinAutenticacion:
    def test_atribuye_la_identidad_anonima_en_lugar_de_inventar_una_persona(self) -> None:
        with _client({}) as test_client:
            assert test_client.get("/api/probe/protegida").json() == {"sujeto": "anonymous"}
            # Sin identidad no hay forma de distinguir roles: se conceden todos.
            assert test_client.get("/api/probe/raiz").status_code == 200

    def test_el_contrato_interno_sigue_exigiendo_firma(self) -> None:
        with _client({}) as test_client:
            assert test_client.post("/api/probe/interna", json={}).status_code == 503

    def test_sin_verificador_configurado_no_acepta_nada(self) -> None:
        config = load_config({"APP_ENV": "test"})
        app = create_app(config)
        verifier = app.state.auth.verifier
        with pytest.raises(RuntimeError):
            anyio.run(verifier.verify, "cualquiera")

    def test_compone_el_verificador_de_cognito_con_jwt(self) -> None:
        app = create_app(load_config({"APP_ENV": "test", **JWT_ENV}))
        assert type(app.state.auth.verifier).__name__ == "CognitoTokenVerifier"


class TestReadiness:
    def test_responde_503_si_la_base_no_responde(self) -> None:
        class DownPool:
            def connection(self, timeout: float) -> object:
                raise OSError("motor caido")

            async def open(self, wait: bool) -> None:
                return None

            async def close(self) -> None:
                return None

        with _client(JWT_ENV, pool=DownPool()) as test_client:
            response = test_client.get("/api/health/ready")
            assert response.status_code == 503
            assert response.json() == {"status": "error", "checks": {"database": "error"}}
