"""
Dashboard del Taller de Renta Fija (mIAx).

Ejecutar en local:
    streamlit run app/app.py
"""
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import rf_core as rf

st.set_page_config(page_title="Renta Fija · Análisis de Cartera", page_icon="📈", layout="wide")

# Paleta categórica (orden fijo) y estilos comunes de los gráficos
C = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
GRIS = "#8a8984"
ORDEN_RATING = ["AAA", "AA+", "AA", "AA-", "A+", "A", "A-", "BBB+", "BBB", "BBB-",
                "BB+", "BB", "BB-", "B+", "B", "B-", "CCC+", "NR"]
HY = {"BB+", "BB", "BB-", "B+", "B", "B-", "CCC+", "CCC", "CC", "C", "D"}


def estilo(fig: go.Figure, alto: int = 420) -> go.Figure:
    fig.update_layout(
        height=alto,
        margin=dict(l=10, r=10, t=80, b=10),
        title=dict(yref="container", y=0.97, yanchor="top", x=0, xanchor="left"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, title=None),
        hoverlabel=dict(namelength=-1),
        colorway=C,
    )
    fig.update_xaxes(showgrid=False, zeroline=False)
    fig.update_yaxes(gridcolor="rgba(128,128,128,0.18)", zeroline=False)
    return fig


def kpi(col, etiqueta: str, valor: str, nota: str | None = None) -> None:
    """Métrica con una nota informativa debajo (sin flecha de variación)."""
    col.metric(etiqueta, valor)
    if nota:
        col.caption(nota)


def mostrar(fig: go.Figure, alto: int = 420) -> None:
    st.plotly_chart(estilo(fig, alto), width="stretch", theme="streamlit")


# ---------------------------------------------------------------------------
# Datos (cacheados)
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner="Cargando datos de mercado…")
def datos():
    universo = rf.cargar_universo()
    curva = rf.cargar_curva()
    procesados = rf.DATA_DIR / "processed"
    metricas_path = procesados / "metricas_universo.csv"
    backtest_path = procesados / "backtest_equiponderado.csv"

    if metricas_path.exists():
        metricas = pd.read_csv(metricas_path)
    else:
        c = rf.Curva(curva)
        metricas = pd.DataFrame([rf.metricas_bono(r, c) for _, r in universo.iterrows()])

    varios = rf.cargar_precios_varios()
    if backtest_path.exists():
        backtest = pd.read_csv(backtest_path, index_col=0, parse_dates=True)
    else:
        backtest = rf.backtest_equiponderado(universo, rf.cargar_precios_universo(), varios["RECMTREU Index"])

    df = universo.merge(metricas, on="ISIN", how="left")
    df["Grado"] = np.where(df["Rating"].isin(HY), "High Yield", np.where(df["Rating"].isna(), "Sin rating", "Investment Grade"))
    df["Año vencimiento"] = pd.to_datetime(df["Vencimiento_Efectivo"]).dt.year
    return df, curva, varios, backtest, rf.cargar_cartera_mandato()


@st.cache_data
def precios_historicos():
    return rf.cargar_precios_universo()


df, curva, varios, backtest, cartera = datos()

# ---------------------------------------------------------------------------
# Cabecera
# ---------------------------------------------------------------------------

st.title("Análisis de cartera de renta fija corporativa")
st.caption(
    "Taller de Renta Fija · mIAx · Diego Muñoz, Javi Chulvi y Luis Coello · "
    f"Fecha de valoración {rf.FECHA_VALORACION:%d/%m/%Y} · curva €STR"
)

tabs = st.tabs([
    "Resumen", "Universo", "Curva €STR", "Valoración y riesgo",
    "Ficha de bono", "Backtest", "Cartera mandato", "Coberturas",
])

