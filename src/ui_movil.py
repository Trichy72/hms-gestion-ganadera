"""Pantallas nuevas pensadas para el celular: Inicio y Ficha del lote.

Diseño aprobado por Mauricio el 14/10/2026 (lienzo "Gestión ganadera —
nuevo diseño"). Todo se dibuja con HTML/CSS propio dentro de Streamlit
y los datos salen de la misma base que el resto de la app.

Reglas:
- Solo lotes activos de clientes activos. Un cliente sin lote no ocupa
  lugar en Inicio.
- Lo medido y lo estimado se distinguen siempre en pantalla.
- Si una sección falla (tabla que no existe, dato raro), se muestra un
  aviso chico y el resto de la pantalla sigue.
"""
from __future__ import annotations

import html
import json
import logging
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

import streamlit as st

from . import database as db

log = logging.getLogger(__name__)

VERDE = "#1B3E27"
LIMA = "#8BC53F"
ESTADO_COLOR = {
    "verde": ("#2E7D32", "#E3F1E4"),
    "amarillo": ("#B07A00", "#FBF0D3"),
    "rojo": ("#B3261E", "#F9E1DE"),
    "gris": ("#6B7A6E", "#E6EAE3"),
}
DIAS_SEM = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


# ---------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------
def _e(x) -> str:
    return html.escape(str(x if x is not None else ""))


def _num(x, dec: int = 1) -> str:
    """Número con coma decimal argentina."""
    try:
        s = f"{float(x):,.{dec}f}"
    except (TypeError, ValueError):
        return "—"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def _fecha(s) -> Optional[date]:
    if not s:
        return None
    try:
        return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _dm(d: Optional[date]) -> str:
    return d.strftime("%d/%m") if d else "—"


def _saludo() -> str:
    try:
        from zoneinfo import ZoneInfo
        h = datetime.now(ZoneInfo("America/Argentina/Buenos_Aires")).hour
    except Exception:
        h = datetime.now().hour
    if 6 <= h < 13:
        return "Buen día"
    if 13 <= h < 20:
        return "Buenas tardes"
    return "Buenas noches"


def _subir_arriba(clave: str) -> None:
    """Lleva la pantalla arriba de todo al abrir una ficha (si no, queda
    a la altura de la tarjeta que se tocó y uno no sabe dónde está)."""
    js = ("(function(){var d=(window.parent&&window.parent.document)||document;"
          "['[data-testid=\"stMain\"]','[data-testid=\"stAppViewContainer\"]','section.main']"
          ".forEach(function(q){var e=d.querySelector(q);if(e){e.scrollTo(0,0);}});"
          "try{window.scrollTo(0,0);}catch(e){}})();")
    try:
        st.html(f"<script>/*{clave}*/{js}</script>", unsafe_allow_javascript=True)
    except TypeError:
        try:
            import streamlit.components.v1 as components
            components.html(f"<script>/*{clave}*/{js}</script>", height=0)
        except Exception:
            pass
    except Exception:
        pass


def _dia_corto(d: date) -> str:
    return f"{DIAS_SEM[d.weekday()]} {d.day}"


def _sql(query: str, params: tuple = ()) -> List[Dict]:
    """Consulta directa para las tablas nuevas (plan, controles,
    informes). Si la tabla no existe devuelve []."""
    try:
        return db.leer_cache(query, tuple(params))
    except Exception as e:  # tabla inexistente en SQLite local, etc.
        log.info("ui_movil: consulta sin resultado (%s)", e)
        return []


# ---------------------------------------------------------------------
# Datos de un lote
# ---------------------------------------------------------------------
def datos_lote(lote: Dict, hoy: Optional[date] = None) -> Dict:
    """Junta en un solo dict lo que muestran Inicio y la ficha."""
    from . import stock_producto as sp

    hoy = hoy or date.today()
    lid = lote["id"]
    d: Dict = {"lote": lote, "id": lid}
    d["cliente"] = lote.get("cliente_nombre") or ""
    try:
        cli = db.obtener_cliente(lote.get("cliente_id")) or {}
    except Exception:
        cli = {}
    d["localidad"] = cli.get("localidad") or ""
    try:
        d["animales"] = int(db.cantidad_vigente_lote(lid) or 0)
    except Exception:
        d["animales"] = int(lote.get("cantidad_inicial") or 0)

    ingreso = _fecha(lote.get("fecha_ingreso"))
    d["ingreso"] = ingreso
    d["dia"] = (hoy - ingreso).days + 1 if ingreso else None

    # Pesadas
    try:
        pes = db.listar_pesadas(lid) or []
    except Exception:
        pes = []
    pes = [p for p in pes if p.get("peso_promedio_kg")]
    d["pesadas"] = pes
    d["peso"] = pes[-1]["peso_promedio_kg"] if pes else None
    d["fecha_peso"] = _fecha(pes[-1]["fecha"]) if pes else None
    d["adpv"] = None
    if len(pes) >= 2:
        f0, f1 = _fecha(pes[-2]["fecha"]), _fecha(pes[-1]["fecha"])
        if f0 and f1 and (f1 - f0).days > 0:
            d["adpv"] = (
                (pes[-1]["peso_promedio_kg"] - pes[-2]["peso_promedio_kg"])
                / (f1 - f0).days
            )
            d["dias_entre"] = (f1 - f0).days
            d["ganancia"] = (
                pes[-1]["peso_promedio_kg"] - pes[-2]["peso_promedio_kg"]
            )
    d["proxima_pesada"] = (
        d["fecha_peso"] + timedelta(days=30) if d["fecha_peso"] else None
    )

    # Stock de lo que vende HMS
    d["stock"] = []
    try:
        prods = sp.listar_productos_hms_lote(lote.get("cliente_id"), lid)
    except Exception:
        prods = []
    for prod in prods:
        try:
            s = sp.calcular_stock_actual(lote.get("cliente_id"), lid, prod)
        except Exception as e:
            log.info("ui_movil: stock %s lote %s: %s", prod, lid, e)
            s = None
        if s:
            d["stock"].append({"producto": prod, **s})
    d["stock_min"] = (
        min(d["stock"], key=lambda x: x.get("dias_restantes") or 9999)
        if d["stock"] else None
    )

    # Último control semanal
    ctrl = _sql(
        "SELECT * FROM controles_semanales WHERE lote_id = ? "
        "ORDER BY COALESCE(fecha_respuesta, fecha_envio) DESC LIMIT 1",
        (lid,),
    )
    d["control"] = ctrl[0] if ctrl else None
    try:
        _seguimiento(d, hoy)
    except Exception as e:
        log.info("ui_movil: seguimiento lote %s: %s", lid, e)
    return d


_AREAS_TXT = (("sanidad", "sanidad"), ("consumo", "consumo"),
              ("ambiente", "ambiente"), ("alimento", "alimento"))


def _txt_caudal(lote: Dict, d: Dict, ag: Optional[Dict]) -> str:
    """Compara la reposición del bebedero con lo que hace falta en verano."""
    from . import clima_reco as cr
    req = cr.caudal_requerido(d.get("animales"), d.get("peso_hoy") or d.get("peso"),
                              (ag or {}).get("l_dia"), verano=True)
    if not req:
        return ""
    cau = lote.get("caudal_l_min")
    base = f' Con calor, el bebedero tiene que reponer <b>{_num(req["l_min"], 0)} L/min</b> (el agua del día en 4 horas)'
    if not cau:
        return base + '; falta medir la reposición (cargala en Corral).'
    ok = float(cau) >= req["l_min"]
    return base + (f'; hoy repone {_num(cau, 0)} L/min: ' + ('alcanza.' if ok else '<b>no alcanza</b>.'))


def _ms_animal(d: Dict) -> Optional[float]:
    """Materia seca consumida por animal según la ración cargada; None si
    la ración no tiene materia seca (no se supone)."""
    for x in d.get("stock") or []:
        v = (x.get("consumo_info") or {}).get("dmi_kg_animal")
        if v:
            return float(v)
    return None


def _seguimiento(d: Dict, hoy: date) -> None:
    """Datos para la tabla de seguimiento: ración, engorde contra lo
    esperado, consumo real, salida estimada, último contacto, muertes."""
    lote = d["lote"]
    lid = d["id"]

    # Semáforo con el área que lo puso en ese color (control de 7 días)
    ctrl = d.get("control") or {}
    f_c = _fecha(ctrl.get("fecha_respuesta") or ctrl.get("fecha_envio"))
    col = (ctrl.get("semaforo_general") or "").lower()
    if f_c and (hoy - f_c).days <= 7 and col in ("verde", "amarillo", "rojo"):
        areas = [n for k, n in _AREAS_TXT if (ctrl.get(f"semaforo_{k}") or "").lower() == col]
        d["sem"] = col
        d["sem_txt"] = ", ".join(areas) if col != "verde" else "bien"
    else:
        d["sem"] = "sin"
        d["sem_txt"] = "sin control" if not f_c else f"último {_dm(f_c)}"

    # Pedido: dos días antes de que se termine
    sm = d.get("stock_min") or {}
    fa = _fecha(sm.get("fecha_agotamiento"))
    d["pedir"] = (fa - timedelta(days=2)) if fa else None

    # Ración: en qué escalón del plan está y cuándo cambia
    dietas = _sql("SELECT fecha FROM dietas WHERE lote_id = ? ORDER BY fecha", (lid,))
    fechas = [x for x in (_fecha(r.get("fecha")) for r in dietas) if x]
    vig = [f for f in fechas if f <= hoy]
    prox = [f for f in fechas if f > hoy]
    if not fechas:
        d["racion_txt"] = "sin ración cargada"
    elif prox:
        d["racion_txt"] = f"escalón {len(vig)} de {len(fechas)}, cambia el {_dm(prox[0])}"
        d["racion_cambio"] = prox[0]
    elif len(fechas) > 1:
        d["racion_txt"] = f"ración final desde el {_dm(vig[-1])}"
    else:
        d["racion_txt"] = f"ración del {_dm(vig[-1])}"

    # Ganancia esperada: la del lote, o la de la categoría
    esp = lote.get("adpv_objetivo_kg")
    if not esp:
        r = _sql("SELECT adpv_default_kg_dia FROM categorias_animales WHERE nombre = ?",
                 ((lote.get("categoria") or "").lower(),))
        esp = (r[0].get("adpv_default_kg_dia") if r else None) or None
    d["adpv_esp"] = float(esp) if esp else None
    if d.get("adpv") is not None and d["adpv_esp"]:
        d["engorde_pct"] = d["adpv"] / d["adpv_esp"] * 100

    # Peso hoy (última pesada + ganancia) y fecha estimada de salida
    gan = d.get("adpv") if d.get("adpv") is not None else d.get("adpv_esp")
    if d.get("peso") and d.get("fecha_peso") and gan:
        d["peso_hoy"] = float(d["peso"]) + gan * (hoy - d["fecha_peso"]).days
    obj = lote.get("objetivo_peso_kg")
    d["peso_venta"] = float(obj) if obj else None
    if obj and d.get("peso_hoy") and gan and gan > 0:
        faltan = (float(obj) - d["peso_hoy"]) / gan
        d["salida"] = hoy + timedelta(days=max(0, int(round(faltan))))

    # Consumo real contra el teórico, por entregas: lo entregado antes de
    # la última entrega contra lo que tendrían que haber comido hasta esa
    # fecha (se pide cuando se está terminando). Solo con 2+ entregas y
    # al menos 14 días entre la primera y la última.
    try:
        from . import stock_producto as sp
        ents = sorted(sm.get("entregas") or [], key=lambda e: str(e.get("fecha_entrega")))
        if len(ents) >= 2:
            f1, fu = _fecha(ents[0].get("fecha_entrega")), _fecha(ents[-1].get("fecha_entrega"))
            if f1 and fu and (fu - f1).days >= 14:
                kg_antes = sum(float(e.get("kg_total") or 0) for e in ents[:-1])
                teo = sp._consumo_acumulado_kg(
                    lid, sm["producto"], f1.isoformat(), (fu - timedelta(days=1)).isoformat())
                if teo and teo > 0:
                    ratio = kg_antes / teo * 100
                    if 30 <= ratio <= 300:
                        d["consumo_pct"] = ratio
    except Exception as e:
        log.info("ui_movil: consumo real lote %s: %s", lid, e)

    # Último contacto: control, pesada o entrega más reciente
    cands = [f_c, d.get("fecha_peso")]
    ent = _sql("SELECT max(fecha_entrega) AS f FROM entregas_producto WHERE lote_id = ?", (lid,))
    cands.append(_fecha(ent[0].get("f")) if ent else None)
    ch = _sql("SELECT max(fecha) AS f FROM charlas WHERE lote_id = ?", (lid,))
    cands.append(_fecha(ch[0].get("f")) if ch else None)
    cands = [c for c in cands if c]
    d["ult_contacto"] = max(cands) if cands else None

    # Muertes acumuladas
    m = _sql("SELECT COALESCE(SUM(ABS(cantidad)), 0) AS n FROM movimientos "
             "WHERE lote_id = ? AND tipo = 'muerte'", (lid,))
    d["muertes"] = int((m[0].get("n") if m else 0) or 0)
    ini = lote.get("cantidad_inicial") or 0
    d["muertes_pct"] = d["muertes"] / ini * 100 if ini else None


def _estado_stock(dias) -> str:
    if dias is None:
        return "gris"
    if dias <= 3:
        return "rojo"
    if dias <= 10:
        return "amarillo"
    return "verde"


def _texto_dias(dias) -> str:
    if dias is None:
        return "—"
    n = int(round(float(dias)))
    return "1 día" if n == 1 else f"{n} días"


