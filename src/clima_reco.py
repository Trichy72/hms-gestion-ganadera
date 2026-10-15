"""Avisos de clima por lote: el motivo con números y qué hacer según
cómo come el lote (silo comedero o comedero lineal).

Criterio acordado con Mauri (15/10/2026):
- El aviso siempre dice por qué (mínima, viento, lluvia → sensación;
  máxima, humedad → THI).
- "Hielo en bebederos" solo si la mínima baja de 1 °C.
- Silo comedero: no se cambia la mezcla por unos días; se cuida que no
  se moje ni se quede vacío, y la fibra larga va aparte (rollo/picado).
- Comedero lineal: se puede mover el horario de la comida.
- Durante el evento no se cambia la ración.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Dict, List, Optional


def _f(x) -> Optional[float]:
    try:
        return None if x is None else float(x)
    except (TypeError, ValueError):
        return None


def _n(x, dec: int = 0) -> str:
    if x is None:
        return "—"
    s = f"{x:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return s


def sensacion_frio(tmin, viento_kmh, lluvia_mm) -> Optional[float]:
    """Mínima sentida por el bovino: cada 10 km/h de viento ≈ 3 °C menos,
    y mojado (lluvia > 5 mm) ≈ 4 °C menos. Mismo criterio que la columna
    'estrés real' del pronóstico."""
    t = _f(tmin)
    if t is None:
        return None
    s = t - (_f(viento_kmh) or 0) / 10 * 3
    if (_f(lluvia_mm) or 0) > 5:
        s -= 4
    return s


def _es_silo(tipo_comedero: str) -> bool:
    t = (tipo_comedero or "").lower()
    return t.startswith("silo") or t == "autoconsumo"


def evento_del_dia(dia: Dict) -> Optional[Dict]:
    """Si el día del pronóstico tiene estrés moderado o crítico, devuelve
    {tipo: 'frio'|'calor', nivel: 'moderado'|'critico', motivo}."""
    sev = str(dia.get("severidad_real") or "")
    if not sev or sev[:1] not in ("🔴", "🟠"):
        return None
    nivel = "critico" if sev[:1] == "🔴" else "moderado"
    tmin, tmax = _f(dia.get("t_min")), _f(dia.get("t_max"))
    hr, viento = _f(dia.get("hr_media")), _f(dia.get("viento_max_kmh"))
    lluvia = _f(dia.get("precipitacion_mm")) or 0
    if "calor" in sev.lower():
        motivo = (f"máxima {_n(tmax)} °C con humedad {_n(hr)} % "
                  f"(THI {_n(_f(dia.get('thi')))})")
        return {"tipo": "calor", "nivel": nivel, "motivo": motivo,
                "tmax": tmax, "hr": hr}
    sent = sensacion_frio(tmin, viento, lluvia)
    partes = [f"mínima {_n(tmin)} °C", f"viento {_n(viento)} km/h"]
    if lluvia >= 1:
        partes.append(f"{_n(lluvia)} mm de lluvia")
    motivo = ", ".join(partes) + (f" → los animales sienten {_n(sent)} °C" if sent is not None else "")
    return {"tipo": "frio", "nivel": nivel, "motivo": motivo,
            "tmin": tmin, "lluvia": lluvia, "viento": viento}


INSTALACIONES = {
    "reparo": {"si": "Tiene reparo (monte, cortina o armado)", "parcial": "Reparo parcial",
               "no": "No tiene reparo"},
    "sombra": {"si": "Tiene sombra", "parcial": "Sombra parcial", "no": "No tiene sombra"},
    "piso_corral": {"firme": "Piso firme, drena bien", "medio": "Se embarra con lluvias fuertes",
                    "malo": "Se embarra con cualquier lluvia"},
    "bebederos": {"ok": "Bebederos de sobra", "justo": "Bebederos justos", "pocos": "Pocos bebederos"},
}


def _resp(control: Optional[Dict], k: str) -> str:
    r = (control or {}).get("respuestas") or {}
    if isinstance(r, str):
        try:
            import json
            r = json.loads(r)
        except Exception:
            r = {}
    v = r.get(k)
    return (v[0] if isinstance(v, list) and v else (v or "")).upper()


def recomendaciones(evento: Dict, tipo_comedero: str = "",
                    inst: Optional[Dict] = None, control: Optional[Dict] = None) -> List[str]:
    """Qué hacer, en orden de importancia, según el evento, el comedero,
    las instalaciones del corral y el último control del productor.
    Puede subir el nivel del evento (lo deja en evento['nivel'])."""
    inst = inst or {}
    silo = _es_silo(tipo_comedero)
    reparo, sombra = inst.get("reparo") or "", inst.get("sombra") or ""
    piso, beb = inst.get("piso_corral") or "", inst.get("bebederos") or ""
    barro_ctrl = _resp(control, "7") in ("C", "D")      # barro que tapa la pezuña o más
    agua_ctrl = _resp(control, "6") in ("C", "D")       # faltó agua en la semana
    out: List[str] = []
    notas: List[str] = []
    if evento["tipo"] == "frio":
        lluvia = evento.get("lluvia") or 0
        # Sube a crítico: lluvia sobre un corral que ya tiene barro o se
        # embarra fácil, o sin reparo con viento fuerte.
        if evento["nivel"] == "moderado" and (
                (lluvia > 5 and (barro_ctrl or piso == "malo"))
                or (reparo == "no" and (evento.get("viento") or 0) >= 25)):
            evento["nivel"] = "critico"
            notas.append("sube a crítico por las condiciones del corral")
        critico = evento["nivel"] == "critico"
        if reparo == "no":
            out.append("Armar reparo YA: rollos apilados del lado del viento (el corral no tiene)")
        if barro_ctrl and lluvia > 5:
            out.append("El corral ya tiene barro (último control): sector alto y seco "
                       "para echarse antes de que llueva")
        if silo:
            out.append("Silo comedero: que no se quede vacío esos días y que la mezcla "
                       "no se moje ni se apelmace (cubrir la boca si llueve)")
            out.append("Fibra larga aparte (rollo o picado a disposición); "
                       "no cambiar la mezcla del silo")
        else:
            out.append("Comedero: cargar la comida principal a la tarde y que no "
                       "quede vacío a la noche")
            out.append("Fibra larga disponible esos días (rollo o picado)")
        if reparo in ("", "parcial"):
            out.append("Reparo del viento: rollos apilados, monte o cortina"
                       + (" (hoy es parcial)" if reparo == "parcial" else ""))
        if (lluvia > 5 or critico) and not (barro_ctrl and lluvia > 5):
            out.append("Sector alto y seco para echarse; evitar barro en la zona "
                       "del comedero y del bebedero"
                       + (" (el piso se embarra fácil)" if piso in ("malo", "medio") else ""))
        if (evento.get("tmin") is not None and evento["tmin"] < 1):
            out.append("Bebederos: revisar hielo al amanecer")
        out.append("No cambiar la ración durante el evento")
        if critico:
            out.append("Recorrer temprano: animales chicos, débiles o echados en el barro")
    else:  # calor
        if evento["nivel"] == "moderado" and (sombra == "no" or beb == "pocos" or agua_ctrl):
            evento["nivel"] = "critico"
            notas.append("sube a crítico por falta de sombra o de agua")
        critico = evento["nivel"] == "critico"
        if agua_ctrl:
            out.append("En el último control faltó agua: revisar bomba, caudal y flotantes ANTES del calor")
        out.append("Agua: bebederos limpios, con caudal y espacio para todos"
                   + (" (son pocos: sumar un tanque o bebedero)" if beb == "pocos" else ""))
        if sombra == "no":
            out.append("No tiene sombra: si se puede, media sombra provisoria")
        if silo:
            out.append("Silo comedero: no llenarlo de más, que la mezcla no se caliente "
                       "ni fermente; revisar que no se quede vacío")
        else:
            out.append("Comedero: dar la mayor parte de la comida después de las 18 h")
        if sombra != "no":
            out.append("No mover ni trabajar animales en horas de calor")
        out.append("No cambiar la ración durante el evento")
        if critico:
            out.append("Mirar jadeo a la siesta; si hay forma, mojar el piso del corral")
    evento["notas"] = notas
    return out


def eventos_proximos(pronostico: List[Dict], hoy: Optional[date] = None,
                     dias: int = 5) -> List[Dict]:
    """Eventos de hoy en adelante (hasta `dias`), con su fecha."""
    hoy = hoy or date.today()
    out = []
    for x in pronostico or []:
        try:
            f = datetime.strptime(str(x.get("fecha"))[:10], "%Y-%m-%d").date()
        except ValueError:
            continue
        if f < hoy or (f - hoy).days > dias:
            continue
        ev = evento_del_dia(x)
        if ev:
            ev["fecha"] = f
            out.append(ev)
    return out
