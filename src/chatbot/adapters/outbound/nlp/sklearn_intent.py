"""Clasificador de intencion (ADR-022, HU-47.2).

Vive en adaptadores: el dominio y la aplicacion no importan scikit-learn.
La etiqueta es `idioma:intencion`, para no mezclar la respuesta en espanol
con la de ingles.
"""

import io
import json

_MAX_FEATURES = 20_000


class _SingleIntent:
    def __init__(self, label: str | None) -> None:
        self._label = label

    def predict(self, text: str) -> tuple[str | None, float, tuple[str, ...]]:
        del text
        if self._label is None:
            return None, 0.0, ()
        return self._label, 1.0, ()

    def artifact(self) -> bytes:
        label = "" if self._label is None else self._label
        return json.dumps({"kind": "single", "label": label}).encode()


class _SklearnIntent:
    def __init__(self, vectorizer: object, classifier: object) -> None:
        self._vectorizer = vectorizer
        self._classifier = classifier

    def predict(self, text: str) -> tuple[str | None, float, tuple[str, ...]]:
        matrix = self._vectorizer.transform([text])  # type: ignore[attr-defined]
        probabilities = self._classifier.predict_proba(matrix)[0]  # type: ignore[attr-defined]
        order = sorted(
            range(len(probabilities)),
            key=lambda index: probabilities[index],
            reverse=True,
        )
        best = order[0]
        classes = self._classifier.classes_  # type: ignore[attr-defined]
        others = tuple(str(classes[index]) for index in order[1:4])
        return str(classes[best]), float(probabilities[best]), others

    def artifact(self) -> bytes:
        from joblib import dump  # noqa: PLC0415

        buffer = io.BytesIO()
        dump({"vectorizer": self._vectorizer, "classifier": self._classifier}, buffer)
        return buffer.getvalue()


class SklearnIntentModelFactory:
    def train(self, examples: tuple[tuple[str, str], ...]) -> _SingleIntent | _SklearnIntent:
        usable = tuple((label, text) for label, text in examples if text != "")
        labels = list(dict.fromkeys(label for label, _text in usable))
        if len(labels) < 2:
            return _SingleIntent(labels[0] if labels else None)
        # La importacion queda aqui: el resto del servicio no carga scikit-learn
        # hasta que hay una consulta que entrenar.
        from sklearn.feature_extraction.text import TfidfVectorizer  # noqa: PLC0415
        from sklearn.linear_model import LogisticRegression  # noqa: PLC0415

        vectorizer = TfidfVectorizer(
            analyzer="char_wb",
            ngram_range=(2, 5),
            max_features=_MAX_FEATURES,
        )
        matrix = vectorizer.fit_transform([text for _label, text in usable])
        classifier = LogisticRegression(C=1.0, class_weight="balanced", max_iter=1000)
        classifier.fit(matrix, [label for label, _text in usable])
        return _SklearnIntent(vectorizer, classifier)

    def load(self, artifact: bytes) -> _SingleIntent | _SklearnIntent:
        if artifact.startswith(b"{"):
            raw = json.loads(artifact)
            if isinstance(raw, dict) and raw.get("kind") == "single":
                label = raw.get("label")
                return _SingleIntent(None if not isinstance(label, str) or label == "" else label)
        from joblib import load as joblib_load  # noqa: PLC0415

        loaded = joblib_load(io.BytesIO(artifact))
        return _SklearnIntent(loaded["vectorizer"], loaded["classifier"])
