def describe_error(error: object) -> str:
    """Describe un error de origen desconocido sin producir texto inutil.

    Vive con la observabilidad y no con la persistencia: no tiene nada de
    especifico de una base de datos.
    """
    if isinstance(error, BaseException):
        return str(error) or type(error).__name__
    return repr(error)
