"""Pestañas Lotes y Clientes con el diseño nuevo, y las cargas de campo.

Pensado para el celular: tarjetas, botones grandes y formularios cortos
que se abren en una ventana (pesada, entrega, movimiento, encierre,
cierre de lote, cliente). La gestión completa anterior sigue en la
pestaña "Más".
"""
from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional

import streamlit as st

from . import database as db
from . import ui_movil as um

CATEGORIAS = ["novillo", "vaquillona", "ternero", "ternera", "toro", "vaca"]
COMEDEROS = {
    "Silo comedero (autoconsumo)": "silocomedero",
    "Comedero lineal": "lineal",
    "Otro": "otro",
}
METODOS_PESADA = {
    "Balanza": "balanza",
    "Estimación visual / cinta": "estimacion",
}
MOVIMIENTOS = {
    "Muerte": "muerte",
    "Venta (gordo / descarte)": "venta",
    "Ingreso (compra)": "ingreso",
}


def _iso(d: date) -> str:
    return d.strftime("%Y-%m-%d")


def _refrescar():
    try:
        st.cache_data.clear()
    except Exception:
        pass
    st.rerun()


def _nav(kp: str) -> Dict:
    """Estado de navegación de cada pestaña (lote o cliente abierto)."""
    k = f"{kp}_nav"
    if k not in st.session_state:
        st.session_state[k] = {}
    return st.session_state[k]


# =====================================================================
# Formularios (ventanas)
# =====================================================================
@st.dialog("Cargar pesada")
def dialog_pesada(lote_id: int):
    lote = db.obtener_lote(lote_id) or {}
    try:
        cant_v = int(db.cantidad_vigente_lote(lote_id) or 0)
    except Exception:
        cant_v = int(lote.get("cantidad_inicial") or 0)
    with st.form("f_pesada"):
        f = st.date_input("Fecha", value=date.today(), format="DD/MM/YYYY")
        met = st.selectbox("Cómo se pesó", list(METODOS_PESADA))
        cant = st.number_input("Animales pesados", min_value=1, value=max(cant_v, 1), step=1)
        modo = st.radio("Dato que tenés", ["Peso promedio", "Peso total"], horizontal=True)
        valor = st.number_input("kg", min_value=0.0, step=1.0, format="%.1f")
        notas = st.text_area("Notas (grupos, animales a revisar…)", height=80)
        ok = st.form_submit_button("Guardar pesada", type="primary", width="stretch")
    if ok:
        if valor <= 0:
            st.error("Falta el peso.")
            return
        prom = valor if modo == "Peso promedio" else valor / cant
        total = valor if modo == "Peso total" else valor * cant
        db.guardar_pesada(lote_id, _iso(f), METODOS_PESADA[met], int(cant),
                          round(prom, 2), round(total, 1), None, notas=notas)
        st.success(f"Guardada: {um._num(prom)} kg promedio.")
        _refrescar()


@st.dialog("Cargar entrega de alimento")
def dialog_entrega(lote_id: int):
    lote = db.obtener_lote(lote_id) or {}
    try:
        from .stock_producto import listar_productos_lote
        prods = listar_productos_lote(lote_id) or []
    except Exception:
        prods = []
    prods = [p for p in prods if p] + ["Otro producto"]
    st.caption("Lo que facturás o remitís en la gestión pasa solo, todas las mañanas. "
               "Cargalo acá solo si la entrega todavía no está en la gestión: cuando "
               "aparezca la factura, se une con esta carga y no se cuenta dos veces.")
    with st.form("f_entrega"):
        f = st.date_input("Fecha de entrega", value=date.today(), format="DD/MM/YYYY")
        prod = st.selectbox("Producto", prods)
        otro = st.text_input("Nombre (si elegiste otro)")
        formato = st.radio("Formato", ["Bolsas", "Granel"], horizontal=True)
        c1, c2 = st.columns(2)
        bolsas = c1.number_input("Bolsas", min_value=0, step=1)
        kg_bolsa = c2.number_input("kg por bolsa", min_value=0.0, value=30.0, step=1.0)
        kg_granel = st.number_input("kg totales (si es granel)", min_value=0.0, step=10.0)
        notas = st.text_input("Notas (n.º de factura, remito…)")
        ok = st.form_submit_button("Guardar entrega", type="primary", width="stretch")
    if ok:
        nombre = otro.strip() if prod == "Otro producto" else prod
        if not nombre:
            st.error("Falta el producto.")
            return
        if formato == "Bolsas":
            kg = bolsas * kg_bolsa
            fmt = "bolsa"
        else:
            kg = kg_granel
            fmt = "granel"
        if kg <= 0:
            st.error("Falta la cantidad.")
            return
        db.crear_entrega(lote["cliente_id"], nombre, float(kg), _iso(f),
                         lote_id=lote_id, formato=fmt,
                         cantidad_bolsas=float(bolsas) if fmt == "bolsa" else 0,
                         kg_por_bolsa=float(kg_bolsa), notas=notas)
        st.success(f"Guardada: {um._num(kg, 0)} kg de {nombre}.")
        _refrescar()


@st.dialog("Movimiento de hacienda")
def dialog_movimiento(lote_id: int):
    with st.form("f_mov"):
        tipo = st.selectbox("Qué pasó", list(MOVIMIENTOS))
        f = st.date_input("Fecha", value=date.today(), format="DD/MM/YYYY")
        cant = st.number_input("Cantidad de animales", min_value=1, value=1, step=1)
        kg = st.number_input("kg por animal (opcional)", min_value=0.0, step=1.0)
        det = st.text_input("Detalle (causa, caravana, destino…)")
        ok = st.form_submit_button("Guardar", type="primary", width="stretch")
    if ok:
        db.crear_movimiento_lote(lote_id, _iso(f), MOVIMIENTOS[tipo], int(cant),
                                 kg_promedio_animal=kg or None, detalles=det)
        st.success("Guardado.")
        _refrescar()


