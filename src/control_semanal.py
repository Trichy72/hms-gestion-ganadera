"""Control semanal del corral: preguntas, semáforo y guardado.

Sigue el documento "Control semanal por WhatsApp — HMS" (13/10/2026):
nueve preguntas por corral, tres del campo, cuatro áreas con semáforo
(el corral toma el peor color) y combinaciones que suben a rojo.

Por ahora las respuestas y las fotos se cargan desde la ficha del lote
(Mauri pasa lo que el productor le mandó por WhatsApp). Cuando se
conecte WhatsApp, el mismo circuito escribe en las mismas tablas:
`controles_semanales` (respuestas y colores) y `fotos_lote` (fotos,
con `control_id` y `tema`).
"""
from __future__ import annotations

import io
import json
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from . import database as db

# ---------------------------------------------------------------------
# Preguntas
# ---------------------------------------------------------------------
# Cada pregunta: (clave, texto, opciones {letra: texto}, multiple)
def preguntas(tipo_comedero: str) -> List[Tuple[str, str, Dict[str, str], bool]]:
    silo = (tipo_comedero or "").lower().startswith("silo") or tipo_comedero == "autoconsumo"
    p1 = ("Recorriendo el corral, ¿cuántos animales ves apartados, decaídos o huecos?"
          if silo else
          "Cuando cargás la comida, ¿cuántos animales no se arriman al comedero?")
    p4 = (("En la semana, ¿cómo estuvo el silo comedero?",
           {"A": "Salió parejo, siempre hubo alimento abajo",
            "B": "Hubo, pero se apelmazó o se trancó",
            "C": "Quedó vacío algunas horas",
            "D": "Quedó vacío un día o más"})
          if silo else
          ("La mayoría de los días, antes de cargar, el comedero estaba…",
           {"A": "Limpio, se comió todo", "B": "Quedaba un poco",
            "C": "Quedaba bastante", "D": "Estuvo vacío varias horas antes de cargar"}))
    p8 = {"A": "No", "B": "La cantidad", "C": "Algún ingrediente"}
    if not silo:
        p8["D"] = "Hubo días sin cargar"
    return [
        ("1", p1, {"A": "Ninguno", "B": "1 o 2", "C": "3 a 5", "D": "Más de 5"}, False),
        ("2", "¿Hubo muertes esta semana?", {"A": "No", "B": "Una", "C": "Dos", "D": "Tres o más"}, False),
        ("3", "¿Viste animales con alguno de estos problemas?",
         {"A": "Ninguno", "B": "Rengos", "C": "Tos o moco", "D": "Hinchados"}, True),
        ("4", p4[0], p4[1], False),
        ("5", "Hoy, de 10 bostas frescas, ¿cuántas están blandas o líquidas?",
         {"A": "Ninguna", "B": "1 a 3", "C": "4 a 6", "D": "7 o más"}, False),
        ("6", "¿Cómo está el agua hoy y cómo estuvo en la semana? (la peor)",
         {"A": "Limpia y siempre hubo", "B": "Hubo, pero sucia o con verdín",
          "C": "Faltó algún rato", "D": "Faltó medio día o más"}, False),
        ("7", "¿Cómo está el piso del corral hoy?",
         {"A": "Seco", "B": "Barro que no tapa la pezuña", "C": "Barro que tapa la pezuña",
          "D": "Barro arriba de la pezuña o echados en el barro"}, False),
        ("8", "¿Cambió algo de la comida esta semana?", p8, False),
        ("9", "¿Entraron o salieron animales (sin contar muertes)?",
         {"A": "No", "B": "Vendí o saqué", "C": "Entraron nuevos", "D": "Pasé a otro corral"}, False),
        ("10", "¿Cuánto alimento le queda guardado?",
         {"A": "Lleno", "B": "Más de la mitad", "C": "Menos de la mitad", "D": "Casi nada"}, False),
        ("12", "Solo semanas de calor: en las horas de más calor, ¿cómo están?",
         {"A": "Normales", "B": "Algunos respirando agitado",
          "C": "Muchos jadeando con la boca abierta",
          "D": "Amontonados en sombra o bebedero, sin comer"}, False),
    ]


TEMAS_FOTO = {
    "bosta": "Bosta fresca (4 o 5)",
    "comedero": "Comedero",
    "bebedero": "Bebedero",
    "lote": "Lote (1 o 2)",
}

AREAS = [("sanidad", "Sanidad"), ("consumo", "Consumo"),
         ("ambiente", "Ambiente"), ("alimento", "Alimento")]
_ORDEN = {"verde": 0, "amarillo": 1, "rojo": 2}


def _peor(*colores: str) -> str:
    cs = [c for c in colores if c]
    return max(cs, key=lambda c: _ORDEN[c]) if cs else "gris"


