"""Entrevista inicial del lote: preguntas, estado de situación y puntos débiles.

Sigue el documento "Entrevista inicial de lote — HMS" (Claude Docs). Se hace
una vez, cuando entra el lote. Con las respuestas:

- se completan los datos del lote que ya usa la app (comedero, reparo,
  sombra, piso, reserva y reposición de agua, edad, altura, objetivos);
- se arma el estado de situación: los puntos débiles de ESE lote, cada uno
  con su número, su fuente y las preguntas del control semanal que lo
  vigilan. El control semanal pregunta eso y no todo.

Los criterios con número salen de fuentes leídas (INTA y universidades),
las mismas de la "Base técnica" del documento. Lo que no se sabe queda como
faltante: nunca se reemplaza por un supuesto.
"""
from __future__ import annotations

import json
from typing import Dict, List, Optional

NS = "No sabe"

# Fuentes (texto corto que se muestra al lado de cada punto)
F_COM = "Pordomingo 2003, INTA Anguil"
F_SILO = "INTA Balcarce, Comederos de autoconsumo"
F_FIBRA = "Pordomingo 2013, INTA Anguil"
F_AGUA_Q = "Sager 2000, INTA San Luis"
F_CAUDAL = "MLA, Feedlot design sección 14; UNL G2266 (2015); Pordomingo 2003"
F_FRAME = "BIF; Pourrain 2004, INTA Mercedes"

