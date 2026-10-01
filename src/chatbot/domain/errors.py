"""Errores del dominio.

El dominio no importa framework, drivers ni adaptadores: lo impide
import-linter en CI (ver `pyproject.toml`). Cada Historia de Usuario anade aqui
sus errores; el andamiaje solo declara la raiz.
"""


class DomainError(Exception):
    """Raiz de los errores de negocio de este contexto."""
