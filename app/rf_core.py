"""
Motor de cálculo de renta fija usado por el dashboard.

Replica las convenciones del notebook `src/TallerRF_AnálisisCartera_COMPLETO.ipynb`:
- Vencimiento efectivo: Next Call Date si el bono es callable (o perpetuo), si no Maturity.
- Flujos generados desde el First Coupon Date, incluyendo el último cupón pagado.
- Cupón corrido ACT/365.
- Descuento con la curva €STR (interpolación log-lineal de factores de descuento)
  y spread con capitalización continua: DF(T) · exp(-s·T).
- Z-spread y YTM resueltos con el método de Brent.
- Duración de Macaulay / modificada y convexidad a partir de la YTM.
"""
from __future__ import annotations

from calendar import monthrange
from datetime import date
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd
from dateutil.relativedelta import relativedelta
from scipy.optimize import brentq

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
FECHA_VALORACION = date(2025, 10, 1)

Flujos = List[Tuple[date, float]]


# ---------------------------------------------------------------------------
# Carga de datos
# ---------------------------------------------------------------------------

def cargar_universo() -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / "universo.csv", sep=";", encoding="utf-8-sig")
    df["spread_bid_ask"] = (df["Ask Price"] - df["Bid Price"]).abs().round(4)
    return df


def cargar_curva() -> pd.DataFrame:
    curva = pd.read_csv(DATA_DIR / "curvaESTR.csv", sep=";")
    curva["Date"] = pd.to_datetime(curva["Date"], format="%d/%m/%Y", errors="coerce")
    for col in ("Market Rate", "Zero Rate", "Discount"):
        curva[col] = pd.to_numeric(curva[col], errors="coerce")
    return curva.dropna(subset=["Date", "Discount"]).reset_index(drop=True)


def cargar_precios_universo() -> pd.DataFrame:
    """Precios históricos (fechas en filas, ISIN en columnas), solo días hábiles."""
    raw = pd.read_csv(DATA_DIR / "precios_historicos_universo.csv", sep=";", na_values=["#N/D"])
    raw = raw.rename(columns={raw.columns[0]: "ISIN"})
    raw["ISIN"] = raw["ISIN"].str.replace(" Corp", "", regex=False)
    precios = raw.set_index("ISIN").T
    precios.index = pd.to_datetime(precios.index, format="%d/%m/%Y")
    precios = precios.apply(pd.to_numeric, errors="coerce").sort_index()
    return precios[precios.index.dayofweek < 5]


def cargar_precios_varios() -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / "precios_historicos_varios.csv", sep=";")
    df = df.rename(columns={df.columns[0]: "Fecha"})
    df["Fecha"] = pd.to_datetime(df["Fecha"], format="%d/%m/%Y")
    return df.set_index("Fecha").sort_index().apply(pd.to_numeric, errors="coerce")


def cargar_cartera_mandato() -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / "cartera_mandato.csv", sep=";")


# ---------------------------------------------------------------------------
# Fechas y flujos
# ---------------------------------------------------------------------------

def parse_date(valor) -> Optional[date]:
    if valor is None or (isinstance(valor, float) and np.isnan(valor)):
        return None
    texto = str(valor).strip()
    if not texto:
        return None
    return pd.to_datetime(texto, format="%d/%m/%Y").date()


def fecha_vencimiento_efectiva(row: pd.Series) -> date:
    maturity = parse_date(row["Maturity"])
    next_call = parse_date(row["Next Call Date"])
    if row["Callable"] == "Y" and next_call:
        return next_call
    if maturity is None and next_call:
        return next_call
    if maturity is None:
        raise ValueError("Sin fecha de vencimiento")
    return maturity


def _avanzar_fecha(fecha: date, meses: int, dia_objetivo: int) -> date:
    destino = fecha + relativedelta(months=meses)
    ultimo_dia = monthrange(destino.year, destino.month)[1]
    return destino.replace(day=min(dia_objetivo, ultimo_dia))


