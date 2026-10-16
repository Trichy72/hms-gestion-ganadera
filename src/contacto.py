"""Tipos de contacto con el cliente (política de HMS): WhatsApp de rutina,
llamado cuando el semáforo lo pide, visita técnica incluida o con cargo,
entrevista y recordatorios internos. Los usan la agenda, las charlas y el
calendario.

(clave, nombre, ícono, color, cómo se lee en "Para hoy")
"""
TIPOS_CONTACTO = [
    ("whatsapp", "WhatsApp", "💬", "#1E8E4E", "WhatsApp"),
    ("llamado", "Llamado", "📲", "#1F6FB2", "llamar"),
    ("visita", "Visita técnica", "🚗", "#8A5A00", "visita técnica"),
    ("visita_cargo", "Visita con cargo", "💵", "#6A3FA0", "visita con cargo"),
    ("entrevista", "Entrevista", "🗒", "#2E7D32", "entrevista"),
    ("tarea", "Recordatorio", "📌", "#B42318", "recordatorio"),
]

# Íconos de línea, mismo estilo que los del semáforo (trazo redondeado sobre
# círculo), pero el círculo toma el color de cada tipo de contacto.
_SVG_IN = {
    "whatsapp": '<path d="M5.2 18.8l1-3.2A7.6 7.6 0 1 1 9 18.3z"/><path d="M9.3 9.2c.2 2.3 2.2 4.4 4.6 4.8l.9-1.1 1.6.8-.4 1.4c-3.5.3-7-3.2-6.7-6.7l1.4-.4.8 1.6z"/>',
    "llamado": '<path d="M6.5 4h3l1.5 4-2 1.3a10 10 0 0 0 5.7 5.7L16 13l4 1.5v3a2 2 0 0 1-2.2 2A15.5 15.5 0 0 1 4.5 6.2 2 2 0 0 1 6.5 4z"/>',
    "visita": '<path d="M3.5 15.5v-3.2l2-4.3h9l3 4.3h1.5a1.5 1.5 0 0 1 1.5 1.5v1.7"/><path d="M3.5 15.5h1.4M9.6 15.5h4.8M19.1 15.5h1.4"/><circle cx="7.2" cy="15.8" r="2.1"/><circle cx="16.8" cy="15.8" r="2.1"/><path d="M8 8v4.3h9.5"/>',
    "visita_cargo": '<rect x="3" y="6.5" width="18" height="11" rx="2"/><circle cx="12" cy="12" r="2.6"/><path d="M6.5 9.5v5M17.5 9.5v5"/>',
    "entrevista": '<rect x="5" y="4.5" width="14" height="16.5" rx="2"/><path d="M9 4.5V3.5h6v1"/><path d="M8.5 10h7M8.5 13.5h7M8.5 17h4"/>',
    "tarea": '<path d="M9 4h6l-1 5 3 3v1.5H7V12l3-3z"/><path d="M12 13.5V20"/>',
}
_COLOR = {k: c for k, _, _, c, _ in TIPOS_CONTACTO}
_POR_EMOJI = {ico: k for k, _, ico, _, _ in TIPOS_CONTACTO}


def svg(clave: str, tam: int = 18, color: str = "") -> str:
    """Solo el trazo, del color del tipo (o el que se pase)."""
    if clave not in _SVG_IN:
        return ""
    col = color or _COLOR.get(clave, "currentColor")
    return (f'<svg viewBox="0 0 24 24" width="{tam}" height="{tam}" fill="none" stroke="{col}" '
            f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" '
            f'style="vertical-align:-3px;flex:none">{_SVG_IN[clave]}</svg>')


def icono(clave: str, tam: int = 38) -> str:
    """Ícono en círculo, como los del semáforo, con el color del tipo."""
    col = _COLOR.get(clave, "#5B6B5F")
    return (f'<span style="display:inline-flex;align-items:center;justify-content:center;width:{tam}px;'
            f'height:{tam}px;border-radius:50%;background:{col}1F;box-shadow:inset 0 0 0 1.5px {col}40;'
            f'flex:none">{svg(clave, int(tam * 0.55))}</span>')


def clave_de_emoji(ico: str) -> str:
    return _POR_EMOJI.get(ico, "")


# Para los botones de Streamlit (solo aceptan íconos de Google Material)
MATERIAL = {"whatsapp": ":material/chat:", "llamado": ":material/call:",
            "visita": ":material/directions_car:", "visita_cargo": ":material/payments:",
            "entrevista": ":material/assignment:", "tarea": ":material/push_pin:"}