# ---------------------------------------------------------------------
# Preguntas: (clave, texto, tipo, opciones, para qué)
# tipo: "op" una opción, "multi" varias, "num" número, "txt" texto
# ---------------------------------------------------------------------
BLOQUES = [
    ("A", "Los animales", [
        ("A2", "Raza o biotipo", "op", ["Británico (Angus, Hereford)", "Cruza británica",
                                        "Con sangre índica (Braford, Brangus)", "Lechero", NS],
         "El índico tolera más calor"),
        ("A3", "Cantidad de animales", "num", None, "Consumo total, espacio por animal"),
        ("A4", "Peso al entrar (kg)", "num", None, "Punto de partida de ganancia y consumo"),
        ("A4b", "¿Cómo se sacó el peso?", "op", ["Balanza", "Estimado", NS], "Cuánto creerle"),
        ("A5", "Edad (meses)", "num", None, "Con la altura da el frame"),
        ("A6", "Altura a la grupa (cm, promedio de 5 a 10)", "num", None,
         "Con la edad da el frame y el peso de terminación"),
        ("A7", "Uniformidad", "op", ["Parejos", "Algunos chicos", "Muy disparejos"],
         "Desparejos = más competencia en el comedero"),
        ("A8", "Origen", "op", ["Propios", "Compra directa", "Remate o feria", "Varios orígenes"],
         "Remate o mezcla = más riesgo respiratorio al principio"),
        ("A9", "Horas de viaje hasta el corral", "num", None,
         "Viaje largo = más cuidado en la recepción"),
        ("A10", "De dónde vienen comiendo", "op", ["Pasto", "Verdeo", "Rastrojo",
                                                   "Ya comían grano", NS],
         "Cuánto dura la adaptación al grano"),
    ]),
    ("B", "Sanidad al ingreso", [
        ("B1", "Vacunas al entrar", "multi", ["Clostridiales", "Respiratorias", "Ninguna", NS],
         "Sin respiratoria + remate = vigilar tos y moco"),
        ("B2", "Desparasitado", "op", ["Sí", "No", NS], "Explica ganancias bajas sin causa en la dieta"),
        ("B3", "Llegaron animales enfermos o flacos (cuántos, 0 si ninguno)", "num", None,
         "Base para comparar controles y muertes"),
        ("B4", "Veterinario del lote (nombre y teléfono)", "txt", None, "A quién derivar"),
    ]),
    ("C", "Alimentación y comedero", [
        ("C1", "Cómo come", "op", ["Silo comedero (autoconsumo)", "Comedero lineal con mixer",
                                   "Comedero lineal a mano", "Otro"], "Cambia todas las recomendaciones"),
        ("C2", "Cada cuánto se carga", "op", ["Todos los días", "Cada 2 o 3 días", "Cada 4 o más"],
         "Qué tan rápido se corrige algo"),
        ("C3", "Comedero lineal: metros totales", "num", None, "Frente por animal (INTA: 30 cm)"),
        ("C3b", "Comedero lineal: comen de", "op", ["Un lado", "Los dos lados"],
         "De los dos lados el frente cuenta doble"),
        ("C4", "Silo comedero: cantidad de silos", "num", None, "Boca por animal (INTA: 10 cm)"),
        ("C4b", "Silo comedero: capacidad de cada silo (kg)", "num", None, "Cada cuánto recargar"),
        ("C4c", "Silo comedero: centímetros de boca por silo (sumando todas las bocas)", "num", None,
         "Boca por animal (INTA: 10 cm)"),
        ("C5", "Silo comedero: ¿se adapta antes en comedero lineal?", "op",
         ["Sí, en comedero lineal", "No, va directo al silo", NS], "INTA: 20 a 30 días"),
        ("C5b", "Días de adaptación en comedero lineal", "num", None, "INTA: 20 a 30 días"),
        ("C6", "Ingredientes que tiene", "multi", ["Maíz entero", "Maíz partido", "Silo de maíz o sorgo",
                                                   "Rollo", "Pellet", "Núcleo", "Otros"],
         "Armar la ración con lo que hay"),
        ("C7", "El maíz es", "op", ["Propio", "Comprado"], "Costo y si puede faltar"),
        ("C8", "Pesa lo que carga", "op", ["Balanza en el mixer", "Balde o bolsa contada", "A ojo"],
         "Cuánto creerle al consumo calculado"),
        ("C9", "Fibra larga", "op", ["Rollo o picado a disposición", "En la mezcla", "No tiene"],
         "Seguridad ruminal (INTA: 5 a 10 % de la dieta)"),
        ("C10", "Dónde guarda el alimento", "op", ["Galpón", "Silo bolsa", "A la intemperie"],
         "Riesgo de mojado y hongos"),
    ]),
    ("D", "Agua", [
        ("D1", "De dónde sale", "op", ["Molino", "Bomba eléctrica", "Bomba solar", "Red"],
         "Riesgo de quedarse sin agua"),
        ("D2", "Si se corta la luz o no hay viento", "op", ["Tanque de reserva", "Generador", "Nada"],
         "Cuántas horas aguanta"),
        ("D2b", "Litros del tanque de reserva", "num", None, "Horas de reserva"),
        ("D3", "Cantidad de bebederos", "num", None, "INTA: dos por corral"),
        ("D3b", "Largo total de bebedero (cm, sumando todos)", "num", None, "INTA: 3 cm por animal"),
        ("D3c", "Segundos que tarda en llenar un balde de 20 L con el bebedero bajo", "num", None,
         "Reposición: tiene que reponer el agua del día en 4 horas"),
        ("D4", "Tiene análisis de agua", "op", ["Sí", "No"], "Sales y sulfatos"),
        ("D5", "Sabor del agua", "op", ["Dulce", "Algo salada", "Muy salada", NS],
         "Si no hay análisis, se pide"),
    ]),
    ("E", "Corral e instalaciones", [
        ("E1", "Superficie del corral (m²; largo × ancho)", "num", None, "INTA: 15 a 20 m² por animal"),
        ("E2", "Piso", "op", ["Firme, drena bien", "Se embarra con lluvias fuertes",
                              "Se embarra con cualquier lluvia"], "Avisos de barro y frío"),
        ("E3", "Pendiente", "op", ["Sí, el agua escurre", "Plano", "Bajo, se junta agua"],
         "INTA: 2 a 4 %"),
        ("E4", "Sector alto y seco para echarse", "op", ["Sí", "No"], "Qué recomendar con lluvia"),
        ("E5", "Reparo del viento", "op", ["Monte o cortina", "Armado con rollos o chapa",
                                           "Parcial", "No tiene"], "Avisos de frío"),
        ("E6", "Lado del reparo", "op", ["Sur", "Oeste", "Otro"], "Contra el viento del pronóstico"),
        ("E7", "Sombra", "op", ["Natural", "Media sombra", "No tiene"], "Avisos de calor"),
        ("E8", "Hay agua para mojar el piso con calor", "op", ["Sí", "No"], "Calor crítico"),
    ]),
    ("F", "Manejo, personas y objetivos", [
        ("F1", "Quién da de comer y recorre", "txt", None, "A quién le llega el control"),
        ("F1b", "WhatsApp de esa persona", "txt", None, "A quién le llega el control"),
        ("F2", "Cada cuánto recorre el corral", "op", ["Todos los días", "Día por medio", "Menos"],
         "Qué tan pronto se ve un problema"),
        ("F3", "Puede pesar", "op", ["Balanza propia", "Prestada", "No puede"],
         "Ganancias medidas o estimadas"),
        ("F4", "Hizo encierres antes", "op", ["Varios", "Alguno", "Es el primero"],
         "Cuánto detalle llevan las recomendaciones"),
        ("F5", "Peso de venta buscado (kg)", "num", None, "Fecha de salida"),
        ("F6", "Fecha de venta buscada (o 'cuando lleguen')", "txt", None, "Si la ganancia alcanza"),
        ("F7", "Destino", "op", ["Consumo", "Exportación", NS], "Peso y terminación"),
        ("F8", "Mejor día y hora para el control", "txt", None, "Cuándo mandar el WhatsApp"),
        ("F9", "Qué le preocupa de este encierre", "txt", None, "Lo que quiere que miremos"),
    ]),
]