def calcular_flujos_caja(
    fecha_valoracion: date,
    fecha_vencimiento: date,
    fecha_primer_cupon: date,
    nominal: float,
    tasa_cupon: float,
    frecuencia: int,
) -> Flujos:
    """Flujos (fecha, importe), incluyendo el último cupón pagado antes de la valoración."""
    if tasa_cupon == 0:
        return [(fecha_vencimiento, nominal)] if fecha_vencimiento > fecha_valoracion else []

    cupon = nominal * tasa_cupon / frecuencia
    salto = 12 // frecuencia
    dia = fecha_primer_cupon.day

    flujos: Flujos = []
    fecha = fecha_primer_cupon
    previo = None
    while fecha < fecha_valoracion:
        previo = fecha
        fecha = _avanzar_fecha(fecha, salto, dia)
    if previo is not None:
        flujos.append((previo, cupon))

    while fecha <= fecha_vencimiento:
        flujos.append((fecha, cupon))
        fecha = _avanzar_fecha(fecha, salto, dia)

    if flujos and flujos[-1][0] == fecha_vencimiento:
        flujos[-1] = (fecha_vencimiento, flujos[-1][1] + nominal)
        return flujos

    # Vencimiento (o call) fuera de fecha de cupón: principal + cupón corrido
    ultimo = max((f for f, _ in flujos if f < fecha_vencimiento), default=None)
    if ultimo is None:
        ultimo = fecha_primer_cupon
        siguiente = _avanzar_fecha(ultimo, salto, dia)
        while siguiente < fecha_vencimiento:
            ultimo, siguiente = siguiente, _avanzar_fecha(siguiente, salto, dia)
    siguiente = _avanzar_fecha(ultimo, salto, dia)
    dias = (fecha_vencimiento - ultimo).days
    dias_periodo = (siguiente - ultimo).days
    corrido = cupon * dias / dias_periodo if dias_periodo > 0 and dias > 0 else 0.0
    flujos.append((fecha_vencimiento, nominal + corrido))
    return flujos


def flujos_bono(row: pd.Series, fecha_valoracion: date = FECHA_VALORACION) -> Flujos:
    return calcular_flujos_caja(
        fecha_valoracion,
        fecha_vencimiento_efectiva(row),
        parse_date(row["First Coupon Date"]),
        float(row["Outstanding Amount"]),
        float(row["Coupon"]) / 100,
        int(row["Coupon Frequency"]),
    )


def cupon_corrido_pct(flujos: Flujos, fecha_valoracion: date, tasa_cupon: float) -> float:
    """Cupón corrido en % del nominal (ACT/365)."""
    if not flujos or tasa_cupon == 0 or flujos[0][0] >= fecha_valoracion:
        return 0.0
    if not any(f >= fecha_valoracion for f, _ in flujos):
        return 0.0
    dias = (fecha_valoracion - flujos[0][0]).days
    return round(tasa_cupon * dias / 365 * 100, 6) if dias > 0 else 0.0


# ---------------------------------------------------------------------------
# Descuento con curva
# ---------------------------------------------------------------------------

class Curva:
    """Curva de factores de descuento con interpolación log-lineal en ACT/365."""

    def __init__(self, df_curva: pd.DataFrame, fecha_valoracion: date = FECHA_VALORACION):
        self.fecha_valoracion = fecha_valoracion
        origen = pd.Timestamp(fecha_valoracion)
        self.t = ((df_curva["Date"] - origen).dt.days / 365.0).to_numpy()
        self.log_df = np.log(df_curva["Discount"].to_numpy())

    def factores(self, t: np.ndarray) -> np.ndarray:
        # np.interp extrapola en plano en los extremos, como en el notebook
        return np.exp(np.interp(t, self.t, self.log_df))

    def zero_rate(self, t: np.ndarray) -> np.ndarray:
        t = np.asarray(t, dtype=float)
        return -np.log(self.factores(t)) / np.where(t > 0, t, np.nan)


def tiempos_futuros(flujos: Flujos, fecha_valoracion: date) -> Tuple[np.ndarray, np.ndarray]:
    t = np.array([(f - fecha_valoracion).days / 365.0 for f, _ in flujos])
    importes = np.array([m for _, m in flujos])
    futuros = t > 0
    return t[futuros], importes[futuros]


def precio_curva(t: np.ndarray, importes: np.ndarray, curva: Curva, spread: float = 0.0) -> float:
    return float(np.sum(importes * curva.factores(t) * np.exp(-spread * t)))


def z_spread_bps(t: np.ndarray, importes_pct: np.ndarray, precio_sucio_pct: float, curva: Curva) -> float:
    def objetivo(s):
        return precio_curva(t, importes_pct, curva, s) - precio_sucio_pct

    if len(t) == 0 or objetivo(-0.05) * objetivo(0.20) > 0:
        return np.nan
    return brentq(objetivo, -0.05, 0.20, xtol=1e-10, rtol=1e-8, maxiter=100) * 1e4


# ---------------------------------------------------------------------------
# Yield, duración y convexidad
# ---------------------------------------------------------------------------

def _vp_yield(t: np.ndarray, importes: np.ndarray, y: float, freq: int) -> float:
    return float(np.sum(importes / (1 + y / freq) ** (t * freq)))


def ytm(t: np.ndarray, importes_pct: np.ndarray, precio_sucio_pct: float, freq: int) -> float:
    if len(t) == 0 or precio_sucio_pct <= 0:
        return np.nan

    def objetivo(y):
        return _vp_yield(t, importes_pct, y, freq) - precio_sucio_pct

    lo, hi = -0.02, 0.50
    if objetivo(lo) * objetivo(hi) > 0:
        if objetivo(lo) > 0:
            hi = 1.0
        else:
            lo = -0.10
        if objetivo(lo) * objetivo(hi) > 0:
            return np.nan
    return brentq(objetivo, lo, hi, xtol=1e-10, rtol=1e-8, maxiter=100)