# ---------------------------------------------------------------------------
# 1. Resumen
# ---------------------------------------------------------------------------
with tabs[0]:
    tr_cartera = backtest["Cartera_Equiponderada"].iloc[-1] / 100 - 1
    tr_bench = backtest["Benchmark_RECMTREU"].iloc[-1] / 100 - 1
    tir_mandato = (cartera["TIR"] * cartera["Peso"]).sum()
    dur_mandato = (cartera["Duracion_Modificada"] * cartera["Peso"]).sum()

    k = st.columns(4)
    kpi(k[0], "Bonos en el universo", f"{len(df):,}".replace(",", "."), f"{df['Issuer'].nunique()} emisores")
    kpi(k[1], "Z-spread mediano", f"{df['Z_Spread_bps'].median():.0f} pb", f"YTM mediana {df['YTM'].median():.2f}%")
    k[2].metric("Cartera equiponderada (TR)", f"{tr_cartera:.2%}", f"{tr_cartera - tr_bench:+.2%} vs RECMTREU")
    kpi(k[3], "Cartera mandato", f"TIR {tir_mandato:.2f}%", f"{len(cartera)} bonos · duración {dur_mandato:.2f}")

    st.markdown(
        """
**Qué contiene este dashboard**

1. **Universo** — composición del universo de bonos corporativos en EUR: sectores, ratings, prelación y liquidez (horquilla bid/ask vs tamaño de emisión).
2. **Curva €STR** — curva cupón cero y factores de descuento usados para valorar.
3. **Valoración y riesgo** — Z-spread, YTM, duración modificada y convexidad de los 2.255 bonos, calculados con la misma metodología que el notebook.
4. **Ficha de bono** — flujos de caja de cualquier ISIN, precio frente a spread y aproximación por duración + convexidad.
5. **Backtest** — cartera equiponderada con rebalanceo mensual (Total Return, precios MID) frente al índice RECMTREU.
6. **Cartera mandato** — cartera óptima (MILP con PuLP) que maximiza la TIR con ≤20 bonos, duración ≤3, HY ≤10%, sin subordinados, emisiones >500M y límites por emisión (10%) y emisor (15%).
7. **Coberturas** — cobertura de duración con futuros Schatz/Bobl/Bund y de crédito con iTraxx Main/Crossover, con parámetros ajustables.
"""
    )
    st.info(
        "Metodología: flujos desde *First Coupon Date*, vencimiento efectivo en la *Next Call Date* para callables y perpetuos, "
        "cupón corrido ACT/365, descuento log-lineal sobre la curva €STR con spread en capitalización continua, "
        "Z-spread e YTM por el método de Brent.",
        icon="ℹ️",
    )

# ---------------------------------------------------------------------------
# 2. Universo
# ---------------------------------------------------------------------------
with tabs[1]:
    f1, f2, f3 = st.columns(3)
    sectores = f1.multiselect("Sector", sorted(df["Industry Sector"].dropna().unique()), placeholder="Todos")
    grados = f2.multiselect("Grado crediticio", ["Investment Grade", "High Yield", "Sin rating"], placeholder="Todos")
    prelaciones = f3.multiselect("Prelación", sorted(df["Seniority"].dropna().unique()), placeholder="Todos")

    u = df.copy()
    if sectores:
        u = u[u["Industry Sector"].isin(sectores)]
    if grados:
        u = u[u["Grado"].isin(grados)]
    if prelaciones:
        u = u[u["Seniority"].isin(prelaciones)]

    k = st.columns(4)
    k[0].metric("Bonos", len(u))
    k[1].metric("Emisores", u["Issuer"].nunique())
    k[2].metric("Callables", f"{(u['Callable'] == 'Y').mean():.0%}")
    k[3].metric("Nominal vivo total", f"{u['Outstanding Amount'].sum() / 1e9:,.0f} mil M€".replace(",", "."))

    a, b = st.columns(2)
    with a:
        sec = u["Industry Sector"].value_counts().sort_values()
        fig = go.Figure(go.Bar(x=sec.values, y=sec.index, orientation="h", marker_color=C[0],
                               hovertemplate="%{y}: %{x} bonos<extra></extra>"))
        fig.update_layout(title="Bonos por sector")
        mostrar(fig, 380)
    with b:
        rat = u["Rating"].fillna("NR").value_counts().reindex(ORDEN_RATING).dropna()
        colores = [C[1] if r in HY else (GRIS if r == "NR" else C[0]) for r in rat.index]
        fig = go.Figure(go.Bar(x=rat.index, y=rat.values, marker_color=colores,
                               hovertemplate="%{x}: %{y} bonos<extra></extra>"))
        fig.update_layout(title="Distribución de ratings (azul IG · naranja HY · gris sin rating)")
        mostrar(fig, 380)

    a, b = st.columns(2)
    with a:
        sen = u["Seniority"].value_counts().sort_values()
        fig = go.Figure(go.Bar(x=sen.values, y=sen.index, orientation="h", marker_color=C[2],
                               hovertemplate="%{y}: %{x} bonos<extra></extra>"))
        fig.update_layout(title="Prelación")
        mostrar(fig, 340)
    with b:
        emi = u["Issuer"].value_counts().head(15).sort_values()
        fig = go.Figure(go.Bar(x=emi.values, y=emi.index, orientation="h", marker_color=C[6],
                               hovertemplate="%{y}: %{x} emisiones<extra></extra>"))
        fig.update_layout(title="Top 15 emisores por número de emisiones")
        mostrar(fig, 340)

    st.subheader("Liquidez: horquilla bid/ask frente a tamaño de emisión")
    fig = px.scatter(
        u, x="Outstanding Amount", y="spread_bid_ask", color="Grado", log_x=True,
        color_discrete_map={"Investment Grade": C[0], "High Yield": C[1], "Sin rating": GRIS},
        hover_data={"ISIN": True, "Description": True, "Outstanding Amount": ":,.0f", "spread_bid_ask": ":.3f", "Grado": False},
        labels={"Outstanding Amount": "Nominal vivo (€, escala log)", "spread_bid_ask": "Horquilla bid/ask (puntos de precio)"},
    )
    fig.update_traces(marker=dict(size=8, opacity=0.65, line=dict(width=1, color="white")))
    mostrar(fig, 440)
    st.caption("A mayor tamaño de emisión, más liquidez y menor horquilla bid/ask.")

