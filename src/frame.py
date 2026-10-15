"""Frame (tamaño estructural) a partir de la edad y la altura a la grupa,
y el rango de peso de faena que corresponde según el INTA.

Fuentes:
- Fórmulas de frame: Beef Improvement Federation, Guidelines, "Hip
  Height/Frame". Altura en pulgadas sobre los huesos de la cadera, edad en
  días; tablas de 5 a 21 meses. Para novillos se usa la de machos (la BIF
  indica que la altura de toros aproxima la de novillos).
- Peso de faena por frame: Pourrain 2004, INTA EEA Mercedes: frame 4 a 6,
  novillos de 390 a 490 kg (consumo interno); frame 7 a 9, 520 a 620 kg
  (exportación).
- La BIF advierte que las predicciones de peso a partir del frame salen de
  datos de los años 70 y pueden no ajustar a la genética actual: es una
  referencia, no un objetivo cerrado.
"""
from __future__ import annotations

from typing import Dict, Optional

_HEMBRAS = ("vaquillona", "ternera", "vaca", "vaca_adulta", "vaca de descarte")


def frame_score(altura_cm, edad_meses, categoria: str = "") -> Optional[float]:
    try:
        h = float(altura_cm) / 2.54
        dias = float(edad_meses) * 30.44
    except (TypeError, ValueError):
        return None
    if h <= 0 or dias <= 0:
        return None
    if (categoria or "").lower() in _HEMBRAS:
        fs = -11.7086 + 0.4723 * h - 0.0239 * dias + 0.0000146 * dias ** 2 + 0.0000759 * h * dias
    else:
        fs = -11.548 + 0.4878 * h - 0.0289 * dias + 0.00001947 * dias ** 2 + 0.0000334 * h * dias
    return fs


def evaluar_frame(altura_cm, edad_meses, categoria: str = "") -> Optional[Dict]:
    fs = frame_score(altura_cm, edad_meses, categoria)
    if fs is None:
        return None
    try:
        edad = float(edad_meses)
    except (TypeError, ValueError):
        edad = None
    fuera_rango = edad is not None and (edad < 5 or edad > 21)
    r = round(fs, 1)
    if 4 <= r < 6.5:
        peso, destino = (390, 490), "consumo interno"
    elif r >= 6.5:
        peso, destino = (520, 620), "exportación"
    else:
        peso, destino = None, ""
    return {"frame": r, "peso_faena": peso, "destino": destino, "fuera_rango": fuera_rango}
