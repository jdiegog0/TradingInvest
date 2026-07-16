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
    
    # Descargar precios actuales en bloque
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
# FUNCIÓN PARA CALCULAR RENDIMIENTOS HISTÓRICOS (EL MODELO DE ANÁLISIS)
# ==========================================
@st.cache_data(ttl=86400)  # Caché de 24 horas
def calcular_rendimientos_historicos(tickers):
    rendimientos = {}
    for ticker in tickers:
        try:
            # Descargamos 5 años de historial para estimar el retorno anualizado (CAGR)
            hist = yf.download(ticker, period="5y", progress=False)['Close']
            if not hist.empty:
                precio_inicial = float(hist.dropna().iloc[0])
                precio_final = float(hist.dropna().iloc[-1])
                anios = len(hist) / 252  # ~252 días laborables al año
                
                cagr = (precio_final / precio_inicial) ** (1 / anios) - 1
                # Límites realistas para la proyección (4% a 25%)
                rendimientos[ticker] = max(min(cagr, 0.25), 0.04)  
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
        
        # 1. BANDERAS / FLAGS DE MÉTRICAS (Ubicadas horizontalmente arriba de los gráficos)
        st.subheader("📌 Resumen del Portafolio")
        m_col1, m_col2, m_col3 = st.columns(3)
        
        with m_col1:
            st.metric(
                label="Total de Inversión (Costo Inicial)", 
                value=f"${total_inversion_inicial:,.2f}"
            )
        with m_col2:
            st.metric(
                label="Precio Portafolio Actual (Valor de Mercado)", 
                value=f"${total_portafolio_actual:,.2f}",
                delta=f"${rendimiento_absoluto:+,.2f}"
            )
        with m_col3:
            st.metric(
                label="Porcentaje Rendimiento Total", 
                value=f"{rendimiento_total_pct:+.2f}%",
                delta="Retorno sobre inversión"
            )
            
        st.divider()
        
        # 2. GRÁFICOS DE PASTEL
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

        # TABLA 2: Consolidada
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

        # TABLA 3: Detalle histórico
        st.subheader("📜 Detalle de Transacciones Históricas (Tabla 3)")
        df_t3_mostrar = df_detalles[['Fecha', 'Tipo', 'Ticker', '#Acciones', 'USD Actual', '$/Acción compra', '$/Acción actual', '$ ganancia (o perdida)', '% de ganancia (o perdida)']].rename(columns={'USD Actual': 'USD'})
        st.dataframe(df_t3_mostrar.style.format({
            '#Acciones': '{:,.4f}', 'USD': '${:,.2f}', '$/Acción compra': '${:,.2f}', '$/Acción actual': '${:,.2f}', '$ ganancia (o perdida)': '${:,.2f}', '% de ganancia (o perdida)': '{:+.2f}%'
        }), use_container_width=True, hide_index=True)

    # =========================================================================
    # PESTAÑA 2: MODELO DE PROYECCIÓN (A 5 AÑOS MES A MES)
    # =========================================================================
    with tab_proyeccion:
        st.subheader("🔮 Simulación de Crecimiento de Capital (5 Años)")
        st.markdown("Esta proyección utiliza las tasas de crecimiento reales calculadas por nuestro modelo de análisis histórico de los últimos 5 años.")

        # Obtener rendimientos históricos calculados (Modelo de análisis)
        tickers_unicos_proyeccion = sorted(list(set(df_agrupado['Ticker'].tolist())))
        cagrs = calcular_rendimientos_historicos(tickers_unicos_proyeccion)
        
        col_p1, col_p2 = st.columns(2)
        
        # Panel izquierdo: Tabla de Tasas de Crecimiento del Modelo de Análisis
        with col_p1:
            st.write("**📈 Tasas de Crecimiento Anual Estimadas por Ticker (Modelo de Análisis):**")
            
            # Construir un DataFrame limpio para la visualización de la tabla de tasas
            tasas_data = []
            for ticker in tickers_unicos_proyeccion:
                tasas_data.append({
                    "Ticker": ticker,
                    "Tasa de Crecimiento (CAGR)": cagrs.get(ticker, 0.08)
                })
            df_tasas_modelo = pd.DataFrame(tasas_data)
            
            # Mostrar la tabla de tasas formateada
            st.dataframe(
                df_tasas_modelo.style.format({"Tasa de Crecimiento (CAGR)": "{:.2%}"}),
                use_container_width=True,
                hide_index=True
            )
            
        # Panel derecho: Control de DCA mensual
        with col_p2:
            st.write("**💵 Aportaciones Adicionales (Opcional):**")
            dca_mensual = st.number_input("Inyección de capital mensual (DCA en USD)", min_value=0, value=0, step=50)
            st.caption("Si agregas un monto aquí, se simula que compras este valor mensualmente distribuyéndolo de forma proporcional en tus posiciones actuales.")

        # ---- CONSTRUCCIÓN DE LA SIMULACIÓN MES A MES ----
        meses = 60  # 5 años
        fechas_proyeccion = [datetime.today().date() + pd.DateOffset(months=i) for i in range(meses + 1)]
        fechas_proyeccion = [f.date() for f in fechas_proyeccion]

        proyeccion_dict = {"Fecha": fechas_proyeccion}
        
        # Obtener pesos actuales para el DCA
        capital_inicial_total = df_agrupado['USD Actual'].sum()
        pesos_activos = {row['Ticker']: row['USD Actual'] / capital_inicial_total if capital_inicial_total > 0 else 0 for _, row in df_agrupado.iterrows()}

        # Simular mes a mes por ticker usando la tasa fija asignada por el modelo
        for ticker in tickers_unicos_proyeccion:
            capital_inicial_activo = float(df_agrupado[df_agrupado['Ticker'] == ticker]['USD Actual'].iloc[0])
            tasa_anual = cagrs.get(ticker, 0.08)
            tasa_mensual = (1 + tasa_anual) ** (1/12) - 1
            peso_activo = pesos_activos.get(ticker, 0)
            
            saldos_mes = [capital_inicial_activo]
            for m in range(1, meses + 1):
                nuevo_saldo = saldos_mes[-1] * (1 + tasa_mensual) + (dca_mensual * peso_activo)
                saldos_mes.append(nuevo_saldo)
                
            proyeccion_dict[ticker] = saldos_mes

        df_proyeccion = pd.DataFrame(proyeccion_dict)
        df_proyeccion['Total Portafolio'] = df_proyeccion[tickers_unicos_proyeccion].sum(axis=1)

        # ---- 1. GRÁFICO DE LÍNEAS TEMPORALES ----
        fig_lineas = go.Figure()
        
        # Línea de capital total
        fig_lineas.add_trace(go.Scatter(
            x=df_proyeccion['Fecha'],
            y=df_proyeccion['Total Portafolio'],
            mode='lines',
            name='Capital Total Proyectado',
            line=dict(color='#00ffcc', width=4)
        ))
        
        # Líneas individuales por ticker
        for ticker in tickers_unicos_proyeccion:
            fig_lineas.add_trace(go.Scatter(
                x=df_proyeccion['Fecha'],
                y=df_proyeccion[ticker],
                mode='lines',
                name=f"{ticker} Proyectado",
                line=dict(width=1.5),
                opacity=0.6
            ))

        fig_lineas.update_layout(
            template="plotly_dark",
            title="Evolución Estimada del Capital a 5 Años",
            xaxis_title="Fecha de Proyección",
            yaxis_title="Capital Estimado (USD)",
            hovermode="x unified"
        )
        st.plotly_chart(fig_lineas, use_container_width=True)

        st.divider()

        # ---- 2. TABLA DESGLOSADA POR TICKER ----
        st.subheader("📋 Tabla de Saldos Proyectados Fin de Año (Mes 12 a 60)")
        
        # Seleccionamos las filas correspondientes a los cierres anuales (Meses 0, 12, 24, 36, 48, 60)
        meses_corte = [0, 12, 24, 36, 48, 60]
        df_cortes = df_proyeccion.iloc[meses_corte].copy()
        
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