# ---------------------------------------------------------------------------
# 3. Curva €STR
# ---------------------------------------------------------------------------
with tabs[2]:
    cz = curva.dropna(subset=["Zero Rate"]).copy()
    cz["Plazo"] = (cz["Date"] - pd.Timestamp(rf.FECHA_VALORACION)).dt.days / 365
    a, b = st.columns(2)
    with a:
        fig = go.Figure(go.Scatter(x=cz["Plazo"], y=cz["Zero Rate"], mode="lines+markers", line=dict(width=2, color=C[0]),
                                   marker=dict(size=8), name="Tipo cupón cero",
                                   hovertemplate="%{x:.2f} años: %{y:.3f}%<extra></extra>"))
        fig.update_layout(title="Curva cupón cero €STR (%)", xaxis_title="Plazo (años)")
        mostrar(fig)
    with b:
        fig = go.Figure(go.Scatter(x=cz["Plazo"], y=cz["Discount"], mode="lines+markers", line=dict(width=2, color=C[2]),
                                   marker=dict(size=8), name="Factor de descuento",
                                   hovertemplate="%{x:.2f} años: %{y:.5f}<extra></extra>"))
        fig.update_layout(title="Factores de descuento", xaxis_title="Plazo (años)")
        mostrar(fig)
    st.dataframe(cz[["Date", "Plazo", "Market Rate", "Zero Rate", "Discount"]].round(5),
                 hide_index=True, width="stretch",
                 column_config={"Date": st.column_config.DateColumn("Fecha", format="DD/MM/YYYY")})

# ---------------------------------------------------------------------------
# 4. Valoración y riesgo
# ---------------------------------------------------------------------------
with tabs[3]:
    v = df.dropna(subset=["Z_Spread_bps", "YTM"])
    excluir = st.toggle("Excluir outliers (Z-spread fuera de [-50, 600] pb)", value=True)
    if excluir:
        v = v[v["Z_Spread_bps"].between(-50, 600)]

    k = st.columns(4)
    k[0].metric("Z-spread medio", f"{v['Z_Spread_bps'].mean():.1f} pb")
    k[1].metric("YTM media", f"{v['YTM'].mean():.2f}%")
    k[2].metric("Duración modificada media", f"{v['Duracion_Modificada'].mean():.2f}")
    k[3].metric("Convexidad media", f"{v['Convexidad'].mean():.1f}")

    hover = {"ISIN": True, "Description": True, "Rating": True, "Z_Spread_bps": ":.1f", "YTM": ":.2f", "Grado": False}
    mapa_grado = {"Investment Grade": C[0], "High Yield": C[1], "Sin rating": GRIS}
    a, b = st.columns(2)
    with a:
        fig = px.scatter(v, x="Z_Spread_bps", y="YTM", color="Grado", color_discrete_map=mapa_grado, hover_data=hover,
                         labels={"Z_Spread_bps": "Z-spread (pb)", "YTM": "YTM (%)"})
        fig.update_traces(marker=dict(size=8, opacity=0.6, line=dict(width=1, color="white")))
        fig.update_layout(title="YTM frente a Z-spread")
        mostrar(fig, 440)
    with b:
        fig = px.scatter(v, x="Plazo_Anos", y="Duracion_Modificada", color="Grado", color_discrete_map=mapa_grado,
                         hover_data=hover, labels={"Plazo_Anos": "Plazo al vencimiento efectivo (años)",
                                                   "Duracion_Modificada": "Duración modificada"})
        fig.update_traces(marker=dict(size=8, opacity=0.6, line=dict(width=1, color="white")))
        fig.update_layout(title="Duración modificada frente a plazo")
        mostrar(fig, 440)

    st.subheader("Z-spread por rating")
    vr = v.assign(Rating=v["Rating"].fillna("NR"))
    orden = [r for r in ORDEN_RATING if r in vr["Rating"].unique()]
    fig = px.box(vr, x="Rating", y="Z_Spread_bps", category_orders={"Rating": orden}, points=False,
                 labels={"Z_Spread_bps": "Z-spread (pb)"}, color_discrete_sequence=[C[0]])
    mostrar(fig, 380)
    st.caption("El spread aumenta conforme empeora la calidad crediticia: la prima por riesgo de crédito se ve en el salto IG → HY.")

    with st.expander("Tabla completa de métricas"):
        cols = ["ISIN", "Description", "Issuer", "Rating", "Price", "Cupon_Corrido_Pct", "Z_Spread_bps", "YTM",
                "Duracion_Macaulay", "Duracion_Modificada", "Convexidad", "Vencimiento_Efectivo"]
        st.dataframe(df[cols].round(4), hide_index=True, width="stretch")
        st.download_button("Descargar CSV", df[cols].to_csv(index=False).encode("utf-8"),
                           "metricas_universo.csv", "text/csv")

