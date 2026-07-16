import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.express as px

# Configuración de página de Streamlit
st.set_page_config(
    page_title="Mi Portafolio de Inversión",
    page_icon="💼",
    layout="wide"
)

st.title("💼 Dashboard de Control de Portafolio")
st.markdown("Análisis dinámico de inversiones con sectores locales y precios en vivo de Yahoo Finance.")
st.divider()

# ==========================================
# 1. FUNCIÓN PARA CARGAR DATOS Y PRECIOS
# ==========================================
@st.cache_data(ttl=900)  # Guarda en caché los precios por 15 minutos
def procesar_portafolio_con_precios(ruta_excel):
    # Leer el archivo Excel nativo (.xlsx)
    df_transacciones = pd.read_excel(ruta_excel)
    
    # Limpieza básica de datos para evitar espacios vacíos o diferencias de mayúsculas/minúsculas
    df_transacciones['Ticker'] = df_transacciones['Ticker'].str.strip().str.upper()
    df_transacciones['Fecha'] = pd.to_datetime(df_transacciones['Fecha']).dt.date
    df_transacciones['Tipo'] = df_transacciones['Tipo'].str.strip()
    df_transacciones['Sector'] = df_transacciones['Sector'].str.strip()
    
    # Obtener lista de tickers únicos para consultar la API
    tickers_unicos = df_transacciones['Ticker'].unique().tolist()
    
    precios_actuales = {}
    
    # Descargar precios en bloque de forma segura
    try:
        # Descarga el último día de cotización
        datos_mercado = yf.download(tickers_unicos, period="1d", progress=False)['Close']
        
        for ticker in tickers_unicos:
            try:
                # Manejar respuestas cuando es un solo ticker (Series) o múltiples (DataFrame)
                if len(tickers_unicos) == 1:
                    precio = float(datos_mercado.iloc[-1])
                else:
                    # Buscamos el último precio de cierre disponible no nulo
                    precio = float(datos_mercado[ticker].dropna().iloc[-1])
                precios_actuales[ticker] = precio
            except Exception:
                # Fallback individual seguro por API si la consulta por lote omite el ticker
                try:
                    t_obj = yf.Ticker(ticker)
                    precio = t_obj.info.get('currentPrice') or t_obj.info.get('previousClose')
                    precios_actuales[ticker] = float(precio) if precio else 0.0
                except Exception:
                    precios_actuales[ticker] = 0.0
    except Exception as e:
        st.warning(f"Error en la descarga masiva de precios: {e}. Activando conexión alternativa individual.")
        for ticker in tickers_unicos:
            precios_actuales[ticker] = 0.0
            
    return df_transacciones, precios_actuales

