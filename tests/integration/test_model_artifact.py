"""El artefacto guardado vuelve a clasificar igual."""

from chatbot.adapters.outbound.nlp.sklearn_intent import SklearnIntentModelFactory


def test_el_artefacto_se_vuelve_a_cargar() -> None:
    factory = SklearnIntentModelFactory()
    examples = tuple(("es:regla_turno", f"turno {index}") for index in range(6)) + tuple(
        ("es:cuenta", f"cuenta {index}") for index in range(6)
    )
    trained = factory.train(examples)
    restored = factory.load(trained.artifact())
    assert restored.predict("turno 1")[0] == "es:regla_turno"
    assert restored.predict("cuenta 1")[0] == "es:cuenta"
