"""
Precalcula las métricas del universo y el backtest para que el dashboard arranque rápido.

Uso:
    python app/build_metrics.py
Genera:
    data/processed/metricas_universo.csv
    data/processed/backtest_equiponderado.csv
"""
import time

import pandas as pd

import rf_core as rf

SALIDA = rf.DATA_DIR / "processed"


def main() -> None:
    SALIDA.mkdir(exist_ok=True)
    inicio = time.time()

    universo = rf.cargar_universo()
    curva = rf.Curva(rf.cargar_curva())
    metricas = pd.DataFrame([rf.metricas_bono(r, curva) for _, r in universo.iterrows()])
    metricas.to_csv(SALIDA / "metricas_universo.csv", index=False)
    print(f"Métricas: {len(metricas)} bonos, "
          f"{metricas['Z_Spread_bps'].notna().sum()} con Z-spread ({time.time() - inicio:.1f}s)")

    precios = rf.cargar_precios_universo()
    benchmark = rf.cargar_precios_varios()["RECMTREU Index"]
    bt = rf.backtest_equiponderado(universo, precios, benchmark)
    bt.to_csv(SALIDA / "backtest_equiponderado.csv")
    print(f"Backtest: {len(bt)} fechas, cartera {bt.iloc[-1, 0] - 100:.2f}% "
          f"vs benchmark {bt.iloc[-1, 1] - 100:.2f}% ({time.time() - inicio:.1f}s)")


if __name__ == "__main__":
    main()
