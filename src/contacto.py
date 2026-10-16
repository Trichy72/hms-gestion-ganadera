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
