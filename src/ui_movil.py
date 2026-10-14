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
    try:
        import streamlit.components.v1 as components
        components.html(
            "<script>/*" + clave + "*/(function(){var d=window.parent.document;"
            "['[data-testid=\"stMain\"]','[data-testid=\"stAppViewContainer\"]','section.main']"
            ".forEach(function(q){var e=d.querySelector(q);if(e){e.scrollTo(0,0);}});"
            "window.parent.scrollTo(0,0);})();</script>",
            height=0,
        )
    except Exception:
        pass


def _dia_corto(d: date) -> str:
    return f"{DIAS_SEM[d.weekday()]} {d.day}"


def _sql(query: str, params: tuple = ()) -> List[Dict]:
    """Consulta directa para las tablas nuevas (plan, controles,
    informes). Si la tabla no existe devuelve []."""
    try:
        with db.get_conn() as conn:
            return [dict(r) for r in conn.execute(query, params).fetchall()]
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
    return d


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
.hm-ag .d {{ width: 70px; font-weight: 700; color: var(--hm-acc); flex-shrink: 0; }}
.hm-kgrid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin: 14px 0 4px; }}
.hm-tile {{ margin-bottom: 0; padding: 12px 14px; }}
.hm-tile .n {{ font-size: 11px; color: var(--hm-sub); letter-spacing: .6px; }}
.hm-tile .f {{ font-size: 11px; color: var(--hm-sub); margin-top: 2px; }}
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
        if ctrl and f_ctrl and (hoy - f_ctrl).days > 7:
            tareas.append((
                "var(--hm-chip)", "var(--hm-sub)", "✓",
                f"{d['cliente']} · control semanal",
                f"El último control es del {_dm(f_ctrl)}.",
            ))

    # Clima: solo clientes con lote activo (una consulta por hora).
    try:
        ids = tuple(sorted({d["lote"].get("cliente_id") for d in datos}))
        for cli, al in _alertas_clima(ids):
            tareas.append((
                "#E3ECF7", "#2C5E9E", al.get("icono") or "☁",
                f"{cli} · {al.get('titulo') or 'alerta de clima'}",
                f"{al.get('cuando') or ''}. "
                + ("; ".join((al.get("acciones") or [])[:2]) if al.get("acciones") else ""),
            ))
    except Exception as e:
        log.info("ui_movil: clima: %s", e)

    n_anim = sum(d.get("animales") or 0 for d in datos)
    n_cli = len({d["lote"].get("cliente_id") for d in datos})
    resto = (f' · <b>{len(tareas)} cosa{"s" if len(tareas) != 1 else ""} para mirar</b>'
             if tareas else " · nada urgente hoy")
    st.markdown(
        f'<div class="hm"><div class="hm-top">'
        f'<div class="t">{_saludo()}, Mauri</div>'
        f'<div class="s"><b>{n_anim} animales</b> en {len(datos)} lote{"s" if len(datos) != 1 else ""} '
        f'de {n_cli} cliente{"s" if n_cli != 1 else ""}{resto}.</div>'
        f'</div></div>',
        unsafe_allow_html=True,
    )

    if st.button("➕ Cargar encierre nuevo", key=f"{kp}_nuevo_enc", type="primary",
                 width="stretch"):
        from . import ui_gestion as _g
        _g.dialog_encierre()

    pedidos = _pedidos_proximos(datos)
    try:
        _resumen_inicio(datos, pedidos, hoy)
    except Exception as e:
        log.info("ui_movil: resumen: %s", e)

    col_a, col_b = st.columns([1.15, 1], gap="medium")
    with col_a:
        if tareas:
            h = '<div class="hm"><div class="hm-lbl">PARA HOY</div>'
            for bg, fg, ico, tit, sub in tareas:
                h += (
                    f'<div class="hm-card"><div class="hm-row">'
                    f'<div class="hm-ico" style="background:{bg};color:{fg}">{_e(ico)}</div>'
                    f'<div><div class="hm-h">{_e(tit)}</div>'
                    f'<div class="hm-sub">{_e(sub)}</div></div></div></div>'
                )
            st.markdown(h + "</div>", unsafe_allow_html=True)

        st.markdown('<div class="hm"><div class="hm-lbl">LOTES ACTIVOS</div></div>',
                    unsafe_allow_html=True)
        if not datos:
            st.info("No hay lotes activos. Cargá un encierre con el botón de arriba.")
        for d in datos:
            _tarjeta_lote(d)
            if st.button("Ver ficha", key=f"{kp}_ver_{d['id']}", width="stretch"):
                on_abrir_lote(d["id"])

    with col_b:
        if pedidos:
            h = ('<div class="hm"><div class="hm-lbl">PRÓXIMOS PEDIDOS DE ALIMENTO</div><div class="hm-card">'
                 '<table class="hm-tab"><tr><th>Cliente</th><th>Producto</th><th>Se termina</th>'
                 '<th>Próx. 30 días</th></tr>')
            for p in pedidos:
                plata = f'<div class="hm-sub">${_num(p["plata30"], 0)}</div>' if p.get("plata30") else ""
                h += (f'<tr><td>{_e(p["cliente"])}</td><td>{_e(p["producto"])}</td>'
                      f'<td>{_dm(p["fecha"])}</td><td>{_num(p["kg30"], 0)} kg{plata}</td></tr>')
            h += ('</table><div class="hm-sub" style="margin-top:6px">Lo que va a consumir cada lote en '
                  'los próximos 30 días con la ración vigente (estimado). Plata a último precio, sin IVA.'
                  '</div></div></div>')
            st.markdown(h, unsafe_allow_html=True)

        ag = []
        for d in datos:
            sm = d.get("stock_min")
            fa = _fecha((sm or {}).get("fecha_agotamiento"))
            if fa:
                ag.append((fa - timedelta(days=2), f"Pedido de {sm['producto']} · {d['cliente']}"))
            if d.get("fecha_peso"):
                ag.append((d["fecha_peso"] + timedelta(days=15), f"Seguimiento de 15 días · {d['cliente']}"))
            if d.get("proxima_pesada"):
                ag.append((d["proxima_pesada"], f"Pesada mensual · {d['cliente']}"))
        ag = sorted([a for a in ag if a[0] >= hoy - timedelta(days=1)])[:8]
        if ag:
            h = '<div class="hm"><div class="hm-lbl">AGENDA</div><div class="hm-card">'
            for f, t in ag:
                h += f'<div class="hm-ag"><div class="d">{_dia_corto(f)}/{f.month}</div><div>{_e(t)}</div></div>'
            st.markdown(h + "</div></div>", unsafe_allow_html=True)


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


