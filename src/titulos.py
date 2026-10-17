"""Títulos de sección con ícono.

Todas las pantallas arman sus títulos como <div class="hm-lbl">TEXTO · detalle</div>.
`con_iconos` les agrega el ícono que corresponde según la primera palabra y
separa el detalle (lo que va después del "·") para mostrarlo más chico.
"""
from __future__ import annotations

import re
import unicodedata

# Íconos de línea, 24x24, trazo del color del texto
_P = {
    "hoy": '<rect x="4" y="5" width="16" height="16" rx="2"/><path d="M8 3v4M16 3v4M4 10h16"/><path d="m9 15 2 2 4-4"/>',
    "clientes": '<circle cx="9" cy="8" r="3.2"/><path d="M3 20c0-3.3 2.7-5.5 6-5.5s6 2.2 6 5.5"/><path d="M16 4.6a3.2 3.2 0 0 1 0 6.3M18 14.8c1.9.7 3 2.6 3 5.2"/>',
    "semaforo": '<rect x="7" y="2.5" width="10" height="19" rx="3"/><circle cx="12" cy="7" r="1.6"/><circle cx="12" cy="12" r="1.6"/><circle cx="12" cy="17" r="1.6"/>',
    "calendario": '<rect x="4" y="5" width="16" height="16" rx="2"/><path d="M8 3v4M16 3v4M4 10h16M8 14h2M12 14h2M16 14h0M8 17.5h2M12 17.5h2"/>',
    "peso": '<path d="M5 20h14l-2-11H7z"/><circle cx="12" cy="6" r="2.4"/><path d="m12 12 1.6 3"/>',
    "alimento": '<path d="M6 8h12l-1.2 12H7.2z"/><path d="M8 8c0-2.5 1.8-4.5 4-4.5s4 2 4 4.5"/><path d="M10 13h4"/>',
    "control": '<rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 4V2.8h6V4"/><path d="m9 13 2 2 4-4"/>',
    "plan": '<path d="M4 20h4v-5h4v-5h4V5h4"/>',
    "informe": '<path d="M7 3h7l5 5v13H7z"/><path d="M14 3v5h5M10 13h6M10 17h6"/>',
    "seguimiento": '<path d="M3 12h4l2.5-6 5 12 2.5-6H21"/>',
    "historia": '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
    "fotos": '<path d="M4 8h3l1.5-2.5h7L17 8h3v11H4z"/><circle cx="12" cy="13" r="3.3"/>',
    "charlas": '<path d="M4 5h16v10H9l-5 4z"/><path d="M8 9h8M8 12h5"/>',
    "situacion": '<path d="M12 3 4.5 6v5.5c0 4.5 3.2 8.2 7.5 9.5 4.3-1.3 7.5-5 7.5-9.5V6z"/><path d="m9 12 2 2 4-4"/>',
    "ia": '<path d="M12 3.5 13.8 9l5.7 1.8-5.7 1.8L12 18l-1.8-5.4L4.5 10.8 10.2 9z"/><path d="M19 3v3M17.5 4.5h3"/>',
    "racion": '<path d="M3.5 11h17c0 5-3.8 8.5-8.5 8.5S3.5 16 3.5 11z"/><path d="M8 8c0-1.5 1-1.5 1-3M12 8c0-1.5 1-1.5 1-3M16 8c0-1.5 1-1.5 1-3"/>',
    "movimientos": '<path d="M4 8h13l-3-3M20 16H7l3 3"/>',
    "uniformidad": '<path d="M5 20V12M10 20V6M15 20V9M20 20v-6M3 20h18"/>',
    "clima": '<circle cx="8" cy="9" r="3"/><path d="M8 2.5v1.5M2.5 9H4M3.8 4.8l1 1M12.2 4.8l-1 1"/><path d="M9 20h9a3.5 3.5 0 0 0 .3-7 5 5 0 0 0-9.6 1.2A3 3 0 0 0 9 20z"/>',
    "cargar": '<circle cx="12" cy="12" r="8.5"/><path d="M12 8v8M8 12h8"/>',
    "datos": '<rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="8.5" cy="11" r="2"/><path d="M5.5 16c.6-1.5 1.7-2.2 3-2.2s2.4.7 3 2.2M14 10h4M14 13.5h4"/>',
    "lotes": '<path d="m12 3 9 4.5-9 4.5-9-4.5z"/><path d="m3 12 9 4.5 9-4.5M3 16.5 12 21l9-4.5"/>',
    "anteriores": '<rect x="3.5" y="4" width="17" height="5" rx="1"/><path d="M5 9v11h14V9M10 13h4"/>',
}