# Preguntas del control semanal (control_semanal.py) en criollo, para
# decir qué se vigila.
CONTROL_TXT = {"1": "animales apartados", "2": "muertes", "3": "tos, renguera o hinchados",
               "4": "comedero", "5": "bosta", "6": "agua", "7": "barro",
               "8": "cambios en la comida", "10": "alimento guardado", "12": "jadeo con calor"}
CONTROL_BASE = ["1", "2"]


# ---------------------------------------------------------------------
def cargar(lote: Dict) -> Dict:
    r = (lote or {}).get("entrevista") or {}
    if isinstance(r, str):
        try:
            r = json.loads(r)
        except Exception:
            r = {}
    return r if isinstance(r, dict) else {}


def _n(r: Dict, k: str) -> Optional[float]:
    try:
        v = float(r.get(k))
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None


def _num(x, dec=0) -> str:
    s = f"{x:,.{dec}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def caudal_l_min(r: Dict) -> Optional[float]:
    s = _n(r, "D3c")
    return 20 * 60 / s if s else None


def campos_lote(r: Dict) -> Dict:
    """Lo que la entrevista completa en el lote (columnas que ya usa la app)."""
    out: Dict = {}
    c1 = r.get("C1") or ""
    if c1:
        out["tipo_comedero_concentrado"] = ("silocomedero" if c1.startswith("Silo") else
                                            ("lineal" if c1.startswith("Comedero lineal") else "otro"))
    if _n(r, "C4") and _n(r, "C4b"):
        out["capacidad_silo_kg"] = _n(r, "C4") * _n(r, "C4b")
    for k, col in (("A5", "edad_meses"), ("A6", "altura_grupa_cm"), ("F5", "objetivo_peso_kg")):
        if _n(r, k):
            out[col] = _n(r, k)
    if _n(r, "D2b"):
        out["reserva_agua_l"] = _n(r, "D2b")
    if caudal_l_min(r):
        out["caudal_l_min"] = round(caudal_l_min(r), 1)
    e2 = r.get("E2") or ""
    if e2:
        out["piso_corral"] = {"Firme": "firme", "Se embarra con lluvias fuertes": "medio"}.get(
            e2.split(",")[0], "malo")
    e5 = r.get("E5") or ""
    if e5:
        out["reparo"] = "no" if e5 == "No tiene" else ("parcial" if e5 == "Parcial" else "si")
    e7 = r.get("E7") or ""
    if e7:
        out["sombra"] = "no" if e7 == "No tiene" else "si"
    n = _n(r, "A3")
    nb, cm = _n(r, "D3"), _n(r, "D3b")
    if n and (nb or cm):
        pocos = (nb is not None and nb < 2) or (cm is not None and cm / n < 3)
        out["bebederos"] = "pocos" if pocos else "ok"
    if (r.get("F1") or "").strip():
        out["encargado_nombre"] = r["F1"].strip()
    if (r.get("F1b") or "").strip():
        out["encargado_whatsapp"] = r["F1b"].strip()
    if (r.get("F6") or "").strip():
        out["objetivo_fecha"] = r["F6"].strip()
    if r.get("F2"):
        out["recorre"] = r["F2"]
    return out


