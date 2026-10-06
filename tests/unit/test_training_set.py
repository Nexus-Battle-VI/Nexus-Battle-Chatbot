"""Filtro del conjunto, el corte 80/20 y la regla de promoción. Sin modelo."""

from chatbot.domain.knowledge_entry import knowledge_entry
from chatbot.domain.training_set import (
    MINIMUM_ACCURACY,
    ConversationTurn,
    ValidationMetrics,
    conversation_example,
    dictionary_examples,
    should_promote,
    split_examples,
    validation_metrics,
)


def _entry(intent: str, variations: tuple[str, ...]) -> object:
    return knowledge_entry(
        entry_id="00000000-0000-4000-8000-000000000010",
        intent=intent,
        language="es",
        priority=1,
        answer="respuesta",
        variations=variations,
    )


def test_solo_entra_la_conversacion_util_con_intencion() -> None:
    useful = ConversationTurn("Cuanto dura?", "es", "regla_turno", True, False)
    useless = ConversationTurn("Cuanto dura?", "es", "regla_turno", False, False)
    pending = ConversationTurn("Cuanto dura?", "es", "regla_turno", None, False)
    deleted = ConversationTurn("Cuanto dura?", "es", "regla_turno", True, True)
    unlabeled = ConversationTurn("Cuanto dura?", "es", None, True, False)

    assert conversation_example(useful) == ("es:regla_turno", "cuanto dura")
    assert conversation_example(useless) is None
    assert conversation_example(pending) is None
    assert conversation_example(deleted) is None
    assert conversation_example(unlabeled) is None


def test_una_clase_con_un_ejemplo_no_entra_en_validacion() -> None:
    examples = dictionary_examples(
        (
            _entry("regla_turno", ("uno", "dos", "tres", "cuatro", "cinco")),  # type: ignore[arg-type]
            _entry("cuenta", ("sola",)),  # type: ignore[arg-type]
        )
    )
    train, validation, singles = split_examples(examples)
    assert singles == ("es:cuenta",)
    assert ("es:cuenta", "sola") in train
    assert all(label != "es:cuenta" for label, _text in validation)
    assert len(validation) >= 1
    assert len(train) + len(validation) == len(examples)


def test_por_debajo_de_0_80_no_se_promueve() -> None:
    low = ValidationMetrics(MINIMUM_ACCURACY - 0.01, 0.9, (), ())
    enough = ValidationMetrics(MINIMUM_ACCURACY, 0.7, (), ())
    assert should_promote(low, None) is False
    assert should_promote(enough, None) is True
    assert should_promote(enough, 0.7) is True
    assert should_promote(enough, 0.71) is False


def test_las_metricas_cuentan_aciertos_y_la_matriz() -> None:
    metrics = validation_metrics(("es:a", "es:a", "es:b"), ("es:a", "es:b", "es:b"))
    assert metrics.accuracy == 2 / 3
    assert metrics.confusion == (("es:a", "es:a", 1), ("es:a", "es:b", 1), ("es:b", "es:b", 1))
    assert validation_metrics((), ()).accuracy == 0.0
