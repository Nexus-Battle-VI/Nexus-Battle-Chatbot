# Arquitectura de Chatbot

Fuente de la decisión: [ADR-022](https://github.com/Nexus-Battle-VI/Nexus-Battle-Infrastructure/blob/develop/docs/adr/ADR-022-sprint-3-bounded-contexts.md).
Este documento describe lo **previsto**. Los contratos exactos se publican en `Nexus-Battle-Infrastructure/docs/contracts` antes de implementarse.

## Responsabilidad

Asistencia conversacional disponible en todas las vistas, para visitantes y jugadores, en español e inglés (§7.4 del documento oficial). Los temas son productos, reglas, modos de juego, cuenta, subastas, soporte técnico, términos y preguntas frecuentes. Cuando el jugador tiene sesión, la respuesta usa sus datos reales. Cuando el bot no sabe, lo dice y escala a soporte, **nunca inventa**.

## Motor propio (sin LLM)

```text
Pregunta -> normalizar -> clasificador de intencion -> confianza >= umbral ?
                                                         | si: respuesta de la base de conocimiento
                                                         |     (+ datos del jugador via /me, HU-48)
                                                         | no: preguntas sugeridas + escalamiento (HU-49)
```

- **Clasificador**: `TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5))` + `LogisticRegression`.
  - Los n-gramas de caracteres toleran errores ortográficos y no necesitan un tokenizador por idioma.
  - `max_features` acotado, para que el modelo y su memoria tengan techo. Los números del primer entreno (`max_features` 20000, confianza 0,55, exactitud mínima 0,80) están en [parametros-entrenamiento-v1.md](parametros-entrenamiento-v1.md). La semilla de intenciones de texto está en [diccionario/semilla-v1.json](diccionario/semilla-v1.json).
- **Datos de entrenamiento**: las variaciones de pregunta de la base de conocimiento (HU-53) y las conversaciones etiquetadas tras revisión (HU-51). **Ninguna conversación entra al entrenamiento sin revisión.**
- **Ciclo de vida (HU-54)**:
  1. Entrenar produce una versión `CANDIDATE`, con métricas sobre un conjunto de validación separado: exactitud, F1 por intención y matriz de confusión.
  2. Solo pasa a `ACTIVE` si supera el umbral mínimo **y** a la versión vigente.
  3. La prueba A/B reparte sesiones por hash estable entre `ACTIVE` y `CANDIDATE`.
  4. Cada respuesta guarda la versión que la produjo.
- **Almacenamiento del modelo**: `bytea` versionado en la propia base. El nodo `app` no guarda estado y S3 está prohibido (ADR-007). «Solo una versión `ACTIVE`» es un índice único parcial.
- **Entrenamiento dentro del proceso**, en segundo plano. Sigue el patrón de temporizadores de ADR-019: estado en la base y una sola ejecución a la vez.
- **Caché de respuestas frecuentes**: LRU en proceso, con clave (versión del modelo, pregunta normalizada). Cambiar de versión la invalida.

## Historial y valoración (HU-51)

Cada consulta se guarda cifrada, ligada al `player:{sub}` o al `visitor:{sesión}` que el servicio emitió. `GET /api/v1/chatbot/messages/history` devuelve solo ese historial. `POST /api/v1/chatbot/messages/{id}/rating` con `{useful}` califica esa respuesta una vez: útil entra al siguiente entrenamiento con su intención; no útil queda revisada y no se suma como ejemplo. Borrar el historial lo saca del conjunto. La preferencia que ya existe, mostrar la hora, se guarda por persona en `PUT /api/v1/chatbot/preferences`. El diccionario no tiene una variante breve y otra extensa, así que el texto de la respuesta no cambia de longitud. Una pregunta sin resolver sigue siendo el ticket de HU-49; no se inserta sola en el diccionario.

## Analíticas (HU-52)

`GET /api/v1/chatbot/admin/analytics` exige `ADMINISTRATOR` y un periodo `from`/`to` de hasta 366 días. Cuenta conversaciones cuyo primer turno cae en el periodo, las preguntas y las intenciones más repetidas, la tasa de turnos que sí trajeron respuesta, el promedio de los milisegundos medidos al responder, la satisfacción entre valoraciones útiles y no útiles, los tickets de HU-49 y, por día UTC, las consultas y las resueltas. Las palabras salen del texto ya normalizado, sin partículas gramaticales. No hay cifra cuando no hay turnos, duraciones o valoraciones. El listado no incluye al actor.

## Tickets (HU-49)

Si `answered` es falso, la respuesta incluye `ticketId` y el servicio guarda la pregunta ya redactada, la vista y el actor (`player:{sub}` o `visitor:{sesión}`). `POST /api/v1/chatbot/tickets` abre un ticket con el texto que envía el widget al transferir. `GET /api/v1/chatbot/admin/tickets` lista esos tickets y exige `ADMINISTRATOR`. No se envía correo y la pregunta no entra al diccionario.

## Datos del jugador y acciones (HU-48, HU-50)

Chatbot llama por la red interna a las rutas `/me` **públicas** de Player/Inventory, Missions, Auction, Wallet, Notifications y Tournament. Reenvía el **testimonio del propio usuario**.

- No tiene privilegios propios ni figura en ningún `INTERNAL_CALLERS`.
- Solo ve lo que el usuario podría ver por sí mismo. Es lo que exige HU-50: «sin privilegios adicionales».
- Sin sesión, solo responde con la base de conocimiento pública.
- Las acciones de HU-50 son intenciones que devuelven **navegación o consultas**. El bot no ejecuta operaciones de dinero ni de inventario.

## Seguridad y privacidad (§7.4.8)

- Límite de tasa por IP o sujeto, en memoria (una sola réplica, ADR-019), y longitud máxima por mensaje.
- Filtro de contenido inapropiado y tratamiento de toda entrada como texto: nunca se interpreta como código ni como consulta.
- **Nunca se persisten contraseñas ni datos de pago**: se redactan con patrones antes de guardar.
- El usuario puede borrar su historial (PO-18). La retención la fija el Product Owner.

## Datos que posee

| Dato | Notas |
| --- | --- |
| Base de conocimiento | Entradas, variaciones, intenciones, prioridades, idioma; búsqueda full-text `tsvector` español/inglés |
| Conversaciones y mensajes | Ligadas al `sub` del testimonio o a una sesión anónima |
| Valoraciones | Útil / no útil, por respuesta |
| Tickets de escalamiento | Consulta original y contexto (HU-49) |
| Versiones del modelo | Artefacto, métricas, estado |
| Métricas | Para el panel de HU-52 |

## Orden sugerido

HU-53 → HU-47 → HU-54 → HU-48 → HU-50 → HU-49 → HU-51 → HU-52.

## Decisiones abiertas (Product Owner)

- Aviso por correo de los tickets de HU-49. El servicio ya guarda el ticket y un administrador lo lista; Notifications sigue sin un destino definido.
- Qué es «generar reportes de actividad» (HU-50).
- Retención del historial de conversaciones.
- Alcance mínimo aceptable de A/B y reentrenamiento en este sprint.