# Primera(s) palabra(s) del título → ícono
_CLAVES = [
    ("para hoy", "hoy"), ("clientes", "clientes"), ("semaforo", "semaforo"),
    ("calendario", "calendario"), ("peso", "peso"), ("alimento", "alimento"),
    ("control semanal", "control"), ("plan de adaptacion", "plan"), ("informes", "informe"),
    ("borrador", "informe"), ("seguimiento", "seguimiento"), ("historia", "historia"),
    ("fotos", "fotos"), ("charlas", "charlas"), ("estado de situacion", "situacion"),
    ("analisis", "ia"), ("racion", "racion"), ("movimientos", "movimientos"),
    ("uniformidad", "uniformidad"), ("clima", "clima"), ("cargar", "cargar"),
    ("datos", "datos"), ("lotes anteriores", "anteriores"), ("lotes", "lotes"),
]


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFD", t.lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn").strip()


def icono(clave: str) -> str:
    p = _P.get(clave)
    if not p:
        return ""
    return ('<span class="hm-lbl-i"><svg viewBox="0 0 24 24" width="18" height="18" fill="none" '
            'stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">'
            f'{p}</svg></span>')


_RE = re.compile(r'<div class="hm-lbl"([^>]*)>(.*?)</div>', re.S)


def _arreglar(m: "re.Match") -> str:
    attrs, txt = m.group(1), m.group(2)
    if "hm-lbl-t" in txt:          # ya procesado
        return m.group(0)
    plano = _norm(re.sub(r"<[^>]+>", "", txt))
    ico = ""
    for k, c in _CLAVES:
        if plano.startswith(k):
            ico = icono(c)
            break
    if " · " in txt:
        tit, det = txt.split(" · ", 1)
        txt = f'<span class="hm-lbl-t">{tit}</span><span class="hm-lbl-x">{det}</span>'
    else:
        txt = f'<span class="hm-lbl-t">{txt}</span>'
    return f'<div class="hm-lbl"{attrs}>{ico}{txt}</div>'


def con_iconos(body):
    if not isinstance(body, str) or "hm-lbl" not in body:
        return body
    return _RE.sub(_arreglar, body)


CSS = """
.hm-lbl{display:flex !important;align-items:center;gap:10px;margin:30px 0 12px !important;
  font-family:'Barlow Condensed',sans-serif;font-size:20px !important;font-weight:700;letter-spacing:.6px !important;
  color:var(--hm-txt) !important;line-height:1.1}
.hm-lbl::after{content:"";flex:1;height:1px;background:var(--hm-line);margin-left:4px;min-width:20px}
.hm-lbl-i{width:32px;height:32px;border-radius:9px;display:inline-flex;align-items:center;justify-content:center;
  flex-shrink:0;background:rgba(79,122,31,.13);color:#2F6B1F}
.hm-lbl-x{font-family:'Source Sans 3',system-ui,sans-serif;font-size:13px;font-weight:600;letter-spacing:.2px;
  color:var(--hm-sub);text-transform:none}
.hm-card .hm-lbl{margin:0 0 10px !important;font-size:17px !important}
.hm-card .hm-lbl::after{display:none}
@media (prefers-color-scheme: dark){.hm-lbl-i{background:rgba(139,197,63,.16);color:#A7D46A}}
@media (max-width:640px){.hm-lbl{font-size:18px !important;margin:24px 0 10px !important}
  .hm-lbl-i{width:28px;height:28px}.hm-lbl-x{font-size:12px}}
"""
