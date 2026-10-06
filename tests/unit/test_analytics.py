"""Agregados de uso a partir de turnos ya guardados."""

from datetime import UTC, datetime

from chatbot.domain.analytics import ObservedQuery, summarize


def test_resume_preguntas_temas_resolucion_satisfaccion_y_tendencia() -> None:
    start = datetime(2026, 10, 6, 8, tzinfo=UTC)
    end = datetime(2026, 10, 7, 9, tzinfo=UTC)
    queries = (
        ObservedQuery("cuanto dura un turno", True, "regla_turno", True, 20, start),
        ObservedQuery("Cuanto dura un turno?", True, "regla_turno", False, 40, start),
        ObservedQuery("????", False, None, None, None, end),
    )

    report = summarize(queries, 2, 1, start, end)

    assert report.conversations_started == 2
    assert report.escalations == 1
    assert report.resolution_rate == 2 / 3
    assert report.average_response_ms == 30
    assert report.satisfaction == 0.5
    assert report.frequent_questions[0].text == "cuanto dura un turno"
    assert report.frequent_questions[0].count == 2
    assert report.topics[0].intent == "regla_turno"
    assert any(item.text == "turno" for item in report.keywords)
    assert "que" not in {item.text for item in report.keywords}
    assert [point.queries for point in report.trend] == [2, 1]
    assert report.trend[0].resolved == 2
    assert report.trend[1].resolved == 0


def test_sin_consultas_no_inventa_tasa_ni_satisfaccion() -> None:
    moment = datetime(2026, 10, 6, tzinfo=UTC)
    report = summarize((), 0, 0, moment, moment)
    assert report.resolution_rate is None
    assert report.average_response_ms is None
    assert report.satisfaction is None
    assert report.trend[0].queries == 0