@st.dialog("Cerrar lote")
def dialog_cerrar(lote_id: int):
    lote = db.obtener_lote(lote_id) or {}
    try:
        cant_v = int(db.cantidad_vigente_lote(lote_id) or 0)
    except Exception:
        cant_v = int(lote.get("cantidad_inicial") or 0)
    st.caption("El lote deja de aparecer en Inicio y deja de generar avisos. "
               "Sus datos quedan guardados.")
    with st.form("f_cerrar"):
        f = st.date_input("Fecha de salida", value=date.today(), format="DD/MM/YYYY")
        peso = st.number_input("Peso de salida promedio (si se pesó)", min_value=0.0, step=1.0)
        cant = st.number_input("Animales que salieron", min_value=0, value=cant_v, step=1)
        notas = st.text_input("Notas (destino, precio, rendimiento…)")
        conf = st.checkbox("Confirmo que el lote terminó")
        ok = st.form_submit_button("Cerrar lote", type="primary", width="stretch")
    if ok:
        if not conf:
            st.error("Marcá la confirmación.")
            return
        if peso > 0 and cant > 0:
            db.guardar_pesada(lote_id, _iso(f), "balanza", int(cant), float(peso),
                              float(peso) * cant, None, notas="Pesada de salida. " + notas)
        campos = {"estado": "cerrado", "fecha_salida": _iso(f)}
        if notas:
            campos["notas"] = ((lote.get("notas") or "") + f"\nSalida {_iso(f)}: {notas}").strip()
        db.actualizar_lote(lote_id, **campos)
        st.success("Lote cerrado.")
        _refrescar()


@st.dialog("Cargar encierre nuevo")
def dialog_encierre(cliente_id: Optional[int] = None):
    clientes = [c for c in db.listar_clientes() if (c.get("estado") or "activo") != "baja"]
    nombres = ["➕ Cliente nuevo"] + [c["nombre"] for c in clientes]
    idx = 0
    if cliente_id:
        for i, c in enumerate(clientes):
            if c["id"] == cliente_id:
                idx = i + 1
    with st.form("f_encierre"):
        cli = st.selectbox("Cliente", nombres, index=idx)
        c1, c2 = st.columns(2)
        nuevo_nom = c1.text_input("Nombre (si es nuevo)")
        nuevo_loc = c2.text_input("Localidad (si es nuevo)")
        ident = st.text_input("Nombre del lote", placeholder="Ej.: Novillos terminación oct-26")
        cat = st.selectbox("Categoría", CATEGORIAS)
        c3, c4 = st.columns(2)
        f = c3.date_input("Fecha de encierre", value=date.today(), format="DD/MM/YYYY")
        cant = c4.number_input("Animales", min_value=1, value=30, step=1)
        peso = st.number_input("Peso promedio al entrar (kg, si se pesó)", min_value=0.0, step=1.0)
        com = st.selectbox("Comedero", list(COMEDEROS))
        c5, c6 = st.columns(2)
        p_venta = c5.number_input("Peso de venta buscado (kg)", min_value=0.0, step=5.0,
                                  help="Para estimar la fecha de salida. Dejalo en 0 si no lo sabés.")
        g_esp = c6.number_input("Ganancia esperada (kg/día)", min_value=0.0, step=0.05, format="%.2f",
                                help="Si lo dejás en 0 se usa la de la categoría.")
        notas = st.text_area("Notas (orígenes, sanidad, ración de arranque…)", height=80)
        ok = st.form_submit_button("Guardar encierre", type="primary", width="stretch")
    if ok:
        if cli == "➕ Cliente nuevo":
            if not nuevo_nom.strip():
                st.error("Falta el nombre del cliente nuevo.")
                return
            cid = db.crear_cliente(nuevo_nom.strip(), localidad=nuevo_loc.strip())
        else:
            cid = next(c["id"] for c in clientes if c["nombre"] == cli)
        if not ident.strip():
            ident = f"{cat.capitalize()} {f.strftime('%d/%m/%Y')}"
        lid = db.crear_lote(cid, ident.strip(), categoria=cat, fecha_ingreso=_iso(f),
                            cantidad_inicial=int(cant), peso_ingreso_kg=float(peso),
                            notas=notas)
        try:
            extra = {"tipo_comedero_concentrado": COMEDEROS[com]}
            if p_venta > 0:
                extra["objetivo_peso_kg"] = float(p_venta)
            if g_esp > 0:
                extra["adpv_objetivo_kg"] = float(g_esp)
            db.actualizar_lote(lid, **extra)
        except Exception:
            pass
        if peso > 0:
            db.guardar_pesada(lid, _iso(f), "balanza", int(cant), float(peso),
                              float(peso) * cant, None, notas="Pesada inicial, inicio del encierre.")
        st.success("Encierre guardado.")
        _refrescar()


