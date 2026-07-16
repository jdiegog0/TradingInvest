import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

# Configuración de página de Streamlit
st.set_page_config(
    page_title="Mi Portafolio de Inversión",
    page_icon="💼",
    layout="wide"
)

st.title("💼 Dashboard de Control & Proyección de Portafolio")
st.divider()

# ==========================================
# 1. FUNCIÓN PARA CARGAR DATOS Y PRECIOS (CON CACHÉ)
# ==========================================
@st.cache_data(ttl=900)
def procesar_portafolio_con_precios(ruta_excel):
    df_transacciones = pd.read_excel(ruta_excel)
    
    # Limpieza estándar de datos
    df_transacciones['Ticker'] = df_transacciones['Ticker'].str.strip().str.upper()
    df_transacciones['Fecha'] = pd.to_datetime(df_transacciones['Fecha']).dt.date
    df_transacciones['Tipo'] = df_transacciones['Tipo'].str.strip()
    df_transacciones['Sector'] = df_transacciones['Sector'].str.strip()
    
    tickers_unicos = df_transacciones['Ticker'].unique().tolist()
    precios_actuales = {}
    
    # Descargar precios actuales en lote
    try:
        datos_mercado = yf.download(tickers_unicos, period="1d", progress=False)['Close']
        for ticker in tickers_unicos:
            try:
                if len(tickers_unicos) == 1:
                    precio = float(datos_mercado.iloc[-1])
                else:
                    precio = float(datos_mercado[ticker].dropna().iloc[-1])
                precios_actuales[ticker] = precio
            except Exception:
                try:
                    t_obj = yf.Ticker(ticker)
                    precio = t_obj.info.get('currentPrice') or t_obj.info.get('previousClose')
                    precios_actuales[ticker] = float(precio) if precio else 0.0
                except Exception:
                    precios_actuales[ticker] = 0.0
    except Exception as e:
        st.warning(f"Error en la descarga masiva de precios: {e}")
        for ticker in tickers_unicos:
            precios_actuales[ticker] = 0.0
            
    return df_transacciones, precios_actuales

# ==========================================
# FUNCIÓN PARA CALCULAR RENDIMIENTOS HISTÓRICOS INDIVIDUALES (PUNTO 2.2)
# ==========================================
@st.cache_data(ttl=86400)  # Caché de 24 horas
def calcular_rendimientos_historicos(tickers):
    rendimientos = {}
    for ticker in tickers:
        try:
            # Descargamos 5 años de historial día a día
            hist = yf.download(ticker, period="5y", progress=False)
            if not hist.empty and 'Close' in hist.columns:
                serie_close = hist['Close'].dropna()
                if len(serie_close) > 10:
                    precio_inicial = float(serie_close.iloc[0])
                    precio_final = float(serie_close.iloc[-1])
                    
                    # Calcular años reales transcurridos en el dataset
                    fecha_ini = serie_close.index[0]
                    fecha_fin = serie_close.index[-1]
                    anios_reales = (fecha_fin - fecha_ini).days / 365.25
                    
                    if anios_reales > 0:
                        cagr = (precio_final / precio_inicial) ** (1 / anios_reales) - 1
                        # Límites más amplios para el modelo de análisis (entre -10% y 45%)
                        rendimientos[ticker] = float(max(min(cagr, 0.45), -0.10))
                    else:
                        rendimientos[ticker] = 0.08
                else:
                    rendimientos[ticker] = 0.08
            else:
                rendimientos[ticker] = 0.08
        except Exception:
            rendimientos[ticker] = 0.08
    return rendimientos