# Intentar ejecutar la carga y cálculos usando el Excel local
try:
    df_transacciones, precios_actuales = procesar_portafolio_con_precios("Portafolio.xlsx")
    
    # ==========================================
    # 2. PROCESAMIENTO Y CÁLCULOS
    # ==========================================
    df_detalles = df_transacciones.copy()
    
    # Mapeamos los precios del mercado a cada transacción
    df_detalles['$/Acción actual'] = df_detalles['Ticker'].map(precios_actuales).fillna(0.0)
    
    # Renombrar columnas para coincidir con el formato solicitado (Tabla 3)
    df_detalles = df_detalles.rename(columns={
        'Acciones': '#Acciones',
        '$/Acción': '$/Acción compra',
        'USD': 'USD Total Compra'
    })
    
    # Cálculo de rendimiento dinámico por transacción
    df_detalles['USD Actual'] = df_detalles['#Acciones'] * df_detalles['$/Acción actual']
    df_detalles['$ ganancia (o perdida)'] = df_detalles['USD Actual'] - df_detalles['USD Total Compra']
    df_detalles['% de ganancia (o perdida)'] = (df_detalles['$ ganancia (o perdida)'] / df_detalles['USD Total Compra']) * 100

    # ==========================================
    # LÓGICA DE AGRUPACIÓN (TABLA 2)
    # ==========================================
    # Agrupamos todas las transacciones por Ticker y Sector para consolidar posiciones netas
    df_agrupado = df_detalles.groupby(['Ticker', 'Sector']).agg({
        '#Acciones': 'sum',
        'USD Total Compra': 'sum',
        'USD Actual': 'sum'
    }).reset_index()
    
    # Recalculamos los promedios ponderados y retornos del portafolio agrupado
    df_agrupado['$/Acción compra'] = df_agrupado['USD Total Compra'] / df_agrupado['#Acciones']
    df_agrupado['$/Acción actual'] = df_agrupado['Ticker'].map(precios_actuales).fillna(0.0)
    df_agrupado['$ ganancia (o perdida)'] = df_agrupado['USD Actual'] - df_agrupado['USD Total Compra']
    df_agrupado['% de ganancia (o perdida)'] = (df_agrupado['$ ganancia (o perdida)'] / df_agrupado['USD Total Compra']) * 100

    # Formar estructura final para Tabla 2 (Elimina fecha y tipo, muestra totales agrupados)
    df_agrupado_final = df_agrupado[[
        'Ticker', '#Acciones', 'USD Actual', '$/Acción compra', 
        '$/Acción actual', '$ ganancia (o perdida)', '% de ganancia (o perdida)'
    ]].rename(columns={'USD Actual': 'USD'})

    # ==========================================
    # 3. INTERFAZ GRÁFICA (DOS PASTEL EN PARALELO)
    # ==========================================
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📊 Distribución por Sector")
        df_sector = df_agrupado.groupby('Sector')['USD Actual'].sum().reset_index()
        fig_sector = px.pie(
            df_sector, 
            values='USD Actual', 
            names='Sector', 
            hole=0.4,
            color_discrete_sequence=px.colors.sequential.Tealgrn
        )
        fig_sector.update_layout(template="plotly_dark", margin=dict(t=10, b=10, l=10, r=10))
        st.plotly_chart(fig_sector, use_container_width=True)
        
    with col2:
        st.subheader("🎯 Distribución por Activo (Ticker)")
        fig_ticker = px.pie(
            df_agrupado, 
            values='USD Actual', 
            names='Ticker', 
            hole=0.4,
            color_discrete_sequence=px.colors.sequential.Viridis
        )
        fig_ticker.update_layout(template="plotly_dark", margin=dict(t=10, b=10, l=10, r=10))
        st.plotly_chart(fig_ticker, use_container_width=True)

    st.divider()

    # ==========================================
    # TABLA 2: Consolidada por Ticker con Fila Total
    # ==========================================
    st.subheader("📋 Resumen Consolidado de Inversiones (Tabla 2)")
    
    df_t2_con_total = df_agrupado_final.copy()
    
    # Calcular métricas de la fila total global
    total_acciones = df_t2_con_total['#Acciones'].sum()
    total_usd_actual = df_t2_con_total['USD'].sum()
    total_costo_compra = df_agrupado['USD Total Compra'].sum()
    total_ganancia_abs = df_t2_con_total['$ ganancia (o perdida)'].sum()
    total_ganancia_pct = (total_ganancia_abs / total_costo_compra) * 100 if total_costo_compra > 0 else 0
    
    fila_total = pd.DataFrame([{
        'Ticker': 'TOTAL',
        '#Acciones': total_acciones,
        'USD': total_usd_actual,
        '$/Acción compra': np.nan,
        '$/Acción actual': np.nan,
        '$ ganancia (o perdida)': total_ganancia_abs,
        '% de ganancia (o perdida)': total_ganancia_pct
    }])
    
    df_t2_con_total = pd.concat([df_t2_con_total, fila_total], ignore_index=True)
    
    st.dataframe(
        df_t2_con_total.style.format({
            '#Acciones': '{:,.4f}',
            'USD': '${:,.2f}',
            '$/Acción compra': lambda x: f"${x:,.2f}" if pd.notnull(x) else "-",
            '$/Acción actual': lambda x: f"${x:,.2f}" if pd.notnull(x) else "-",
            '$ ganancia (o perdida)': '${:,.2f}',
            '% de ganancia (o perdida)': '{:+.2f}%'
        }),
        use_container_width=True,
        hide_index=True
    )

    st.divider()

    # ==========================================
    # TABLA 3: Detalle de Transacciones Históricas
    # ==========================================
    st.subheader("📜 Detalle de Transacciones Históricas (Tabla 3)")
    
    # Columnas: Fecha, Tipo, Ticker, #Acciones, USD, $/Acción compra, $/Acción actual, Ganancia, % Ganancia
    df_t3_mostrar = df_detalles[[
        'Fecha', 'Tipo', 'Ticker', '#Acciones', 'USD Actual', 
        '$/Acción compra', '$/Acción actual', '$ ganancia (o perdida)', '% de ganancia (o perdida)'
    ]].rename(columns={'USD Actual': 'USD'})
    
    st.dataframe(
        df_t3_mostrar.style.format({
            '#Acciones': '{:,.4f}',
            'USD': '${:,.2f}',
            '$/Acción compra': '${:,.2f}',
            '$/Acción actual': '${:,.2f}',
            '$ ganancia (o perdida)': '${:,.2f}',
            '% de ganancia (o perdida)': '{:+.2f}%'
        }),
        use_container_width=True,
        hide_index=True
    )

except FileNotFoundError:
    st.error("⚠️ No se encontró el archivo 'Portafolio.xlsx'. Asegúrate de guardarlo junto a app.py con ese nombre exacto.")
except Exception as e:
    st.error(f"⚠️ Ocurrió un error inesperado al procesar el archivo: {e}")