# ---------------------------------------------------------------------------
# 5. Ficha de bono
# ---------------------------------------------------------------------------
with tabs[4]:
    opciones = df.sort_values("Description")
    etiquetas = (opciones["ISIN"] + " · " + opciones["Description"]).tolist()
    por_defecto = next((i for i, e in enumerate(etiquetas) if e.startswith("XS2356041165")), 0)
    elegido = st.selectbox("Bono", etiquetas, index=por_defecto)
    bono = opciones.iloc[etiquetas.index(elegido)]

    k = st.columns(6)
    k[0].metric("Duración mod.", f"{bono['Duracion_Modificada']:.3f}")
    k[1].metric("Rating", bono["Rating"] if isinstance(bono["Rating"], str) else "NR")
    k[2].metric("Cupón", f"{bono['Coupon']:.3f}%")
    k[3].metric("Precio limpio", f"{bono['Price']:.3f}")
    k[4].metric("Z-spread", f"{bono['Z_Spread_bps']:.1f} pb")
    k[5].metric("YTM", f"{bono['YTM']:.3f}%")
    st.caption(
        f"{bono['Issuer']} · {bono['Industry Sector']} · vencimiento efectivo {pd.Timestamp(bono['Vencimiento_Efectivo']):%d/%m/%Y}"
        f"{' (call)' if bono['Callable'] == 'Y' else ''} · {bono['Seniority']} · "
        f"frecuencia {int(bono['Coupon Frequency'])} · cupón corrido {bono['Cupon_Corrido_Pct']:.4f}% · "
        f"convexidad {bono['Convexidad']:.3f}"
    )

    flujos = rf.flujos_bono(bono)
    nominal = float(bono["Outstanding Amount"])
    tabla = pd.DataFrame(flujos, columns=["Fecha", "Importe"])
    tabla["Importe (% nominal)"] = tabla["Importe"] / nominal * 100
    tabla["Plazo"] = [(f - rf.FECHA_VALORACION).days / 365 for f in tabla["Fecha"]]
    c_obj = rf.Curva(curva)
    tabla["Factor descuento"] = np.where(tabla["Plazo"] > 0,
                                         c_obj.factores(tabla["Plazo"].to_numpy()) * np.exp(-bono["Z_Spread_bps"] / 1e4 * tabla["Plazo"]),
                                         np.nan)
    tabla["Valor presente (%)"] = tabla["Importe (% nominal)"] * tabla["Factor descuento"]

    a, b = st.columns(2)
    with a:
        futuros = tabla[tabla["Plazo"] > 0]
        fig = go.Figure()
        fig.add_bar(x=futuros["Fecha"], y=futuros["Importe (% nominal)"], name="Flujo nominal", marker_color=C[0],
                    hovertemplate="%{x|%d/%m/%Y}: %{y:.3f}%<extra>Flujo</extra>")
        fig.add_bar(x=futuros["Fecha"], y=futuros["Valor presente (%)"], name="Valor presente (curva + Z-spread)",
                    marker_color=C[2], hovertemplate="%{x|%d/%m/%Y}: %{y:.3f}%<extra>VP</extra>")
        fig.update_layout(title="Flujos de caja futuros (% del nominal)", barmode="group", bargap=0.3)
        mostrar(fig)
    with b:
        t, imp = rf.tiempos_futuros(flujos, rf.FECHA_VALORACION)
        imp_pct = imp / nominal * 100
        spreads = np.linspace(-100, 400, 101)
        precios = [rf.precio_curva(t, imp_pct, c_obj, s / 1e4) - bono["Cupon_Corrido_Pct"] for s in spreads]
        fig = go.Figure(go.Scatter(x=spreads, y=precios, mode="lines", line=dict(width=2, color=C[0]), name="Precio limpio",
                                   hovertemplate="%{x:.0f} pb → %{y:.3f}<extra></extra>"))
        fig.add_scatter(x=[bono["Z_Spread_bps"]], y=[bono["Price"]], mode="markers", name="Mercado",
                        marker=dict(size=12, color=C[1], line=dict(width=2, color="white")),
                        hovertemplate="Z-spread %{x:.1f} pb · precio %{y:.3f}<extra></extra>")
        fig.update_layout(title="Precio limpio en función del spread sobre €STR", xaxis_title="Spread (pb)", yaxis_title="Precio")
        mostrar(fig)

    st.subheader("Aproximación del precio por duración y convexidad")
    dy = st.slider("Movimiento paralelo de la TIR (pb)", -300, 300, 100, step=25)
    p0 = bono["Precio_Sucio_Mercado"]
    D, Cx = bono["Duracion_Modificada"], bono["Convexidad"]
    y0 = bono["YTM"] / 100
    freq = int(bono["Coupon Frequency"])
    exacto = rf._vp_yield(t, imp_pct, y0 + dy / 1e4, freq)
    solo_dur = p0 * (1 - D * dy / 1e4)
    dur_conv = p0 * (1 - D * dy / 1e4 + 0.5 * Cx * (dy / 1e4) ** 2)
    k = st.columns(4)
    k[0].metric("Precio sucio actual", f"{p0:.3f}")
    k[1].metric("Revaluación exacta", f"{exacto:.3f}", f"{exacto / p0 - 1:+.2%}")
    kpi(k[2], "Solo duración", f"{solo_dur:.3f}", f"error {solo_dur - exacto:+.3f}")
    kpi(k[3], "Duración + convexidad", f"{dur_conv:.3f}", f"error {dur_conv - exacto:+.3f}")

    with st.expander("Tabla de flujos"):
        st.dataframe(tabla.round(6), hide_index=True, width="stretch")