def duracion_convexidad(
    t: np.ndarray, importes_pct: np.ndarray, precio_sucio_pct: float, y: float, freq: int
) -> Tuple[float, float, float]:
    """(Duración Macaulay, Duración modificada, Convexidad)."""
    if len(t) == 0 or precio_sucio_pct <= 0 or np.isnan(y):
        return np.nan, np.nan, np.nan
    base = 1 + y / freq
    vp = importes_pct / base ** (t * freq)
    macaulay = float(np.sum(vp * t) / precio_sucio_pct)
    modificada = macaulay / base
    convexidad = float(np.sum(vp * t * (t + 1)) / (precio_sucio_pct * base**2))
    return macaulay, modificada, convexidad


def metricas_bono(row: pd.Series, curva: Curva) -> dict:
    """Todas las métricas de un bono a la fecha de valoración de la curva."""
    fv = curva.fecha_valoracion
    nominal = float(row["Outstanding Amount"])
    tasa = float(row["Coupon"]) / 100
    freq = int(row["Coupon Frequency"])

    flujos = flujos_bono(row, fv)
    t, importes = tiempos_futuros(flujos, fv)
    importes_pct = importes / nominal * 100
    cc = cupon_corrido_pct(flujos, fv, tasa)
    sucio_mercado = float(row["Price"]) + cc

    y = ytm(t, importes_pct, sucio_mercado, freq)
    mac, mod, conv = duracion_convexidad(t, importes_pct, sucio_mercado, y, freq)
    return {
        "ISIN": row["ISIN"],
        "Vencimiento_Efectivo": fecha_vencimiento_efectiva(row),
        "Plazo_Anos": float(t.max()) if len(t) else np.nan,
        "Num_Flujos": len(t),
        "Cupon_Corrido_Pct": cc,
        "Precio_Sucio_Mercado": sucio_mercado,
        "Precio_Teorico_Spread0": precio_curva(t, importes_pct, curva) - cc,
        "Z_Spread_bps": z_spread_bps(t, importes_pct, sucio_mercado, curva),
        "YTM": y * 100 if not np.isnan(y) else np.nan,
        "Duracion_Macaulay": mac,
        "Duracion_Modificada": mod,
        "Convexidad": conv,
    }


# ---------------------------------------------------------------------------
# Backtest cartera equiponderada (Total Return)
# ---------------------------------------------------------------------------

def _fechas_cupon(row: pd.Series) -> List[pd.Timestamp]:
    try:
        venc = pd.Timestamp(fecha_vencimiento_efectiva(row))
    except ValueError:
        return []
    primer = parse_date(row["First Coupon Date"])
    freq = int(row["Coupon Frequency"])
    if not primer or freq == 0:
        return []
    paso = pd.DateOffset(months=12 // freq)
    fechas, f = [], pd.Timestamp(primer)
    while f <= venc:
        fechas.append(f)
        f += paso
    if fechas and fechas[-1] != venc:
        fechas[-1] = venc
    return fechas


def backtest_equiponderado(
    universo: pd.DataFrame, precios: pd.DataFrame, benchmark: pd.Series
) -> pd.DataFrame:
    """Rebalanceo mensual (último día común de cada mes), retornos precio + cupones."""
    comun = precios.index.intersection(benchmark.dropna().index)
    fechas = comun.to_series().groupby(comun.to_period("M")).max().tolist()

    info = universo.set_index("ISIN")
    cupones = {isin: (_fechas_cupon(r), float(r["Coupon"]) / int(r["Coupon Frequency"]))
               for isin, r in info.iterrows() if int(r["Coupon Frequency"]) > 0}

    valores, n_bonos = [100.0], [np.nan]
    for f0, f1 in zip(fechas[:-1], fechas[1:]):
        p0, p1 = precios.loc[f0], precios.loc[f1]
        vivos = p0.dropna().index.intersection(p1.dropna().index)
        retornos = []
        for isin in vivos:
            fechas_c, importe = cupones.get(isin, ([], 0.0))
            pagado = importe * sum(f0 < fc <= f1 for fc in fechas_c)
            retornos.append((p1[isin] - p0[isin] + pagado) / p0[isin])
        valores.append(valores[-1] * (1 + (np.mean(retornos) if retornos else 0.0)))
        n_bonos.append(len(vivos))

    bench = benchmark.reindex(fechas).ffill()
    return pd.DataFrame(
        {
            "Cartera_Equiponderada": valores,
            "Benchmark_RECMTREU": bench.to_numpy() / bench.iloc[0] * 100,
            "Num_Bonos": n_bonos,
        },
        index=pd.DatetimeIndex(fechas, name="Fecha"),
    )