@st.dialog("Objetivos del lote")
def dialog_objetivos(lote_id: int):
    l = db.obtener_lote(lote_id) or {}
    st.caption("Con esto se calcula si el lote viene engordando lo esperado y cuándo sale.")
    with st.form("f_objetivos"):
        p_venta = st.number_input("Peso de venta buscado (kg)", min_value=0.0, step=5.0,
                                  value=float(l.get("objetivo_peso_kg") or 0))
        g_esp = st.number_input("Ganancia esperada (kg/día)", min_value=0.0, step=0.05, format="%.2f",
                                value=float(l.get("adpv_objetivo_kg") or 0),
                                help="En 0 se usa la ganancia típica de la categoría.")
        st.caption("Para el frame (BIF): edad y altura a la grupa promedio de 5 a 10 animales, "
                   "medida sobre los huesos de la cadera, en el brete y sobre piso plano.")
        c1, c2 = st.columns(2)
        edad = c1.number_input("Edad (meses)", min_value=0.0, step=1.0,
                               value=float(l.get("edad_meses") or 0))
        alt = c2.number_input("Altura a la grupa (cm)", min_value=0.0, step=1.0,
                              value=float(l.get("altura_grupa_cm") or 0))
        ok = st.form_submit_button("Guardar", type="primary", width="stretch")
    if ok:
        db.actualizar_lote(lote_id, objetivo_peso_kg=(float(p_venta) or None),
                           adpv_objetivo_kg=(float(g_esp) or None),
                           edad_meses=(float(edad) or None), altura_grupa_cm=(float(alt) or None))
        st.success("Guardado.")
        _refrescar()


@st.dialog("Corral del lote")
def dialog_instalaciones(lote_id: int):
    from . import clima_reco as cr
    l = db.obtener_lote(lote_id) or {}
    st.caption("Con esto los avisos de clima se ajustan a cómo es el corral.")
    elegidos = {}
    with st.form("f_inst"):
        for campo, titulo in (("reparo", "Reparo del viento"), ("sombra", "Sombra"),
                              ("piso_corral", "Piso del corral"), ("bebederos", "Bebederos")):
            ops = {"Sin dato": ""} | {v: k for k, v in cr.INSTALACIONES[campo].items()}
            actual = l.get(campo) or ""
            idx = list(ops.values()).index(actual) if actual in ops.values() else 0
            elegidos[campo] = ops[st.selectbox(titulo, list(ops), index=idx)]
        reserva = st.number_input("Tanque de reserva de agua (litros, 0 si no tiene o no sabe)",
                                  min_value=0, step=500, value=int(l.get("reserva_agua_l") or 0),
                                  help="Para calcular cuántas horas aguanta el lote si se corta la bomba.")
        caudal = st.number_input("Reposición del bebedero (litros por minuto, 0 si no sabe)",
                                 min_value=0.0, step=1.0, value=float(l.get("caudal_l_min") or 0),
                                 help="Cómo medirlo: con el bebedero bajo, contar cuántos segundos tarda el "
                                      "flotante en llenar un balde de 20 L. Litros por minuto = 20 × 60 ÷ segundos.")
        ok = st.form_submit_button("Guardar", type="primary", width="stretch")
    if ok:
        datos = {k: (v or None) for k, v in elegidos.items()}
        datos["reserva_agua_l"] = float(reserva) or None
        datos["caudal_l_min"] = float(caudal) or None
        db.actualizar_lote(lote_id, **datos)
        st.success("Guardado.")
        _refrescar()


@st.dialog("Entrevista inicial del lote", width="large")
def dialog_entrevista(lote_id: int):
    import json as _json
    from . import entrevista as ent
    l = db.obtener_lote(lote_id) or {}
    r0 = ent.cargar(l)
    # Lo que ya está cargado en el lote sirve de punto de partida
    pre = {"A3": l.get("cantidad_inicial"), "A4": l.get("peso_ingreso_kg"), "A5": l.get("edad_meses"),
           "A6": l.get("altura_grupa_cm"), "F5": l.get("objetivo_peso_kg"), "D2b": l.get("reserva_agua_l"),
           "F1": l.get("encargado_nombre"), "F1b": l.get("encargado_whatsapp")}
    st.caption("Se hace una vez, cuando entra el lote. Lo que no se sabe se deja vacío o en "
               "\"No sabe\": la app lo muestra como faltante, no lo inventa.")
    r: Dict = {}
    with st.form("f_entrevista"):
        for letra, titulo, pregs in ent.BLOQUES:
            st.markdown(f"**{letra}. {titulo}**")
            for k, texto, tipo, ops, para in pregs:
                v0 = r0.get(k, pre.get(k))
                ayuda = f"Para qué: {para}"
                if tipo == "op":
                    lista = ["—"] + ops
                    idx = lista.index(v0) if v0 in lista else 0
                    x = st.selectbox(texto, lista, index=idx, key=f"ent_{k}", help=ayuda)
                    r[k] = "" if x == "—" else x
                elif tipo == "multi":
                    v0l = v0 if isinstance(v0, list) else ([v0] if v0 else [])
                    v0l = ["Grano" if x == "Ya comían grano" else x for x in v0l]
                    dflt = [x for x in v0l if x in ops]
                    r[k] = st.multiselect(texto, ops, default=dflt, key=f"ent_{k}", help=ayuda,
                                          placeholder="Elegí una o más")
                elif tipo == "num":
                    try:
                        val = float(v0 or 0)
                    except (TypeError, ValueError):
                        val = 0.0
                    r[k] = st.number_input(texto + " (0 = no sabe)", min_value=0.0, value=val,
                                           step=1.0, key=f"ent_{k}", help=ayuda)
                else:
                    r[k] = st.text_input(texto, value=str(v0 or ""), key=f"ent_{k}", help=ayuda)
        st.markdown("**Fotos del inicio** (opcional): quedan como punto de partida para comparar.")
        fotos = []
        cf = st.columns(3)
        for i, (tema, et) in enumerate((("lote", "Corral entero"), ("comedero", "Comedero"),
                                         ("bebedero", "Bebedero"))):
            up = cf[i].file_uploader(et, type=["jpg", "jpeg", "png", "webp"], accept_multiple_files=True,
                                     key=f"ent_foto_{tema}")
            fotos += [(tema, u.getvalue()) for u in up or []]
        ok = st.form_submit_button("Guardar entrevista", type="primary", width="stretch")
    if ok:
        r = {k: v for k, v in r.items() if v not in ("", 0, 0.0, [], None)}
        campos = ent.campos_lote(r)
        db.actualizar_lote(lote_id, entrevista=_json.dumps(r, ensure_ascii=False),
                           entrevista_fecha=l.get("entrevista_fecha") or _iso(date.today()), **campos)
        if fotos:
            from . import control_semanal as cs
            cs.guardar_fotos(lote_id, l.get("entrevista_fecha") or _iso(date.today()), fotos, "entrevista")
        st.success("Entrevista guardada. El estado de situación del lote ya está en la ficha.")
        _refrescar()


