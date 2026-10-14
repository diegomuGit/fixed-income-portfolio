# Análisis de cartera de renta fija corporativa · mIAx

![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-1.66-FF4B4B?logo=streamlit&logoColor=white)
![Railway](https://img.shields.io/badge/Deploy-Railway-0B0D0E?logo=railway&logoColor=white)

Práctica del **Taller de Renta Fija del máster mIAx**: análisis de un universo de **2.255 bonos corporativos en EUR**,
valoración sobre la curva **€STR**, construcción de una cartera bajo mandato y cobertura de sus riesgos de tipos y de crédito.

**🔗 Dashboard interactivo:** <https://fixed-income-portfolio-production.up.railway.app>

**Autores:** Diego Muñoz · Javi Chulvi · Luis Coello

---

## 📊 Resultados principales

| Bloque | Resultado |
|---|---|
| Universo | 2.255 bonos de 613 emisores, todos en EUR; ~45% financieros; 73% callables |
| Valoración | Z-spread mediano **74 pb**, YTM mediana **2,89%**, duración modificada media **3,8** |
| Cartera equiponderada (oct-23 → oct-25) | **+14,7%** Total Return frente a **+13,1%** del índice RECMTREU |
| Cartera mandato (MILP) | 12 bonos, **TIR 5,38%**, duración 3,00, 10% HY, PD 1 año ponderada 0,97% |
| Cobertura de tipos | 55 futuros **Bobl** vendidos para neutralizar 3.000 €/pb de DV01 (cartera de 10 M€) |
| Cobertura de crédito | ~6,7 M€ de protección en iTraxx (90% Main / 10% Crossover), coste ~0,5% anual |

## 🧭 Contenido del análisis

El notebook [`src/TallerRF_AnálisisCartera_COMPLETO.ipynb`](src/TallerRF_AnálisisCartera_COMPLETO.ipynb) recorre:

1. **Datos** — divisas, tipos de cupón, prelación, opcionalidad, perpetuos, sectores, emisores, ratings y liquidez
   (horquilla bid/ask frente a nominal vivo). Limpieza de precios históricos (`#N/D`, fines de semana).
2. **Valoración** — generación de flujos de caja, cupón corrido y descuento con la curva €STR.
3. **Spread** — Z-spread que iguala el precio teórico con el de mercado (método de Brent).
4. **YTM, duración y convexidad** — y aproximación del precio por duración + convexidad.
5. **Cartera equiponderada** — backtest con rebalanceo mensual y Total Return frente a RECMTREU.
6. **Cartera mandato** — optimización lineal entera mixta con PuLP que maximiza la TIR sujeta a:
   ≤ 20 bonos · duración ≤ 3 · HY ≤ 10% · sin subordinados · emisiones > 500 M · ≤ 10% por emisión · ≤ 15% por emisor.
   Análisis de riesgo de crédito y de liquidez.
7. **Cobertura de tipos** — futuros Schatz (DU1), Bobl (OE1) y Bund (RX1).
8. **Cobertura de crédito** — iTraxx Europe Main y Crossover.
9. **Estrategia propia** — estrategias de valor relativo en crédito corporativo.

### Convenciones de cálculo

- **Vencimiento efectivo**: *Next Call Date* si el bono es callable o perpetuo; si no, *Maturity*.
- **Flujos**: generados desde *First Coupon Date* con la frecuencia del bono; principal + cupón corrido si el vencimiento no cae en fecha de cupón.
- **Cupón corrido**: ACT/365.
- **Descuento**: interpolación log-lineal de factores de descuento €STR; spread en capitalización continua `DF(T)·e^(−s·T)`.
- **YTM**: TIR con capitalización a la frecuencia del cupón; duración de Macaulay/modificada y convexidad derivadas de ella.

## 🖥️ Dashboard

La carpeta [`app/`](app/) contiene un dashboard en **Streamlit + Plotly** que expone el análisis de forma interactiva:

| Pestaña | Qué muestra |
|---|---|
| Resumen | KPIs del universo, el backtest y la cartera mandato |
| Universo | Filtros por sector, grado y prelación; ratings, emisores y liquidez |
| Curva €STR | Curva cupón cero y factores de descuento |
| Valoración y riesgo | YTM vs Z-spread, duración vs plazo, Z-spread por rating; tabla descargable |
| Ficha de bono | Flujos de cualquier ISIN, precio vs spread y simulador de shocks de TIR |
| Backtest | Cartera equiponderada vs RECMTREU: retorno, volatilidad, drawdown, exceso mensual |
| Cartera mandato | Verificación de restricciones, pesos, exposición sectorial y por rating |
| Coberturas | Calculadora de futuros e iTraxx con valor, duración objetivo y % de cobertura ajustables |

El motor de cálculo ([`app/rf_core.py`](app/rf_core.py)) replica las funciones del notebook y reproduce sus resultados
(TIR y duración idénticas para los bonos de la cartera mandato). Las métricas del universo y el backtest se precalculan con
[`app/build_metrics.py`](app/build_metrics.py) en `data/processed/` para que el dashboard arranque al instante.

## 📁 Estructura

```
02-renta-fija/
├── app/
│   ├── app.py                  # Dashboard Streamlit
│   ├── rf_core.py              # Motor de valoración, riesgo y backtest
│   └── build_metrics.py        # Precálculo de métricas → data/processed/
├── data/
│   ├── universo.csv            # Universo de bonos (características y precios a 01/10/2025)
│   ├── curvaESTR.csv           # Curva €STR (tipos y factores de descuento)
│   ├── precios_historicos_universo.csv   # Precios diarios oct-23 → oct-25
│   ├── precios_historicos_varios.csv     # iTraxx Main/Crossover, futuros DU1/OE1/RX1, RECMTREU
│   ├── cartera_mandato.csv     # Cartera óptima resultante del punto 6
│   └── processed/              # Métricas y backtest precalculados para el dashboard
├── src/
│   ├── TallerRF_AnálisisCartera_COMPLETO.ipynb
│   └── descuento.py            # Valor presente por curva + spread o por yield
├── railway.json                # Configuración de despliegue
├── .python-version
└── requirements.txt
```

## 🛠️ Instalación

Requisitos: Python 3.11 o superior.

```bash
git clone https://github.com/diegomuGit/02-renta-fija.git
cd 02-renta-fija
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Ejecutar el notebook

```bash
pip install jupyter
jupyter notebook src/TallerRF_AnálisisCartera_COMPLETO.ipynb
```

### Ejecutar el dashboard

```bash
python app/build_metrics.py   # opcional: regenera data/processed/ (≈10 s)
streamlit run app/app.py
```

Se abre en <http://localhost:8501>.

## 🚀 Despliegue en Railway

El repositorio está listo para desplegarse en [Railway](https://railway.com) directamente desde GitHub:

1. Crear un servicio a partir del repositorio `diegomuGit/02-renta-fija`.
2. Railway detecta Python (Railpack), instala `requirements.txt` y usa el `startCommand` de [`railway.json`](railway.json):
   `streamlit run app/app.py --server.port $PORT --server.address 0.0.0.0`.
3. Generar un dominio público en *Settings → Networking*. El healthcheck apunta a `/_stcore/health`.

Cada push a la rama conectada vuelve a desplegar el dashboard.

## 📦 Dependencias principales

`numpy` · `pandas` · `scipy` (Brent) · `pulp` (MILP) · `matplotlib` / `seaborn` (notebook) · `plotly` / `streamlit` (dashboard).

## 📝 Licencia

Proyecto de uso educativo y académico, desarrollado para el máster mIAx.
