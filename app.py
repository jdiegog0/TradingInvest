import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

# Configuración de página
st.set_page_config(
    page_title="Mi Portafolio de Inversión",
    page_icon="💼",
    layout="wide"
)

st.title("💼 Dashboard de Control & Proyección de Portafolio")
st.divider()

# ==========================================
# 1. FUNCIÓN PARA CARGAR PRECIOS ACTUALES
# ==========================================
@st.cache_data(ttl=900)
def procesar_portafolio_con_precios(ruta_excel):
    df_transacciones = pd.read_excel(ruta_excel)
    
    df_transacciones['Ticker'] = df_transacciones['Ticker'].str.strip().str.upper()
    df_transacciones['Fecha'] = pd.to_datetime(df_transacciones['Fecha']).dt.date
    df_transacciones['Tipo'] = df_transacciones['Tipo'].str.strip()
    df_transacciones['Sector'] = df_transacciones['Sector'].str.strip()
    
    tickers_unicos = df_transacciones['Ticker'].unique().tolist()
    precios_actuales = {}
    
    try:
        data = yf.download(tickers_unicos, period="1d", progress=False)
        # Compatibilidad con MultiIndex de nuevas versiones de yfinance
        if isinstance(data.columns, pd.MultiIndex):
            cierres = data.xs('Close', level=0, axis=1) if 'Close' in data.columns.levels[0] else data['Close']
        else:
            cierres = pd.DataFrame(data['Close'])
            if len(tickers_unicos) == 1: cierres.columns = tickers_unicos

        for ticker in tickers_unicos:
            if ticker in cierres.columns:
                precios_actuales[ticker] = float(cierres[ticker].dropna().iloc[-1])
            else:
                precios_actuales[ticker] = 0.0
    except Exception:
        for ticker in tickers_unicos: precios_actuales[ticker] = 0.0
            
    return df_transacciones, precios_actuales

# ==========================================
# 2. MOTOR MATEMÁTICO HISTÓRICO (AÑO A AÑO)
# ==========================================
@st.cache_data(ttl=86400)
def obtener_analisis_historico(tickers):
    historico_dict = {t: {"retornos": {}, "cagr": 0.08} for t in tickers}
    if not tickers: return historico_dict
    
    try:
        # Descargamos 6 años en bloque para asegurar 5 saltos anuales perfectos
        data = yf.download(tickers, period="6y", progress=False)
        
        if isinstance(data.columns, pd.MultiIndex):
            cierres = data.xs('Close', level=0, axis=1) if 'Close' in data.columns.levels[0] else data['Close']
        else:
            cierres = pd.DataFrame(data['Close'])
            if len(tickers) == 1: cierres.columns = tickers

        cierres.index = pd.to_datetime(cierres.index)
        # Agrupar por año y extraer el último precio de cierre
        anual_precios = cierres.groupby(cierres.index.year).last()
        # Porcentaje de cambio año contra año
        anual_retornos = anual_precios.pct_change().dropna()
        
        ultimos_5_anios = anual_retornos.tail(5)
        
        for ticker in tickers:
            if ticker in ultimos_5_anios.columns:
                retornos_reales = ultimos_5_anios[ticker].dropna()
                ret_dict = {str(k): float(v) for k, v in retornos_reales.items()}
                
                precios_validos = anual_precios[ticker].dropna()
                if len(precios_validos) > 1:
                    p_ini = precios_validos.iloc[0]
                    p_fin = precios_validos.iloc[-1]
                    anios = len(precios_validos) - 1
                    cagr = (p_fin / p_ini) ** (1/anios) - 1
                else:
                    cagr = 0.08
                    
                historico_dict[ticker] = {
                    "retornos": ret_dict,
                    "cagr": max(min(float(cagr), 0.45), -0.10) # Límite sano -10% a 45%
                }
    except Exception as e:
        pass 
        
    return historico_dict