# ---------------------------------------------------------------------
# Semáforo (criterio del asesor, se ajusta en el mes de prueba)
# ---------------------------------------------------------------------
def semaforo(resp: Dict, tipo_comedero: str) -> Dict[str, str]:
    silo = (tipo_comedero or "").lower().startswith("silo")
    g = lambda k: (resp.get(k) or "").upper()
    p3 = set(resp.get("3") or [])

    # Sanidad: 1, 2, 3
    san = "verde"
    if g("1") in ("C", "D") or g("2") in ("C", "D") or "D" in p3:
        san = "rojo"
    elif g("1") == "B" or g("2") == "B" or p3 & {"B", "C"}:
        san = "amarillo"

    # Consumo y digestión: 4, 5
    p4, p5 = g("4"), g("5")
    con = "verde"
    if p5 in ("C", "D") or (silo and p4 == "D"):
        con = "rojo"
    elif p5 == "B" or (silo and p4 in ("B", "C")) or (not silo and p4 in ("C", "D")):
        con = "amarillo"

    # Ambiente: 6, 7, 12
    p6, p7, p12 = g("6"), g("7"), g("12")
    amb = "verde"
    if p6 in ("C", "D") or p7 == "D" or p12 == "D":
        amb = "rojo"
    elif p6 == "B" or p7 == "C" or p12 == "C":
        amb = "amarillo"

    # Alimento y manejo: 8, 10
    p8, p10 = g("8"), g("10")
    ali = "verde"
    if p8 == "D" or p10 == "D":
        ali = "rojo"
    elif (p8 == "B" and not resp.get("8_comen_mas")) or p8 == "C" or p10 == "C":
        ali = "amarillo"

    # Combinaciones que suben a rojo
    sobrante = (not silo and p4 in ("B", "C")) or (silo and p4 == "B")
    blandas = p5 in ("B", "C", "D")
    if sobrante and blandas:
        con = "rojo"
    if (p8 == "D" or (silo and p4 in ("C", "D"))) and blandas:
        con = "rojo"
    if p8 == "C" and g("1") in ("B", "C", "D"):
        san = _peor(san, "rojo")

    res = {"sanidad": san, "consumo": con, "ambiente": amb, "alimento": ali}
    res["general"] = _peor(*res.values())
    return res


# ---------------------------------------------------------------------
# Guardado
# ---------------------------------------------------------------------
def _achicar(datos: bytes) -> Tuple[bytes, str]:
    """Foto a 1280 px de lado mayor, JPEG calidad 75 (~150 KB)."""
    try:
        from PIL import Image, ImageOps
        im = Image.open(io.BytesIO(datos))
        im = ImageOps.exif_transpose(im).convert("RGB")
        im.thumbnail((1280, 1280))
        out = io.BytesIO()
        im.save(out, "JPEG", quality=75, optimize=True)
        return out.getvalue(), "image/jpeg"
    except Exception:
        return datos, "application/octet-stream"


def guardar_control(lote_id: int, fecha: str, resp: Dict, tipo_comedero: str,
                    comentarios: str = "", canal: str = "app",
                    fotos: Optional[List[Tuple[str, bytes]]] = None,
                    es_prueba: bool = False) -> int:
    sem = semaforo(resp, tipo_comedero)
    ahora = datetime.now().isoformat(timespec="seconds")
    with db.get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO controles_semanales (lote_id, fecha_envio, fecha_respuesta, version, "
            "tipo_comedero, canal, respondio, respuestas, comentarios, semaforo_sanidad, "
            "semaforo_consumo, semaforo_ambiente, semaforo_alimento, semaforo_general, "
            "estado, es_prueba) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (lote_id, fecha, fecha + "T12:00:00", "2026-10-13", tipo_comedero, canal,
             "productor", json.dumps(resp, ensure_ascii=False), comentarios,
             sem["sanidad"], sem["consumo"], sem["ambiente"], sem["alimento"],
             sem["general"], "respondido", es_prueba),
        )
        cid = cur.lastrowid
        if cid is None:
            r = conn.execute("SELECT max(id) AS id FROM controles_semanales WHERE lote_id = ?",
                             (lote_id,)).fetchone()
            cid = dict(r)["id"]
        for tema, datos in fotos or []:
            chico, mime = _achicar(datos)
            conn.execute(
                "INSERT INTO fotos_lote (lote_id, tipo, archivo_path, fecha, control_id, "
                "tema, datos, mime) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (lote_id, tema, "", ahora, cid, tema, chico, mime),
            )
    try:
        db.invalidar_cache_lecturas()
    except Exception:
        pass
    return cid


def listar_controles(lote_id: int) -> List[Dict]:
    try:
        with db.get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM controles_semanales WHERE lote_id = ? "
                "ORDER BY COALESCE(fecha_respuesta, fecha_envio) DESC, id DESC", (lote_id,),
            ).fetchall()
            out = []
            for r in rows:
                d = dict(r)
                if isinstance(d.get("respuestas"), str):
                    try:
                        d["respuestas"] = json.loads(d["respuestas"])
                    except Exception:
                        d["respuestas"] = {}
                out.append(d)
            return out
    except Exception:
        return []


def fotos_control(control_id: int) -> List[Dict]:
    try:
        with db.get_conn() as conn:
            rows = conn.execute(
                "SELECT id, tema, mime, datos FROM fotos_lote WHERE control_id = ? ORDER BY id",
                (control_id,),
            ).fetchall()
            out = []
            for r in rows:
                d = dict(r)
                if d.get("datos") is not None:
                    d["datos"] = bytes(d["datos"])
                    out.append(d)
            return out
    except Exception:
        return []