# ---------------------------------------------------------------------------
# 6. Backtest
# ---------------------------------------------------------------------------
with tabs[5]:
    bt = backtest.copy()
    ret = bt[["Cartera_Equiponderada", "Benchmark_RECMTREU"]].pct_change().dropna()
    anos = (bt.index[-1] - bt.index[0]).days / 365.25

    def resumen(serie, r):
        total = serie.iloc[-1] / serie.iloc[0] - 1
        vol = r.std() * np.sqrt(12)
        dd = (serie / serie.cummax() - 1).min()
        return total, (1 + total) ** (1 / anos) - 1, vol, dd

    rc = resumen(bt["Cartera_Equiponderada"], ret["Cartera_Equiponderada"])
    rb = resumen(bt["Benchmark_RECMTREU"], ret["Benchmark_RECMTREU"])
    k = st.columns(4)
    k[0].metric("Retorno total cartera", f"{rc[0]:.2%}", f"{rc[0] - rb[0]:+.2%} vs benchmark")
    kpi(k[1], "Retorno anualizado", f"{rc[1]:.2%}", f"benchmark {rb[1]:.2%}")
    kpi(k[2], "Volatilidad anualizada", f"{rc[2]:.2%}", f"benchmark {rb[2]:.2%}")
    kpi(k[3], "Máximo drawdown", f"{rc[3]:.2%}", f"benchmark {rb[3]:.2%}")

    fig = go.Figure()
    fig.add_scatter(x=bt.index, y=bt["Cartera_Equiponderada"], name="Cartera equiponderada (TR)",
                    line=dict(width=2, color=C[0]), mode="lines+markers", marker=dict(size=8),
                    hovertemplate="%{x|%b %Y}: %{y:.2f}<extra>Cartera</extra>")
    fig.add_scatter(x=bt.index, y=bt["Benchmark_RECMTREU"], name="RECMTREU Index (TR)",
                    line=dict(width=2, color=C[1], dash="dash"), mode="lines+markers", marker=dict(size=8),
                    hovertemplate="%{x|%b %Y}: %{y:.2f}<extra>Benchmark</extra>")
    fig.update_layout(title="Evolución base 100 · rebalanceo mensual · precios MID", hovermode="x unified")
    mostrar(fig, 460)

    a, b = st.columns(2)
    with a:
        diff = (ret["Cartera_Equiponderada"] - ret["Benchmark_RECMTREU"]) * 100
        fig = go.Figure(go.Bar(x=diff.index, y=diff.values, marker_color=[C[0] if d >= 0 else C[7] for d in diff],
                               hovertemplate="%{x|%b %Y}: %{y:+.2f} pp<extra></extra>"))
        fig.update_layout(title="Exceso de retorno mensual frente al benchmark (pp)")
        mostrar(fig, 340)
    with b:
        fig = go.Figure(go.Scatter(x=bt.index, y=bt["Num_Bonos"], mode="lines+markers", line=dict(width=2, color=C[2]),
                                   marker=dict(size=8), hovertemplate="%{x|%b %Y}: %{y:.0f} bonos<extra></extra>"))
        fig.update_layout(title="Bonos vivos con precio en cada rebalanceo")
        mostrar(fig, 340)

    st.markdown(
        "- **Mejor que MID:** comprar al *ask* y vender al *bid* para incorporar el coste real de transacción.\n"
        "- **Benchmarks alternativos:** iBoxx EUR Corporates, Bloomberg Euro Aggregate Corporate o ICE BofA Euro Corporate."
    )

