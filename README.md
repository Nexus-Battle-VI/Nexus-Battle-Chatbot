# Nexus-Battle-Chatbot

Servicio de Nexus Battles VI para el bounded context **Chatbot**: asistencia conversacional con un modelo propio, base de conocimiento, historial, escalamiento a soporte y analíticas.

Este repositorio contiene código y Pull Requests. No contiene Issues ni Product Backlog: la fuente única de verdad es [Nexus-Battle-Management](https://github.com/Nexus-Battle-VI/Nexus-Battle-Management).

- **Decisión que lo crea:** [ADR-022](https://github.com/Nexus-Battle-VI/Nexus-Battle-Infrastructure/blob/develop/docs/adr/ADR-022-sprint-3-bounded-contexts.md) (`Accepted`)
- **Épica:** [EPIC-04 Chatbot](https://github.com/Nexus-Battle-VI/Nexus-Battle-Management/issues/4)
- **Team propietario:** Team Alfa
- **Lenguaje:** **Python 3.13 con FastAPI.** Es la única excepción al arquetipo NestJS de [ADR-002](https://github.com/Nexus-Battle-VI/Nexus-Battle-Infrastructure/blob/develop/docs/adr/ADR-002-backend-stack.md), porque el motor es un modelo propio entrenable (scikit-learn). Las garantías del arquetipo se mantienen; ver «Paridad con los servicios NestJS».
- **Arquitectura interna:** Clean + Hexagonal
- **Base de datos:** PostgreSQL, propia y exclusiva
- **Puerto:** 3011
- **Ruta pública:** `/api/v1/chatbot*`, con las rutas de administración bajo el mismo prefijo

## Estado

**Andamiaje.** Arranca, verifica identidad, firma y comprueba el contrato interno, expone sus sondas y conecta con su base.

**No tiene todavía ninguna ruta de negocio, tabla ni modelo**: los añade cada Historia de Usuario. Mientras tanto, cualquier ruta bajo ese prefijo responde `404` en JSON.

## Qué posee este contexto

- Base de conocimiento: entradas, variaciones de pregunta, intenciones y prioridades.
- Conversaciones, historial y valoraciones (útil / no útil).
- Tickets de escalamiento a soporte humano.
- Versiones del modelo entrenado (`CANDIDATE` / `ACTIVE`) y sus métricas, guardadas en la propia base.
- Métricas de uso para el panel de analíticas.

Ningún otro servicio accede a este almacén. **Chatbot tampoco lee almacenes ajenos**: los datos del jugador (HU-48) los pide a las rutas `/me` públicas de cada servicio **con el testimonio del propio usuario**, así que solo ve lo que el usuario ya puede ver y no figura en ningún `INTERNAL_CALLERS`.

## Historias de Usuario que viven aquí

| HU | Historia |
| --- | --- |
| HU-47 | [Asistencia inteligente y contextual desde cualquier vista](https://github.com/Nexus-Battle-VI/Nexus-Battle-Management/issues/66) |
| HU-48 | [Respuestas con información real y actual del jugador](https://github.com/Nexus-Battle-VI/Nexus-Battle-Management/issues/67) |
| HU-49 | [Continuidad de soporte cuando el chatbot no resuelve](https://github.com/Nexus-Battle-VI/Nexus-Battle-Management/issues/68) |
| HU-50 | [Asistencia conversacional para realizar acciones](https://github.com/Nexus-Battle-VI/Nexus-Battle-Management/issues/80) |
| HU-51 | [Personalización, historial y aprendizaje continuo](https://github.com/Nexus-Battle-VI/Nexus-Battle-Management/issues/81) |
| HU-52 | [Analíticas de uso, resolución y calidad](https://github.com/Nexus-Battle-VI/Nexus-Battle-Management/issues/82) |
| HU-53 | [Administración de la base de conocimiento](https://github.com/Nexus-Battle-VI/Nexus-Battle-Management/issues/83) |
| HU-54 | [Entrenamiento y validación del modelo](https://github.com/Nexus-Battle-VI/Nexus-Battle-Management/issues/84) |

Diseño del motor y orden sugerido en [docs/architecture.md](docs/architecture.md).

## Estructura

```text
src/chatbot/
  domain/            Entidades, objetos de valor y politicas (sin framework ni drivers)
  application/       Casos de uso y puertos
  adapters/
    inbound/http/    Rutas FastAPI, guards y marcadores (`@public`, `@internal_only`)
    outbound/        Identidad (Cognito, firma interna), sistema, persistencia, clientes
  infrastructure/    Configuracion, observabilidad, salud, persistencia y composicion
tests/
  unit/  integration/  db/
```

`import-linter` hace fallar la CI si el dominio importa framework, drivers o adaptadores, o si la aplicación importa adaptadores o infraestructura. La composición ocurre solo en `src/chatbot/infrastructure/bootstrap/app.py`.

## Verificación local

**Este repositorio no necesita Node.** Necesita Python 3.13 y [uv](https://docs.astral.sh/uv/) (se instala con `pip install uv`).

```bash
uv sync --frozen
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run lint-imports
uv run pytest -m "not db" --cov --cov-config=.coveragerc-unit
uv run pytest -m db --cov --cov-config=.coveragerc-db   # requiere Docker
```

Cobertura mínima del **80 %** en ambas suites; por debajo, el comando falla.

**Sin Python instalado** (por ejemplo, en Windows), todo se puede ejecutar dentro de un contenedor:

```bash
docker run --rm -it -v "$PWD:/work" -w /work -e UV_PROJECT_ENVIRONMENT=/tmp/venv python:3.13.15-slim \
  sh -c 'pip install -q uv==0.12.21 && uv sync --frozen && uv run pytest -m "not db"'
```

Para arrancar el servicio en local:

```bash
uv run python -m chatbot.main                          # puerto 3011
uv run python -m chatbot.infrastructure.persistence.migrate   # con PERSISTENCE_DRIVER=postgres
```

## Configuración

Ver [.env.example](.env.example). `APP_ENV` cumple el papel de `NODE_ENV` en los servicios NestJS. Las reglas que hacen fallar el arranque son deliberadas:

| Situación | Resultado |
| --- | --- |
| `APP_ENV=production` con `AUTH_MODE=disabled` | **No arranca** (ADR-004) |
| `APP_ENV=production` con `PERSISTENCE_DRIVER=memory` | **No arranca** (ADR-022) |
| `PERSISTENCE_DRIVER=postgres` sin `DATABASE_URL` | **No arranca** |
| `AUTH_MODE=jwt` sin pool o cliente | **No arranca** |

## Paridad con los servicios NestJS

| Garantía | Aquí |
| --- | --- |
| Toda ruta nace protegida; abrir una exige `@Public()` | Dependencia global `authenticate`; abrir una ruta exige `@public` |
| Identidad del token de acceso verificado (`aws-jwt-verify`) | PyJWT contra el JWKS del pool: firma RS256, `iss`, `exp`, `token_use=access`, `client_id` |
| Solo roles conocidos de `cognito:groups`; `SUPER_ADMINISTRATOR` satisface a `ADMINISTRATOR` y no al revés | Igual, en `require_roles` |
| `@InternalOnly(...)` con HMAC-SHA256 | `@internal_only(...)`; **misma firma byte a byte**, comprobada con vectores generados por la implementación TypeScript |
| Sin secreto interno, las rutas internas responden `503` | Igual |
| Errores `{statusCode, message, error}`; `forbidNonWhitelisted` → `400` | Igual (`extra="forbid"` en los modelos de entrada) |
| Sondas `live`, `ready` (`503` sin base) y `version` | Igual; la CI para la base y exige `503` con el proceso vivo |
| Migraciones explícitas, nunca al arrancar | Contenedor `chatbot-migrate`; tabla `_migrations`; todas las pendientes en una transacción |

## Ramas

`main` y `develop` están protegidas. Todo Pull Request va a **`develop`**; `main` solo recibe la promoción completa de `develop`, y el workflow `Flujo de ramas` lo hace cumplir. Ver [CONTRIBUTING.md](CONTRIBUTING.md).

## Licencia

Licensing pending project governance.