def _p(area, nivel, texto, fuente=None, vigilar=()):
    return {"area": area, "nivel": nivel, "texto": texto, "fuente": fuente, "vigilar": list(vigilar)}


def puntos_debiles(r: Dict, lote: Optional[Dict] = None, peso_actual=None) -> List[Dict]:
    """Puntos débiles del lote, rojo primero. Cada uno con número, fuente y
    qué pregunta del control semanal lo vigila."""
    lote = lote or {}
    out: List[Dict] = []
    n = _n(r, "A3") or _n(lote, "cantidad_inicial")
    c1 = r.get("C1") or ""
    silo = c1.startswith("Silo")
    lineal = c1.startswith("Comedero lineal")

    # --- Comedero
    if lineal and n and _n(r, "C3"):
        lados = 2 if r.get("C3b") == "Los dos lados" else 1
        cm = _n(r, "C3") * 100 * lados / n
        if cm < 30:
            out.append(_p("consumo", "amarillo",
                          f"Frente de comedero corto: {_num(cm)} cm por animal; el INTA pide 30 cm "
                          "para que no limite. Los más chicos comen menos", F_COM, ["1", "4"]))
    if silo:
        if n and _n(r, "C4") and _n(r, "C4c"):
            cm = _n(r, "C4") * _n(r, "C4c") / n
            if cm < 10:
                out.append(_p("consumo", "amarillo",
                              f"Poca boca de silo: {_num(cm, 1)} cm por animal; el INTA pide 10 cm",
                              F_SILO, ["1", "4"]))
        if n and n > 120:
            out.append(_p("consumo", "amarillo",
                          f"{_num(n)} animales en autoconsumo: el INTA recomienda lotes de no más de 120",
                          F_SILO, ["1", "4"]))
        c5 = r.get("C5") or ""
        dias = _n(r, "C5b") if c5.startswith("Sí") else (0 if c5.startswith("No") else None)
        if dias is not None and dias < 20:
            previo = r.get("A10") or ""
            extra = f" y vienen de {previo.lower()}" if previo in ("Pasto", "Verdeo", "Rastrojo") else ""
            out.append(_p("consumo", "rojo",
                          (f"Adaptación de {_num(dias)} días en comedero lineal" if dias else
                           "Van directo al silo comedero sin adaptación") + extra +
                          ": el INTA recomienda 20 a 30 días antes del autoconsumo; los casos graves de "
                          "acidosis aparecen sobre todo en los primeros 15 días",
                          F_SILO, ["5", "1", "3"]))
    if r.get("C9") == "No tiene":
        out.append(_p("consumo", "amarillo",
                      "Sin fibra larga: en dietas de alto grano el INTA pide un mínimo de 5 a 10 % de la dieta",
                      F_FIBRA, ["5"]))
    if r.get("C8") == "A ojo":
        out.append(_p("alimento", "amarillo",
                      "Carga a ojo: el consumo calculado es aproximado; tomarlo con cuidado", None, ["4"]))
    if r.get("C10") == "A la intemperie":
        out.append(_p("alimento", "amarillo",
                      "Alimento a la intemperie: se puede mojar y enmohecer", None, ["8", "10"]))
    if r.get("C2") == "Cada 4 o más" and lineal:
        out.append(_p("alimento", "amarillo",
                      "Carga cada 4 días o más en comedero lineal: un problema tarda en corregirse",
                      None, ["4"]))

    # --- Agua
    d1, d2 = r.get("D1") or "", r.get("D2") or ""
    if d2 == "Nada" and d1 in ("Molino", "Bomba eléctrica", "Bomba solar"):
        causa = {"Molino": "sin viento", "Bomba eléctrica": "si se corta la luz",
                 "Bomba solar": "en días nublados"}[d1]
        out.append(_p("agua", "rojo" if d1 == "Molino" else "amarillo",
                      f"Sin respaldo de agua: {causa} el lote se queda sin agua y no hay tanque de reserva",
                      None, ["6"]))
    nb, cmb = _n(r, "D3"), _n(r, "D3b")
    if nb is not None and nb < 2:
        out.append(_p("agua", "amarillo", "Un solo bebedero: el INTA pide dos separados por corral",
                      F_COM, ["6", "12"]))
    if n and cmb and cmb / n < 3:
        out.append(_p("agua", "amarillo",
                      f"Bebedero corto: {_num(cmb / n, 1)} cm por animal; el INTA pide al menos 3 cm",
                      F_COM, ["6", "12"]))
    cau = caudal_l_min(r) or _n(lote, "caudal_l_min")
    if n:
        from . import clima_reco as cr
        req = cr.caudal_requerido(n, peso_actual or _n(r, "A4"), None, verano=True)
        if req and cau and cau < req["l_min"]:
            out.append(_p("agua", "rojo",
                          f"La reposición del bebedero ({_num(cau)} L/min) no alcanza para el verano: hacen "
                          f"falta {_num(req['l_min'])} L/min para reponer en 4 horas los "
                          f"{_num(req['l_dia_pico'])} L del día (70 L por animal)", F_CAUDAL, ["6", "12"]))
    d4, d5 = r.get("D4") or "", r.get("D5") or ""
    if d4 != "Sí" and d5 in ("Algo salada", "Muy salada"):
        out.append(_p("agua", "rojo" if d5 == "Muy salada" else "amarillo",
                      f"Agua {d5.lower()} sin análisis: con más de 4 g/L de sales puede bajar el consumo y "
                      "con más de 10 no es apta. Hacer el análisis", F_AGUA_Q, ["6"]))

    # --- Corral
    m2 = _n(r, "E1")
    if n and m2 and m2 / n < 15:
        out.append(_p("ambiente", "amarillo",
                      f"Corral chico: {_num(m2 / n, 1)} m² por animal; el INTA pide 15 a 20 m². "
                      "Más barro y más polvo", F_COM, ["7"]))
    e2, e3 = r.get("E2") or "", r.get("E3") or ""
    if e2 == "Se embarra con cualquier lluvia" or e3 == "Bajo, se junta agua":
        rojo = e2 == "Se embarra con cualquier lluvia" and e3 == "Bajo, se junta agua"
        sin_alto = " y no tiene sector alto para echarse" if r.get("E4") == "No" else ""
        out.append(_p("ambiente", "rojo" if rojo else "amarillo",
                      "Corral que se embarra" + (" y junta agua" if e3.startswith("Bajo") else "") + sin_alto +
                      ": el INTA pide 2 a 4 % de pendiente", F_COM, ["7"]))
    if r.get("E5") == "No tiene":
        out.append(_p("ambiente", "amarillo",
                      "Sin reparo del viento: los avisos de frío lo van a pedir primero", None, ["7", "1"]))
    if r.get("E7") == "No tiene":
        out.append(_p("ambiente", "amarillo",
                      "Sin sombra: con calor el aviso sube a crítico antes; el INTA recomienda 1,5 a 4 m² "
                      "de sombra por animal", F_COM, ["12", "6"]))

    # --- Sanidad
    b1 = r.get("B1") or []
    if isinstance(b1, str):
        b1 = [b1]
    if r.get("A8") in ("Remate o feria", "Varios orígenes") and "Respiratorias" not in b1:
        out.append(_p("sanidad", "amarillo",
                      f"{r['A8']} y sin vacuna respiratoria: vigilar tos y moco las primeras 3 semanas",
                      None, ["3", "1"]))
    if (_n(r, "B3") or 0) > 0:
        out.append(_p("sanidad", "amarillo",
                      f"Llegaron {_num(_n(r, 'B3'))} enfermos o flacos: base para comparar muertes",
                      None, ["1", "2"]))
    if r.get("B2") == "No":
        out.append(_p("sanidad", "amarillo",
                      "Sin desparasitar: si la ganancia sale baja sin causa en la dieta, mirar esto", None))
    if r.get("A7") == "Muy disparejos":
        out.append(_p("consumo", "amarillo",
                      "Muy disparejos: más competencia en el comedero y salidas escalonadas", None, ["1"]))

    # --- Manejo
    if not (r.get("B4") or "").strip():
        out.append(_p("manejo", "amarillo", "Sin veterinario cargado: no hay a quién derivar un rojo en sanidad"))
    if r.get("F3") == "No puede":
        out.append(_p("manejo", "amarillo", "No puede pesar: las ganancias van a ser estimadas"))
    if r.get("F2") == "Menos":
        out.append(_p("manejo", "amarillo", "Recorre menos de día por medio: un problema se ve tarde",
                      None, ["1", "2"]))
    if r.get("F4") == "Es el primero":
        out.append(_p("manejo", "amarillo",
                      "Primer encierre: las recomendaciones tienen que ir con más detalle"))

    # --- Frame contra peso de venta
    from . import frame
    alt, edad = _n(r, "A6"), _n(r, "A5")
    venta = _n(r, "F5")
    if alt and edad and venta:
        ev = frame.evaluar_frame(alt, edad, lote.get("categoria") or "")
        if ev and ev.get("peso_faena"):
            lo, hi = ev["peso_faena"]
            if venta > hi:
                out.append(_p("objetivo", "amarillo",
                              f"Busca vender a {_num(venta)} kg, pero con frame {_num(ev['frame'], 1)} el INTA "
                              f"estima la terminación entre {lo} y {hi} kg: más pesado puede salir engrasado",
                              F_FRAME))
            elif venta < lo:
                out.append(_p("objetivo", "amarillo",
                              f"Busca vender a {_num(venta)} kg, debajo de los {lo} a {hi} kg que el INTA "
                              f"estima para frame {_num(ev['frame'], 1)}: puede salir sin terminar",
                              F_FRAME))

    orden = {"rojo": 0, "amarillo": 1}
    out.sort(key=lambda p: orden.get(p["nivel"], 2))
    return out


FALTANTES = [("A4", "peso al entrar"), ("A5", "edad"), ("A6", "altura a la grupa"),
             ("C1", "tipo de comedero"), ("D3c", "reposición del bebedero"),
             ("E1", "superficie del corral"), ("F5", "peso de venta")]


def faltantes(r: Dict) -> List[str]:
    return [t for k, t in FALTANTES if r.get(k) in (None, "", 0, 0.0, NS)]


def preguntas_semanales(puntos: List[Dict]) -> List[str]:
    """Qué preguntas del control semanal van para este lote: las de base más
    las que vigilan sus puntos débiles (la 12, jadeo, solo semanas de calor)."""
    ks = list(CONTROL_BASE)
    for p in puntos:
        for k in p.get("vigilar") or []:
            if k not in ks:
                ks.append(k)
    return ks