def _resumen_inicio(datos: List[Dict], pedidos: List[Dict], hoy: date) -> None:
    tiles = []
    num = den = 0.0
    kg_carne = 0.0
    for d in datos:
        if d.get("adpv") is not None and d.get("animales"):
            num += d["adpv"] * d["animales"]
            den += d["animales"]
        pes = d.get("pesadas") or []
        if len(pes) >= 2 and d.get("animales"):
            kg_carne += (float(pes[-1]["peso_promedio_kg"])
                         - float(pes[0]["peso_promedio_kg"])) * d["animales"]
    if den:
        tiles.append(_tile("GANANCIA DIARIA", _num(num / den, 2),
                           "kg/día promedio, medida en balanza"))
    if kg_carne:
        tiles.append(_tile("KG DE CARNE GANADOS", _num(kg_carne, 0),
                           "entre pesadas, todos los lotes"))
    if pedidos:
        kg_campo = sum(float(p.get("kg_hoy") or 0) for p in pedidos)
        prim = pedidos[0]
        tiles.append(_tile("ALIMENTO EN EL CAMPO",
                           f'{_num(kg_campo, 0)}<span style="font-size:14px"> kg</span>',
                           f"primero se termina {prim['cliente']}, el {_dm(prim['fecha'])}"))
        kg30 = sum(p["kg30"] for p in pedidos)
        plata = sum(p["plata30"] or 0 for p in pedidos)
        tiles.append(_tile("VENTA PRÓXIMOS 30 DÍAS",
                           f'{_num(kg30, 0)}<span style="font-size:14px"> kg</span>',
                           (f"≈ ${_num(plata, 0)} sin IVA, " if plata else "") + "estimado por consumo"))
    ini_mes = hoy.replace(day=1).isoformat()
    filas = _sql("SELECT kg_total, precio_total FROM entregas_producto WHERE fecha_entrega >= ?",
                 (ini_mes,))
    kg_m = sum(float(f.get("kg_total") or 0) for f in filas)
    pl_m = sum(float(f.get("precio_total") or 0) for f in filas)
    tiles.append(_tile(f"ENTREGADO EN {MESES[hoy.month - 1].upper()}",
                       f'{_num(kg_m, 0)}<span style="font-size:14px"> kg</span>',
                       (f"${_num(pl_m, 0)} sin IVA" if pl_m else
                        ("todavía no hubo entregas" if not filas else f"{len(filas)} entregas"))))
    st.markdown(f'<div class="hm"><div class="hm-kgrid">{"".join(tiles)}</div></div>',
                unsafe_allow_html=True)

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
        try:
            _seccion_clima(lote)
        except Exception as e:
            st.caption(f"No se pudo mostrar el clima: {e}")
        # Control semanal
        try:
            ctrl = d.get("control")
            areas = [("Sanidad", "semaforo_sanidad"), ("Consumo", "semaforo_consumo"),
                     ("Ambiente", "semaforo_ambiente"), ("Alimento", "semaforo_alimento")]
            sem = ""
            for nom, campo in areas:
                est = ((ctrl or {}).get(campo) or "gris").lower()
                fg, bg = ESTADO_COLOR.get(est, ESTADO_COLOR["gris"])
                sem += f'<div><div class="c" style="background:{bg};border:2px solid {fg}"></div><div class="hm-sub">{nom}</div></div>'
            f_c = _fecha((ctrl or {}).get("fecha_respuesta") or (ctrl or {}).get("fecha_envio"))
            cab = f"respondido el {_dm(f_c)}" if ctrl else "pendiente"
            txt = (_e(ctrl.get("comentarios")) if ctrl and ctrl.get("comentarios")
                   else "Cuando lleguen las respuestas del productor se pintan en verde, amarillo o rojo.")
            st.markdown(
                f'<div class="hm"><div class="hm-lbl">ÚLTIMO CONTROL SEMANAL · {cab}</div>'
                f'<div class="hm-card"><div class="hm-sem">{sem}</div>'
                f'<div class="hm-nota">{txt}</div></div></div>',
                unsafe_allow_html=True,
            )
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
                      f'<div>{_e(i.get("tipo")).replace("_", " ")} · {_e(i.get("estado"))}</div></div>')
        else:
            pp = d.get("proxima_pesada")
            h += f'<div class="hm-sub">Todavía no hay. El primero sale después de la pesada{" del " + _dm(pp) if pp else ""}.</div>'
        st.markdown(h + "</div></div>", unsafe_allow_html=True)


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