# Cargar datos locales
try:
    df_transacciones, precios_actuales = procesar_portafolio_con_precios("Portafolio.xlsx")
    
    # Cálculos Generales
    df_detalles = df_transacciones.copy()
    df_detalles['$/Acción actual'] = df_detalles['Ticker'].map(precios_actuales).fillna(0.0)
    df_detalles = df_detalles.rename(columns={'Acciones': '#Acciones', '$/Acción': '$/Acción compra', 'USD': 'USD Total Compra'})
    df_detalles['USD Actual'] = df_detalles['#Acciones'] * df_detalles['$/Acción actual']
    df_detalles['$ ganancia (o perdida)'] = df_detalles['USD Actual'] - df_detalles['USD Total Compra']
    df_detalles['% de ganancia (o perdida)'] = (df_detalles['$ ganancia (o perdida)'] / df_detalles['USD Total Compra']) * 100

    df_agrupado = df_detalles.groupby(['Ticker', 'Sector']).agg({'#Acciones': 'sum', 'USD Total Compra': 'sum', 'USD Actual': 'sum'}).reset_index()
    df_agrupado['$/Acción compra'] = df_agrupado['USD Total Compra'] / df_agrupado['#Acciones']
    df_agrupado['$/Acción actual'] = df_agrupado['Ticker'].map(precios_actuales).fillna(0.0)
    df_agrupado['$ ganancia (o perdida)'] = df_agrupado['USD Actual'] - df_agrupado['USD Total Compra']
    df_agrupado['% de ganancia (o perdida)'] = (df_agrupado['$ ganancia (o perdida)'] / df_agrupado['USD Total Compra']) * 100

    total_inversion_inicial = df_agrupado['USD Total Compra'].sum()
    total_portafolio_actual = df_agrupado['USD Actual'].sum()
    rendimiento_total_pct = ((total_portafolio_actual - total_inversion_inicial) / total_inversion_inicial) * 100 if total_inversion_inicial > 0 else 0.0
    rendimiento_absoluto = total_portafolio_actual - total_inversion_inicial

    tab_actual, tab_proyeccion = st.tabs(["📊 Portafolio Actual", "🔮 Modelo de Proyección"])

    # =========================================================================
    # PESTAÑA 1: PORTAFOLIO ACTUAL (Sin Cambios - Ya optimizado)
    # =========================================================================
    with tab_actual:
        st.subheader("📌 Resumen del Portafolio")
        m_col1, m_col2, m_col3 = st.columns(3)
        with m_col1: st.metric(label="Total de Inversión (Costo Inicial)", value=f"${total_inversion_inicial:,.2f}")
        with m_col2: st.metric(label="Precio Portafolio Actual", value=f"${total_portafolio_actual:,.2f}", delta=f"${rendimiento_absoluto:+,.2f}")
        with m_col3: st.metric(label="Porcentaje Rendimiento Total", value=f"{rendimiento_total_pct:+.2f}%", delta="Retorno sobre inversión")
            
        st.divider()
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("📊 Distribución por Sector")
            df_sector = df_agrupado.groupby('Sector')['USD Actual'].sum().reset_index()
            fig_sector = px.pie(df_sector, values='USD Actual', names='Sector', hole=0.4, color_discrete_sequence=px.colors.sequential.Tealgrn)
            fig_sector.update_layout(template="plotly_dark", margin=dict(t=10, b=10, l=10, r=10))
            st.plotly_chart(fig_sector, use_container_width=True)
            
        with col2:
            st.subheader("🎯 Distribución por Activo (Ticker)")
            fig_ticker = px.pie(df_agrupado, values='USD Actual', names='Ticker', hole=0.4, color_discrete_sequence=px.colors.sequential.Viridis)
            fig_ticker.update_layout(template="plotly_dark", margin=dict(t=10, b=10, l=10, r=10))
            st.plotly_chart(fig_ticker, use_container_width=True)

        st.divider()
        st.subheader("📋 Resumen Consolidado de Inversiones (Tabla 2)")
        df_agrupado_final = df_agrupado[['Ticker', '#Acciones', 'USD Actual', '$/Acción compra', '$/Acción actual', '$ ganancia (o perdida)', '% de ganancia (o perdida)']].rename(columns={'USD Actual': 'USD'})
        df_t2_con_total = df_agrupado_final.copy()
        
        fila_total = pd.DataFrame([{'Ticker': 'TOTAL', '#Acciones': df_t2_con_total['#Acciones'].sum(), 'USD': df_t2_con_total['USD'].sum(), '$/Acción compra': np.nan, '$/Acción actual': np.nan, '$ ganancia (o perdida)': df_t2_con_total['$ ganancia (o perdida)'].sum(), '% de ganancia (o perdida)': ((df_t2_con_total['$ ganancia (o perdida)'].sum() / df_agrupado['USD Total Compra'].sum()) * 100) if df_agrupado['USD Total Compra'].sum() > 0 else 0}])
        df_t2_con_total = pd.concat([df_t2_con_total, fila_total], ignore_index=True)
        st.dataframe(df_t2_con_total.style.format({'#Acciones': '{:,.4f}', 'USD': '${:,.2f}', '$/Acción compra': lambda x: f"${x:,.2f}" if pd.notnull(x) else "-", '$/Acción actual': lambda x: f"${x:,.2f}" if pd.notnull(x) else "-", '$ ganancia (o perdida)': '${:,.2f}', '% de ganancia (o perdida)': '{:+.2f}%'}), use_container_width=True, hide_index=True)

        st.divider()
        st.subheader("📜 Detalle de Transacciones Históricas (Tabla 3)")
        df_t3_mostrar = df_detalles[['Fecha', 'Tipo', 'Ticker', '#Acciones', 'USD Actual', '$/Acción compra', '$/Acción actual', '$ ganancia (o perdida)', '% de ganancia (o perdida)']].rename(columns={'USD Actual': 'USD'})
        st.dataframe(df_t3_mostrar.style.format({'#Acciones': '{:,.4f}', 'USD': '${:,.2f}', '$/Acción compra': '${:,.2f}', '$/Acción actual': '${:,.2f}', '$ ganancia (o perdida)': '${:,.2f}', '% de ganancia (o perdida)': '{:+.2f}%'}), use_container_width=True, hide_index=True)

    # =========================================================================
    # PESTAÑA 2: MODELO DE PROYECCIÓN (REDISEÑO TOTAL)
    # =========================================================================
    with tab_proyeccion:
        st.subheader("🔮 Configuración de Simulación a 5 Años")
        
        # 1. PARÁMETROS SUPERIORES (Aportaciones arriba)
        col_ctrl1, col_ctrl2 = st.columns(2)
        with col_ctrl1:
            st.write("**💵 Aportaciones Adicionales (Opcional):**")
            dca_mensual = st.number_input("Inyección de capital mensual (DCA en USD)", min_value=0, value=100, step=50)
            st.caption("Capital que sumarás mes a mes distribuido en tus activos.")
            
        with col_ctrl2:
            st.write("**📅 Rango y Visualización del Tiempo:**")
            granularidad = st.radio("Frecuencia de la gráfica:", options=["Mes a Mes", "Año a Año"], horizontal=True)

        st.divider()

        # 2. CONFIGURACIÓN DE TASAS: HISTORIA VS FUTURO AÑO A AÑO
        st.write("**📈 Configuración de Tasas de Crecimiento Anual (Por Ticker)**")
        st.markdown("Revisa el comportamiento real de tus activos en los últimos años. Las columnas verdes (Próximos 5 Años) **son editables**, haz doble clic sobre ellas si quieres ajustar el crecimiento proyectado en un año específico.")
        
        tickers_unicos_proyeccion = sorted(list(set(df_agrupado['Ticker'].tolist())))
        historial_datos = obtener_analisis_historico(tickers_unicos_proyeccion)
        
        # Extraer los años históricos dinámicamente (ej: 2021, 2022, 2023...)
        años_hist = set()
        for v in historial_datos.values(): años_hist.update(v["retornos"].keys())
        años_hist = sorted(list(años_hist))[-5:]
        
        # Construir matriz de datos para el editor
        filas_editor = []
        for ticker in tickers_unicos_proyeccion:
            fila = {"Ticker": ticker}
            for yr in años_hist: 
                fila[f"Histórico {yr}"] = historial_datos[ticker]["retornos"].get(yr, 0.0)
            
            cagr = historial_datos[ticker]["cagr"]
            # Setear el CAGR promedio del activo por defecto para los próximos 5 años
            for i in range(1, 6): fila[f"Proyección Año {i}"] = cagr
            filas_editor.append(fila)
            
        df_editor_input = pd.DataFrame(filas_editor)
        
        # Configurar las propiedades de las columnas (Bloquear históricas, permitir edición en proyecciones)
        column_config = {"Ticker": st.column_config.TextColumn("Ticker", disabled=True)}
        for yr in años_hist:
            column_config[f"Histórico {yr}"] = st.column_config.NumberColumn(f"Hist. {yr}", format="%.2%", disabled=True)
        for i in range(1, 6):
            column_config[f"Proyección Año {i}"] = st.column_config.NumberColumn(f"Año {i} (Proy)", format="%.2%", min_value=-0.99, max_value=2.0, step=0.01)
            
        # Renderizar Editor
        df_editor_output = st.data_editor(df_editor_input, column_config=column_config, hide_index=True, use_container_width=True)
        
        # Extraer las tasas anuales proyectadas para el motor de simulación
        tasas_proyectadas_matrices = {}
        for _, row in df_editor_output.iterrows():
            tasas_proyectadas_matrices[row['Ticker']] = [row[f'Proyección Año {i}'] for i in range(1, 6)]

        st.divider()

        # 3. SELECTOR DE TICKERS PARA LA GRÁFICA
        st.subheader("📉 Gráfico de Evolución del Capital")
        tickers_seleccionados = st.multiselect("Selecciona los activos a graficar (Desmarca para limpiar la vista):", options=tickers_unicos_proyeccion, default=tickers_unicos_proyeccion)

        # ---- 4. MOTOR DE SIMULACIÓN MATEMÁTICO (Mes a mes con tasas que varían por año) ----
        meses = 60
        fechas_proyeccion = [datetime.today().date() + pd.DateOffset(months=i) for i in range(meses + 1)]
        fechas_proyeccion = [f.date() for f in fechas_proyeccion]

        proyeccion_dict = {"Fecha": fechas_proyeccion}
        capital_inicial_total = df_agrupado['USD Actual'].sum()
        pesos_activos = {row['Ticker']: row['USD Actual'] / capital_inicial_total if capital_inicial_total > 0 else 0 for _, row in df_agrupado.iterrows()}

        for ticker in tickers_unicos_proyeccion:
            saldos_mes = [float(df_agrupado[df_agrupado['Ticker'] == ticker]['USD Actual'].iloc[0])]
            tasas_anuales_ticker = tasas_proyectadas_matrices[ticker]
            peso_activo = pesos_activos.get(ticker, 0)
            
            for m in range(1, meses + 1):
                # Determinar en qué año de la proyección estamos (0 al 4) para usar la tasa correcta
                año_idx = (m - 1) // 12
                tasa_mensual = (1 + tasas_anuales_ticker[año_idx]) ** (1/12) - 1
                
                nuevo_saldo = saldos_mes[-1] * (1 + tasa_mensual) + (dca_mensual * peso_activo)
                saldos_mes.append(nuevo_saldo)
                
            proyeccion_dict[ticker] = saldos_mes

        df_proyeccion = pd.DataFrame(proyeccion_dict)
        df_proyeccion['Total Portafolio'] = df_proyeccion[tickers_unicos_proyeccion].sum(axis=1)

        # Filtrar si el usuario quiere ver agrupado anual
        df_display = df_proyeccion.iloc[[0, 12, 24, 36, 48, 60]].copy() if granularidad == "Año a Año" else df_proyeccion.copy()

        # ---- 5. DIBUJAR GRÁFICA INTERACTIVA ----
        fig_lineas = go.Figure()
        
        # Capital Total
        fig_lineas.add_trace(go.Scatter(x=df_display['Fecha'], y=df_display['Total Portafolio'], mode='lines+markers' if granularidad == "Año a Año" else 'lines', name='Total Proyectado', line=dict(color='#00ffcc', width=4)))
        
        # Líneas individuales filtradas
        for ticker in tickers_seleccionados:
            fig_lineas.add_trace(go.Scatter(x=df_display['Fecha'], y=df_display[ticker], mode='lines+markers' if granularidad == "Año a Año" else 'lines', name=f"{ticker}", line=dict(width=1.5), opacity=0.7))

        fig_lineas.update_layout(template="plotly_dark", xaxis_title="Tiempo", yaxis_title="Capital Estimado (USD)", hovermode="x unified")
        st.plotly_chart(fig_lineas, use_container_width=True)

        st.divider()

        # ---- 6. TABLA DESGLOSADA FINAL ----
        st.subheader("📋 Detalle de Saldos Proyectados")
        df_cortes = df_proyeccion.iloc[[0, 12, 24, 36, 48, 60]].copy().drop(columns=['Fecha']).T
        df_cortes.columns = ["Capital Inicial", "Año 1", "Año 2", "Año 3", "Año 4", "Año 5"]
        df_cortes = df_cortes.reset_index().rename(columns={'index': 'Ticker'})

        st.dataframe(df_cortes.style.format({col: "${:,.2f}" for col in df_cortes.columns if col != 'Ticker'}), use_container_width=True, hide_index=True)

except FileNotFoundError:
    st.error("⚠️ No se encontró el archivo 'Portafolio.xlsx' en el directorio.")