# ---------------------------------------------------------------------------
# 7. Cartera mandato
# ---------------------------------------------------------------------------
with tabs[6]:
    cm = cartera.copy()
    cm["Peso %"] = cm["Peso"] * 100
    cm["Es_HY"] = cm["Rating"].isin(HY) | cm["Rating"].eq("NR")
    tir = (cm["TIR"] * cm["Peso"]).sum()
    dur = (cm["Duracion_Modificada"] * cm["Peso"]).sum()
    pd_cartera = (cm["PD 1YR"] * cm["Peso"]).sum()
    hy = cm.loc[cm["Es_HY"], "Peso"].sum()

    k = st.columns(5)
    k[0].metric("TIR ponderada", f"{tir:.2f}%")
    k[1].metric("Duración modificada", f"{dur:.2f}")
    k[2].metric("Bonos", len(cm))
    k[3].metric("HY / sin rating", f"{hy:.0%}")
    k[4].metric("PD 1 año ponderada", f"{pd_cartera:.2%}")

    st.subheader("Restricciones del mandato")
    max_emisor = cm.groupby("Issuer")["Peso"].sum().max()
    checks = pd.DataFrame([
        ("Número de bonos ≤ 20", len(cm), len(cm) <= 20),
        ("Duración de la cartera ≤ 3 años", round(dur, 4), dur <= 3 + 1e-6),
        ("Exposición HY ≤ 10%", f"{hy:.2%}", hy <= 0.10 + 1e-6),
        ("Sin deuda subordinada", int(cm["Seniority"].str.contains("Subordinated").sum()), not cm["Seniority"].str.contains("Subordinated").any()),
        ("Emisiones > 500M", f"mín. {cm['Outstanding Amount'].min() / 1e6:,.0f}M", (cm["Outstanding Amount"] > 5e8).all()),
        ("Peso por emisión ≤ 10%", f"{cm['Peso'].max():.2%}", cm["Peso"].max() <= 0.10 + 1e-6),
        ("Concentración por emisor ≤ 15%", f"{max_emisor:.2%}", max_emisor <= 0.15 + 1e-6),
    ], columns=["Restricción", "Valor", "Cumple"])
    checks["Cumple"] = checks["Cumple"].map({True: "✅ Sí", False: "❌ No"})
    checks["Valor"] = checks["Valor"].astype(str)
    st.dataframe(checks, hide_index=True, width="stretch")

    a, b = st.columns(2)
    with a:
        orden = cm.sort_values("Peso")
        fig = go.Figure(go.Bar(x=orden["Peso %"], y=orden["Description"], orientation="h",
                               marker_color=[C[1] if h else C[0] for h in orden["Es_HY"]],
                               customdata=orden[["Issuer", "Rating", "TIR"]],
                               hovertemplate="%{y}<br>%{customdata[0]} · %{customdata[1]}<br>Peso %{x:.2f}% · TIR %{customdata[2]:.2f}%<extra></extra>"))
        fig.update_layout(title="Pesos por bono (naranja = HY / sin rating)", xaxis_title="Peso (%)")
        mostrar(fig, 440)
    with b:
        fig = px.scatter(cm, x="Duracion_Modificada", y="TIR", size="Peso %", color="Industry Sector",
                         hover_data={"Description": True, "Rating": True, "Peso %": ":.2f"},
                         labels={"Duracion_Modificada": "Duración modificada", "TIR": "TIR (%)"},
                         color_discrete_sequence=C)
        fig.update_traces(marker=dict(line=dict(width=1, color="white")))
        fig.add_vline(x=dur, line_dash="dot", line_color=GRIS, annotation_text=f"Duración cartera {dur:.2f}")
        fig.update_layout(title="TIR frente a duración (tamaño = peso)")
        mostrar(fig, 440)

    a, b = st.columns(2)
    with a:
        sec = cm.groupby("Industry Sector")["Peso %"].sum().sort_values()
        fig = go.Figure(go.Bar(x=sec.values, y=sec.index, orientation="h", marker_color=C[2],
                               hovertemplate="%{y}: %{x:.2f}%<extra></extra>"))
        fig.update_layout(title="Exposición sectorial (%)")
        mostrar(fig, 320)
    with b:
        rat = cm.groupby("Rating")["Peso %"].sum()
        rat = rat.reindex([r for r in ORDEN_RATING if r in rat.index])
        fig = go.Figure(go.Bar(x=rat.index, y=rat.values, marker_color=[C[1] if r in HY or r == "NR" else C[0] for r in rat.index],
                               hovertemplate="%{x}: %{y:.2f}%<extra></extra>"))
        fig.update_layout(title="Exposición por rating (%)")
        mostrar(fig, 320)

    st.warning(
        "El bono de Heathrow (XS1186176571) aporta una TIR del 21% porque es callable con *Next Call Date* en febrero de 2026 "
        "y cotiza a 93,7: el cálculo a la fecha de call (yield-to-call) dispara la rentabilidad. Es un buen ejemplo de por qué "
        "convendría usar *yield-to-worst* o restringir bonos con call muy próximo.",
        icon="⚠️",
    )

    cols = ["ISIN", "Description", "Issuer", "Industry Sector", "Rating", "Seniority", "Outstanding Amount",
            "Price", "TIR", "Duracion_Modificada", "PD 1YR", "spread", "Peso %"]
    st.dataframe(cm[cols].sort_values("Peso %", ascending=False).round(4), hide_index=True, width="stretch")

    with st.expander("Evolución histórica de precios de los bonos de la cartera"):
        ph = precios_historicos()
        sel = [i for i in cm["ISIN"] if i in ph.columns]
        serie = ph[sel].dropna(how="all").ffill()
        nombres = dict(zip(cm["ISIN"], cm["Description"]))
        fig = go.Figure()
        for i, isin in enumerate(sel):
            fig.add_scatter(x=serie.index, y=serie[isin], name=nombres[isin], mode="lines",
                            line=dict(width=2, color=C[i % len(C)] if i < len(C) else GRIS))
        fig.update_layout(title="Precio limpio histórico", hovermode="x unified")
        mostrar(fig, 460)