def _seccion_clima(lote: Dict) -> None:
    info = _clima_cliente(lote.get("cliente_id"))
    if not info or info.get("estado") not in (None, "ok"):
        return
    pron = [x for x in info.get("pronostico_7d") or []
            if "Pronóstico" in str(x.get("tramo")) or "HOY" in str(x.get("tramo"))][:6]
    if not pron and info.get("temp_c") is None:
        return
    filas = ""
    for x in pron:
        f = _fecha(x.get("fecha"))
        dia = "Hoy" if "HOY" in str(x.get("tramo")) else (_dia_corto(f) if f else "")
        lluvia = x.get("precipitacion_mm")
        filas += (f'<tr><td>{dia}</td><td>{_num(x.get("t_min"), 0)}° / {_num(x.get("t_max"), 0)}°</td>'
                  f'<td>{_num(lluvia, 0) + " mm" if lluvia else "—"}</td>'
                  f'<td>{_num(x.get("viento_max_kmh"), 0)} km/h</td>'
                  f'<td>{_e(x.get("thi_estado") or "")}</td></tr>')
    alertas = []
    for al_l in info.get("alertas_lotes") or []:
        for al in al_l.get("alertas") or []:
            if str(al.get("severidad") or "").lower() in ("warning", "critica") and al.get("titulo") not in alertas:
                alertas.append(al.get("titulo"))
    ahora = ""
    if info.get("temp_c") is not None:
        ahora = (f'<div class="hm-sub" style="margin-bottom:6px">Ahora: <b>{_num(info["temp_c"], 0)}°</b>, '
                 f'humedad {_num(info.get("humedad_pct"), 0)} %, {_e(info.get("thi_estado") or "")}</div>')
    al_html = "".join(f'<div class="hm-nota">⚠ {_e(a)}</div>' for a in alertas[:3])
    st.markdown(
        f'<div class="hm"><div class="hm-lbl">CLIMA · {_e(info.get("localidad") or "")}</div>'
        f'<div class="hm-card">{ahora}<table class="hm-tab"><tr><th>Día</th><th>Mín / máx</th>'
        f'<th>Lluvia</th><th>Viento</th><th>Estrés</th></tr>{filas}</table>{al_html}</div></div>',
        unsafe_allow_html=True,
    )
