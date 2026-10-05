# Parámetros del primer entrenamiento

Decisión de diseño para el clasificador de intención de ADR-022. No cambia el algoritmo. Fija los números que la arquitectura deja abiertos. La semilla de textos está en [diccionario/semilla-v1.json](diccionario/semilla-v1.json).

## Algoritmo, ya decidido

- `TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5))`
- `LogisticRegression`
- La confianza es la probabilidad de la clase ganadora.
- Ejemplos: variaciones de la base y conversaciones revisadas. Ninguna conversación entra sin revisión.
- Validación separada del entrenamiento. Métricas: exactitud, F1 por intención, matriz de confusión.
- Una versión nace `CANDIDATE` y solo pasa a `ACTIVE` si cumple el umbral de abajo y no empeora a la vigente. Solo hay una `ACTIVE`.
- El artefacto se guarda en PostgreSQL (`bytea`).

## Números de esta versión

| Parámetro | Valor | Por qué |
| --- | --- | --- |
| `max_features` | `20000` | Techo de memoria. Con pocas variaciones por clase, subirlo no separa mejor. |
| `C` | `1.0` | Valor de partida de la regresión. |
| `class_weight` | `balanced` | Unas intenciones tendrán más frases que otras. |
| Umbral de confianza | `0.55` | Por debajo, el bot no responde: sugiere preguntas y escala. Se mueve solo con la matriz de confusión. |
| Exactitud mínima de la primera `ACTIVE` | `0.80` en validación | Si no se alcanza, faltan variaciones. No se cambia de algoritmo. |
| Promociones siguientes | el F1 macro de validación no baja respecto de la `ACTIVE` | Además de la exactitud mínima. |
| Reparto entrenamiento / validación | `80 / 20`, estratificado por intención | Cada clase aparece en los dos conjuntos. |

## Normalización, antes del vectorizador

1. Minúsculas.
2. Recortar espacios y colapsar los repetidos.
3. Quitar signos de puntuación.

No se corrige la ortografía: el n-grama de caracteres ya absorbe el error. No se traduce. Español e inglés son entradas distintas de la base.

## Qué no es una feature

La entrada del modelo es solo el texto ya normalizado. No entran vida, poder, nivel, equipo, dificultad de misión ni resultado de partida. Esos datos, si la intención lo pide, se consultan después por `/me` (HU-48) y no forman parte de este entreno.

## Sigue abierto

El reparto A/B entre `ACTIVE` y `CANDIDATE` lo cierra el Product Owner. Esta nota no lo fija.
