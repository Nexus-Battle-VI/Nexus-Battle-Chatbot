"""Firma interna: conformidad con la implementacion TypeScript de los servicios NestJS.

Los vectores de `tests/fixtures/internal-signature-vectors.json` los genero
`internal-signature.ts` (Wallet 4d9f0e9). Si este modulo firmara distinto, un
servicio NestJS rechazaria toda llamada de Chatbot, o al reves, sin ningun
mensaje que explicara por que.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from chatbot.adapters.outbound.identity.internal_signature import (
    CanonicalRequest,
    canonical_body,
    canonical_string,
    sign_internal_request,
    signature_matches,
    timestamp_within_window,
)

FIXTURE = json.loads(
    (Path(__file__).parent.parent / "fixtures" / "internal-signature-vectors.json").read_text(
        encoding="utf-8"
    )
)
VECTORS = FIXTURE["vectors"]


def _request(vector: dict[str, object]) -> CanonicalRequest:
    raw = vector["request"]
    assert isinstance(raw, dict)
    return CanonicalRequest(
        service=raw["service"],
        method=raw["method"],
        path=raw["path"],
        timestamp=raw["timestamp"],
        body=raw["body"],
    )


@pytest.mark.parametrize("vector", VECTORS, ids=[str(i) for i in range(len(VECTORS))])
def test_reproduce_el_cuerpo_canonico_de_typescript(vector: dict[str, object]) -> None:
    assert canonical_body(_request(vector).body) == vector["canonicalBody"]


@pytest.mark.parametrize("vector", VECTORS, ids=[str(i) for i in range(len(VECTORS))])
def test_reproduce_la_firma_de_typescript(vector: dict[str, object]) -> None:
    request = _request(vector)
    assert canonical_string(request) == vector["canonicalString"]
    assert sign_internal_request(FIXTURE["secret"], request) == vector["signature"]


def test_los_vectores_cubren_los_casos_dificiles() -> None:
    # Control de la conformidad: si los vectores no ejercitaran numeros, orden de
    # claves y texto no ASCII, las pruebas de arriba pasarian sin demostrar nada.
    bodies = "".join(vector["canonicalBody"] for vector in VECTORS)
    for fragment in ("1e+21", "1e-7", "123456789012345680000", "último", "\\u0001", '"10":10,"2"'):
        assert fragment in bodies


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (5.0, "5"),
        (-0.0, "0"),
        (0.5, "0.5"),
        (0.000001, "0.000001"),
        (1e-7, "1e-7"),
        (100.0, "100"),
        (2**53 + 1, "9007199254740992"),
        (float("nan"), "null"),
        ({"b": 1, "a": None}, '{"a":null,"b":1}'),
        (("x", True), '["x",true]'),
    ],
)
def test_formatea_como_json_stringify(value: object, expected: str) -> None:
    assert canonical_body(value) == expected


def test_rechaza_tipos_que_no_son_json() -> None:
    with pytest.raises(TypeError):
        canonical_body({"fecha": datetime.now(UTC)})


def test_ordena_las_claves_por_unidades_utf16_como_javascript() -> None:
    # Por puntos de codigo, U+FF5E va antes que U+1F600. Por unidades UTF-16 va
    # despues, porque U+1F600 se codifica como el sustituto D83D, menor que FF5E.
    # JavaScript ordena por unidades UTF-16, y la firma debe coincidir con la suya.
    tilde = chr(0xFF5E)
    smile = chr(0x1F600)
    assert canonical_body({tilde: 1, smile: 2}) == '{"' + smile + '":2,"' + tilde + '":1}'
    # Control: ordenar por puntos de codigo daria el orden contrario.
    assert sorted([tilde, smile]) == [tilde, smile]


def test_firma_metodo_ruta_sello_y_resumen() -> None:
    lines = canonical_string(
        CanonicalRequest(service="combat", method="post", path="/p", timestamp="1", body={})
    ).split("\n")
    assert lines[:4] == ["combat", "POST", "/p", "1"]
    assert len(lines[4]) == 64


def test_compara_firmas_sin_aceptar_ausentes_ni_distintas() -> None:
    assert signature_matches("abc", "abc")
    assert not signature_matches("abc", "abd")
    assert not signature_matches("abc", "ab")
    assert not signature_matches("abc", None)


def test_acota_la_ventana_del_sello() -> None:
    now = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)
    now_ms = int(now.timestamp() * 1000)
    assert timestamp_within_window(str(now_ms - 30_000), now, 30_000)
    assert not timestamp_within_window(str(now_ms - 30_001), now, 30_000)
    assert not timestamp_within_window("no-es-numero", now, 30_000)
    assert not timestamp_within_window("inf", now, 30_000)
    # `Number('')` es 0 en JavaScript: muy fuera de la ventana.
    assert not timestamp_within_window("", now, 30_000)