# ---------------------------------------------------------------------
# Agenda: actividades que carga Mauri (llamar, visitar, recordatorios)
# ---------------------------------------------------------------------
# Política de contacto con el cliente: WhatsApp de rutina, llamado cuando
# el semáforo lo pide, visita técnica (incluida o con cargo), entrevista.
# (clave, nombre, ícono, color, cómo se lee en "Para hoy")
from .contacto import TIPOS_CONTACTO  # noqa: E402
TIPOS_ACTIVIDAD = {f"{ico} {nom}": k for k, nom, ico, _, _ in TIPOS_CONTACTO}
_ICO_CONTACTO = {k: ico for k, _, ico, _, _ in TIPOS_CONTACTO}


def _ensure_agenda() -> None:
    if db._usando_postgres():
        return  # la tabla se creó en Supabase
    with db.get_conn() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS agenda (
            id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT NOT NULL,
            tipo TEXT NOT NULL DEFAULT 'tarea', cliente_id INTEGER, titulo TEXT NOT NULL,
            hecho INTEGER NOT NULL DEFAULT 0, creado TEXT)""")


def listar_agenda(desde: str, hasta: str) -> List[Dict]:
    try:
        _ensure_agenda()
        with db.get_conn() as conn:
            rows = conn.execute(
                "SELECT a.*, c.nombre AS cliente FROM agenda a LEFT JOIN clientes c ON c.id = a.cliente_id "
                "WHERE a.fecha >= ? AND a.fecha <= ? ORDER BY a.fecha, a.id", (desde, hasta)).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []


def marcar_actividad(act_id: int, hecho: bool) -> None:
    with db.get_conn() as conn:
        conn.execute("UPDATE agenda SET hecho = ? WHERE id = ?", (1 if hecho else 0, act_id))


def borrar_actividad(act_id: int) -> None:
    with db.get_conn() as conn:
        conn.execute("DELETE FROM agenda WHERE id = ?", (act_id,))


@st.dialog("Agregar actividad")
def dialog_actividad(fecha_inicial: Optional[date] = None):
    clientes = [c for c in (db.listar_clientes() or []) if c.get("activo", 1) not in (0, False)]
    ops_cli = {"Sin cliente": None} | {c["nombre"]: c["id"] for c in clientes}
    with st.form("f_actividad"):
        tipo = st.radio("Tipo de contacto", list(TIPOS_ACTIVIDAD), horizontal=True)
        cli = st.selectbox("Cliente", list(ops_cli))
        f = st.date_input("Fecha", value=fecha_inicial or date.today(), format="DD/MM/YYYY")
        txt = st.text_input("Qué hay que hacer", placeholder="Ej.: llamar para ver cómo vienen comiendo")
        ok = st.form_submit_button("Guardar", type="primary", width="stretch")
    if ok:
        titulo = txt.strip() or tipo.lower()
        _ensure_agenda()
        with db.get_conn() as conn:
            conn.execute("INSERT INTO agenda (fecha, tipo, cliente_id, titulo, hecho, creado) VALUES (?, ?, ?, ?, 0, ?)",
                          (_iso(f), TIPOS_ACTIVIDAD[tipo], ops_cli[cli], titulo, _iso(date.today())))
        st.success("Guardado. Aparece en el calendario y, el día que toca, en Para hoy.")
        _refrescar()


# ---------------------------------------------------------------------
# Charlas con el cliente: qué se habló y qué se acordó
# ---------------------------------------------------------------------
MEDIOS_CHARLA = [f"{ico} {nom}" for k, nom, ico, _, _ in TIPOS_CONTACTO if k != "tarea"] + ["🤝 En persona (otro lugar)"]


def _ensure_charlas() -> None:
    if db._usando_postgres():
        return  # la tabla se creó en Supabase
    with db.get_conn() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS charlas (
            id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT NOT NULL, cliente_id INTEGER,
            lote_id INTEGER, medio TEXT, resumen TEXT NOT NULL, acuerdos TEXT, creado TEXT)""")


def listar_charlas(lote_id: int, limite: int = 20) -> List[Dict]:
    try:
        _ensure_charlas()
        with db.get_conn() as conn:
            rows = conn.execute("SELECT * FROM charlas WHERE lote_id = ? ORDER BY fecha DESC, id DESC LIMIT ?",
                                (lote_id, limite)).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []


def borrar_charla(charla_id: int) -> None:
    with db.get_conn() as conn:
        conn.execute("DELETE FROM charlas WHERE id = ?", (charla_id,))