# Cargar el archivo principal
try:
    df_transacciones, precios_actuales = procesar_portafolio_con_precios("Portafolio.xlsx")
    
    # ==========================================
    # 2. PROCESAMIENTO Y CÁLCULOS GENERALES
    # ==========================================
    df_detalles = df_transacciones.copy()
    df_detalles['$/Acción actual'] = df_detalles['Ticker'].map(precios_actuales).fillna(0.0)
    df_detalles = df_detalles.rename(columns={
        'Acciones': '#Acciones',
        '$/Acción': '$/Acción compra',
        'USD': 'USD Total Compra'
    })
    df_detalles['USD Actual'] = df_detalles['#Acciones'] * df_detalles['$/Acción actual']
    df_detalles['$ ganancia (o perdida)'] = df_detalles['USD Actual'] - df_detalles['USD Total Compra']
    df_detalles['% de ganancia (o perdida)'] = (df_detalles['$ ganancia (o perdida)'] / df_detalles['USD Total Compra']) * 100

    # Agrupado por Ticker
    df_agrupado = df_detalles.groupby(['Ticker', 'Sector']).agg({
        '#Acciones': 'sum',
        'USD Total Compra': 'sum',
        'USD Actual': 'sum'
    }).reset_index()
    
    df_agrupado['$/Acción compra'] = df_agrupado['USD Total Compra'] / df_agrupado['#Acciones']
    df_agrupado['$/Acción actual'] = df_agrupado['Ticker'].map(precios_actuales).fillna(0.0)
    df_agrupado['$ ganancia (o perdida)'] = df_agrupado['USD Actual'] - df_agrupado['USD Total Compra']
    df_agrupado['% de ganancia (o perdida)'] = (df_agrupado['$ ganancia (o perdida)'] / df_agrupado['USD Total Compra']) * 100

    # Variables globales para las Métricas (Flags)
    total_inversion_inicial = df_agrupado['USD Total Compra'].sum()
    total_portafolio_actual = df_agrupado['USD Actual'].sum()
    rendimiento_total_pct = ((total_portafolio_actual - total_inversion_inicial) / total_inversion_inicial) * 100 if total_inversion_inicial > 0 else 0.0
    rendimiento_absoluto = total_portafolio_actual - total_inversion_inicial

    # Crear las Pestañas de la App
    tab_actual, tab_proyeccion = st.tabs(["📊 Portafolio Actual", "🔮 Modelo de Proyección"])

    # =========================================================================
    # PESTAÑA 1: PORTAFOLIO ACTUAL
    # =========================================================================
    with tab_actual:
        st.subheader("📌 Resumen del Portafolio")
        m_col1, m_col2, m_col3 = st.columns(3)
        
        with m_col1:
            st.metric(label="Total de Inversión (Costo Inicial)", value=f"${total_inversion_inicial:,.2f}")
        with m_col2:
            st.metric(label="Precio Portafolio Actual", value=f"${total_portafolio_actual:,.2f}", delta=f"${rendimiento_absoluto:+,.2f}")
        with m_col3:
            st.metric(label="Porcentaje Rendimiento Total", value=f"{rendimiento_total_pct:+.2f}%", delta="Retorno sobre inversión")
            
        st.divider()
        
        # Gráficos
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

        # Tablas
        st.subheader("📋 Resumen Consolidado de Inversiones (Tabla 2)")
        df_agrupado_final = df_agrupado[['Ticker', '#Acciones', 'USD Actual', '$/Acción compra', '$/Acción actual', '$ ganancia (o perdida)', '% de ganancia (o perdida)']].rename(columns={'USD Actual': 'USD'})
        
        df_t2_con_total = df_agrupado_final.copy()
        total_acciones = df_t2_con_total['#Acciones'].sum()
        total_usd_actual = df_t2_con_total['USD'].sum()
        total_costo_compra = df_agrupado['USD Total Compra'].sum()
        total_ganancia_abs = df_t2_con_total['$ ganancia (o perdida)'].sum()
        total_ganancia_pct = (total_ganancia_abs / total_costo_compra) * 100 if total_costo_compra > 0 else 0
        
        fila_total = pd.DataFrame([{'Ticker': 'TOTAL', '#Acciones': total_acciones, 'USD': total_usd_actual, '$/Acción compra': np.nan, '$/Acción actual': np.nan, '$ ganancia (o perdida)': total_ganancia_abs, '% de ganancia (o perdida)': total_ganancia_pct}])
        df_t2_con_total = pd.concat([df_t2_con_total, fila_total], ignore_index=True)
        
        st.dataframe(df_t2_con_total.style.format({
            '#Acciones': '{:,.4f}', 'USD': '${:,.2f}',
            '$/Acción compra': lambda x: f"${x:,.2f}" if pd.notnull(x) else "-",
            '$/Acción actual': lambda x: f"${x:,.2f}" if pd.notnull(x) else "-",
            '$ ganancia (o perdida)': '${:,.2f}', '% de ganancia (o perdida)': '{:+.2f}%'
        }), use_container_width=True, hide_index=True)

        st.divider()

        st.subheader("📜 Detalle de Transacciones Históricas (Tabla 3)")
        df_t3_mostrar = df_detalles[['Fecha', 'Tipo', 'Ticker', '#Acciones', 'USD Actual', '$/Acción compra', '$/Acción actual', '$ ganancia (o perdida)', '% de ganancia (o perdida)']].rename(columns={'USD Actual': 'USD'})
        st.dataframe(df_t3_mostrar.style.format({
            '#Acciones': '{:,.4f}', 'USD': '${:,.2f}', '$/Acción compra': '${:,.2f}', '$/Acción actual': '${:,.2f}', '$ ganancia (o perdida)': '${:,.2f}', '% de ganancia (o perdida)': '{:+.2f}%'
        }), use_container_width=True, hide_index=True)

    # =========================================================================
    # PESTAÑA 2: MODELO DE PROYECCIÓN 
    # =========================================================================
    with tab_proyeccion:
        st.subheader("🔮 Configuración de Simulación a 5 Años")
        
        # 1. PARÁMETROS SUPERIORES: APORTACIÓN (DCA) Y GRANULARIDAD (Puntos 1 y 3)
        col_ctrl1, col_ctrl2 = st.columns(2)
        with col_ctrl1:
            st.write("**💵 Aportaciones Adicionales (Opcional):**")
            dca_mensual = st.number_input("Inyección de capital mensual (DCA en USD)", min_value=0, value=0, step=50)
            st.caption("Se simula que compras este valor mensualmente de forma proporcional en tus activos actuales.")
            
        with col_ctrl2:
            st.write("**📅 Rango y Visualización del Tiempo:**")
            granularidad = st.radio(
                "Frecuencia de la proyección:",
                options=["Mes a Mes", "Año a Año"],
                horizontal=True
            )
            st.caption("Determina si el cálculo de la proyección y las tablas muestran la trayectoria detallada mensual o agrupada anual.")

        st.divider()

        # 2. CONFIGURACIÓN DE TASAS DE CRECIMIENTO HISTÓRICAS VS PROYECTADAS (Puntos 2 y 2.1)
        st.subheader("📈 Configuración de Tasas de Crecimiento Anual (Por Ticker)")
        st.markdown("La columna **'Tasa Proyectada (Futura)'** está habilitada para edición. Haz doble clic sobre cualquier celda para modificar la tasa y ver la simulación en tiempo real.")
        
        tickers_unicos_proyeccion = sorted(list(set(df_agrupado['Ticker'].tolist())))
        cagrs = calcular_rendimientos_historicos(tickers_unicos_proyeccion)
        
        # Construir el DataFrame dinámico para st.data_editor
        tasas_dict_list = []
        for ticker in tickers_unicos_proyeccion:
            tasa_hist = cagrs.get(ticker, 0.08)
            tasas_dict_list.append({
                "Ticker": ticker,
                "Tasa Histórica (Últimos 5 Años)": float(tasa_hist),
                "Tasa Proyectada (Futura)": float(tasa_hist) # Inicializado con la histórica
            })
        df_editor_input = pd.DataFrame(tasas_dict_list)
        
        # st.data_editor permite modificar los valores dinámicamente en pantalla
        df_editor_output = st.data_editor(
            df_editor_input,
            column_config={
                "Ticker": st.column_config.TextColumn("Ticker", disabled=True),
                "Tasa Histórica (Últimos 5 Años)": st.column_config.NumberColumn("Tasa Histórica (Últimos 5 Años)", format="%.2%", disabled=True),
                "Tasa Proyectada (Futura)": st.column_config.NumberColumn("Tasa Proyectada (Futura)", format="%.2%", min_value=-0.50, max_value=1.00, step=0.01)
            },
            hide_index=True,
            use_container_width=True,
            key="editor_tasas"
        )
        
        # Mapeamos las tasas proyectadas ingresadas por el usuario
        tasas_proyectadas = dict(zip(df_editor_output['Ticker'], df_editor_output['Tasa Proyectada (Futura)']))

        st.divider()

        # ---- CONSTRUCCIÓN DE LA SIMULACIÓN MEN DE PROYECCIÓN ----
        meses = 60  # 5 años
        fechas_proyeccion = [datetime.today().date() + pd.DateOffset(months=i) for i in range(meses + 1)]
        fechas_proyeccion = [f.date() for f in fechas_proyeccion]

        proyeccion_dict = {"Fecha": fechas_proyeccion}
        
        # Obtener pesos actuales para distribuir el DCA
        capital_inicial_total = df_agrupado['USD Actual'].sum()
        pesos_activos = {row['Ticker']: row['USD Actual'] / capital_inicial_total if capital_inicial_total > 0 else 0 for _, row in df_agrupado.iterrows()}

        for ticker in tickers_unicos_proyeccion:
            capital_inicial_activo = float(df_agrupado[df_agrupado['Ticker'] == ticker]['USD Actual'].iloc[0])
            tasa_anual = tasas_proyectadas.get(ticker, 0.08)
            tasa_mensual = (1 + tasa_anual) ** (1/12) - 1
            peso_activo = pesos_activos.get(ticker, 0)
            
            saldos_mes = [capital_inicial_activo]
            for m in range(1, meses + 1):
                # Aplicar rendimiento compuesto mensual + aportación DCA
                nuevo_saldo = saldos_mes[-1] * (1 + tasa_mensual) + (dca_mensual * peso_activo)
                saldos_mes.append(nuevo_saldo)
                
            proyeccion_dict[ticker] = saldos_mes

        df_proyeccion = pd.DataFrame(proyeccion_dict)
        df_proyeccion['Total Portafolio'] = df_proyeccion[tickers_unicos_proyeccion].sum(axis=1)

        # Si el usuario eligió ver la escala Año a Año, filtramos el dataframe
        if granularidad == "Año a Año":
            meses_corte = [0, 12, 24, 36, 48, 60]
            df_proyeccion_display = df_proyeccion.iloc[meses_corte].copy()
        else:
            df_proyeccion_display = df_proyeccion.copy()

        # ---- 3. SELECTOR DE TICKERS PARA EVITAR CONTAMINACIÓN VISUAL (Punto 3.1) ----
        st.subheader("📉 Gráfico de Evolución del Capital")
        
        col_sel, _ = st.columns([3, 1])
        with col_sel:
            tickers_seleccionados = st.multiselect(
                "Selecciona los Tickers que quieres analizar en la gráfica:",
                options=tickers_unicos_proyeccion,
                default=tickers_unicos_proyeccion
            )
            
        # ---- 4. DIBUJAR GRÁFICA DE EVOLUCIÓN ----
        fig_lineas = go.Figure()
        
        # Línea de capital total (siempre visible)
        fig_lineas.add_trace(go.Scatter(
            x=df_proyeccion_display['Fecha'],
            y=df_proyeccion_display['Total Portafolio'],
            mode='lines+markers' if granularidad == "Año a Año" else 'lines',
            name='Capital Total Proyectado',
            line=dict(color='#00ffcc', width=4)
        ))
        
        # Líneas individuales solo para los tickers seleccionados
        for ticker in tickers_seleccionados:
            fig_lineas.add_trace(go.Scatter(
                x=df_proyeccion_display['Fecha'],
                y=df_proyeccion_display[ticker],
                mode='lines+markers' if granularidad == "Año a Año" else 'lines',
                name=f"{ticker} Proyectado",
                line=dict(width=1.5),
                opacity=0.7
            ))

        fig_lineas.update_layout(
            template="plotly_dark",
            xaxis_title="Fecha",
            yaxis_title="Capital Estimado (USD)",
            hovermode="x unified",
            margin=dict(t=20, b=20, l=10, r=10)
        )
        st.plotly_chart(fig_lineas, use_container_width=True)

        st.divider()

        # ---- 5. TABLA DESGLOSADA POR TICKER ----
        st.subheader("📋 Detalle de Saldos Proyectados")
        
        # Generar la tabla estructurada para mostrar a fin de año
        meses_corte_tabla = [0, 12, 24, 36, 48, 60]
        df_cortes = df_proyeccion.iloc[meses_corte_tabla].copy()
        
        # Eliminamos la columna de fecha antes de transponer
        df_cortes_sin_fecha = df_cortes.drop(columns=['Fecha'])
        
        # Transponer el DataFrame
        df_cortes_transpuesto = df_cortes_sin_fecha.T
        
        # Definimos las columnas anuales
        columnas_años = ["Capital Inicial", "Año 1", "Año 2", "Año 3", "Año 4", "Año 5"]
        df_cortes_transpuesto.columns = columnas_años
        
        # Resetear el índice para dejar los Tickers como columna limpia
        df_cortes_transpuesto = df_cortes_transpuesto.reset_index().rename(columns={'index': 'Ticker'})

        # Formatear visualmente con signo de dólar
        formatos_tabla = {col: "${:,.2f}" for col in columnas_años}
        st.dataframe(
            df_cortes_transpuesto.style.format(formatos_tabla),
            use_container_width=True,
            hide_index=True
        )

except FileNotFoundError:
    st.error("⚠️ No se encontró el archivo 'Portafolio.xlsx' en el directorio. Asegúrate de guardarlo junto a app.py.")
except Exception as e:
    st.error(f"⚠️ Ocurrió un error inesperado: {e}")
