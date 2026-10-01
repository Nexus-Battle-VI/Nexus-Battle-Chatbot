# Contribución a Nexus-Battle-Chatbot

Toda contribución ingresa mediante Pull Request y debe ser trazable hasta una Issue de [Nexus-Battle-Management](https://github.com/Nexus-Battle-VI/Nexus-Battle-Management), fuente única del Product Backlog. Este repositorio no tiene Issues ni Project propios.

## Ramas

Hay **dos ramas protegidas**: `develop` y `main`.

- Cada cambio se hace en una rama corta creada desde `develop` y vuelve a `develop` por Pull Request.
- `main` es la rama que publica la imagen en GHCR. Solo recibe la promoción completa de `develop`; el workflow `Flujo de ramas` falla si el árbol propuesto no coincide exactamente con `develop`.
- Solo se admite _squash_. Por eso contar commits no dice si dos ramas están a la par; se compara el contenido:

```bash
git diff --stat origin/main origin/develop
```

Nombres de rama:

```text
feat/hu-NN-descripcion-corta
fix/bug-NN-descripcion-corta
test/hu-NN-concurrencia
docs/contrato-interno
```

## Commits

Conventional Commits con los tipos `feat`, `fix`, `docs`, `test`, `refactor`, `chore`, `ci` y `build`. El título del Pull Request es el mensaje del commit de integración:

```text
feat(chatbot): [HU-NN] descripcion en infinitivo
fix(chatbot): [BUG-NN] descripcion en infinitivo
```

## Trazabilidad

```text
Refs Nexus-Battle-VI/Nexus-Battle-Management#NUMERO
```

Nunca `#NUMERO` a secas. `Closes` solo cuando el Pull Request completa totalmente una Task o un Bug. **Un Pull Request no cierra la Historia de Usuario padre**, y una suite verde no basta para cerrarla: la HU se cierra con evidencia y aceptación del Product Owner.

## Flujo

1. La Issue cumple la Definition of Ready.
2. Si la HU cambia un contrato público o interno, el contrato se actualiza primero en `Nexus-Battle-Infrastructure/docs/contracts`.
3. Rama desde `develop` actualizada.
4. Red → Green → Refactor.
5. Verificación local completa (ver README).
6. Pull Request hacia `develop` con la plantilla completa.
7. Revisión del Code Owner e integración por _squash_ con la CI en verde.

## Reglas de arquitectura

- El dominio (`src/chatbot/domain`) no importa FastAPI, Pydantic, drivers, HTTP, scikit-learn ni adaptadores. Lo hace cumplir `lint-imports`.
- La aplicación (`src/chatbot/application`) depende de sus puertos (`typing.Protocol`), nunca de adaptadores concretos.
- Las implementaciones se eligen solo en `src/chatbot/infrastructure/bootstrap/app.py`.
- Casos de uso como clases planas, construidas en la raíz de composición.
- **Toda ruta nace protegida.** Abrir una exige `@public`; el marcador va debajo del decorador de FastAPI.
- La identidad se obtiene con `Depends(current_identity)`, nunca del cuerpo ni de la URL.
- Los modelos de entrada declaran `model_config = ConfigDict(extra="forbid")`: un cliente no fija datos que el contrato no contempla.
- **Las invariantes se declaran también en el motor de base de datos**, no solo en el código.
- Prohibido acceder a la base de datos de otro servicio, claves foráneas entre servicios y paquetes comunes de dominio (ADR-001).
- Chatbot no mueve créditos ni productos: los datos del jugador se leen de las rutas `/me` con el testimonio del propio usuario (ADR-022).
- Las migraciones se numeran en secuencia (`001-...`), nunca con la fecha de escritura.

## Pruebas

- Unitarias para dominio, aplicación y adaptadores (`tests/unit`).
- Integración HTTP con `TestClient` contra la aplicación FastAPI real (`tests/integration`).
- Contra motor real con Testcontainers en `tests/db` (marca `db`).
- **Todo modelo entrenado se valida contra un conjunto separado antes de activarse** (HU-54).
- **Cada afirmación importante lleva un control**: un caso que fallaría si fuera falsa. Una prueba que solo puede pasar no prueba nada.
- No se admiten pruebas vacías ni deshabilitadas sin justificación en el Pull Request.

## Seguridad

Ningún secreto, token ni credencial en el repositorio. Ver [SECURITY.md](SECURITY.md).

## Dependencias

Solo **uv**, con `uv.lock` (`uv sync --frozen`). Versiones fijadas exactas en `pyproject.toml` (ADR-022).