@st.dialog("Anotar charla con el cliente")
def dialog_charla(lote_id: int):
    l = db.obtener_lote(lote_id) or {}
    st.caption(f"{l.get('cliente_nombre') or ''} · {l.get('identificador') or ''}. "
               "Queda en la historia del lote y la IA la tiene en cuenta al analizarlo.")
    with st.form("f_charla"):
        c1, c2 = st.columns(2)
        f = c1.date_input("Fecha", value=date.today(), format="DD/MM/YYYY")
        medio = c2.selectbox("Cómo", MEDIOS_CHARLA)
        resumen = st.text_area("Qué se habló", height=140,
                               placeholder="Ej.: dice que dejan algo de comida a la mañana, bosta normal, "
                                           "una vaquillona renga. Quiere vender a fin de diciembre.")
        acuerdos = st.text_area("Qué se acordó (opcional)", height=80,
                                placeholder="Ej.: bajar 0,5 kg la carga de la mañana y avisar el viernes.")
        st.markdown("**Próximo paso (opcional)**: se agrega al calendario.")
        c3, c7, c4 = st.columns([1, 1.2, 2])
        sigue = c3.date_input("Para el", value=None, format="DD/MM/YYYY")
        sigue_tipo = c7.selectbox("Cómo", list(TIPOS_ACTIVIDAD), index=1)
        sigue_txt = c4.text_input("Qué hacer", placeholder="Ej.: ver si mejoró la bosta")
        from . import control_semanal as cs
        c5, c6 = st.columns([1, 2])
        tema_f = c5.selectbox("Fotos de", list(cs.TEMAS_TODOS.values()), index=0)
        ups = c6.file_uploader("Fotos (opcional)", type=["jpg", "jpeg", "png", "webp"],
                               accept_multiple_files=True)
        ok = st.form_submit_button("Guardar", type="primary", width="stretch")
    if ok:
        if not resumen.strip():
            st.error("Escribí qué se habló.")
            return
        _ensure_charlas()
        with db.get_conn() as conn:
            conn.execute("INSERT INTO charlas (fecha, cliente_id, lote_id, medio, resumen, acuerdos, creado) "
                         "VALUES (?, ?, ?, ?, ?, ?, ?)",
                         (_iso(f), l.get("cliente_id"), lote_id, medio.split(" ", 1)[1], resumen.strip(),
                          acuerdos.strip() or None, _iso(date.today())))
        if sigue:
            _ensure_agenda()
            with db.get_conn() as conn:
                conn.execute("INSERT INTO agenda (fecha, tipo, cliente_id, titulo, hecho, creado) "
                             "VALUES (?, ?, ?, ?, 0, ?)",
                             (_iso(sigue), TIPOS_ACTIVIDAD[sigue_tipo], l.get("cliente_id"), sigue_txt.strip() or "seguimiento de la charla",
                              _iso(date.today())))
        if ups:
            tema_k = next((k for k, v in cs.TEMAS_TODOS.items() if v == tema_f), "otra")
            cs.guardar_fotos(lote_id, _iso(f), [(tema_k, u.getvalue()) for u in ups], "charla",
                             comentario=resumen.strip()[:200])
        st.success("Charla guardada.")
        _refrescar()


@st.dialog("Subir fotos del lote")
def dialog_fotos(lote_id: int):
    from . import control_semanal as cs
    st.caption("Fotos sueltas de una recorrida o que te mandó el productor. Quedan en la historia del lote "
               "para comparar cómo cambia el corral.")
    with st.form("f_fotos"):
        c1, c2 = st.columns(2)
        f = c1.date_input("Fecha", value=date.today(), format="DD/MM/YYYY")
        tema = c2.selectbox("De qué son", list(cs.TEMAS_TODOS.values()))
        ups = st.file_uploader("Fotos", type=["jpg", "jpeg", "png", "webp"], accept_multiple_files=True)
        nota = st.text_input("Comentario (opcional)")
        ok = st.form_submit_button("Guardar", type="primary", width="stretch")
    if ok:
        if not ups:
            st.error("Elegí al menos una foto.")
            return
        tema_k = next((k for k, v in cs.TEMAS_TODOS.items() if v == tema), "otra")
        n = cs.guardar_fotos(lote_id, _iso(f), [(tema_k, u.getvalue()) for u in ups], "suelta", nota)
        st.success(f"{n} foto{'s' if n != 1 else ''} guardada{'s' if n != 1 else ''}.")
        _refrescar()


@st.dialog("Datos del cliente")
def dialog_cliente(cliente_id: Optional[int] = None):
    c = db.obtener_cliente(cliente_id) if cliente_id else {}
    c = c or {}
    with st.form("f_cliente"):
        nom = st.text_input("Nombre", value=c.get("nombre") or "")
        loc = st.text_input("Localidad", value=c.get("localidad") or "")
        est = st.text_input("Establecimiento", value=c.get("establecimiento") or "")
        wa = st.text_input("WhatsApp", value=c.get("whatsapp") or "", placeholder="+54 9 …")
        em = st.text_input("Email", value=c.get("email") or "")
        cuit = st.text_input("CUIT", value=c.get("cuit") or "")
        notas = st.text_area("Notas", value=c.get("notas") or "", height=80)
        ok = st.form_submit_button("Guardar", type="primary", width="stretch")
    if ok:
        if not nom.strip():
            st.error("Falta el nombre.")
            return
        datos = dict(nombre=nom.strip(), localidad=loc.strip(), establecimiento=est.strip(),
                     whatsapp=wa.strip(), email=em.strip(), cuit=cuit.strip(), notas=notas)
        if cliente_id:
            db.actualizar_cliente(cliente_id, **datos)
        else:
            db.crear_cliente(**datos)
        st.success("Guardado.")
        _refrescar()


@st.dialog("Dar de baja al cliente")
def dialog_baja(cliente_id: int):
    st.caption("Deja de aparecer en las listas y no recibe avisos. Se puede reactivar.")
    with st.form("f_baja"):
        motivo = st.text_input("Motivo")
        ok = st.form_submit_button("Dar de baja", type="primary", width="stretch")
    if ok:
        db.actualizar_cliente(cliente_id, estado="baja", fecha_baja=_iso(date.today()),
                              motivo_baja=motivo)
        _refrescar()


