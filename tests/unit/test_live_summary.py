"""El número de un dato propio concuerda en singular y en plural."""

from chatbot.domain.live_summary import (
    summarize_auctions,
    summarize_missions,
    summarize_notifications,
    summarize_transactions,
)


def test_una_mision_va_en_singular() -> None:
    text = summarize_missions(
        {"items": [{"missionName": "Travesía por el Bosque Sombrío", "progressPercent": 86}]}
    )
    assert text == "Tienes 1 misión en curso: Travesía por el Bosque Sombrío (86%)."


def test_varias_misiones_van_en_plural() -> None:
    text = summarize_missions(
        {
            "items": [
                {"missionName": "Bosque", "progressPercent": 10},
                {"missionName": "Costa", "progressPercent": 20},
            ]
        }
    )
    assert text == "Tienes 2 misiones en curso: Bosque (10%), Costa (20%)."


def test_una_subasta_una_notificacion_y_una_transaccion_van_en_singular() -> None:
    assert summarize_auctions({"items": [{"status": "OPEN"}], "total": 1}) == (
        "Tienes 1 subasta. Estados en esta página: OPEN."
    )
    assert summarize_notifications({"items": [{"id": "n1"}]}) == "Tienes 1 notificación pendiente."
    assert summarize_transactions({"items": [{"type": "BID"}], "total": 1}) == (
        "Tienes 1 transacción de subasta. En esta página: BID."
    )
