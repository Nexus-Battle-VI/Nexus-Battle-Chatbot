"""Caminos que el jugador ya puede abrir. El chatbot no ejecuta la acción."""

ASSISTED_ACTIONS: dict[str, tuple[str, str]] = {
    "cuenta_gestion": ("configuracion_cuenta", "/account"),
    "mi_inventario": ("buscar_inventario", "/inventory"),
    "mi_mision": ("consultar_misiones", "/missions"),
    "modo_mision": ("consultar_misiones", "/missions"),
    "modo_jcj": ("ir_a_jugar", "/play"),
    "modo_jce": ("ir_a_jugar", "/play"),
    "modo_torneo": ("ir_a_torneo", "/tournament"),
    "mi_subasta": ("ir_a_subasta", "/auction"),
    "reporte_actividad": ("reporte_actividad", "/missions/history"),
}


def assisted_action(label: str | None) -> tuple[str, str] | None:
    if label is None:
        return None
    _language, separator, intent = label.partition(":")
    if separator == "":
        return None
    return ASSISTED_ACTIONS.get(intent)