# =====================================================================
# Acciones dentro de la ficha del lote
# =====================================================================
def acciones_lote(lote: Dict, d: Dict, kp: str) -> None:
    lid = lote["id"]
    st.markdown('<div class="hm"><div class="hm-lbl">CARGAR</div></div>', unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    if c1.button("⚖ Pesada", key=f"{kp}_a_pes_{lid}", width="stretch"):
        dialog_pesada(lid)
    if c2.button("🌾 Entrega", key=f"{kp}_a_ent_{lid}", width="stretch"):
        dialog_entrega(lid)
    if c3.button("🐄 Movimiento", key=f"{kp}_a_mov_{lid}", width="stretch"):
        dialog_movimiento(lid)
    if (lote.get("estado") or "activo") == "activo":
        if c4.button("🔒 Cerrar lote", key=f"{kp}_a_cer_{lid}", width="stretch"):
            dialog_cerrar(lid)
    else:
        if c4.button("↺ Reabrir lote", key=f"{kp}_a_reab_{lid}", width="stretch"):
            db.actualizar_lote(lid, estado="activo", fecha_salida=None)
            _refrescar()


# =====================================================================
# Pestaña LOTES
# =====================================================================
def render_lotes(kp: str = "lt") -> None:
    um.estilos()
    nav = _nav(kp)
    if nav.get("lote"):
        def volver():
            nav.pop("lote", None)
            st.rerun()
        um.render_ficha(nav["lote"], volver, kp=kp, texto_volver="← Lotes")
        return

    if st.button("➕ Cargar encierre nuevo", key=f"{kp}_nuevo", type="primary", width="stretch"):
        dialog_encierre()

    ver = st.segmented_control("Ver", ["Activos", "Cerrados"], default="Activos",
                               key=f"{kp}_filtro", label_visibility="collapsed") or "Activos"
    hoy = date.today()
    if ver == "Activos":
        lotes = um._lotes_activos()
        if not lotes:
            st.info("No hay lotes activos.")
        for l in lotes:
            try:
                d = um.datos_lote(l, hoy)
            except Exception as e:
                st.caption(f"{l.get('identificador')}: {e}")
                continue
            um._tarjeta_lote(d)
            if st.button("Ver ficha", key=f"{kp}_ver_{l['id']}", width="stretch"):
                nav["lote"] = l["id"]
                st.rerun()
    else:
        try:
            lotes = [l for l in db.listar_lotes() if (l.get("estado") or "") != "activo"]
        except Exception:
            lotes = []
        lotes.sort(key=lambda l: str(l.get("fecha_salida") or l.get("fecha_ingreso") or ""), reverse=True)
        if not lotes:
            st.info("Todavía no hay lotes cerrados.")
        for l in lotes[:30]:
            fi, fs = um._fecha(l.get("fecha_ingreso")), um._fecha(l.get("fecha_salida"))
            dias = (fs - fi).days if fi and fs else None
            st.markdown(
                f'<div class="hm"><div class="hm-card"><div class="hm-h">{um._e(l.get("cliente_nombre"))}</div>'
                f'<div class="hm-sub">{um._e(l.get("identificador"))} · {um._dm(fi)} → {um._dm(fs)}'
                f'{f" · {dias} días" if dias else ""}</div></div></div>',
                unsafe_allow_html=True,
            )
            if st.button("Ver ficha", key=f"{kp}_verc_{l['id']}", width="stretch"):
                nav["lote"] = l["id"]
                st.rerun()


# =====================================================================
# LOTES TERMINADOS (dentro de "Más")
# =====================================================================
def render_terminados(kp: str = "lterm") -> None:
    """Todos los encierres cerrados, de todos los clientes. Es la base
    de los informes y de los resultados para redes."""
    um.estilos()
    nav = _nav(kp)
    if nav.get("lote"):
        def volver():
            nav.pop("lote", None)
            st.rerun()
        um.render_ficha(nav["lote"], volver, kp=kp, texto_volver="← Lotes terminados")
        return
    try:
        lotes = [l for l in db.listar_lotes() if (l.get("estado") or "") != "activo"]
    except Exception:
        lotes = []
    lotes.sort(key=lambda l: str(l.get("fecha_salida") or l.get("fecha_ingreso") or ""), reverse=True)
    if not lotes:
        st.info("Todavía no hay encierres terminados. Cuando cierres un lote desde su ficha, aparece acá.")
        return
    st.caption(f"{len(lotes)} encierres terminados. Solo datos medidos: días, peso de entrada y de salida.")
    for l in lotes[:60]:
        fi, fs = um._fecha(l.get("fecha_ingreso")), um._fecha(l.get("fecha_salida"))
        dias = (fs - fi).days if fi and fs else None
        res = ""
        try:
            pes = [p for p in (db.listar_pesadas(l["id"]) or []) if p.get("peso_promedio_kg")]
        except Exception:
            pes = []
        if len(pes) >= 2:
            f0, f1 = um._fecha(pes[0]["fecha"]), um._fecha(pes[-1]["fecha"])
            p0, p1 = float(pes[0]["peso_promedio_kg"]), float(pes[-1]["peso_promedio_kg"])
            if f0 and f1 and (f1 - f0).days > 0:
                res = (f'{um._num(p0, 0)} → {um._num(p1, 0)} kg · '
                       f'{um._num((p1 - p0) / (f1 - f0).days, 2)} kg/día')
        st.markdown(
            f'<div class="hm"><div class="hm-card"><div class="hm-h">{um._e(l.get("cliente_nombre"))}</div>'
            f'<div class="hm-sub">{um._e(l.get("identificador"))} · {um._dm(fi)} → {um._dm(fs)}'
            f'{f" · {dias} días" if dias else ""}</div>'
            f'{f"<div class=hm-sub style=margin-top:4px><b>{res}</b></div>" if res else ""}'
            f'</div></div>',
            unsafe_allow_html=True,
        )
        if st.button("Ver ficha", key=f"{kp}_ver_{l['id']}", width="stretch"):
            nav["lote"] = l["id"]
            st.rerun()


# =====================================================================
# Pestaña CLIENTES
# =====================================================================
def render_clientes(kp: str = "cl") -> None:
    um.estilos()
    nav = _nav(kp)
    if nav.get("lote"):
        def volver_l():
            nav.pop("lote", None)
            st.rerun()
        um.render_ficha(nav["lote"], volver_l, kp=kp, texto_volver="← Cliente")
        return
    if nav.get("cliente"):
        _ficha_cliente(nav["cliente"], kp, nav)
        return

    if st.button("➕ Cliente nuevo", key=f"{kp}_nuevo", type="primary", width="stretch"):
        dialog_cliente()
    buscar = st.text_input("Buscar", key=f"{kp}_buscar", placeholder="Buscar cliente o localidad",
                           label_visibility="collapsed")
    ver_baja = st.toggle("Mostrar dados de baja", key=f"{kp}_baja")

    clientes = db.listar_clientes()
    try:
        activos = db.listar_lotes(estado="activo") or []
    except Exception:
        activos = []
    por_cli: Dict[int, List[Dict]] = {}
    for l in activos:
        por_cli.setdefault(l.get("cliente_id"), []).append(l)
    q = (buscar or "").strip().lower()
    filas = []
    for c in clientes:
        baja = (c.get("estado") or "activo") == "baja"
        if baja and not ver_baja:
            continue
        if q and q not in (c.get("nombre") or "").lower() and q not in (c.get("localidad") or "").lower():
            continue
        filas.append((0 if por_cli.get(c["id"]) else 1, (c.get("nombre") or "").lower(), c, baja))
    filas.sort(key=lambda x: (x[0], x[1]))
    for _, _, c, baja in filas:
        ls = por_cli.get(c["id"], [])
        if ls:
            n = 0
            for l in ls:
                try:
                    n += int(db.cantidad_vigente_lote(l["id"]) or 0)
                except Exception:
                    n += int(l.get("cantidad_inicial") or 0)
            linea = f'{len(ls)} lote{"s" if len(ls) > 1 else ""} activo{"s" if len(ls) > 1 else ""} · {n} animales'
            color = "var(--hm-acc)"
        else:
            linea = "Dado de baja" if baja else "Sin lotes activos"
            color = "var(--hm-sub)"
        ini = "".join(p[0] for p in (c.get("nombre") or "?").split()[:2]).upper()
        st.markdown(
            f'<div class="hm"><div class="hm-card"><div class="hm-row">'
            f'<div class="hm-ico" style="background:#E6EFE3;color:{um.VERDE}">{um._e(ini)}</div>'
            f'<div style="flex:1;min-width:0"><div class="hm-h">{um._e(c.get("nombre"))}</div>'
            f'<div class="hm-sub">{um._e(c.get("localidad") or "")}</div></div>'
            f'<div class="hm-sub" style="color:{color};font-weight:600;text-align:right">{um._e(linea)}</div>'
            f'</div></div></div>',
            unsafe_allow_html=True,
        )
        if st.button("Abrir", key=f"{kp}_abrir_{c['id']}", width="stretch"):
            nav["cliente"] = c["id"]
            st.rerun()


def _ficha_cliente(cliente_id: int, kp: str, nav: Dict) -> None:
    c = db.obtener_cliente(cliente_id)
    if not c:
        nav.pop("cliente", None)
        st.rerun()
    um._subir_arriba(f"{kp}-cli-{cliente_id}")
    if st.button("← Clientes", key=f"{kp}_volver_cli", type="primary"):
        nav.pop("cliente", None)
        st.rerun()
    baja = (c.get("estado") or "activo") == "baja"
    datos = []
    for etiqueta, campo in [("WhatsApp", "whatsapp"), ("Email", "email"), ("CUIT", "cuit"),
                            ("Establecimiento", "establecimiento")]:
        if c.get(campo):
            datos.append(f'<div class="hm-ag"><div class="d" style="width:110px">{etiqueta}</div>'
                         f'<div>{um._e(c[campo])}</div></div>')
    if not c.get("whatsapp"):
        datos.append('<div class="hm-ag"><div class="d" style="width:110px">WhatsApp</div>'
                     '<div class="hm-sub">Falta cargarlo (lo necesitan los avisos)</div></div>')
    nota_html = f'<div class="hm-nota">{um._e(c["notas"])}</div>' if c.get("notas") else ""
    st.markdown(
        f'<div class="hm"><div class="hm-top"><div class="t">{um._e(c.get("nombre"))}</div>'
        f'<div class="s">{um._e(c.get("localidad") or "")}{" · dado de baja" if baja else ""}</div></div>'
        f'<div class="hm-lbl">DATOS</div><div class="hm-card">{"".join(datos)}'
        f'{nota_html}'
        f'</div></div>',
        unsafe_allow_html=True,
    )
    c1, c2 = st.columns(2)
    if c1.button("✏️ Editar datos", key=f"{kp}_edit_{cliente_id}", width="stretch"):
        dialog_cliente(cliente_id)
    if not baja:
        if c2.button("➕ Encierre nuevo", key=f"{kp}_enc_{cliente_id}", width="stretch"):
            dialog_encierre(cliente_id)

    try:
        lotes = db.listar_lotes(cliente_id=cliente_id) or []
    except Exception:
        lotes = []
    act = [l for l in lotes if (l.get("estado") or "") == "activo"]
    cer = [l for l in lotes if (l.get("estado") or "") != "activo"]
    st.markdown('<div class="hm"><div class="hm-lbl">LOTES ACTIVOS</div></div>', unsafe_allow_html=True)
    if not act:
        st.caption("Sin lotes activos.")
    for l in act:
        try:
            um._tarjeta_lote(um.datos_lote(l))
        except Exception as e:
            st.caption(str(e))
        if st.button("Ver ficha", key=f"{kp}_vl_{l['id']}", width="stretch"):
            nav["lote"] = l["id"]
            st.rerun()
    if cer:
        st.markdown('<div class="hm"><div class="hm-lbl">LOTES ANTERIORES</div></div>', unsafe_allow_html=True)
        for l in cer:
            fi, fs = um._fecha(l.get("fecha_ingreso")), um._fecha(l.get("fecha_salida"))
            if st.button(f"{l.get('identificador')} · {um._dm(fi)} → {um._dm(fs)}",
                         key=f"{kp}_vc_{l['id']}", width="stretch"):
                nav["lote"] = l["id"]
                st.rerun()

    if not baja:
        st.write("")
        if st.button("Dar de baja al cliente", key=f"{kp}_baja_{cliente_id}"):
            dialog_baja(cliente_id)
    else:
        if st.button("Reactivar cliente", key=f"{kp}_react_{cliente_id}"):
            db.actualizar_cliente(cliente_id, estado="activo", fecha_baja=None, motivo_baja=None)
            _refrescar()


# =====================================================================
# Control semanal: carga y historial
# =====================================================================
_LETRAS_COLOR = {"verde": "🟢", "amarillo": "🟡", "rojo": "🔴", "gris": "⚪"}


@st.dialog("Control semanal", width="large")
def dialog_control(lote_id: int):
    from . import control_semanal as cs
    lote = db.obtener_lote(lote_id) or {}
    tipo = lote.get("tipo_comedero_concentrado") or "lineal"
    st.caption(f"Comedero: {'silo comedero (autoconsumo)' if tipo.startswith('silo') else 'lineal'}. "
               "Cargá lo que contestó el productor; el semáforo se calcula solo.")
    with st.form("f_control"):
        f = st.date_input("Fecha de las respuestas", value=date.today(), format="DD/MM/YYYY")
        resp: Dict = {}
        for clave, texto, ops, multiple in cs.preguntas(tipo):
            etiquetas = [f"{k}) {v}" for k, v in ops.items()]
            if multiple:
                sel = st.multiselect(f"{clave}. {texto}", etiquetas, key=f"cq_{clave}")
                resp[clave] = [x[0] for x in sel]
            else:
                opciones = ["— sin respuesta —"] + etiquetas
                sel = st.selectbox(f"{clave}. {texto}", opciones, key=f"cq_{clave}")
                resp[clave] = None if sel.startswith("—") else sel[0]
        comen_mas = st.checkbox("En la 8: cambió la cantidad porque comen más", key="cq_8m")
        detalle = st.text_area("Lo que contó el productor (causas, cantidades, repreguntas)", height=90)
        st.markdown("**Fotos**")
        fotos = []
        cols = st.columns(2)
        for i, (tema, et) in enumerate(cs.TEMAS_FOTO.items()):
            up = cols[i % 2].file_uploader(et, type=["jpg", "jpeg", "png", "webp", "heic"],
                                           accept_multiple_files=True, key=f"cf_{tema}")
            for u in up or []:
                fotos.append((tema, u.getvalue()))
        ok = st.form_submit_button("Guardar control", type="primary", width="stretch")
    if ok:
        resp = {k: v for k, v in resp.items() if v}
        if comen_mas:
            resp["8_comen_mas"] = True
        if not resp:
            st.error("No cargaste ninguna respuesta.")
            return
        cs.guardar_control(lote_id, _iso(f), resp, tipo, comentarios=detalle, fotos=fotos)
        sem = cs.semaforo(resp, tipo)
        st.success(f"Guardado. Resultado: {_LETRAS_COLOR[sem['general']]} {sem['general']}.")
        _refrescar()


def historial_controles(lote_id: int, kp: str) -> None:
    from . import control_semanal as cs
    ctrls = cs.listar_controles(lote_id)
    if not ctrls:
        return
    lote = db.obtener_lote(lote_id) or {}
    pregs = {k: (t, o) for k, t, o, _ in cs.preguntas(lote.get("tipo_comedero_concentrado") or "")}
    for c in ctrls[:12]:
        fch = um._fecha(str(c.get("fecha_respuesta") or c.get("fecha_envio") or ""))
        gen = (c.get("semaforo_general") or "gris").lower()
        areas = " ".join(f"{_LETRAS_COLOR.get((c.get('semaforo_' + a) or 'gris').lower(), '⚪')} {n}"
                         for a, n in cs.AREAS)
        with st.expander(f"{_LETRAS_COLOR.get(gen, '⚪')} {um._dm(fch)} · {areas}"):
            resp = c.get("respuestas") or {}
            filas = []
            for k, (t, ops) in pregs.items():
                v = resp.get(k)
                if not v:
                    continue
                vs = v if isinstance(v, list) else [v]
                filas.append(f"**{k}.** {t} → " + ", ".join(f"{x}) {ops.get(x, '')}" for x in vs))
            if filas:
                st.markdown("\n\n".join(filas))
            if c.get("comentarios"):
                st.info(c["comentarios"])
            fotos = cs.fotos_control(c["id"])
            if fotos:
                cols = st.columns(4)
                for i, ft in enumerate(fotos):
                    cols[i % 4].image(ft["datos"], caption=cs.TEMAS_FOTO.get(ft.get("tema"), ft.get("tema")),
                                      width="stretch")
            else:
                st.caption("Sin fotos en este control.")
