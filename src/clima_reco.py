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


def recomendaciones(evento: Dict, tipo_comedero: str = "") -> List[str]:
    """Qué hacer, en orden de importancia, según el evento y el comedero."""
    silo = _es_silo(tipo_comedero)
    critico = evento.get("nivel") == "critico"
    out: List[str] = []
    if evento["tipo"] == "frio":
        lluvia = evento.get("lluvia") or 0
        if silo:
            out.append("Silo comedero: que no se quede vacío esos días y que la mezcla "
                       "no se moje ni se apelmace (cubrir la boca si llueve)")
            out.append("Fibra larga aparte (rollo o picado a disposición); "
                       "no cambiar la mezcla del silo")
        else:
            out.append("Comedero: cargar la comida principal a la tarde y que no "
                       "quede vacío a la noche")
            out.append("Fibra larga disponible esos días (rollo o picado)")
        out.append("Reparo del viento: rollos apilados, monte o cortina")
        if lluvia > 5 or critico:
            out.append("Sector alto y seco para echarse; evitar barro en la zona "
                       "del comedero y del bebedero")
        if (evento.get("tmin") is not None and evento["tmin"] < 1):
            out.append("Bebederos: revisar hielo al amanecer")
        out.append("No cambiar la ración durante el evento")
        if critico:
            out.append("Recorrer temprano: animales chicos, débiles o echados en el barro")
    else:  # calor
        out.append("Agua: bebederos limpios, con caudal y espacio para todos")
        if silo:
            out.append("Silo comedero: no llenarlo de más, que la mezcla no se caliente "
                       "ni fermente; revisar que no se quede vacío")
        else:
            out.append("Comedero: dar la mayor parte de la comida después de las 18 h")
        out.append("Sombra si hay; no mover ni trabajar animales en horas de calor")
        out.append("No cambiar la ración durante el evento")
        if critico:
            out.append("Mirar jadeo a la siesta; si hay forma, mojar el piso del corral")
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