# ---------------------------------------------------------------------------
# 8. Coberturas
# ---------------------------------------------------------------------------
with tabs[7]:
    st.markdown("Parámetros de la cobertura (por defecto, los del notebook: cartera de 10 M€ con la duración de la cartera mandato).")
    p1, p2, p3 = st.columns(3)
    valor = p1.number_input("Valor de la cartera (€)", 1_000_000, 1_000_000_000, 10_000_000, step=1_000_000)
    dur_cartera = p2.number_input("Duración modificada de la cartera", 0.0, 15.0, float(round(dur, 4)), step=0.1)
    dur_obj = p3.slider("Duración objetivo tras la cobertura", 0.0, float(dur_cartera), 0.0, step=0.25)

    st.subheader("Riesgo de tipos de interés · futuros sobre bonos alemanes")
    dv01 = valor * dur_cartera / 1e4
    futuros = pd.DataFrame({
        "Futuro": ["Schatz (DU1)", "Bobl (OE1)", "Bund (RX1)"],
        "Ticker": ["DU1 Comdty", "OE1 Comdty", "RX1 Comdty"],
        "Duración CTD": [1.92, 5.44, 10.00],
    })
    futuros["Último precio"] = [varios[t].dropna().iloc[-1] for t in futuros["Ticker"]]
    futuros["Contratos (exacto)"] = (dur_cartera - dur_obj) * valor / (futuros["Duración CTD"] * 100_000)
    futuros["Contratos a vender"] = futuros["Contratos (exacto)"].round().astype(int)
    futuros["DV01 cubierto (€/pb)"] = futuros["Contratos a vender"] * futuros["Duración CTD"] * 100_000 / 1e4

    k = st.columns(3)
    k[0].metric("DV01 de la cartera", f"{dv01:,.0f} €/pb")
    k[1].metric("DV01 a cubrir", f"{valor * (dur_cartera - dur_obj) / 1e4:,.0f} €/pb")
    kpi(k[2], "Recomendado", "Bobl", f"{futuros.loc[1, 'Contratos a vender']} contratos")
    st.dataframe(futuros.drop(columns="Ticker").round(2), hide_index=True, width="stretch")
    st.caption("N = (D cartera − D objetivo) · V / (D CTD · 100.000 · CF), con CF = 1 y la duración del CTD igual a la teórica del contrato.")

    hist = varios[["DU1 Comdty", "OE1 Comdty", "RX1 Comdty"]].dropna()
    hist = hist / hist.iloc[0] * 100
    fig = go.Figure()
    for i, (col, nombre) in enumerate(zip(hist.columns, futuros["Futuro"])):
        fig.add_scatter(x=hist.index, y=hist[col], name=nombre, mode="lines", line=dict(width=2, color=C[i]))
    fig.update_layout(title="Futuros sobre bonos alemanes (base 100)", hovermode="x unified")
    mostrar(fig, 360)

    st.subheader("Riesgo de crédito · iTraxx")
    c1, c2 = st.columns(2)
    rpv01 = c1.number_input("RPV01 del CDS 5Y (DV01 por € nominal × 10⁴)", 1.0, 10.0, 4.5, step=0.1)
    cobertura = c2.slider("Porcentaje de cobertura", 0, 100, 100, step=10)
    cs01 = valor * dur_cartera / 1e4
    nominal_total = cs01 / (rpv01 / 1e4) * cobertura / 100
    spread_main = varios["ITRX EUR CDSI GEN 5Y Corp"].dropna().iloc[-1]
    spread_xo = varios["ITRX XOVER CDSI GEN 5Y Corp"].dropna().iloc[-1]
    n_main, n_xo = nominal_total * (1 - hy), nominal_total * hy
    coste = n_main * spread_main / 1e4 + n_xo * spread_xo / 1e4

    k = st.columns(4)
    k[0].metric("CS01 de la cartera", f"{cs01:,.0f} €/pb")
    kpi(k[1], f"iTraxx Main ({spread_main:.0f} pb)", f"{n_main:,.0f} €", "comprar protección")
    kpi(k[2], f"iTraxx Crossover ({spread_xo:.0f} pb)", f"{n_xo:,.0f} €", "comprar protección")
    kpi(k[3], "Coste anual (prima)", f"{coste:,.0f} €", f"{coste / valor:.2%} de la cartera")

    hist = varios[["ITRX EUR CDSI GEN 5Y Corp", "ITRX XOVER CDSI GEN 5Y Corp"]].dropna()
    a, b = st.columns(2)
    for col, (serie, nombre, color) in zip((a, b), [(hist.iloc[:, 0], "iTraxx Main 5Y", C[0]), (hist.iloc[:, 1], "iTraxx Crossover 5Y", C[1])]):
        with col:
            fig = go.Figure(go.Scatter(x=serie.index, y=serie, mode="lines", line=dict(width=2, color=color), name=nombre,
                                       hovertemplate="%{x|%d/%m/%Y}: %{y:.1f} pb<extra></extra>"))
            fig.update_layout(title=f"{nombre} (pb)")
            mostrar(fig, 320)

    st.markdown(
        "Una cobertura total elimina precisamente la prima de crédito que se busca al invertir en corporativos y "
        "arrastra *basis risk* (12 bonos frente a 125 emisores, duración 3 vs 5 años). Lo razonable es una cobertura "
        "parcial (30–50%) en momentos de estrés o de forma táctica."
    )
