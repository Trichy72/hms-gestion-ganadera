"""Historia del lote: entrevista inicial, controles semanales, charlas,
pesadas, entregas, cambios de ración y movimientos en una sola línea de
tiempo. De acá sale la evolución de los puntos débiles y el informe de
cierre del ciclo.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from typing import Dict, List, Optional

from . import database as db


def _f(x) -> Optional[date]:
    if not x:
        return None
    if isinstance(x, datetime):
        return x.date()
    if isinstance(x, date):
        return x
    try:
        return date.fromisoformat(str(x)[:10])
    except ValueError:
        return None


def _sql(q: str, p: tuple = ()) -> List[Dict]:
    try:
        with db.get_conn() as conn:
            return [dict(r) for r in conn.execute(q, p).fetchall()]
    except Exception:
        return []


def _num(x, dec=0) -> str:
    try:
        s = f"{float(x):,.{dec}f}"
    except (TypeError, ValueError):
        return "—"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


# Áreas del control semanal y de qué áreas de la entrevista vienen
AREAS = [("sanidad", "Sanidad", {"sanidad"}),
         ("consumo", "Consumo", {"consumo"}),
         ("ambiente", "Ambiente", {"ambiente", "agua"}),
         ("alimento", "Alimento", {"alimento"})]


def eventos(lote_id: int, lote: Dict) -> List[Dict]:
    """Todo lo que pasó en el lote, del más nuevo al más viejo."""
    from . import entrevista as ent
    ev: List[Dict] = []

    def add(f, tipo, titulo, detalle=""):
        f = _f(f)
        if f:
            ev.append({"fecha": f, "tipo": tipo, "titulo": titulo, "detalle": detalle})

    add(lote.get("fecha_ingreso"), "encierre",
        f"Encierre: {_num(lote.get('cantidad_inicial'))} animales"
        + (f" de {_num(lote.get('peso_ingreso_kg'))} kg" if lote.get("peso_ingreso_kg") else ""))

    r = ent.cargar(lote)
    if r:
        pts = ent.puntos_debiles(r, lote)
        nr = sum(p["nivel"] == "rojo" for p in pts)
        add(lote.get("entrevista_fecha"), "entrevista",
            f"Entrevista inicial: {nr} en rojo y {len(pts) - nr} para mirar",
            "; ".join(p["texto"] for p in pts[:4]) + ("…" if len(pts) > 4 else ""))

    for c in _sql("SELECT * FROM controles_semanales WHERE lote_id = ?", (lote_id,)):
        if c.get("es_prueba"):
            continue
        cols = {a: (c.get(f"semaforo_{a}") or "gris") for a, _, _ in AREAS}
        malos = [n for a, n, _ in AREAS if cols[a] in ("rojo", "amarillo")]
        add(c.get("fecha_respuesta") or c.get("fecha_envio"), "control",
            f"Control semanal: {c.get('semaforo_general') or 'sin color'}"
            + (f" ({', '.join(malos).lower()})" if malos else ""),
            c.get("comentarios") or "")

    for c in _sql("SELECT * FROM charlas WHERE lote_id = ?", (lote_id,)):
        add(c.get("fecha"), "charla", f"Charla ({(c.get('medio') or '').lower()})",
            (c.get("resumen") or "") + (f" Se acordó: {c['acuerdos']}" if c.get("acuerdos") else ""))

    pes = db.listar_pesadas(lote_id) or []
    prev = None
    for p in pes:
        txt = f"Pesada: {_num(p.get('peso_promedio_kg'), 1)} kg promedio"
        if prev and _f(p.get("fecha")) and _f(prev.get("fecha")):
            dias = (_f(p["fecha"]) - _f(prev["fecha"])).days
            if dias > 0:
                g = (float(p["peso_promedio_kg"]) - float(prev["peso_promedio_kg"])) / dias
                txt += f", ganó {_num(g, 2)} kg/día en {dias} días"
        add(p.get("fecha"), "pesada", txt, p.get("notas") or "")
        prev = p

    for e in _sql("SELECT fecha_entrega, producto_nombre, kg_total FROM entregas_producto WHERE lote_id = ?",
                  (lote_id,)):
        add(e.get("fecha_entrega"), "entrega", f"Entrega: {_num(e.get('kg_total'))} kg de {e.get('producto_nombre') or 'alimento'}")

    for x in _sql("SELECT fecha, observaciones FROM dietas WHERE lote_id = ?", (lote_id,)):
        add(x.get("fecha"), "racion", "Cambio de ración", x.get("observaciones") or "")

    lab = getattr(db, "MOVIMIENTO_LABELS", {})
    for m in _sql("SELECT fecha, tipo, cantidad, detalles FROM movimientos WHERE lote_id = ? AND tipo <> 'conteo_drone'",
                  (lote_id,)):
        add(m.get("fecha"), "movimiento", f"{lab.get(m.get('tipo'), m.get('tipo'))}: {_num(abs(m.get('cantidad') or 0))}",
            m.get("detalles") or "")

    # Fotos, agrupadas por día
    from . import control_semanal as cs
    por_dia: Dict = {}
    for ft in cs.listar_fotos(lote_id, con_datos=False):
        por_dia.setdefault(ft["fecha"], []).append(ft)
    origen_txt = {"control": "del control", "entrevista": "de la entrevista", "charla": "de la charla",
                  "suelta": "sueltas"}
    for fch, fs in por_dia.items():
        temas = sorted({cs.TEMAS_TODOS.get(x.get("tema"), x.get("tema") or "") for x in fs})
        orig = sorted({origen_txt.get(x["origen"], "") for x in fs} - {""})
        add(fch, "foto", f"{len(fs)} foto{'s' if len(fs) != 1 else ''} {' y '.join(orig)}".strip(),
            ", ".join(t.lower() for t in temas))

    ev.sort(key=lambda e: e["fecha"], reverse=True)
    return ev


def fotos_para_comparar(lote_id: int) -> Dict[str, List[Dict]]:
    """Por tema, la primera y la última foto (con datos), para ver el cambio."""
    from . import control_semanal as cs
    por_tema: Dict[str, List[Dict]] = {}
    for ft in cs.listar_fotos(lote_id):
        por_tema.setdefault(ft.get("tema") or "otra", []).append(ft)
    return por_tema


def evolucion(lote_id: int, lote: Dict) -> List[Dict]:
    """Columnas de la grilla de evolución: la entrevista como punto de partida
    y cada control semanal, con el color de cada área."""
    from . import entrevista as ent
    cols: List[Dict] = []
    r = ent.cargar(lote)
    if r:
        pts = ent.puntos_debiles(r, lote)
        claves = {"sanidad": ("A8", "B"), "consumo": ("C1", "C3", "C4", "C5", "C9", "A7", "A10"),
                  "ambiente": ("D", "E"), "alimento": ("C2", "C8", "C10")}
        base = {}
        for a, _, desde in AREAS:
            niv = [p["nivel"] for p in pts if p["area"] in desde]
            contestado = any(any(k.startswith(c) for c in claves[a]) for k in r)
            base[a] = ("rojo" if "rojo" in niv else ("amarillo" if niv else
                       ("verde" if contestado else "gris")))
        cols.append({"fecha": _f(lote.get("entrevista_fecha")), "etiqueta": "Inicio", **base})
    ctr = _sql("SELECT * FROM controles_semanales WHERE lote_id = ?", (lote_id,))
    ctr.sort(key=lambda c: str(c.get("fecha_respuesta") or c.get("fecha_envio") or ""))
    for c in ctr:
        if c.get("es_prueba"):
            continue
        f = _f(c.get("fecha_respuesta") or c.get("fecha_envio"))
        cols.append({"fecha": f, "etiqueta": f"{f.day}/{f.month}" if f else "",
                     **{a: (c.get(f"semaforo_{a}") or "gris") for a, _, _ in AREAS}})
    return cols


def resumen_ciclo(lote_id: int, lote: Dict, d: Dict) -> Dict:
    """Los números y la historia del ciclo, para el informe de cierre."""
    from . import entrevista as ent
    pes = db.listar_pesadas(lote_id) or []
    p0, p1 = (pes[0], pes[-1]) if pes else (None, None)
    f0 = _f(lote.get("fecha_ingreso")) or (_f(p0["fecha"]) if p0 else None)
    f1 = _f(lote.get("fecha_salida")) or date.today()
    dias = (f1 - f0).days if f0 else None
    peso_ini = (p0 or {}).get("peso_promedio_kg") or lote.get("peso_ingreso_kg")
    peso_fin = (p1 or {}).get("peso_promedio_kg") if p1 and p1 is not p0 else None
    adpv = None
    if p0 and p1 and p1 is not p0:
        dd = (_f(p1["fecha"]) - _f(p0["fecha"])).days
        if dd > 0:
            adpv = (float(p1["peso_promedio_kg"]) - float(p0["peso_promedio_kg"])) / dd
    ent_kg = sum(float(e.get("kg_total") or 0) for e in
                 _sql("SELECT kg_total FROM entregas_producto WHERE lote_id = ?", (lote_id,)))
    r = ent.cargar(lote)
    return {
        "cliente": lote.get("cliente_nombre"), "lote": lote.get("identificador"),
        "categoria": lote.get("categoria"), "animales_inicio": lote.get("cantidad_inicial"),
        "animales_hoy": d.get("animales"), "fecha_encierre": str(f0) if f0 else None,
        "fecha_fin_o_hoy": str(f1), "dias": dias,
        "peso_inicial_kg": peso_ini, "peso_ultima_pesada_kg": peso_fin,
        "kg_ganados_por_animal": (peso_fin - peso_ini) if peso_fin and peso_ini else None,
        "ganancia_diaria_entre_primera_y_ultima_pesada": adpv,
        "ganancia_esperada": d.get("adpv_esp"),
        "peso_de_venta_buscado": d.get("peso_venta"),
        "alimento_hms_entregado_kg": ent_kg,
        "consumo_real_vs_racion_pct": d.get("consumo_pct"),
        "muertes": d.get("muertes"), "muertes_pct": d.get("muertes_pct"),
        "puntos_debiles_entrevista_inicial": [
            {"nivel": p["nivel"], "texto": p["texto"], "fuente": p.get("fuente")}
            for p in (ent.puntos_debiles(r, lote) if r else [])],
        "evolucion_semaforo": [{k: (str(v) if k == "fecha" else v) for k, v in c.items()}
                               for c in evolucion(lote_id, lote)],
        "historia": [{"fecha": str(e["fecha"]), "que": e["titulo"], "detalle": e["detalle"]}
                     for e in sorted(eventos(lote_id, lote), key=lambda e: e["fecha"])],
    }


SISTEMA_INFORME = (
    "Sos el asistente de Mauri (HMS Nutrición Animal, asesor en nutrición de bovinos en encierre a corral, "
    "La Pampa). Con los datos del ciclo de UN lote, escribí el borrador del informe de cierre para el "
    "productor, en castellano rioplatense, claro, respetuoso y concreto. Estructura: "
    "1) Resumen en 3 líneas con los números principales (días, kilos ganados por animal, ganancia diaria, "
    "alimento entregado, muertes). "
    "2) Cómo arrancó el lote: los puntos débiles de la entrevista inicial. "
    "3) Cómo evolucionó: qué se vio en los controles semanales y las charlas, qué se ajustó y qué resultado tuvo. "
    "4) Resultado contra lo esperado. "
    "5) Recomendaciones para el próximo encierre, solo las que se apoyan en lo que pasó en este lote. "
    "Reglas: usá solo los números que vienen en los datos; si falta un dato, decí que falta, no lo estimes ni "
    "lo inventes. No nombres marcas comerciales de alimento. Si un criterio técnico trae fuente, citala entre "
    "paréntesis. Sin títulos en inglés ni jerga de programación. "
    "Si vienen fotos, cada una trae su tema y fecha: describí solo lo que se ve con claridad (barro, estado del "
    "comedero y del bebedero, aspecto de la bosta, estado de los animales) y compará la primera con la última "
    "del mismo tema; si una foto no permite sacar una conclusión, decilo."
)