# ---------------------------------------------------------------------
# Estilos
# ---------------------------------------------------------------------
_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;700&family=Source+Sans+3:wght@400;600;700&display=swap');
.hm {{ font-family: 'Source Sans 3', system-ui, sans-serif; color: var(--hm-txt);
  --hm-txt:#18231B; --hm-sub:#5B6B5F; --hm-card:#FFFFFF; --hm-line:#E1E6DD; --hm-bar:#EEF0EC;
  --hm-soft:#F4F6F1; --hm-acc:#1B3E27; --hm-chip:#EEF0EC; --hm-est:#4F7A1F; }}
@media (prefers-color-scheme: dark) {{ .hm {{ --hm-txt:#E8EDE9; --hm-sub:#A3B0A6; --hm-card:#1C231E;
  --hm-line:#2E3A31; --hm-bar:#2E3A31; --hm-soft:#252E28; --hm-acc:#8BC53F; --hm-chip:#2E3A31; --hm-est:#A7D46A; }} }}
.hm-top {{ background: {VERDE}; color: #fff; border-radius: 16px; padding: 18px 18px 20px; display: flex; flex-direction: column; gap: 8px; }}
.hm-top .t {{ font-family: 'Barlow Condensed', sans-serif; font-weight: 700; font-size: 26px; line-height: 1.05; letter-spacing: .2px; }}
.hm-top .s {{ font-size: 14px; color: #DDE7DF; }}
.hm-top b {{ color: #fff; }}
.hm-lbl {{ font-size: 12px; font-weight: 700; letter-spacing: 1.2px; color: var(--hm-sub); margin: 18px 0 8px; }}
.hm-card {{ background: var(--hm-card); border: 1px solid var(--hm-line); border-radius: 14px; padding: 14px 16px; margin-bottom: 10px; }}
.hm-row {{ display: flex; gap: 12px; align-items: center; }}
.hm-ico {{ width: 38px; height: 38px; border-radius: 19px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; font-weight: 700; }}
.hm-h {{ font-weight: 700; font-size: 15px; }}
.hm-sub {{ font-size: 13px; color: var(--hm-sub); }}
.hm-big {{ font-family: 'Barlow Condensed', sans-serif; font-weight: 700; font-size: 26px; line-height: 1; font-variant-numeric: tabular-nums; }}
.hm-kpis {{ display: grid; grid-template-columns: repeat(3, minmax(0,1fr)); gap: 8px; margin-top: 10px; }}
.hm-k .n {{ font-size: 11px; color: var(--hm-sub); letter-spacing: .6px; }}
.hm-k .f {{ font-size: 11px; color: var(--hm-sub); }}
.hm-bar {{ height: 10px; border-radius: 5px; background: var(--hm-bar); overflow: hidden; margin-top: 6px; }}
.hm-bar > div {{ height: 10px; }}
.hm-pill {{ font-size: 12px; font-weight: 700; padding: 4px 10px; border-radius: 99px; white-space: nowrap; }}
.hm-ag {{ display: flex; gap: 14px; padding: 10px 0; border-top: 1px solid var(--hm-bar); font-size: 14px; }}
.hm-ag:first-child {{ border-top: 0; }}
.hm-ag .d {{ width: 78px; white-space: nowrap; font-weight: 700; color: var(--hm-acc); flex-shrink: 0; }}
.hm-kgrid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin: 14px 0 4px; }}
.hm-tile {{ margin-bottom: 0; padding: 12px 14px; }}
.hm-tile .n {{ font-size: 11px; color: var(--hm-sub); letter-spacing: .6px; }}
.hm-tile .f {{ font-size: 11px; color: var(--hm-sub); margin-top: 2px; }}
.hm-hero .hm-kgrid {{ margin-top: 6px; }}
.hm-cal {{ width: 100%; border-collapse: collapse; table-layout: fixed; }}
.hm-cal th {{ font-size: 11px; color: var(--hm-sub); font-weight: 600; text-align: left; padding: 4px 6px; }}
.hm-cal td {{ vertical-align: top; height: 92px; border: 1px solid var(--hm-line); padding: 4px 6px; overflow: hidden; }}
.hm-cal .hm-cal-n {{ font-size: 12px; font-weight: 700; color: var(--hm-sub); }}
.hm-cal td.hm-cal-hoy {{ background: var(--hm-soft); }}
.hm-cal td.hm-cal-hoy .hm-cal-n {{ color: var(--hm-acc); }}
.hm-cal td.hm-cal-fuera {{ opacity: .35; }}
.hm-cal-ev {{ font-size: 11.5px; line-height: 1.25; margin-top: 3px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: var(--hm-txt); }}
.hm-cal-lista {{ display: none; }}
@media (max-width: 700px) {{ .hm-cal {{ display: none; }} .hm-cal-lista {{ display: block; }} }}
.hm-semi {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 10px; }}
.hm-semi .sc {{ border-radius: 14px; padding: 12px 14px; border: 1px solid var(--hm-line); background: var(--hm-card); }}
.hm-semi .sk {{ display: flex; align-items: center; gap: 8px; font-size: 12px; font-weight: 700; letter-spacing: .05em; color: var(--hm-sub); }}
.hm-semi .sd {{ width: 12px; height: 12px; border-radius: 50%; flex-shrink: 0; }}
.hm-semi .sv {{ font-size: 26px; font-weight: 700; color: var(--hm-txt); margin-top: 4px; }}
.hm-semi .sw {{ font-size: 13px; color: var(--hm-sub); margin-top: 2px; line-height: 1.35; }}
.hm-hlbl {{ margin-top: 14px; font-size: 11px; letter-spacing: .08em; color: #C9D8CC; font-weight: 600; }}
.hm-hero .hm-tile {{ background: rgba(255,255,255,.08); border: 1px solid rgba(255,255,255,.14); }}
.hm-hero .hm-tile .n, .hm-hero .hm-tile .f {{ color: #C9D8CC; }}
.hm-hero .hm-big {{ color: #FFFFFF; }}
.hm-clima {{ display: grid; grid-template-columns: repeat(7, minmax(0,1fr)); gap: 4px; text-align: center; font-size: 12px; }}
.hm-clima .ico {{ font-size: 18px; line-height: 1.6; }}
.hm-clima .mx {{ font-weight: 700; }} .hm-clima .mn {{ color: var(--hm-sub); }}
.hm-climat td, .hm-climat th {{ text-align: center; padding: 5px 2px; }}
.hm-climat td:first-child {{ text-align: left; }}
.hm-tl {{ display: grid; grid-template-columns: 0.9fr 1.05fr 1.15fr 0.9fr 1fr; gap: 4px; margin-top: 8px; }}
.hm-tl .b {{ height: 6px; border-radius: 3px; }}
.hm-tl .x {{ font-size: 10.5px; letter-spacing: -.2px; overflow-wrap: normal; word-break: keep-all; color: #C9D8CC; margin-top: 5px; line-height: 1.25; }}
.hm-tl .now {{ color: #fff; font-weight: 700; }}
.hm-sem {{ display: grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap: 8px; text-align: center; }}
.hm-sem .c {{ width: 32px; height: 32px; border-radius: 16px; margin: 0 auto 6px; }}
.hm-tab {{ width: 100%; border-collapse: collapse; font-size: 14px; font-variant-numeric: tabular-nums; }}
.hm-tab td, .hm-tab th {{ padding: 7px 4px; border-top: 1px solid var(--hm-bar); text-align: left; }}
.hm-tab th {{ font-size: 11px; color: var(--hm-sub); font-weight: 600; border-top: 0; }}
.hm-steps {{ display: flex; align-items: flex-end; gap: 6px; height: 70px; margin-top: 8px; }}
.hm-steps > div {{ flex: 1; display: flex; flex-direction: column; align-items: center; gap: 4px; font-size: 11px; color: var(--hm-sub); }}
.hm-steps .v {{ width: 100%; border-radius: 4px 4px 0 0; }}
.hm-nota {{ font-size: 13px; color: var(--hm-sub); background: var(--hm-soft); border-radius: 8px; padding: 8px 10px; margin-top: 8px; }}
</style>
"""


def estilos() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------
# INICIO
# ---------------------------------------------------------------------
def _lotes_activos() -> List[Dict]:
    try:
        lotes = db.listar_lotes(estado="activo") or []
    except Exception:
        return []
    out = []
    for l in lotes:
        try:
            c = db.obtener_cliente(l.get("cliente_id")) or {}
        except Exception:
            c = {}
        if (c.get("estado") or "activo") == "baja":
            continue
        out.append(l)
    return out


def render_inicio(on_abrir_lote, kp: str = "hm") -> None:
    """Pantalla de inicio. `on_abrir_lote(lote_id)` se llama cuando
    Mauricio toca "Ver ficha" en una tarjeta."""
    estilos()
    hoy = date.today()
    lotes = _lotes_activos()
    datos = []
    for l in lotes:
        try:
            datos.append(datos_lote(l, hoy))
        except Exception as e:
            log.warning("ui_movil: lote %s: %s", l.get("id"), e)

    # Pendientes del día
    tareas = []
    for d in datos:
        sm = d.get("stock_min")
        if sm and sm.get("dias_restantes") is not None and sm["dias_restantes"] <= 10:
            fa = _fecha(sm.get("fecha_agotamiento"))
            tareas.append((
                "#FCEBD7", "#B4610E", "↓",
                f"{d['cliente']} · pedir alimento",
                f"Le quedan {_texto_dias(sm['dias_restantes'])} de "
                f"{sm['producto']}" + (f". Se termina el {_dm(fa)}" if fa else ""),
            ))
        pp = d.get("proxima_pesada")
        if pp and (pp - hoy).days <= 3:
            tareas.append((
                "#E3ECF7", "#2C5E9E", "⚖",
                f"{d['cliente']} · pesada mensual",
                f"Toca pesar el {_dm(pp)}.",
            ))
        ctrl = d.get("control")
        f_ctrl = _fecha((ctrl or {}).get("fecha_respuesta") or (ctrl or {}).get("fecha_envio"))
        # Los colores del control van en el semáforo, no acá.
        try:
            _cli = db.obtener_cliente(d["lote"].get("cliente_id")) or {}
            if not (_cli.get("whatsapp") or "").strip():
                tareas.append((
                    "var(--hm-chip)", "var(--hm-sub)", "☎",
                    f"{d['cliente']} · falta el WhatsApp",
                    "Cargalo en Clientes para poder mandarle el control y los avisos.",
                ))
        except Exception:
            pass
        if not (d["lote"].get("entrevista") or ""):
            tareas.append(("var(--hm-chip)", "var(--hm-sub)", "📋",
                           f"{d['cliente']} · falta la entrevista inicial", ""))

    # Lo que cargó Mauri a mano para hoy (o atrasado y sin hacer)
    try:
        from . import ui_gestion as _g
        for a in _g.listar_agenda((hoy - timedelta(days=30)).isoformat(), hoy.isoformat()):
            if a.get("hecho"):
                continue
            fa = _fecha(a.get("fecha"))
            tipo = a.get("tipo") or "tarea"
            ico = _CAL_TIPOS.get(tipo, _CAL_TIPOS["tarea"])[0]
            quien = a.get("cliente") or "Recordatorio"
            atraso = f" Era para el {_dm(fa)}." if fa and fa < hoy else ""
            col = _COL_ACT.get(tipo, "#1F6FB2")
            tareas.append((col + "22", col, ico,
                           f"{quien} · {_TXT_ACT.get(tipo, tipo)}",
                           f"{a.get('titulo') or ''}.{atraso} Se marca hecho en el calendario."))
    except Exception as e:
        log.info("ui_movil: agenda hoy: %s", e)

    # Clima: eventos de frío o calor de los próximos días en el campo de
    # cada cliente, con el motivo y qué hacer según el comedero del lote.
    try:
        from . import clima_reco as cr
        for d in datos:
            info = _clima_cliente(d["lote"].get("cliente_id"))
            evs = cr.eventos_proximos((info or {}).get("pronostico_7d") or [], hoy, dias=5)
            if not evs:
                continue
            ev = evs[0]
            f = ev["fecha"]
            cuando = "hoy" if f == hoy else ("mañana" if (f - hoy).days == 1 else
                                              f"el {_dia_corto(f).lower()}/{f.month}")
            recos = cr.recomendaciones(ev, d["lote"].get("tipo_comedero_concentrado") or "",
                                       d["lote"], d.get("control"),
                                       d.get("animales"), d.get("peso_hoy") or d.get("peso"),
                                       _ms_animal(d))
            nombre = ("frío" if ev["tipo"] == "frio" else "calor") + (" crítico" if ev["nivel"] == "critico" else " moderado")
            mas = f" (y {len(evs) - 1} día{'s' if len(evs) > 2 else ''} más)" if len(evs) > 1 else ""
            tareas.append((
                "#E3ECF7" if ev["tipo"] == "frio" else "#FCE4D6",
                "#2C5E9E" if ev["tipo"] == "frio" else "#B4430E",
                "❄" if ev["tipo"] == "frio" else "☀",
                f"{d['cliente']} · {nombre} {cuando}{mas}",
                ev["motivo"].capitalize() + ". " + "; ".join(recos[:3]) + ".",
            ))
    except Exception as e:
        log.info("ui_movil: clima: %s", e)

    # Orden por urgencia y avisos agrupados (con muchos clientes no se repiten)
    sin_wa = [t for t in tareas if t[2] == "☎"]
    tareas = [t for t in tareas if t[2] != "☎"]
    prio = {"!": 0, "↓": 1, "⚖": 2, "✓": 4} | {_ico: 0.5 for _, _, _ico, _, _ in _TC}
    tareas.sort(key=lambda t: prio.get(t[2], 3))
    # Muchos del mismo tipo: una sola tarjeta con la lista
    for ico, titulo in (("↓", "Pedir alimento"), ("⚖", "Pesada mensual")):
        grupo = [t for t in tareas if t[2] == ico]
        def _clave_fecha(t):
            x = t[4].split("el ")[-1].rstrip(".")
            try:
                dd, mm = x.split("/")[:2]
                return (int(mm), int(dd))
            except Exception:
                return (99, 99)
        grupo.sort(key=_clave_fecha)
        if len(grupo) > 3:
            resto = [t for t in tareas if t[2] != ico]
            det = "; ".join(f"{t[3].split(' · ')[0]} ({t[4].split('el ')[-1].rstrip('.')})" for t in grupo[:6])
            if len(grupo) > 6:
                det += f" y {len(grupo) - 6} más (ver tabla de clientes)"
            det = ("Se terminan: " if ico == "↓" else "Pesar: ") + det
            pos = min(i for i, t in enumerate(tareas) if t[2] == ico)
            resto.insert(min(pos, len(resto)), (grupo[0][0], grupo[0][1], ico,
                                                f"{titulo}: {len(grupo)} lotes", det))
            tareas = resto
    sin_ent = [t for t in tareas if t[2] == "📋"]
    tareas = [t for t in tareas if t[2] != "📋"]
    if sin_ent:
        nombres = [t[3].split(" · ")[0] for t in sin_ent]
        tareas.append(("var(--hm-chip)", "var(--hm-sub)", "📋",
                       f"Falta la entrevista inicial de {len(nombres)} lote{'s' if len(nombres) != 1 else ''}",
                       ", ".join(nombres[:5]) + (f" y {len(nombres) - 5} más" if len(nombres) > 5 else "")
                       + ". Con ella la app marca los puntos débiles de cada lote. Se hace desde la ficha."))
    if sin_wa:
        nombres = [t[3].split(" · ")[0] for t in sin_wa]
        tareas.append(("var(--hm-chip)", "var(--hm-sub)", "☎",
                       f"Falta el WhatsApp de {len(nombres)} cliente{'s' if len(nombres) != 1 else ''}",
                       ", ".join(nombres[:5]) + (f" y {len(nombres) - 5} más" if len(nombres) > 5 else "")
                       + ". Cargalo en Clientes para mandar controles y avisos."))
    n_anim = sum(d.get("animales") or 0 for d in datos)
    clientes = sorted({d["cliente"] for d in datos if d.get("cliente")})
    n_cli = len(clientes)
    if n_cli == 0:
        quien = "Todavía no tenés clientes con lotes en seguimiento"
    elif n_cli <= 3:
        quien = ("Seguís " + " y ".join([", ".join(clientes[:-1]), clientes[-1]] if n_cli > 1 else clientes)
                 + f": <b>{n_anim} animales</b> en {len(datos)} lote{'s' if len(datos) != 1 else ''}")
    else:
        quien = (f"Seguís <b>{n_cli} clientes</b>: <b>{n_anim} animales</b> "
                 f"en {len(datos)} lotes")
    resto = (f' · <b>{len(tareas)} cosa{"s" if len(tareas) != 1 else ""} para mirar</b>'
             if tareas else " · nada urgente hoy")
    pedidos = _pedidos_proximos(datos)
    try:
        tiles = _resumen_inicio(datos, pedidos, hoy)
    except Exception as e:
        log.info("ui_movil: resumen: %s", e)
        tiles = ""
    lbl_tot = ""
    st.markdown(
        f'<div class="hm"><div class="hm-top hm-hero">'
        f'<div class="t">{_saludo()}, Mauri</div>'
        f'<div class="s">{quien}{resto}.</div>'
        + (f'<div class="hm-hlbl">{_e(lbl_tot)}</div>' if tiles and lbl_tot else "")
        + f'<div class="hm-kgrid">{tiles}</div>'
        f'</div></div>',
        unsafe_allow_html=True,
    )

    try:
        _semaforos_inicio(datos, hoy)
    except Exception as e:
        log.info("ui_movil: semaforos: %s", e)

    col_a = st.container()
    with col_a:
        if tareas:
            from . import contacto as _ct

            def _html_tareas(ts):
                h = ""
                for bg, fg, ico, tit, sub in ts:
                    h += (
                        f'<div class="hm-card"><div class="hm-row">'
                        + (_ct.icono(_ct.clave_de_emoji(ico)) if _ct.clave_de_emoji(ico) else
                           f'<div class="hm-ico" style="background:{bg};color:{fg}">{_e(ico)}</div>')
                        + f'<div><div class="hm-h">{_e(tit)}</div>'
                        f'<div class="hm-sub">{_e(sub)}</div></div></div></div>'
                    )
                return h
            st.markdown(f'<div class="hm"><div class="hm-lbl">PARA HOY · {len(tareas)}</div>'
                        f'{_html_tareas(tareas[:6])}</div>', unsafe_allow_html=True)
            if len(tareas) > 6:
                with st.expander(f"Ver {len(tareas) - 6} más"):
                    st.markdown(f'<div class="hm">{_html_tareas(tareas[6:])}</div>',
                                unsafe_allow_html=True)
        else:
            st.markdown('<div class="hm"><div class="hm-lbl">PARA HOY</div><div class="hm-card">'
                        '<div class="hm-sub">Nada pendiente. Todo en orden.</div></div></div>',
                        unsafe_allow_html=True)

    try:
        _calendario(datos, hoy, kp)
    except Exception as e:
        log.info("ui_movil: calendario: %s", e)

    # Una fila por cliente/lote: todo lo de cada uno junto, con su nombre.
    st.markdown('<div class="hm"><div class="hm-lbl">CLIENTES EN SEGUIMIENTO · '
                f'{n_cli}</div></div>', unsafe_allow_html=True)
    if not datos:
        st.info("No hay lotes activos. Cargá un encierre con el botón de abajo.")
    datos_ord = sorted(datos, key=_urgencia)
    if datos_ord:
        _tabla_lotes(datos_ord, on_abrir_lote, kp)
    _, c_b = st.columns([3, 1])
    if c_b.button("➕ Encierre nuevo", key=f"{kp}_nuevo_enc", type="primary", width="stretch"):
        from . import ui_gestion as _g
        _g.dialog_encierre()


def _semaforos_inicio(datos: List[Dict], hoy: date) -> None:
    """Cómo están los lotes según el último control semanal (de los
    últimos 7 días). Rojo y amarillo con nombre; verde solo la cantidad."""
    grupos = {"rojo": [], "amarillo": [], "verde": [], "sin": []}
    for d in datos:
        ctrl = d.get("control") or {}
        f = _fecha(ctrl.get("fecha_respuesta") or ctrl.get("fecha_envio"))
        color = (ctrl.get("semaforo_general") or "").lower()
        if f and (hoy - f).days <= 7 and color in grupos:
            # qué área lo puso en ese color
            areas = [n for k, n in (("sanidad", "sanidad"), ("consumo", "consumo"),
                                    ("ambiente", "ambiente"), ("alimento", "alimento"))
                     if (ctrl.get(f"semaforo_{k}") or "").lower() == color]
            grupos[color].append(d["cliente"] + (f" ({', '.join(areas)})" if color != "verde" and areas else ""))
        else:
            grupos["sin"].append(d["cliente"])

    def _lista(xs, n=4):
        return ", ".join(xs[:n]) + (f" y {len(xs) - n} más" if len(xs) > n else "")

    cajas = [
        ("#C62828", "URGENTE", grupos["rojo"], _lista(grupos["rojo"]) or "Ninguno"),
        ("#E0A100", "PARA MIRAR", grupos["amarillo"], _lista(grupos["amarillo"]) or "Ninguno"),
        ("#2E7D32", "BIEN", grupos["verde"],
         "lotes sin problemas" if grupos["verde"] else "Ninguno todavía"),
        ("#9E9E9E", "SIN CONTROL ESTA SEMANA", grupos["sin"],
         (_lista(grupos["sin"]) + ". Cargá el control desde la ficha o esperá el WhatsApp.")
         if grupos["sin"] else "Todos respondieron"),
    ]
    h = '<div class="hm"><div class="hm-lbl">SEMÁFORO DE LOS CORRALES · CONTROL SEMANAL</div><div class="hm-semi">'
    for col, tit, xs, txt in cajas:
        h += (f'<div class="sc" style="border-left:5px solid {col}">'
              f'<div class="sk"><span class="sd" style="background:{col}"></span>{tit}</div>'
              f'<div class="sv">{len(xs)}</div><div class="sw">{_e(txt)}</div></div>')
    st.markdown(h + "</div></div>", unsafe_allow_html=True)


# Tipos de actividad del calendario: (ícono, color, nombre)
_CAL_TIPOS = {
    "pedido":   ("🛒", "#B4610E", "Pedir alimento"),
    "racion":   ("🔄", "#2C5E9E", "Cambio de ración"),
    "pesada":   ("⚖", "#6A3FA0", "Pesada"),
    "seguim":   ("📞", "#5F6B66", "Seguimiento 15 días"),
    "entrega":  ("🚚", "#2E7D32", "Entrega"),
    "control":  ("📋", "#2E7D32", "Control respondido"),
    "salida":   ("🏁", "#1B4332", "Salida estimada"),
    "clima":    ("🌡", "#C62828", "Clima"),
}
# Tipos de contacto con el cliente (los mismos de la agenda y las charlas)
from .contacto import TIPOS_CONTACTO as _TC  # noqa: E402
for _k, _nom, _ico, _col, _ in _TC:
    _CAL_TIPOS[_k] = (_ico, _col, _nom)
_TXT_ACT = {k: v for k, _, _, _, v in _TC}
_COL_ACT = {k: c for k, _, _, c, _ in _TC}


def _eventos_mes(datos: List[Dict], y: int, m: int, hoy: date) -> Dict[date, List[tuple]]:
    """Actividades del mes: lo que ya pasó (entregas, pesadas, controles)
    y lo que viene (pedidos, cambios de ración, pesadas, salidas, clima)."""
    import calendar as _cal
    ini = date(y, m, 1)
    fin = date(y, m, _cal.monthrange(y, m)[1])
    ev: Dict[date, List[tuple]] = {}

    def add(f, tipo, txt):
        if f and ini <= f <= fin:
            ev.setdefault(f, []).append((tipo, txt))

    for d in datos:
        cli = d["cliente"]
        lid = d["id"]
        # Pasado
        for p in d.get("pesadas") or []:
            add(_fecha(p.get("fecha")), "pesada", f"{cli} · pesada {_num(p.get('peso_promedio_kg'), 0)} kg")
        for e in _sql("SELECT fecha_entrega, kg_total FROM entregas_producto WHERE lote_id = ? "
                      "AND fecha_entrega >= ? AND fecha_entrega <= ?", (lid, ini.isoformat(), fin.isoformat())):
            add(_fecha(e.get("fecha_entrega")), "entrega", f"{cli} · {_num(e.get('kg_total'), 0)} kg")
        for c in _sql("SELECT COALESCE(fecha_respuesta, fecha_envio) AS f, semaforo_general AS g "
                      "FROM controles_semanales WHERE lote_id = ?", (lid,)):
            add(_fecha(c.get("f")), "control", f"{cli} · control {c.get('g') or ''}".strip())
        for r in _sql("SELECT fecha FROM dietas WHERE lote_id = ? AND fecha >= ? AND fecha <= ?",
                      (lid, ini.isoformat(), fin.isoformat())):
            add(_fecha(r.get("fecha")), "racion", f"{cli} · cambio de ración")
        # Lo que viene
        if d.get("pedir") and d["pedir"] >= hoy:
            add(d["pedir"], "pedido", f"{cli} · {(d.get('stock_min') or {}).get('producto') or 'alimento'}")
        elif d.get("pedir") and d["pedir"] < hoy:
            add(hoy, "pedido", f"{cli} · pedir ya")
        pp = d.get("proxima_pesada")
        if pp and pp >= hoy:
            add(pp, "pesada", f"{cli} · pesada mensual")
        if d.get("fecha_peso"):
            f15 = d["fecha_peso"] + timedelta(days=15)
            if f15 >= hoy:
                add(f15, "seguim", f"{cli} · seguimiento")
        if d.get("salida"):
            add(d["salida"], "salida", f"{cli} · salida ({_num(d.get('peso_venta'), 0)} kg)")

    # Lo que cargó Mauri a mano (llamar, visitar, recordatorios)
    try:
        from . import ui_gestion as _g
        for a in _g.listar_agenda(ini.isoformat(), fin.isoformat()):
            quien = a.get("cliente") or ""
            txt = (f"{quien} · " if quien else "") + str(a.get("titulo") or "")
            add(_fecha(a.get("fecha")), a.get("tipo") or "tarea", ("✓ " if a.get("hecho") else "") + txt)
    except Exception as e:
        log.info("ui_movil: agenda: %s", e)

    # Clima de la zona (Catriló): días con estrés moderado o crítico
    try:
        info = _clima_localidad("Catriló, La Pampa")
        for x in info.get("pronostico_7d") or []:
            sev = str(x.get("severidad_real") or "")
            f = _fecha(x.get("fecha"))
            if f and f >= hoy and sev[:1] in ("🔴", "🟠"):
                add(f, "clima", sev[1:].strip())
    except Exception:
        pass
    return ev


def _calendario(datos: List[Dict], hoy: date, kp: str) -> None:
    import calendar as _cal
    from . import contacto as _ct
    key = f"{kp}_cal_mes"
    off = st.session_state.get(key, 0)
    y, m = hoy.year, hoy.month + off
    while m < 1:
        m += 12; y -= 1
    while m > 12:
        m -= 12; y += 1
    nombres = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto",
               "Septiembre", "Octubre", "Noviembre", "Diciembre"]

    c1, c0, c2, c3, c4 = st.columns([2.4, 1.3, 1, 1, 1], vertical_alignment="center")
    if c0.button("＋ Agregar actividad", key=f"{key}_add", type="primary", width="stretch"):
        from . import ui_gestion as _g
        _g.dialog_actividad()
    c1.markdown(f'<div class="hm"><div class="hm-lbl" style="margin:0">CALENDARIO · '
                f'{nombres[m - 1].upper()} {y}</div></div>', unsafe_allow_html=True)
    if c2.button("◀ Anterior", key=f"{key}_a", width="stretch"):
        st.session_state[key] = off - 1
        st.rerun()
    if c3.button("Hoy", key=f"{key}_h", width="stretch", disabled=off == 0):
        st.session_state[key] = 0
        st.rerun()
    if c4.button("Siguiente ▶", key=f"{key}_s", width="stretch"):
        st.session_state[key] = off + 1
        st.rerun()

    ev = _eventos_mes(datos, y, m, hoy)

    # Grilla (compu) y lista (celular)
    sem = _cal.Calendar(firstweekday=0).monthdatescalendar(y, m)
    cab = "".join(f"<th>{x}</th>" for x in DIAS_SEM)
    filas = ""
    for semana in sem:
        filas += "<tr>"
        for dia in semana:
            fuera = dia.month != m
            cls = "hm-cal-fuera" if fuera else ("hm-cal-hoy" if dia == hoy else "")
            chips = ""
            evs = ev.get(dia, []) if not fuera else []
            for tipo, txt in evs[:3]:
                ico, col, _ = _CAL_TIPOS.get(tipo, _CAL_TIPOS["tarea"])
                ico = _ct.svg(tipo, 14) or ico
                pasado = ' style="opacity:.6"' if dia < hoy else ""
                chips += (f'<div class="hm-cal-ev"{pasado}><span style="color:{col}">{ico}</span> '
                          f'{_e(txt)}</div>')
            if len(evs) > 3:
                chips += f'<div class="hm-sub">+{len(evs) - 3} más</div>'
            filas += f'<td class="{cls}"><div class="hm-cal-n">{dia.day}</div>{chips}</td>'
        filas += "</tr>"
    lista = ""
    for dia in sorted(ev):
        if dia < hoy and m == hoy.month and y == hoy.year:
            continue
        for tipo, txt in ev[dia]:
            ico, col, _ = _CAL_TIPOS.get(tipo, _CAL_TIPOS["tarea"])
            ico = _ct.svg(tipo, 15) or ico
            lista += (f'<div class="hm-ag"><div class="d">{_dia_corto(dia)}/{dia.month}</div>'
                      f'<div><span style="color:{col}">{ico}</span> {_e(txt)}</div></div>')
    if not lista:
        lista = '<div class="hm-sub">Sin actividades.</div>'
    ley = " · ".join(f'<span style="color:{c}">{_ct.svg(k, 14) or i}</span> {n}' for k, (i, c, n) in _CAL_TIPOS.items())
    st.markdown(
        f'<div class="hm"><div class="hm-card">'
        f'<table class="hm-cal"><tr>{cab}</tr>{filas}</table>'
        f'<div class="hm-cal-lista">{lista}</div>'
        f'<div class="hm-sub" style="margin-top:8px">{ley}</div></div></div>',
        unsafe_allow_html=True)
    _mis_actividades(y, m, hoy, key)


def _mis_actividades(y: int, m: int, hoy: date, key: str) -> None:
    """Lo cargado a mano en el mes, para marcarlo hecho o borrarlo."""
    import calendar as _cal
    from . import ui_gestion as _g
    acts = _g.listar_agenda(date(y, m, 1).isoformat(), date(y, m, _cal.monthrange(y, m)[1]).isoformat())
    if not acts:
        return
    pend = sum(1 for a in acts if not a.get("hecho"))
    with st.expander(f"Actividades que cargaste este mes · {pend} pendiente{'s' if pend != 1 else ''}"):
        for a in acts:
            f = _fecha(a.get("fecha"))
            from . import contacto as _ct
            quien = a.get("cliente") or ""
            txt = f"<b>{_dia_corto(f)}/{f.month}</b> · " if f else ""
            txt += _e((f"{quien} · " if quien else "") + str(a.get("titulo") or ""))
            if a.get("hecho"):
                txt = f'<s style="opacity:.6">{txt}</s> ✓'
            c1, c2, c3 = st.columns([6, 1.3, 1], vertical_alignment="center")
            c1.markdown(f'<div style="display:flex;align-items:center;gap:10px">'
                        f'{_ct.icono(a.get("tipo") or "tarea", 30)}<div>{txt}</div></div>',
                        unsafe_allow_html=True)
            if c2.button("Pendiente" if a.get("hecho") else "✓ Hecho", key=f"{key}_ok_{a['id']}", width="stretch"):
                _g.marcar_actividad(a["id"], not a.get("hecho"))
                st.rerun()
            if c3.button("Borrar", key=f"{key}_del_{a['id']}", width="stretch"):
                _g.borrar_actividad(a["id"])
                st.rerun()


def _precio_kg(e: Dict) -> Optional[float]:
    """Precio por kg sin IVA de una entrega. Algunas viejas guardaron el
    precio de la bolsa como si fuera por kg: se corrige con kg_por_bolsa."""
    try:
        pk = float(e.get("precio_kg") or 0)
        kb = float(e.get("kg_por_bolsa") or 0)
    except (TypeError, ValueError):
        return None
    if pk <= 0:
        return None
    if pk > 5000 and kb > 0:
        pk = pk / kb
    return pk


def _pedidos_proximos(datos: List[Dict]) -> List[Dict]:
    out = []
    for d in datos:
        for s in d.get("stock") or []:
            dia = float(s.get("consumo_diario_kg") or 0)
            if dia <= 0:
                continue
            ents = sorted(s.get("entregas") or [], key=lambda e: str(e.get("fecha_entrega")))
            pk = _precio_kg(ents[-1]) if ents else None
            kg30 = dia * 30
            out.append({
                "cliente": d["cliente"], "producto": s["producto"],
                "fecha": _fecha(s.get("fecha_agotamiento")),
                "kg_hoy": s.get("kg_restantes_hoy"),
                "kg30": kg30, "plata30": kg30 * pk if pk else None,
            })
    out.sort(key=lambda p: p["fecha"] or date.max)
    return out


def _resumen_inicio(datos: List[Dict], pedidos: List[Dict], hoy: date) -> str:
    """Números del negocio que no están en otro lado de Inicio: lo que se
    va a vender y lo entregado en el mes. Los pedidos van en "Para hoy"."""
    kg_ = '<span style="font-size:14px"> kg</span>'
    tiles = []

    # 2. ¿Cuánto voy a vender el mes que viene?
    if pedidos:
        kg30 = sum(p["kg30"] for p in pedidos)
        plata = sum(p["plata30"] or 0 for p in pedidos)
        tiles.append(_tile("VENTA DEL PRÓXIMO MES", f"{_num(kg30, 0)}{kg_}",
                           (f"≈ ${_num(plata, 0)} sin IVA. " if plata else "")
                           + "Es lo que van a comer tus clientes en 30 días con la ración de hoy: "
                             "sirve para comprar a tiempo."))

    # 3. ¿Cuánto llevo vendido este mes? (contra el mes anterior)
    ini_mes = hoy.replace(day=1)
    ini_ant = (ini_mes - timedelta(days=1)).replace(day=1)
    def _kg(desde, hasta):
        f = _sql("SELECT kg_total, precio_total FROM entregas_producto "
                 "WHERE fecha_entrega >= ? AND fecha_entrega < ?", (desde.isoformat(), hasta.isoformat()))
        return (sum(float(x.get("kg_total") or 0) for x in f),
                sum(float(x.get("precio_total") or 0) for x in f))
    kg_m, pl_m = _kg(ini_mes, hoy + timedelta(days=1))
    kg_a, _ = _kg(ini_ant, ini_mes)
    mes, mes_ant = MESES[hoy.month - 1], MESES[ini_ant.month - 1]
    tiles.append(_tile(f"ENTREGADO EN {mes.upper()}", f"{_num(kg_m, 0)}{kg_}",
                       (f"${_num(pl_m, 0)} sin IVA. " if pl_m else "")
                       + f"En {mes_ant} fueron {_num(kg_a, 0)} kg. "
                       + ("Todavía no se cargó ninguna entrega este mes." if not kg_m else "")))

    return "".join(tiles)

@st.cache_data(ttl=3600, show_spinner=False)
def _alertas_clima(cliente_ids: tuple) -> list:
    """Alertas de clima (frío, calor, barro) de los clientes con lote
    activo. Devuelve [(cliente, alerta)] solo con severidad media o alta."""
    from . import dashboard
    clientes = [c for c in db.listar_clientes() if c.get("id") in cliente_ids]
    res = dashboard._procesar_clima_clientes(clientes)
    out = []
    for c in res.get("consultadas", []):
        vistos = set()
        for al_lote in c.get("alertas_lotes") or []:
            for al in al_lote.get("alertas") or []:
                sev = str(al.get("severidad") or "").lower()
                if sev in ("info", "ok", "baja", "verde", ""):
                    continue
                k = al.get("titulo")
                if k in vistos:
                    continue
                vistos.add(k)
                acc = al.get("acciones") or []
                if acc and not isinstance(acc, list):
                    acc = [str(acc)]
                out.append((c.get("cliente"), {
                    "icono": al.get("icono"), "titulo": al.get("titulo"),
                    "cuando": al.get("cuando"), "acciones": [str(a) for a in acc],
                }))
    return out[:4]


def _tarjeta_lote(d: Dict) -> None:
    l = d["lote"]
    sm = d.get("stock_min")
    dias = (sm or {}).get("dias_restantes")
    est = _estado_stock(dias)
    fg, bg = ESTADO_COLOR[est]
    pct = 0 if dias is None else max(4, min(100, float(dias) / 30 * 100))
    ctrl = d.get("control")
    if ctrl and ctrl.get("semaforo_general"):
        cfg, cbg = ESTADO_COLOR.get(ctrl["semaforo_general"], ESTADO_COLOR["gris"])
        pill = f'<span class="hm-pill" style="background:{cbg};color:{cfg}">Control: {_e(ctrl["semaforo_general"])}</span>'
    else:
        pill = '<span class="hm-pill" style="background:var(--hm-chip);color:var(--hm-sub)">Sin control aún</span>'
    adpv = d.get("adpv")
    h = (
        '<div class="hm"><div class="hm-card">'
        '<div style="display:flex;justify-content:space-between;gap:10px;align-items:flex-start">'
        f'<div><div class="hm-big">{_e(d["cliente"])}</div>'
        f'<div class="hm-sub">{_e(l.get("identificador"))} · {d["animales"]} animales'
        f'{" · " + _e(d["localidad"]) if d["localidad"] else ""}</div></div>{pill}</div>'
        '<div class="hm-kpis">'
        f'<div class="hm-k"><div class="n">DÍA</div><div class="hm-big">{d["dia"] if d["dia"] else "—"}</div>'
        f'<div class="f">desde {_dm(d["ingreso"])}</div></div>'
        f'<div class="hm-k"><div class="n">PESO</div><div class="hm-big">{_num(d["peso"], 0) if d["peso"] else "—"}<span style="font-size:14px"> kg</span></div>'
        f'<div class="f">pesada {_dm(d["fecha_peso"])}</div></div>'
        f'<div class="hm-k"><div class="n">GANANCIA</div><div class="hm-big">{_num(adpv, 2) if adpv is not None else "—"}</div>'
        '<div class="f">kg/día medido</div></div></div>'
    )
    if sm:
        h += (
            '<div style="margin-top:12px;display:flex;justify-content:space-between;font-size:13px">'
            f'<span style="font-weight:600">{_e(sm["producto"])} en el campo</span>'
            f'<span style="color:{fg};font-weight:700">{_texto_dias(dias)}</span></div>'
            f'<div class="hm-bar"><div style="width:{pct:.0f}%;background:{fg}"></div></div>'
        )
    else:
        h += '<div class="hm-sub" style="margin-top:10px">Sin entregas de HMS cargadas para este lote.</div>'
    st.markdown(h + "</div></div>", unsafe_allow_html=True)


# ---------------------------------------------------------------------
# FICHA DEL LOTE
# ---------------------------------------------------------------------
def _grafico_peso(pesadas: List[Dict], adpv_proy: Optional[float],
                  hasta: Optional[date]) -> str:
    pts = [(_fecha(p["fecha"]), float(p["peso_promedio_kg"])) for p in pesadas
           if _fecha(p["fecha"])]
    if not pts:
        return '<div class="hm-sub">Todavía no hay pesadas.</div>'
    proy = None
    if adpv_proy and hasta and hasta > pts[-1][0]:
        proy = (hasta, pts[-1][1] + adpv_proy * (hasta - pts[-1][0]).days)
    xs = [p[0] for p in pts] + ([proy[0]] if proy else [])
    ys = [p[1] for p in pts] + ([proy[1]] if proy else [])
    x0, x1 = min(xs), max(xs)
    span = max((x1 - x0).days, 1)
    lo = int(min(ys) // 10 * 10 - 10)
    hi = int(max(ys) // 10 * 10 + 20)
    W, H, L, R, T, B = 360, 190, 36, 352, 18, 168

    def X(d):
        return L + (R - L) * ((d - x0).days / span) if len(xs) > 1 else (L + R) / 2

    def Y(v):
        return B - (B - T) * ((v - lo) / (hi - lo))

    g = []
    for i in range(4):
        v = lo + (hi - lo) * i / 3
        y = Y(v)
        g.append(f'<line x1="{L}" y1="{y:.1f}" x2="{R}" y2="{y:.1f}" style="stroke:var(--hm-bar)"/>')
        g.append(f'<text x="{L-6}" y="{y+4:.1f}" font-size="11" style="fill:var(--hm-sub)" text-anchor="end">{v:.0f}</text>')
    linea = " ".join(f"{X(d):.1f},{Y(v):.1f}" for d, v in pts)
    g.append(f'<polyline points="{linea}" fill="none" style="stroke:var(--hm-acc)" stroke-width="3" stroke-linecap="round"/>')
    for d, v in pts:
        g.append(f'<circle cx="{X(d):.1f}" cy="{Y(v):.1f}" r="5" style="fill:var(--hm-acc)"/>')
        g.append(f'<text x="{X(d):.1f}" y="{Y(v)-10:.1f}" font-size="12" font-weight="700" style="fill:var(--hm-txt)" text-anchor="middle">{_num(v)}</text>')
        g.append(f'<text x="{X(d):.1f}" y="{H-4}" font-size="11" style="fill:var(--hm-sub)" text-anchor="middle">{_dm(d)}</text>')
    if proy:
        d0, v0 = pts[-1]
        g.append(f'<line x1="{X(d0):.1f}" y1="{Y(v0):.1f}" x2="{X(proy[0]):.1f}" y2="{Y(proy[1]):.1f}" stroke="{LIMA}" stroke-width="3" stroke-dasharray="6 6"/>')
        g.append(f'<circle cx="{X(proy[0]):.1f}" cy="{Y(proy[1]):.1f}" r="5" style="fill:var(--hm-card)" stroke="{LIMA}" stroke-width="2.5"/>')
        g.append(f'<text x="{X(proy[0])-4:.1f}" y="{Y(proy[1])-10:.1f}" font-size="12" font-weight="700" style="fill:var(--hm-est)" text-anchor="end">~{proy[1]:.0f} est.</text>')
        g.append(f'<text x="{X(proy[0]):.1f}" y="{H-4}" font-size="11" style="fill:var(--hm-sub)" text-anchor="end">{_dm(proy[0])}</text>')
    return (
        f'<svg viewBox="0 0 {W} {H}" width="100%" style="max-height:300px;display:block;margin:0 auto" role="img" '
        f'aria-label="Evolución del peso promedio del lote">{"".join(g)}</svg>'
    )


def render_ficha(lote_id: int, on_volver, kp: str = "hm",
                 texto_volver: str = "← Volver") -> None:
    estilos()
    hoy = date.today()
    lote = db.obtener_lote(lote_id)
    if not lote:
        st.warning("No encontré ese lote.")
        return
    d = datos_lote(lote, hoy)

    _subir_arriba(f"{kp}-{lote_id}")
    c_v, c_t = st.columns([1, 4], vertical_alignment="center")
    if c_v.button(texto_volver, key=f"{kp}_volver", type="primary", width="stretch"):
        on_volver()
    destino = texto_volver.replace("←", "").strip()
    c_t.markdown(
        f'<div class="hm" style="font-size:14px;color:var(--hm-sub)">{_e(destino)} › '
        f'<b style="color:var(--hm-txt)">{_e(lote.get("cliente_nombre") or "")}</b> · '
        f'{_e(lote.get("identificador") or "")}</div>',
        unsafe_allow_html=True,
    )

    # Cabecera con línea de tiempo
    plan = _sql("SELECT * FROM planes_adaptacion WHERE lote_id = ? ORDER BY id DESC LIMIT 1", (lote_id,))
    plan = plan[0] if plan else None
    fin_adapt = None
    if plan and plan.get("fecha_inicio") and plan.get("dias_adaptacion"):
        fin_adapt = _fecha(plan["fecha_inicio"]) + timedelta(days=int(plan["dias_adaptacion"]))
    salida = _fecha(lote.get("objetivo_fecha"))
    en_adapt = bool(fin_adapt and hoy < fin_adapt)
    pasos = [
        ("Encierre", _dm(d["ingreso"]), True, False),
        ("Adaptación", f'desde {_dm(_fecha(plan["fecha_inicio"]))}' if plan else "—", not en_adapt and bool(plan), en_adapt),
        ("Terminación", f'hoy, día {d["dia"]}' if d["dia"] else "—", False, not en_adapt),
        ("Pesada", _dm(d.get("proxima_pesada")), False, False),
        ("Salida", _dm(salida) if salida else "a definir", False, False),
    ]
    tl = ""
    for nombre, sub, hecho, ahora in pasos:
        color = LIMA if hecho else ("#FFFFFF" if ahora else "#3C5E47")
        cls = "x now" if ahora else "x"
        tl += f'<div><div class="b" style="background:{color}"></div><div class="{cls}">{_e(nombre)}<br>{_e(sub)}</div></div>'
    st.markdown(
        f'<div class="hm"><div class="hm-top"><div class="t">{_e(d["cliente"])}</div>'
        f'<div class="s">{_e(lote.get("identificador"))} · {d["animales"]} animales'
        f'{" · " + _e(d["localidad"]) if d["localidad"] else ""}</div>'
        f'<div class="hm-tl">{tl}</div></div></div>',
        unsafe_allow_html=True,
    )

    # Acciones de carga
    try:
        from . import ui_gestion as _g
        _g.acciones_lote(lote, d, kp)
    except Exception as e:
        st.caption(f"No se pudieron mostrar las acciones: {e}")

    # Números clave
    try:
        _kpis(lote, d)
    except Exception as e:
        st.caption(f"No se pudieron calcular los números: {e}")

    # En la compu: dos columnas. En el celular se apilan solas.
    col_a, col_b = st.columns([1.25, 1], gap="medium")
    with col_a:
        # Peso
        try:
            adpv_proy = lote.get("adpv_objetivo_kg") or d.get("adpv")
            hasta = d.get("proxima_pesada")
            sub = ""
            if d.get("adpv") is not None:
                sub = (f'+{_num(d.get("ganancia"))} kg en {d.get("dias_entre")} días · '
                       f'<b>{_num(d["adpv"], 2)} kg/día</b>')
            leyenda_proy = (
                f'estimado a {_num(adpv_proy, 2)} kg/día'
                + (" (objetivo)" if lote.get("adpv_objetivo_kg") else " (última ganancia medida)")
            ) if adpv_proy else ""
            st.markdown(
                '<div class="hm"><div class="hm-lbl">PESO DEL LOTE · kg promedio</div><div class="hm-card">'
                f'{_grafico_peso(d["pesadas"], adpv_proy, hasta)}'
                f'<div class="hm-sub">Línea llena: balanza. Línea cortada: {leyenda_proy}.</div>'
                + "".join(
                    f'<div class="hm-nota">{_dm(_fecha(p["fecha"]))}: {_e(p.get("notas"))}</div>'
                    for p in d["pesadas"][-2:] if p.get("notas")
                )
                + '</div></div>',
                unsafe_allow_html=True,
            )
        except Exception as e:
            st.caption(f"No se pudo dibujar el peso: {e}")

        # Seguimiento: engorde contra lo esperado, salida, consumo
        try:
            _seccion_seguimiento(lote, d, kp)
        except Exception as e:
            st.caption(f"No se pudo mostrar el seguimiento: {e}")

        # Alimento
        try:
            h = '<div class="hm"><div class="hm-lbl">ALIMENTO</div><div class="hm-card">'
            if d["stock"]:
                for s in d["stock"]:
                    dias = s.get("dias_restantes")
                    fg, _ = ESTADO_COLOR[_estado_stock(dias)]
                    pct = 0 if dias is None else max(4, min(100, float(dias) / 30 * 100))
                    h += (
                        '<div style="display:flex;justify-content:space-between;font-size:14px;margin-top:4px">'
                        f'<span style="font-weight:600">{_e(s["producto"])}</span>'
                        f'<span style="color:{fg};font-weight:700">{_texto_dias(dias)} · ~{_num(s.get("kg_restantes_hoy"), 0)} kg</span></div>'
                        f'<div class="hm-bar"><div style="width:{pct:.0f}%;background:{fg}"></div></div>'
                        f'<div class="hm-sub" style="margin-top:4px">Calculado: entregas menos consumo según la dieta de cada día '
                        f'({_num(s.get("consumo_diario_kg"), 0)} kg/día hoy).</div>'
                    )
            else:
                h += '<div class="hm-sub">Sin entregas de HMS para este lote.</div>'
            ent = db.listar_entregas_lote(lote_id) or []
            if ent:
                h += '<table class="hm-tab" style="margin-top:8px"><tr><th>Fecha</th><th>Producto</th><th>Cantidad</th></tr>'
                for e in ent[:8]:
                    cant = (f'{_num(e.get("cantidad_bolsas"), 0)} bolsas · ' if e.get("cantidad_bolsas") else "") + f'{_num(e.get("kg_total"), 0)} kg'
                    h += f'<tr><td>{_dm(_fecha(e.get("fecha_entrega")))}</td><td>{_e(e.get("producto_nombre"))}</td><td>{cant}</td></tr>'
                h += "</table>"
            st.markdown(h + "</div></div>", unsafe_allow_html=True)
        except Exception as e:
            st.caption(f"No se pudo mostrar el alimento: {e}")

        try:
            _seccion_racion(lote_id, d)
            _seccion_uniformidad(d)
        except Exception as e:
            st.caption(f"No se pudo mostrar una sección: {e}")

    with col_b:
        # Control semanal
        try:
            ctrl = d.get("control")
            areas = [("Sanidad", "semaforo_sanidad"), ("Consumo", "semaforo_consumo"),
                     ("Ambiente", "semaforo_ambiente"), ("Alimento", "semaforo_alimento")]
            sem = ""
            _ico_ctrl = {"Sanidad": "sanidad", "Consumo": "comedero", "Ambiente": "corral", "Alimento": "alimento"}
            _txt_ctrl = {"verde": ("#2E9E57", "bien"), "amarillo": ("#F2C200", "para mirar"),
                         "rojo": ("#D92D20", "urgente")}
            for nom, campo in areas:
                est = ((ctrl or {}).get(campo) or "gris").lower()
                col, leyenda = _txt_ctrl.get(est, ("#B8B8B8", "sin datos"))
                ico = (_SVG + _ICON_SIT[_ico_ctrl[nom]] + "</svg>").replace(
                    'width="26" height="26"', 'width="58%" height="58%"')
                sem += (f'<div style="border:1px solid var(--hm-line,#e5e5e5);border-radius:12px;padding:10px 2px">'
                        f'<div style="width:clamp(34px,9vw,46px);height:clamp(34px,9vw,46px);border-radius:50%;'
                        f'background:var(--hm-soft);color:var(--hm-est);display:flex;align-items:center;'
                        f'justify-content:center;margin:0 auto">{ico}</div>'
                        f'<div style="font-size:clamp(10px,2.7vw,13px);font-weight:600;margin:4px 0 6px">{nom}</div>'
                        f'<div style="width:16px;height:16px;border-radius:50%;background:{col};margin:0 auto 4px;'
                        f'box-shadow:0 0 0 3px {col}33"></div>'
                        f'<div class="hm-sub" style="font-size:clamp(9px,2.5vw,12px)">{leyenda}</div></div>')
            f_c = _fecha((ctrl or {}).get("fecha_respuesta") or (ctrl or {}).get("fecha_envio"))
            cab = f"respondido el {_dm(f_c)}" if ctrl else "pendiente"
            txt = (_e(ctrl.get("comentarios")) if ctrl and ctrl.get("comentarios")
                   else "Cuando lleguen las respuestas del productor se pintan en verde, amarillo o rojo.")
            if not ctrl:
                txt = ("Todavía no hay controles. Cargá lo que te mande el productor por WhatsApp "
                       "(respuestas y fotos) con el botón de abajo; cuando se conecte WhatsApp "
                       "se va a llenar solo.")
            st.markdown(
                f'<div class="hm"><div class="hm-lbl">CONTROL SEMANAL · último {cab}</div>'
                f'<div class="hm-card"><div class="hm-sem">{sem}</div>'
                f'<div class="hm-nota">{txt}</div></div></div>',
                unsafe_allow_html=True,
            )
            from . import ui_gestion as _g
            if st.button("📋 Cargar control semanal", key=f"{kp}_ctrl_{lote_id}", width="stretch"):
                _g.dialog_control(lote_id)
            _g.historial_controles(lote_id, kp)
        except Exception as e:
            st.caption(f"No se pudo mostrar el control: {e}")

        # Plan de adaptación
        if plan:
            try:
                esc = _sql("SELECT * FROM plan_adaptacion_escalones WHERE plan_id = ? ORDER BY orden", (plan["id"],))
                if esc:
                    mx = max(float(x.get("mezcla_kg_cabeza_dia") or 0) for x in esc) or 1
                    barras = ""
                    n = len(esc)
                    for i, x in enumerate(esc):
                        v = float(x.get("mezcla_kg_cabeza_dia") or 0)
                        tono = int(70 + 130 * (1 - i / max(n - 1, 1)))
                        col = VERDE if i == n - 1 else f"rgb({tono-60},{tono},{tono-90})"
                        barras += (f'<div><div class="v" style="height:{max(6, v / mx * 52):.0f}px;background:{col}"></div>'
                                   f'{_num(v, 1).replace(",0", "")}</div>')
                    estado = "en curso" if en_adapt else "completo"
                    st.markdown(
                        f'<div class="hm"><div class="hm-lbl">PLAN DE ADAPTACIÓN · {estado}</div><div class="hm-card">'
                        f'<div class="hm-steps">{barras}</div>'
                        f'<div class="hm-sub" style="margin-top:6px">kg de mezcla por cabeza por día, desde el {_dm(_fecha(plan["fecha_inicio"]))}. '
                        f'Dieta final: {_e(plan.get("dieta_final"))}.</div></div></div>',
                        unsafe_allow_html=True,
                    )
            except Exception as e:
                st.caption(f"No se pudo mostrar el plan: {e}")

        try:
            _seccion_movimientos(lote_id)
        except Exception as e:
            st.caption(f"No se pudieron mostrar los movimientos: {e}")
        # Informes
        inf = _sql("SELECT * FROM informes_lote WHERE lote_id = ? ORDER BY fecha_creacion DESC LIMIT 5", (lote_id,))
        h = '<div class="hm"><div class="hm-lbl">INFORMES AL CLIENTE</div><div class="hm-card">'
        if inf:
            for i in inf:
                h += (f'<div class="hm-ag"><div class="d">{_dm(_fecha(str(i.get("fecha_creacion"))))}</div>'
                      f'<div>{_e(i.get("tipo")).replace("_", " ").replace("cierre ciclo", "informe de cierre del ciclo")}'
                      f' · {_e(i.get("estado"))}</div></div>')
        else:
            pp = d.get("proxima_pesada")
            h += f'<div class="hm-sub">Todavía no hay. El primero sale después de la pesada{" del " + _dm(pp) if pp else ""}.</div>'
        st.markdown(h + "</div></div>", unsafe_allow_html=True)
        for i in inf:
            if i.get("contenido") and i.get("tipo") == "cierre_ciclo":
                with st.expander(f"Ver informe de cierre del {_dm(_fecha(str(i.get('fecha_creacion'))))}"):
                    st.markdown(i["contenido"])

    # Clima del campo a lo ancho: con todos los datos para estimar estrés
    try:
        _seccion_clima(lote)
    except Exception as e:
        st.caption(f"No se pudo mostrar el clima: {e}")


def _seccion_seguimiento(lote: Dict, d: Dict, kp: str) -> None:
    hoy = date.today()
    filas = []
    if d.get("adpv") is not None:
        esp = d.get("adpv_esp")
        txt = f"<b>{_num(d['adpv'], 2)} kg/día</b>"
        if esp:
            p = d.get("engorde_pct") or 0
            nota = "viene bien" if p >= 95 else ("algo por debajo" if p >= 85 else "se está quedando")
            txt += (f" contra {_num(esp, 2)} esperados ({_num(p, 0)} %, {nota})"
                    + ("" if lote.get("adpv_objetivo_kg") else " · esperado de la categoría"))
        filas.append(("Engorde", txt))
    else:
        filas.append(("Engorde", "hace falta una segunda pesada"))
    if d.get("peso_venta"):
        if d.get("salida"):
            filas.append(("Salida estimada", f"<b>{_dm(d['salida'])}</b> para llegar a "
                          f"{_num(d['peso_venta'], 0)} kg (hoy ~{_num(d.get('peso_hoy'), 0)} kg)"))
        else:
            filas.append(("Salida estimada", f"peso de venta {_num(d['peso_venta'], 0)} kg; falta una pesada"))
    else:
        filas.append(("Salida estimada", "cargá el peso de venta con el botón de abajo"))
    try:
        from .frame import evaluar_frame
        fr = evaluar_frame(lote.get("altura_grupa_cm"), lote.get("edad_meses"), lote.get("categoria") or "")
    except Exception:
        fr = None
    if fr:
        txt = f"<b>{_num(fr['frame'], 1)}</b> (BIF)"
        if fr["peso_faena"]:
            txt += (f" → peso de faena {fr['peso_faena'][0]}-{fr['peso_faena'][1]} kg para "
                    f"{fr['destino']} (INTA)")
        else:
            txt += " → por debajo de frame 4 el INTA no da rango de peso"
        if fr["fuera_rango"]:
            txt += ". Ojo: la fórmula es para 5 a 21 meses"
        filas.append(("Frame", txt))
    else:
        filas.append(("Frame", "cargá edad y altura a la grupa en Objetivos"))
    if d.get("consumo_pct") is not None:
        cp = d["consumo_pct"]
        nota = ("comen más de lo que dice la ración" if cp > 115 else
                ("comen menos de lo que dice la ración" if cp < 85 else "coincide con la ración"))
        filas.append(("Consumo real", f"<b>{_num(cp, 0)} %</b> de lo formulado: {nota}"))
    else:
        filas.append(("Consumo real", "se calcula cuando haya dos entregas separadas por 2 semanas o más"))
    filas.append(("Ración", _e(d.get("racion_txt") or "—")))
    filas.append(("Último contacto", _hace(d.get("ult_contacto"), hoy)))
    m = d.get("muertes") or 0
    filas.append(("Muertes", f"{m}" + (f" ({_num(d['muertes_pct'], 1)} %)" if d.get("muertes_pct") is not None else "")))
    h = "".join(f'<tr><td class="hm-sub" style="white-space:nowrap">{k}</td><td>{v}</td></tr>' for k, v in filas)
    st.markdown(f'<div class="hm"><div class="hm-lbl">SEGUIMIENTO</div><div class="hm-card">'
                f'<table class="hm-tab">{h}</table></div></div>', unsafe_allow_html=True)
    from . import ui_gestion as _g
    from . import clima_reco as cr
    inst = [cr.INSTALACIONES[k].get(lote.get(k) or "") for k in cr.INSTALACIONES]
    inst = [x for x in inst if x]
    if lote.get("reserva_agua_l"):
        inst.append(f"reserva de agua {_num(lote['reserva_agua_l'], 0)} L")
    if lote.get("caudal_l_min"):
        inst.append(f"bebedero repone {_num(lote['caudal_l_min'], 0)} L/min")
    st.markdown(f'<div class="hm"><div class="hm-sub" style="margin:-4px 0 8px">Corral: '
                f'{_e(" · ".join(inst)) if inst else "sin cargar (reparo, sombra, piso, bebederos)"}'
                f'</div></div>', unsafe_allow_html=True)
    b1, b2 = st.columns(2)
    if b1.button("🎯 Objetivos (peso de venta, ganancia, frame)", key=f"{kp}_obj_{d['id']}", width="stretch"):
        _g.dialog_objetivos(d["id"])
    if b2.button("🏠 Corral (reparo, sombra, piso, agua)", key=f"{kp}_inst_{d['id']}", width="stretch"):
        _g.dialog_instalaciones(d["id"])
    _seccion_situacion(lote, d, kp)
    _seccion_charlas(lote, d, kp)
    _seccion_historia(lote, d, kp)
    _analisis_ia(lote, d, kp)


_HIST_ICO = {"encierre": "🐂", "entrevista": "📋", "control": "🚦", "charla": "💬", "pesada": "⚖",
             "entrega": "🚚", "racion": "🔄", "movimiento": "↔", "foto": "📷"}
_HIST_COL = {"verde": "#2E9E57", "amarillo": "#F2C200", "rojo": "#D92D20"}


def _seccion_historia(lote: Dict, d: Dict, kp: str) -> None:
    """Todo conectado: cómo arrancó (entrevista), cómo fue cambiando cada
    área en los controles, y la línea de tiempo con charlas, pesadas,
    entregas y cambios de ración. De acá sale el informe de cierre."""
    from . import historia as hi
    try:
        cols = hi.evolucion(d["id"], lote)
        evs = hi.eventos(d["id"], lote)
    except Exception as e:
        log.info("ui_movil: historia: %s", e)
        return
    st.markdown('<div class="hm"><div class="hm-lbl">HISTORIA DEL LOTE</div></div>', unsafe_allow_html=True)
    # Evolución de cada área: entrevista y controles semanales
    if cols:
        ico_area = {"sanidad": "sanidad", "consumo": "comedero", "ambiente": "corral", "alimento": "alimento"}
        cab = "".join(f'<th style="text-align:center;font-weight:600">{_e(c["etiqueta"])}</th>' for c in cols[-10:])
        filas = ""
        for a, nombre, _ in hi.AREAS:
            ico = (_SVG + _ICON_SIT[ico_area[a]] + "</svg>").replace('width="26" height="26"', 'width="16" height="16"')
            celdas = "".join(
                f'<td style="text-align:center"><span style="display:inline-block;width:14px;height:14px;'
                f'border-radius:50%;background:{_HIST_COL.get(c.get(a), "#B8B8B8")}"></span></td>' for c in cols[-10:])
            filas += (f'<tr><td style="white-space:nowrap"><span style="color:var(--hm-est);display:inline-flex;'
                      f'vertical-align:-3px">{ico}</span> {nombre}</td>{celdas}</tr>')
        nota = ("" if len(cols) > 1 else
                '<div class="hm-sub" style="margin-top:6px">Cada control semanal suma una columna: así se ve si '
                'los puntos débiles se corrigen o se complican.</div>')
        st.markdown(f'<div class="hm"><div class="hm-card"><div class="hm-sub" style="margin-bottom:6px">'
                    f'Evolución por área: de la entrevista inicial a cada control</div>'
                    f'<div style="overflow-x:auto"><table class="hm-tab"><tr><th></th>{cab}</tr>{filas}</table></div>'
                    f'{nota}</div></div>', unsafe_allow_html=True)
    # Línea de tiempo
    def _ev(e):
        f = e["fecha"]
        det = f'<div class="hm-sub">{_e(e["detalle"])}</div>' if e.get("detalle") else ""
        return (f'<div class="hm-ag"><div class="d">{_dm(f)}</div><div>{_HIST_ICO.get(e["tipo"], "•")} '
                f'{_e(e["titulo"])}{det}</div></div>')
    if evs:
        st.markdown('<div class="hm"><div class="hm-card">' + "".join(_ev(e) for e in evs[:6]) + '</div></div>',
                    unsafe_allow_html=True)
        if len(evs) > 6:
            with st.expander(f"Ver toda la historia ({len(evs)} registros)"):
                st.markdown('<div class="hm">' + "".join(_ev(e) for e in evs[6:]) + '</div>', unsafe_allow_html=True)
    # Fotos: primera y última de cada tema, para ver el cambio
    _fotos_historia(d["id"], kp)
    # Informe de cierre
    key = f"{kp}_inf_{d['id']}"
    if st.button("📄 Armar informe del ciclo (borrador con IA)", key=key + "_b", width="stretch"):
        with st.spinner("Juntando toda la historia del lote y armando el informe…"):
            st.session_state[key] = _armar_informe(lote, d)
    txt = st.session_state.get(key)
    if txt:
        st.markdown(f'<div class="hm"><div class="hm-card"><div class="hm-lbl">BORRADOR DEL INFORME · '
                    f'revisalo antes de mandarlo</div></div></div>', unsafe_allow_html=True)
        st.markdown(txt)
        st.download_button("Descargar el borrador", txt.encode("utf-8"),
                           file_name=f"informe_{(lote.get('cliente_nombre') or 'lote').replace(' ', '_')}.md",
                           key=key + "_dl", width="stretch")


def _fotos_historia(lote_id: int, kp: str) -> None:
    from . import historia as hi
    from . import control_semanal as cs
    from . import ui_gestion as _g
    try:
        por_tema = hi.fotos_para_comparar(lote_id)
    except Exception:
        por_tema = {}
    n = sum(len(v) for v in por_tema.values())
    st.markdown(f'<div class="hm"><div class="hm-lbl" style="margin-top:4px">FOTOS · {n}</div></div>',
                unsafe_allow_html=True)
    if st.button("📷 Subir fotos", key=f"{kp}_fot_{lote_id}", width="stretch"):
        _g.dialog_fotos(lote_id)
    if not por_tema:
        st.markdown('<div class="hm"><div class="hm-card"><div class="hm-sub">Todavía no hay fotos. Entran con la '
                    'entrevista inicial, los controles semanales, las charlas o con este botón. Conviene sacar '
                    'siempre las mismas: corral, comedero, bebedero y bosta.</div></div></div>',
                    unsafe_allow_html=True)
        return
    orden = list(cs.TEMAS_TODOS)
    for tema in sorted(por_tema, key=lambda t: orden.index(t) if t in orden else 99):
        fs = por_tema[tema]
        nombre = cs.TEMAS_TODOS.get(tema, tema)
        if len(fs) == 1:
            st.caption(f"{nombre} · {_dm(_fecha(fs[0]['fecha']))}")
            st.image(fs[0]["datos"], width=320)
            continue
        st.caption(f"{nombre} · primera y última de {len(fs)}")
        c1, c2 = st.columns(2)
        c1.image(fs[0]["datos"], caption=f"{_dm(_fecha(fs[0]['fecha']))} (primera)", width="stretch")
        c2.image(fs[-1]["datos"], caption=f"{_dm(_fecha(fs[-1]['fecha']))} (última)", width="stretch")
        if len(fs) > 2:
            with st.expander(f"Ver las {len(fs)} de {nombre.lower()}"):
                cols = st.columns(4)
                for i, ft in enumerate(fs):
                    cols[i % 4].image(ft["datos"], caption=_dm(_fecha(ft["fecha"])), width="stretch")


def _armar_informe(lote: Dict, d: Dict) -> str:
    import json as _json
    import os
    from . import historia as hi
    try:
        key = os.environ.get("ANTHROPIC_API_KEY") or str(st.secrets.get("ANTHROPIC_API_KEY", "") or "")
    except Exception:
        key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        return "Falta configurar la clave de la IA (ANTHROPIC_API_KEY) en la app."
    datos = hi.resumen_ciclo(d["id"], lote, d)
    import base64 as _b64
    from . import control_semanal as cs
    contenido = []
    try:
        for tema, fs in hi.fotos_para_comparar(d["id"]).items():
            for ft in ([fs[0], fs[-1]] if len(fs) > 1 else fs):
                if not str(ft.get("mime") or "").startswith("image/") or len(contenido) >= 16:
                    continue
                contenido.append({"type": "text", "text": f"Foto: {cs.TEMAS_TODOS.get(tema, tema)}, {ft['fecha']}"})
                contenido.append({"type": "image", "source": {"type": "base64", "media_type": ft["mime"],
                                                               "data": _b64.b64encode(ft["datos"]).decode()}})
    except Exception as e:
        log.info("ui_movil: fotos informe: %s", e)
    contenido.append({"type": "text", "text": _json.dumps(datos, ensure_ascii=False, default=str)})
    texto = None
    try:
        from anthropic import Anthropic
        cli = Anthropic(api_key=key, timeout=90.0)
        err = None
        for modelo in ("claude-sonnet-5-5", "claude-sonnet-4-5"):
            try:
                r = cli.messages.create(model=modelo, max_tokens=2500, system=hi.SISTEMA_INFORME,
                                        messages=[{"role": "user", "content": contenido}])
                texto = "".join(getattr(b, "text", "") for b in r.content).strip()
                break
            except Exception as e:
                err = e
        if texto is None:
            return f"No se pudo consultar la IA: {err}"
    except Exception as e:
        return f"No se pudo consultar la IA: {e}"
    try:
        with db.get_conn() as conn:
            conn.execute("INSERT INTO informes_lote (lote_id, tipo, periodo_desde, periodo_hasta, contenido, datos, estado) "
                         "VALUES (?, 'cierre_ciclo', ?, ?, ?, ?, 'borrador')",
                         (d["id"], datos.get("fecha_encierre"), datos.get("fecha_fin_o_hoy"), texto,
                          _json.dumps(datos, ensure_ascii=False, default=str)))
        db.invalidar_cache_lecturas()
    except Exception as e:
        log.info("ui_movil: guardar informe: %s", e)
    return texto


_MEDIO_ICO = {nom: ico for _, nom, ico, _, _ in _TC} | {"Visita al campo": "🚗", "En persona (otro lugar)": "🤝"}


def _seccion_charlas(lote: Dict, d: Dict, kp: str) -> None:
    """Lo que se habló con el cliente: la historia del lote en palabras."""
    from . import ui_gestion as _g
    ch = _g.listar_charlas(d["id"])
    st.markdown(f'<div class="hm"><div class="hm-lbl">CHARLAS CON EL CLIENTE · {len(ch)}</div></div>',
                unsafe_allow_html=True)
    if st.button("💬 Anotar una charla", key=f"{kp}_ch_{d['id']}", width="stretch"):
        _g.dialog_charla(d["id"])
    if not ch:
        st.markdown('<div class="hm"><div class="hm-card"><div class="hm-sub">Todavía no anotaste ninguna. '
                    'Después de cada llamado o visita, dos líneas de qué se habló y qué se acordó.</div></div></div>',
                    unsafe_allow_html=True)
        return
    def _una(c):
        f = _fecha(c.get("fecha"))
        ac = (f'<div class="hm-nota" style="margin-top:6px"><b>Se acordó:</b> {_e(c.get("acuerdos"))}</div>'
              if c.get("acuerdos") else "")
        from . import contacto as _ct
        k = _ct.clave_de_emoji(_MEDIO_ICO.get(c.get("medio"), ""))
        ico = _ct.icono(k, 28) if k else _MEDIO_ICO.get(c.get("medio"), "💬")
        return (f'<div class="hm-card"><div class="hm-sub" style="margin-bottom:6px;display:flex;align-items:center;gap:8px">'
                f'{ico} <span><b>{_dia_corto(f)}/{f.month}</b> · {_e(c.get("medio") or "")}</span></div>'
                f'<div style="white-space:pre-wrap">{_e(c.get("resumen"))}</div>{ac}</div>')
    st.markdown('<div class="hm">' + "".join(_una(c) for c in ch[:3]) + '</div>', unsafe_allow_html=True)
    if len(ch) > 3:
        with st.expander(f"Ver las {len(ch) - 3} anteriores"):
            st.markdown('<div class="hm">' + "".join(_una(c) for c in ch[3:]) + '</div>', unsafe_allow_html=True)



# (clave, ícono, nombre, áreas de los puntos débiles, preguntas de la entrevista)
# (clave, ícono, nombre, áreas de los puntos débiles, preguntas de la entrevista)
_SVG = '<svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">'
_ICON_SIT = {
    'sanidad': '<path d="M12 3l7 3v5c0 4.5-3 8.3-7 10-4-1.7-7-5.5-7-10V6z"/><path d="M12 8.5v6M9 11.5h6"/>',
    'comedero': '<path d="M3 10h18l-2.2 7.5a1.5 1.5 0 0 1-1.4 1H6.6a1.5 1.5 0 0 1-1.4-1z"/><path d="M7 7.5c1.2-1.6 2.6-1.6 3.8 0M13.2 7.5c1.2-1.6 2.6-1.6 3.8 0"/><path d="M6 18.5V21M18 18.5V21"/>',
    'agua': '<path d="M12 3.5c3.2 3.8 6 7.2 6 10.3a6 6 0 0 1-12 0c0-3.1 2.8-6.5 6-10.3z"/><path d="M9.2 14.5a2.9 2.9 0 0 0 2.8 2.6"/>',
    'corral': '<path d="M3 11l9-6.5 9 6.5"/><path d="M5 9.7V20h14V9.7"/><path d="M9.5 20v-5h5v5"/><path d="M9.5 15l5 5M14.5 15l-5 5"/>',
    'alimento': '<path d="M8 4.5h8l-1.2 2.5c2.7 1.7 4.2 4.6 4.2 7.8 0 3.4-2.4 5.7-7 5.7s-7-2.3-7-5.7c0-3.2 1.5-6.1 4.2-7.8z"/><path d="M9.3 7h5.4"/><path d="M9.5 13.5h5M10.5 16.5h3"/>',
    'manejo': '<rect x="5" y="4.5" width="14" height="16.5" rx="2"/><path d="M9 4.5V3.5h6v1"/><path d="M8.5 11l1.6 1.6 3-3"/><path d="M8.5 16.5h7"/>',
}
_GRUPOS_SIT = [
    ("sanidad", _SVG + _ICON_SIT["sanidad"] + "</svg>", "Sanidad", {"sanidad"}, ("A8", "B")),
    ("comedero", _SVG + _ICON_SIT["comedero"] + "</svg>", "Comedero", {"consumo", "alimento"}, ("C", "A7", "A10")),
    ("agua", _SVG + _ICON_SIT["agua"] + "</svg>", "Agua", {"agua"}, ("D",)),
    ("corral", _SVG + _ICON_SIT["corral"] + "</svg>", "Instalaciones", {"ambiente"}, ("E",)),
    ("manejo", _SVG + _ICON_SIT["manejo"] + "</svg>", "Manejo", {"manejo", "objetivo"}, ("F", "A5", "A6")),
]


def _seccion_situacion(lote: Dict, d: Dict, kp: str) -> None:
    """Estado de situación del lote a partir de la entrevista inicial:
    puntos débiles con su número y su fuente, y qué vigila el control semanal."""
    from . import entrevista as ent
    from . import ui_gestion as _g
    r = ent.cargar(lote)
    if not r:
        st.markdown('<div class="hm"><div class="hm-lbl">ESTADO DE SITUACIÓN</div><div class="hm-card">'
                    '<div class="hm-sub">Falta la entrevista inicial. Con ella la app arma los puntos débiles '
                    'de este lote y el control semanal pregunta solo lo que importa.</div></div></div>',
                    unsafe_allow_html=True)
        if st.button("📋 Hacer la entrevista inicial", key=f"{kp}_ent_{d['id']}", type="primary",
                     width="stretch"):
            _g.dialog_entrevista(d["id"])
        return
    pts = ent.puntos_debiles(r, lote, d.get("peso_hoy") or d.get("peso"))
    falt = ent.faltantes(r)
    # Un ícono por área con su semáforo abajo; el detalle va agrupado debajo.
    tiles, filas = [], []
    for _k, ico, nombre, areas, claves in _GRUPOS_SIT:
        ps = [p for p in pts if p["area"] in areas]
        contestado = any(any(k.startswith(c) for c in claves) for k in r)
        n_r = sum(p["nivel"] == "rojo" for p in ps)
        n_a = len(ps) - n_r
        if n_r:
            col, txt = "#D92D20", f'{n_r} rojo{"s" if n_r != 1 else ""}' + (f"<br>{n_a} a mirar" if n_a else "")
        elif n_a:
            col, txt = "#F2C200", f'{n_a} para mirar'
        elif contestado:
            col, txt = "#2E9E57", "bien"
        else:
            col, txt = "#B8B8B8", "sin datos"
        ico_tile = ico.replace('width="26" height="26"', 'width="58%" height="58%"')
        tiles.append(f'<div style="border:1px solid var(--hm-line,#e5e5e5);border-radius:12px;padding:10px 2px;'
                     f'text-align:center;background:var(--hm-card-bg,transparent)">'
                     f'<div style="width:clamp(34px,9vw,46px);height:clamp(34px,9vw,46px);border-radius:50%;background:var(--hm-soft);color:var(--hm-est);'
                     f'display:flex;align-items:center;justify-content:center;margin:0 auto">'
                     f'{ico_tile}</div>'
                     f'<div style="font-size:clamp(9px,2.6vw,13px);font-weight:600;margin:4px 0 6px;'
                     f'hyphens:auto;-webkit-hyphens:auto;line-height:1.2" lang="es">{nombre.replace("Instalaciones", "Instala&shy;ciones")}</div>'
                     f'<div style="width:16px;height:16px;border-radius:50%;background:{col};margin:0 auto 4px;'
                     f'box-shadow:0 0 0 3px {col}33"></div>'
                     f'<div class="hm-sub" style="font-size:clamp(9px,2.5vw,12px);line-height:1.2">{txt}</div></div>')
        if ps:
            items = []
            for p in ps:
                c = "#D92D20" if p["nivel"] == "rojo" else "#F2C200"
                fuente = (f'<div class="hm-sub" style="font-size:12px">Fuente: {_e(p["fuente"])}</div>'
                          if p.get("fuente") else "")
                items.append(f'<div style="display:flex;gap:8px;margin:5px 0"><span style="flex:none;width:10px;'
                             f'height:10px;border-radius:50%;background:{c};margin-top:5px"></span>'
                             f'<div>{_e(p["texto"])}.{fuente}</div></div>')
            ico_chico = ico.replace('width="26" height="26"', 'width="17" height="17"')
            filas.append(f'<div style="margin-top:10px"><b style="display:inline-flex;align-items:center;gap:6px">'
                         f'<span style="color:var(--hm-est);display:inline-flex">{ico_chico}</span>{nombre}</b>'
                         f'{"".join(items)}</div>')
    filas.insert(0, '<div style="display:grid;grid-template-columns:repeat(5,minmax(0,1fr));'
                    f'gap:clamp(4px,1.2vw,8px);margin:6px 0 2px">{"".join(tiles)}</div>')
    vig = ent.preguntas_semanales(pts)
    vig_txt = ", ".join(ent.CONTROL_TXT.get(k, k) for k in vig if k != "12")
    n_r = sum(p["nivel"] == "rojo" for p in pts)
    n_a = sum(p["nivel"] == "amarillo" for p in pts)
    cab = ((f'<b>{n_r} rojo{"s" if n_r != 1 else ""}</b>' if n_r else "")
           + (" y " if n_r and n_a else "") + (f'{n_a} para mirar' if n_a else "")
           or "Sin puntos débiles en lo contestado") + \
          f' · entrevista del {_dm(_fecha(lote.get("entrevista_fecha")))}'
    extra = (f'<div class="hm-nota"><b>Control semanal de este lote:</b> {_e(vig_txt)}'
             f' (y jadeo en semanas de calor).</div>')
    if falt:
        extra += f'<div class="hm-nota"><b>Faltan datos:</b> {_e(", ".join(falt))}.</div>'
    st.markdown(f'<div class="hm"><div class="hm-lbl">ESTADO DE SITUACIÓN</div><div class="hm-card">'
                f'<div class="hm-sub" style="margin-bottom:4px">{cab}</div>{"".join(filas)}{extra}'
                f'</div></div>', unsafe_allow_html=True)
    if st.button("📋 Ver o corregir la entrevista inicial", key=f"{kp}_ent_{d['id']}", width="stretch"):
        _g.dialog_entrevista(d["id"])


def _analisis_ia(lote: Dict, d: Dict, kp: str) -> None:
    """Botón para que la IA lea todo el lote y proponga qué hacer. Es una
    sugerencia para Mauri: la lee y la ajusta antes de decirle nada al cliente."""
    key = f"{kp}_ia_{d['id']}"
    if st.button("🤖 Analizar este lote con IA", key=key + "_b", width="stretch"):
        with st.spinner("Analizando el lote…"):
            st.session_state[key] = _pedir_analisis_ia(lote, d)
    txt = st.session_state.get(key)
    if txt:
        st.markdown(f'<div class="hm"><div class="hm-card"><div class="hm-lbl">ANÁLISIS DE LA IA · '
                    f'borrador para revisar</div></div></div>', unsafe_allow_html=True)
        st.markdown(txt)


def _puntos_ia(lote: Dict, d: Dict):
    from . import entrevista as ent
    r = ent.cargar(lote)
    if not r:
        return "no se hizo la entrevista inicial"
    return [f"{p['nivel']}: {p['texto']}" + (f" ({p['fuente']})" if p.get("fuente") else "")
            for p in ent.puntos_debiles(r, lote, d.get("peso_hoy") or d.get("peso"))]


def _pedir_analisis_ia(lote: Dict, d: Dict) -> str:
    import json as _json
    import os
    from . import clima_reco as cr
    try:
        key = os.environ.get("ANTHROPIC_API_KEY") or str(st.secrets.get("ANTHROPIC_API_KEY", "") or "")
    except Exception:
        key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        return "Falta configurar la clave de la IA (ANTHROPIC_API_KEY) en la app."
    from . import ui_gestion as _gch
    info = _clima_cliente(lote.get("cliente_id")) or {}
    hoy = date.today()
    pron = [x for x in info.get("pronostico_7d") or [] if (_fecha(x.get("fecha")) or hoy) >= hoy - timedelta(days=3)]
    dieta = _sql("SELECT fecha, composicion_json, observaciones FROM dietas WHERE lote_id = ? "
                 "ORDER BY fecha DESC LIMIT 1", (d["id"],))
    ctrl = d.get("control") or {}
    inst = {k: cr.INSTALACIONES[k].get(lote.get(k) or "", "sin dato") for k in cr.INSTALACIONES}
    datos = {
        "cliente": d["cliente"], "localidad": d.get("localidad"),
        "categoria": lote.get("categoria"), "raza": lote.get("raza"),
        "animales": d.get("animales"), "dia_de_encierre": d.get("dia"),
        "peso_ultima_pesada_kg": d.get("peso"), "fecha_ultima_pesada": str(d.get("fecha_peso")),
        "ganancia_kg_dia_medida": d.get("adpv"), "ganancia_esperada": d.get("adpv_esp"),
        "peso_estimado_hoy": d.get("peso_hoy"), "peso_de_venta": d.get("peso_venta"),
        "comedero": lote.get("tipo_comedero_concentrado"),
        "instalaciones_corral": inst,
        "puntos_debiles_entrevista_inicial": _puntos_ia(lote, d),
        "racion_vigente": dieta[0] if dieta else None,
        "alimento_dias_restantes": (d.get("stock_min") or {}).get("dias_restantes"),
        "consumo_real_vs_racion_pct": d.get("consumo_pct"),
        "muertes": d.get("muertes"),
        "charlas_con_el_cliente_ultimas": [
            {k: c.get(k) for k in ("fecha", "medio", "resumen", "acuerdos")}
            for c in _gch.listar_charlas(d["id"], 6)],
        "ultimo_control": {k: ctrl.get(k) for k in ("fecha_respuesta", "respuestas", "comentarios",
                                                     "semaforo_general", "semaforo_sanidad",
                                                     "semaforo_consumo", "semaforo_ambiente",
                                                     "semaforo_alimento")} if ctrl else None,
        "clima_3_dias_atras_hoy_y_7_adelante": [
            {k: x.get(k) for k in ("fecha", "t_min", "t_max", "hr_media", "precipitacion_mm",
                                   "viento_max_kmh", "nubes_pct", "thi", "severidad_real")} for x in pron],
    }
    sistema = (
        "Sos el asistente técnico de Mauri, asesor en nutrición de bovinos en encierre a corral "
        "en La Pampa (HMS Nutrición Animal). Te paso los datos de UN lote de un cliente. "
        "Escribile a Mauri (no al cliente), en castellano rioplatense, claro y concreto: "
        "1) cómo viene el lote en dos o tres líneas con los números que importan; "
        "2) los riesgos de los próximos 7 días por clima, según las instalaciones y el comedero; "
        "3) qué haría, en una lista corta ordenada por prioridad. "
        "Reglas: usá solo los datos que te paso; si falta un dato importante, decilo en vez de suponerlo. "
        "No inventes números. Con silo comedero no se cambia la mezcla por pocos días. "
        "No propongas cambios de ración durante un evento climático. "
        "No nombres marcas comerciales salvo las que aparecen en la ración. Máximo 220 palabras.")
    try:
        from anthropic import Anthropic
        cli = Anthropic(api_key=key, timeout=60.0)
        ultimo_error = None
        for modelo in ("claude-sonnet-5-5", "claude-sonnet-4-5"):
            try:
                r = cli.messages.create(
                    model=modelo, max_tokens=900, system=sistema,
                    messages=[{"role": "user", "content": _json.dumps(datos, ensure_ascii=False, default=str)}])
                return "".join(getattr(b, "text", "") for b in r.content).strip()
            except Exception as e:
                ultimo_error = e
        return f"No se pudo consultar la IA: {ultimo_error}"
    except Exception as e:
        return f"No se pudo consultar la IA: {e}"


def _seccion_racion(lote_id: int, d: Dict) -> None:
    try:
        dietas = db.listar_dietas(lote_id) or []
    except Exception:
        dietas = []
    hoy = date.today().isoformat()
    vig = [x for x in dietas if str(x.get("fecha") or "")[:10] <= hoy]
    if not vig:
        return
    dv = sorted(vig, key=lambda x: str(x.get("fecha")))[-1]
    comp = dv.get("composicion") or []
    if not comp:
        try:
            comp = json.loads(dv.get("composicion_json") or "[]")
        except Exception:
            comp = []
    filas = ""
    total = 0.0
    for c in comp:
        kg = float(c.get("kg_tal_cual") or 0)
        total += kg
        filas += (f'<tr><td>{_e(c.get("nombre"))}</td>'
                  f'<td>{_num(c.get("pct_tal_cual"), 0) + " %" if c.get("pct_tal_cual") else "—"}</td>'
                  f'<td>{_num(kg, 2) if kg else "—"}</td></tr>')
    factor = None
    sm = d.get("stock_min") or {}
    ci = sm.get("consumo_info") or {}
    if ci.get("factor_peso_vivo") and abs(ci["factor_peso_vivo"] - 1) > 0.005:
        factor = ci["factor_peso_vivo"]
    nota = ""
    if factor and total:
        nota = (f'<div class="hm-sub" style="margin-top:6px">Formulada para el peso del '
                f'{_dm(_fecha(dv.get("fecha")))}. Con el peso estimado de hoy '
                f'({_num(ci.get("peso_estimado_kg"), 0)} kg) comen ~{_num(total * factor, 1)} kg/cab.</div>')
    st.markdown(
        f'<div class="hm"><div class="hm-lbl">RACIÓN VIGENTE · desde el {_dm(_fecha(dv.get("fecha")))}</div>'
        f'<div class="hm-card"><table class="hm-tab"><tr><th>Ingrediente</th><th>%</th><th>kg/cab</th></tr>'
        f'{filas}<tr><td><b>Total</b></td><td></td><td><b>{_num(total, 2)}</b></td></tr></table>{nota}</div></div>',
        unsafe_allow_html=True,
    )


def _seccion_movimientos(lote_id: int) -> None:
    try:
        movs = db.listar_movimientos_lote(lote_id) or []
    except Exception:
        movs = []
    movs = [m for m in movs if m.get("tipo") != "conteo_drone"]
    if not movs:
        return
    lab = getattr(db, "MOVIMIENTO_LABELS", {})
    h = '<div class="hm"><div class="hm-lbl">MOVIMIENTOS DE HACIENDA</div><div class="hm-card">'
    for m in movs[-6:][::-1]:
        h += (f'<div class="hm-ag"><div class="d">{_dm(_fecha(m.get("fecha")))}</div>'
              f'<div>{_e(lab.get(m.get("tipo"), m.get("tipo")))} · {_e(m.get("cantidad"))} '
              f'{_e(m.get("detalles") or "")}</div></div>')
    st.markdown(h + "</div></div>", unsafe_allow_html=True)


def _seccion_uniformidad(d: Dict) -> None:
    """Solo si la última pesada trae el peso de cada animal."""
    pes = [p for p in d.get("pesadas") or [] if p.get("pesos_individuales")]
    if not pes:
        return
    p = pes[-1]
    v = sorted(float(x) for x in p["pesos_individuales"] if x)
    if len(v) < 5:
        return
    n = len(v)
    prom = sum(v) / n
    desv = (sum((x - prom) ** 2 for x in v) / (n - 1)) ** 0.5
    cv = desv / prom * 100

    def q(f):
        i = (n - 1) * f
        a = int(i)
        b = min(a + 1, n - 1)
        return v[a] + (v[b] - v[a]) * (i - a)

    atras = sum(1 for x in v if x < prom * 0.9)
    est = "verde" if cv < 10 else ("amarillo" if cv < 15 else "rojo")
    fg, bg = ESTADO_COLOR[est]
    st.markdown(
        f'<div class="hm"><div class="hm-lbl">UNIFORMIDAD · pesada del {_dm(_fecha(p.get("fecha")))}</div>'
        f'<div class="hm-card"><div class="hm-kpis">'
        f'<div class="hm-k"><div class="n">CV</div><div class="hm-big" style="color:{fg}">{_num(cv, 1)} %</div></div>'
        f'<div class="hm-k"><div class="n">10 % MÁS LIVIANO</div><div class="hm-big">{_num(q(.1), 0)}</div><div class="f">kg o menos</div></div>'
        f'<div class="hm-k"><div class="n">QUEDARON ATRÁS</div><div class="hm-big">{atras}</div><div class="f">10 % bajo el promedio</div></div>'
        f'</div><div class="hm-sub" style="margin-top:8px">{n} animales pesados de a uno. '
        f'Mediana {_num(q(.5), 0)} kg, el 10 % más pesado arriba de {_num(q(.9), 0)} kg.</div></div></div>',
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------
# Números clave y clima (ficha)
# ---------------------------------------------------------------------
def _tile(titulo: str, valor: str, sub: str = "") -> str:
    return (f'<div class="hm-card hm-tile"><div class="n">{_e(titulo)}</div>'
            f'<div class="hm-big">{valor}</div><div class="f">{sub}</div></div>')


def _kpis(lote: Dict, d: Dict) -> None:
    from . import stock_producto as sp
    tiles = []
    hoy = date.today()

    pes = d.get("pesadas") or []
    try:
        p_hoy = sp.estimar_peso_vivo_lote(lote, hoy.isoformat(), pesadas=pes)
    except Exception:
        p_hoy = None
    if p_hoy:
        tiles.append(_tile("PESO HOY", f'{_num(p_hoy, 0)}<span style="font-size:14px"> kg</span>',
                           "estimado desde la última pesada"))
    if len(pes) >= 2:
        f0, f1 = _fecha(pes[0]["fecha"]), _fecha(pes[-1]["fecha"])
        g = float(pes[-1]["peso_promedio_kg"]) - float(pes[0]["peso_promedio_kg"])
        tiles.append(_tile("GANADO", f'+{_num(g, 1)}<span style="font-size:14px"> kg</span>',
                           f"medido, {(f1 - f0).days} días" if f0 and f1 else "medido"))
    if d.get("adpv") is not None:
        tiles.append(_tile("GANANCIA DIARIA", _num(d["adpv"], 2),
                           "kg/día, última pesada"))

    # Consumo de mezcla estimado hoy (ración vigente × ajuste por peso)
    try:
        dietas = db.listar_dietas(lote["id"]) or []
        vig = [x for x in dietas if str(x.get("fecha") or "")[:10] <= hoy.isoformat()]
        if vig:
            dv = sorted(vig, key=lambda x: str(x.get("fecha")))[-1]
            comp = dv.get("composicion") or json.loads(dv.get("composicion_json") or "[]")
            tot = sum(float(c.get("kg_tal_cual") or 0) for c in comp)
            ci = (d.get("stock_min") or {}).get("consumo_info") or {}
            f = ci.get("factor_peso_vivo") or 1.0
            if tot:
                tiles.append(_tile("CONSUMO HOY", _num(tot * f, 1),
                                   "kg de ración/cab/día (estimado)"))
    except Exception:
        pass

    try:
        ent = db.listar_entregas_lote(lote["id"]) or []
    except Exception:
        ent = []
    if ent:
        kg = sum(float(e.get("kg_total") or 0) for e in ent)
        plata = sum(float(e.get("precio_total") or 0) for e in ent)
        sub = f"{len(ent)} entrega{'s' if len(ent) != 1 else ''}"
        if plata and d.get("animales"):
            sub += f" · ${_num(plata / d['animales'], 0)}/cab sin IVA"
        tiles.append(_tile("ALIMENTO HMS", f'{_num(kg, 0)}<span style="font-size:14px"> kg</span>', sub))

    st.markdown(f'<div class="hm"><div class="hm-kgrid">{"".join(tiles)}</div></div>',
                unsafe_allow_html=True)


@st.cache_data(ttl=3600, show_spinner=False)
def _clima_cliente(cliente_id: int) -> Dict:
    from . import dashboard
    c = db.obtener_cliente(cliente_id)
    return dashboard.obtener_clima_para_cliente(c) if c else {}


def _sev_corta(x: Dict) -> str:
    """Severidad real (THI ajustado por viento, frío sentido, lluvia y
    barro) en pocas palabras."""
    sev = str(x.get("severidad_real") or "")
    return sev if sev else "—"


def _cielo(n) -> str:
    if n is None:
        return "—"
    n = float(n)
    return "despejado" if n < 30 else ("parcial" if n < 70 else "cubierto")


@st.cache_data(ttl=3600, show_spinner=False)
def _clima_localidad(localidad: str) -> Dict:
    from . import dashboard
    try:
        return dashboard.obtener_clima_para_cliente(
            {"id": -1, "nombre": localidad, "localidad": localidad}) or {}
    except Exception as e:
        log.info("ui_movil: clima %s: %s", localidad, e)
        return {}


def clima_catrilo_header() -> str:
    """Clima de Catriló en una tira chica para el encabezado, a la derecha
    del logo: ahora y los 7 días (pasando el dedo o el mouse, el detalle)."""
    try:
        info = _clima_localidad("Catriló, La Pampa")
    except Exception:
        return ""
    if not info or info.get("estado") not in (None, "ok"):
        return ""
    dias = [x for x in info.get("pronostico_7d") or []
            if "HOY" in str(x.get("tramo")) or "Pronóstico" in str(x.get("tramo"))][:7]
    cel = ""
    for x in dias:
        f = _fecha(x.get("fecha"))
        nom = "Hoy" if "HOY" in str(x.get("tramo")) else (DIAS_SEM[f.weekday()] if f else "")
        sev = str(x.get("severidad_real") or "")
        alerta = sev[:1] in ("🔴", "🟠", "🟡") if sev else False
        borde = ("box-shadow:inset 0 -3px 0 " + ("#D92D20" if sev[:1] == "🔴" else
                 ("#F08C00" if sev[:1] == "🟠" else "#F2C200"))) if alerta else ""
        lluvia = x.get("precipitacion_mm")
        tip = (f'<span class="hm-tip"><b>{nom}{(" " + str(f.day) + "/" + str(f.month)) if f else ""}</b><br>'
               f'{_e(_sev_corta(x))}<br>Mín {_num(x.get("t_min"), 0)}° · máx {_num(x.get("t_max"), 0)}°<br>'
               f'Humedad {_num(x.get("hr_media"), 0)} %<br>Viento {_num(x.get("viento_max_kmh"), 0)} km/h<br>'
               f'Lluvia {(_num(lluvia, 0) + " mm") if lluvia else "no"}<br>'
               f'THI {_num(x.get("thi"), 0)}'
               + (f' · tarde {_num(x.get("thi_ajustado"), 0)}' if x.get("thi_ajustado") is not None else "")
               + '</span>')
        cel += (f'<div class="hm-hc" tabindex="0" style="{borde}">'
                f'<div class="hm-hc-d">{nom}</div><div>{_icono_dia(x)}</div>'
                f'<div><b>{_num(x.get("t_max"), 0)}°</b> <span class="hm-hc-m">{_num(x.get("t_min"), 0)}°</span></div>'
                f'{tip}</div>')
    ahora = ""
    if info.get("temp_c") is not None:
        ahora = (f'<div class="hm-ha"><div class="hm-hc-d">CATRILÓ AHORA</div>'
                 f'<div style="font-size:28px;font-weight:700;line-height:1.1">{_num(info["temp_c"], 0)}°</div>'
                 f'<div class="hm-hc-m">HR {_num(info.get("humedad_pct"), 0)} % · THI {_num(info.get("thi"), 0)}</div></div>')
    peor = str(info.get("severidad_real_max") or "")
    aviso = ""
    if peor and not peor.startswith("🟢"):
        fp = _fecha(info.get("severidad_real_max_fecha"))
        aviso = f'<div class="hm-hv">{_e(peor)}' + (f" el {_dm(fp)}" if fp else "") + "</div>"
    css = ('<style>.hm-hw{display:flex;flex-direction:column;align-items:flex-end;gap:3px;min-width:0}'
           '.hm-hr{display:flex;align-items:stretch;gap:4px}'
           '.hm-ha{padding:4px 12px 4px 0;margin-right:4px;border-right:1px solid #e1e6dd;text-align:right;white-space:nowrap;flex:none}'
           '.hm-hc{min-width:54px;padding:4px 5px 6px;border-radius:8px;background:rgba(127,140,130,.08);'
           'text-align:center;font-size:13.5px;line-height:1.4}'
           '.hm-hc-d{font-size:11px;letter-spacing:.04em;opacity:.65;font-weight:600}'
           '.hm-hc{position:relative;cursor:default}.hm-hc:hover,.hm-hc:focus{background:rgba(127,140,130,.18);outline:none}'
           '.hm-tip{display:none;position:absolute;top:calc(100% + 6px);right:0;z-index:50;min-width:170px;'
           'background:#1B3E27;color:#fff;border-radius:8px;padding:8px 10px;font-size:12.5px;line-height:1.5;'
           'text-align:left;box-shadow:0 6px 18px rgba(0,0,0,.18);white-space:nowrap}'
           '.hm-hc:hover .hm-tip,.hm-hc:focus .hm-tip{display:block}'
           '.hm-hc-m{opacity:.6;font-size:12px}.hm-hv{font-size:12.5px;opacity:.85}'
           '@media (max-width:760px){.hm-hw{align-items:stretch;width:100%}'
           '.hm-tip{position:fixed;top:auto;bottom:16px;left:16px;right:16px;min-width:0;white-space:normal;font-size:14px}'
           '.hm-hr{overflow-x:auto;-webkit-overflow-scrolling:touch}.hm-hc{min-width:48px;flex:none;font-size:12.5px}}</style>')
    return f'{css}<div class="hm-hw"><div class="hm-hr">{ahora}{cel}</div>{aviso}</div>'


def _clima_catrilo() -> None:
    """Clima de Catriló como referencia de la zona, en Inicio."""
    info = _clima_localidad("Catriló, La Pampa")
    if not info or info.get("estado") not in (None, "ok"):
        return
    dias = [x for x in info.get("pronostico_7d") or []
            if "HOY" in str(x.get("tramo")) or "Pronóstico" in str(x.get("tramo"))][:7]
    if not dias:
        return
    cab = celdas = ""
    for x in dias:
        f = _fecha(x.get("fecha"))
        nom = "Hoy" if "HOY" in str(x.get("tramo")) else (DIAS_SEM[f.weekday()] if f else "")
        sev = str(x.get("severidad_real") or "")
        punto = sev[:1] if sev and sev[:1] in "🔴🟠🟡" else ""
        cab += f"<th>{nom}</th>"
        celdas += (f'<td title="{_e(sev)} · HR {_num(x.get("hr_media"), 0)} % · '
                   f'viento {_num(x.get("viento_max_kmh"), 0)} km/h · THI {_num(x.get("thi"), 0)}">'
                   f'{_icono_dia(x)}<br><b>{_num(x.get("t_max"), 0)}°</b>'
                   f'<div class="hm-sub">{_num(x.get("t_min"), 0)}°</div>'
                   f'{punto}</td>')
    ahora = ""
    if info.get("temp_c") is not None:
        ahora = (f'<div class="hm-sub" style="margin-bottom:6px">Ahora <b>{_num(info["temp_c"], 0)}°</b>, '
                 f'humedad {_num(info.get("humedad_pct"), 0)} %, THI {_num(info.get("thi"), 0)} · '
                 f'{_e(info.get("thi_estado") or "")}</div>')
    peor = str(info.get("severidad_real_max") or "")
    aviso = ""
    if peor and not peor.startswith("🟢"):
        fp = _fecha(info.get("severidad_real_max_fecha"))
        aviso = (f'<div class="hm-nota">{_e(peor)}' + (f" el {_dm(fp)}" if fp else "")
                 + ". Mirá la ficha de cada lote para el detalle de su zona.</div>")
    st.markdown(
        f'<div class="hm"><div class="hm-lbl">CLIMA EN CATRILÓ · REFERENCIA DE LA ZONA</div>'
        f'<div class="hm-card">{ahora}<table class="hm-tab hm-climat"><tr>{cab}</tr><tr>{celdas}</tr></table>'
        f'{aviso}</div></div>', unsafe_allow_html=True)


def _seccion_clima(lote: Dict) -> None:
    """Clima del campo del cliente con todo lo que hace falta para
    estimar estrés por calor o frío: temperatura, humedad, viento,
    cielo, lluvia, THI y la severidad real para el bovino."""
    info = _clima_cliente(lote.get("cliente_id"))
    if not info or info.get("estado") not in (None, "ok"):
        return
    todos = info.get("pronostico_7d") or []
    i_hoy = next((i for i, x in enumerate(todos) if "HOY" in str(x.get("tramo"))), None)
    if i_hoy is None:
        dias = todos[-8:]
    else:
        dias = todos[max(0, i_hoy - 3): i_hoy + 8]   # 3 días atrás, hoy y 7 adelante
    if not dias and info.get("temp_c") is None:
        return
    filas = ""
    for x in dias:
        f = _fecha(x.get("fecha"))
        tr = str(x.get("tramo"))
        pasado = "Histórico" in tr
        nom = "Hoy" if "HOY" in tr else ((DIAS_SEM[f.weekday()] + f" {f.day}") if f else "")
        estilo = ' style="opacity:.55"' if pasado else (' style="font-weight:600"' if "HOY" in tr else "")
        lluvia = x.get("precipitacion_mm")
        filas += (
            f'<tr{estilo}><td>{nom}</td>'
            f'<td>{_num(x.get("t_min"), 0)}° / {_num(x.get("t_max"), 0)}°</td>'
            f'<td>{_num(x.get("hr_media"), 0)} %</td>'
            f'<td>{(_num(lluvia, 0) + " mm") if lluvia else "—"}</td>'
            f'<td>{_num(x.get("viento_max_kmh"), 0)} km/h</td>'
            f'<td>{_cielo(x.get("nubes_pct"))}</td>'
            f'<td>{_num(x.get("thi"), 0)}</td>'
            f'<td><b>{_num(x.get("thi_ajustado"), 0) if x.get("thi_ajustado") is not None else "—"}</b></td>'
            f'<td>{_e(_sev_corta(x))}</td></tr>')
    ahora = ""
    if info.get("temp_c") is not None:
        ahora = (f'<div class="hm-sub" style="margin-bottom:6px">Ahora: <b>{_num(info["temp_c"], 0)}°</b>, '
                 f'humedad {_num(info.get("humedad_pct"), 0)} %, THI <b>{_num(info.get("thi"), 0)}</b> '
                 f'({_e(info.get("thi_estado") or "")})</div>')
    alertas = []
    for al_l in info.get("alertas_lotes") or []:
        for al in al_l.get("alertas") or []:
            if str(al.get("severidad") or "").lower() in ("warning", "critica") and al.get("titulo") not in alertas:
                alertas.append(al.get("titulo"))
    al_html = ""
    try:
        from . import clima_reco as cr
        evs = cr.eventos_proximos(todos, date.today(), dias=6)
        if evs:
            ev = evs[0]
            ctrl = (_sql("SELECT * FROM controles_semanales WHERE lote_id = ? "
                         "ORDER BY COALESCE(fecha_respuesta, fecha_envio) DESC LIMIT 1",
                         (lote["id"],)) or [None])[0]
            dd = datos_lote(lote)
            recos = cr.recomendaciones(ev, lote.get("tipo_comedero_concentrado") or "", lote, ctrl,
                                       dd.get("animales"), dd.get("peso_hoy") or dd.get("peso"),
                                       _ms_animal(dd))
            nombre = ("Frío" if ev["tipo"] == "frio" else "Calor") + (" crítico" if ev["nivel"] == "critico" else " moderado")
            if ev.get("notas"):
                nombre += f" ({'; '.join(ev['notas'])})"
            otros = ", ".join(_dm(e["fecha"]) for e in evs[1:])
            al_html = (f'<div class="hm-nota"><b>{nombre} el {_dm(ev["fecha"])}</b>'
                       + (f" (también {otros})" if otros else "")
                       + f": {_e(ev['motivo'])}.<br><b>Qué hacer:</b><ul style='margin:4px 0 0 18px;padding:0'>"
                       + "".join(f"<li>{_e(r)}</li>" for r in recos) + "</ul></div>")
    except Exception as e:
        log.info("ui_movil: reco clima: %s", e)
    agua_html = ""
    try:
        from . import clima_reco as cr
        dd = datos_lote(lote)
        peso = dd.get("peso_hoy") or dd.get("peso")
        futuros = [x for x in dias if "Histórico" not in str(x.get("tramo"))]
        hoy_x = next((x for x in futuros if "HOY" in str(x.get("tramo"))), futuros[0] if futuros else None)
        peor = max(futuros, key=lambda x: x.get("t_max") or -99) if futuros else None
        ms = _ms_animal(dd)
        ag_h = cr.agua_lote(dd.get("animales"), peso, (hoy_x or {}).get("t_max"), lote.get("reserva_agua_l"), ms, hoy_x)
        ag_p = cr.agua_lote(dd.get("animales"), peso, (peor or {}).get("t_max"), lote.get("reserva_agua_l"), ms, peor)
        if ag_h and ag_p:
            fp = _fecha(peor.get("fecha"))
            agua_html = (f'<div class="hm-sub" style="margin:6px 0">💧 Agua: hoy unos <b>{_num(ag_h["l_dia"], 0)} L</b> '
                         f'para el lote ({_num(ag_h["l_animal"], 0)} L por animal con {_num(hoy_x.get("t_max"), 0)}°); '
                         f'el día más caluroso ({_dm(fp)}, {_num(peor.get("t_max"), 0)}°) unos '
                         f'<b>{_num(ag_p["l_dia"], 0)} L</b>.'
                         + (f' La reserva de {_num(lote.get("reserva_agua_l"), 0)} L alcanza para '
                            f'{_num(ag_p["horas_reserva"], 0)} horas ese día.' if ag_p.get("horas_reserva") else
                            ' Sin dato de tanque de reserva (cargalo en Corral).')
                         + _txt_caudal(lote, dd, ag_p)
                         + f' <span style="opacity:.75">Cálculo: {ag_h["metodo"]}'
                         + ('' if ms else ' (la ración no tiene materia seca cargada; con ese dato se usa Ahlberg 2018)')
                         + '. Para dimensionar bomba y tanque, el INTA pide 70 L por animal por día en verano.</span>'
                         + '</div>')
    except Exception as e:
        log.info("ui_movil: agua: %s", e)
    st.markdown(
        f'<div class="hm"><div class="hm-lbl">CLIMA DEL CAMPO · {_e(info.get("localidad") or "")}</div>'
        f'<div class="hm-card">{ahora}{agua_html}<div style="overflow-x:auto"><table class="hm-tab">'
        f'<tr><th>Día</th><th>Mín / máx</th><th>Humedad</th><th>Lluvia</th><th>Viento</th>'
        f'<th>Cielo</th><th>THI máx.</th><th>THI tarde</th><th>Estrés real</th></tr>{filas}</table></div>{al_html}'
        f'<div class="hm-sub" style="margin-top:6px">THI máx. = índice de temperatura y humedad con la máxima del día. '
        f'THI tarde = el peor entre las 14 y las 17 h, corregido por viento (alivia) y sol (agrava) según Mader y otros 2006. '
        f'Con ese se clasifica el calor: 75 alerta, 79 peligro, 84 emergencia (guía de Missouri/Nebraska para ganado en confinamiento). '
        f'El frío usa una aproximación propia (viento y mojado) todavía sin fuente publicada. '
        f'Los 3 primeros días (más claros) son los que ya pasaron: el calor acumulado pesa.</div>'
        f'</div></div>',
        unsafe_allow_html=True,
    )


def _icono_dia(x: Dict) -> str:
    lluvia = float(x.get("precipitacion_mm") or 0)
    tmax = x.get("t_max")
    thi = str(x.get("severidad_real") or "")
    if lluvia >= 10:
        return "🌧"
    if lluvia >= 1:
        return "🌦"
    if tmax is not None and float(tmax) >= 32 or "calor" in thi.lower():
        return "🔥"
    if tmax is not None and float(tmax) <= 8:
        return "🥶"
    return "☀"


def _clima_semana(datos: List[Dict]) -> None:
    """Pronóstico de 7 días: una línea por localidad con lote activo."""
    vistos = set()
    filas = []
    cab = None
    for d in datos:
        info = _clima_cliente(d["lote"].get("cliente_id"))
        if not info or info.get("estado") not in (None, "ok"):
            continue
        loc = (info.get("localidad") or d.get("localidad") or "").split(",")[0]
        if loc in vistos:
            continue
        vistos.add(loc)
        dias = [x for x in info.get("pronostico_7d") or []
                if "HOY" in str(x.get("tramo")) or "Pronóstico" in str(x.get("tramo"))][:7]
        if not dias:
            continue
        if cab is None:
            cab = "".join(
                f'<th>{"Hoy" if "HOY" in str(x.get("tramo")) else (DIAS_SEM[_fecha(x.get("fecha")).weekday()] if _fecha(x.get("fecha")) else "")}</th>'
                for x in dias)
        celdas = "".join(
            f'<td title="mín {_num(x.get("t_min"), 0)}°, {_num(x.get("precipitacion_mm"), 0)} mm">'
            f'{_icono_dia(x)}<br><b>{_num(x.get("t_max"), 0)}°</b></td>' for x in dias)
        filas.append(f'<tr><td><b>{_e(loc)}</b></td>{celdas}</tr>')
    if filas:
        tabla = (f'<table class="hm-tab hm-climat"><tr><th></th>{cab}</tr>'
                 f'{"".join(filas[:6])}</table>')
        extra = (f'<div class="hm-sub">… y {len(filas) - 6} localidades más</div>'
                 if len(filas) > 6 else "")
        st.markdown(f'<div class="hm"><div class="hm-lbl">CLIMA DE LA SEMANA · máxima</div>'
                    f'<div class="hm-card">{tabla}{extra}</div></div>', unsafe_allow_html=True)


def _urgencia(d: Dict) -> tuple:
    """Orden de la tabla: rojo, sin comida en 3 días, amarillo, sin
    comida en 10 días, sin control, el resto por días de alimento."""
    dias = (d.get("stock_min") or {}).get("dias_restantes")
    dias = 9999 if dias is None else dias
    sem = d.get("sem")
    if sem == "rojo":
        g = 0
    elif dias <= 3:
        g = 1
    elif sem == "amarillo":
        g = 2
    elif dias <= 10:
        g = 3
    else:
        g = 4
    return (g, dias)


def _hace(f: Optional[date], hoy: date) -> str:
    if not f:
        return "nunca"
    n = (hoy - f).days
    return "hoy" if n <= 0 else ("ayer" if n == 1 else f"hace {n} días")


def _tabla_lotes(datos: List[Dict], on_abrir_lote, kp: str) -> None:
    """Una fila por lote con lo necesario para el seguimiento, ordenada
    por urgencia. Tocar la fila abre la ficha."""
    import pandas as pd
    hoy = date.today()
    ico = {"verde": "🟢", "amarillo": "🟡", "rojo": "🔴", "sin": "⚪"}
    filas = []
    for d in datos:
        sm = d.get("stock_min") or {}
        dias = sm.get("dias_restantes")
        if d.get("adpv") is not None:
            eng = f"{_num(d['adpv'], 2)}" + (f" / {_num(d['adpv_esp'], 2)}" if d.get("adpv_esp") else "")
            if d.get("engorde_pct") is not None:
                p = d["engorde_pct"]
                eng += "  ✓" if p >= 95 else ("  ↓" if p < 85 else "")
        else:
            eng = "sin 2 pesadas"
        if d.get("consumo_pct") is not None:
            cp = d["consumo_pct"]
            cons = f"{_num(cp, 0)} %" + ("  ↑ más" if cp > 115 else ("  ↓ menos" if cp < 85 else "  ok"))
        else:
            cons = "falta dato"
        if d.get("salida"):
            sal = f"{_dm(d['salida'])} ({_num(d['peso_venta'], 0)} kg)"
        else:
            sal = "cargar peso de venta" if not d.get("peso_venta") else "falta pesada"
        filas.append({
            "Cliente": d["cliente"],
            "Corral": f"{ico.get(d.get('sem'), '⚪')} {d.get('sem_txt') or ''}",
            "Alimento (días)": int(round(dias)) if dias is not None else None,
            "Pedir el": _dm(d["pedir"]) if d.get("pedir") else "—",
            "Ración": d.get("racion_txt") or "—",
            "Engorde kg/día (real / esperado)": eng,
            "Consumo vs ración": cons,
            "Salida estimada": sal,
            "Último contacto": _hace(d.get("ult_contacto"), hoy),
            "Muertes": (f"{d['muertes']} ({_num(d['muertes_pct'], 1)} %)"
                        if d.get("muertes_pct") is not None else str(d.get("muertes") or 0)),
            "Animales": d.get("animales"),
            "Lote": d["lote"].get("identificador") or "",
        })
    df = pd.DataFrame(filas)
    st.caption("Arriba, lo más urgente: corral en rojo, sin comida en 3 días, en amarillo, "
               "sin comida en 10 días. Tocá una fila para abrir la ficha. "
               "Engorde ✓ viene bien, ↓ se está quedando. Consumo: lo que realmente comen "
               "comparado con la ración, calculado con las entregas.")
    ev = st.dataframe(
        df, hide_index=True, width="stretch", on_select="rerun",
        selection_mode="single-row", key=f"{kp}_tabla_lotes",
        column_config={
            "Alimento (días)": st.column_config.ProgressColumn(
                "Alimento (días)", min_value=0, max_value=30, format="%d"),
        },
    )
    try:
        sel = ev.selection.rows
    except Exception:
        sel = []
    if sel:
        on_abrir_lote(datos[sel[0]]["id"])
