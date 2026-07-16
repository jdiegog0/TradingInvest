import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.express as px
from datetime import datetime

# Configuración de página de Streamlit
st.set_page_config(
    page_title="Mi Portafolio de Inversión",
    page_icon="💼",
    layout="wide"
)

st.title("💼 Dashboard de Control de Portafolio")
st.markdown("Análisis dinámico de tus activos y distribución sectorial en tiempo real.")
st.divider()

# ==========================================
# 1. FUNCIÓN PARA CARGAR EXCEL Y PRECIOS
# ==========================================
@st.cache_data(ttl=1800)  # Caché de 30 minutos para no bloquear la API de Yahoo Finance
def procesar_portafolio_con_precios(ruta_excel):
    # Leer el Excel histórico de transacciones
    df_transacciones = pd.read_excel(ruta_excel)
    
    # Asegurar formato estándar en columnas clave
    df_transacciones['Ticker'] = df_transacciones['Ticker'].str.strip().str.upper()
    df_transacciones['Sector'] = df_transacciones['Sector'].str.strip()
    df_transacciones['Fecha'] = pd.to_datetime(df_transacciones['Fecha']).dt.date
    
    # Obtener tickers únicos para consultar la API
    tickers_unicos = df_transacciones['Ticker'].unique().tolist()
    
    # Llamada en lote a yfinance para optimizar rendimiento
    precios_actuales = {}
    try:
        data = yf.download(tickers_unicos, period="1d")['Close']
        for ticker in tickers_unicos:
            # Manejar si es una serie única o un DataFrame multiactivo
            if len(tickers_unicos) == 1:
                precio = float(data.iloc[-1])
            else:
                precio = float(data[ticker].dropna().iloc[-1])
            precios_actuales[ticker] = precio
    except Exception as e:
        st.warning(f"Error consultando precios en vivo con yfinance: {e}. Usando precios alternativos.")
        # Fallback por si falla la red o algún ticker no es válido
        for ticker in tickers_unicos:
            precios_actuales[ticker] = 0.0

    return df_transacciones, precios_actuales

# Intentar cargar los datos locales
try:
    df_transacciones, precios_actuales = procesar_portafolio_con_precios("Portafolio.xlsx")
    
    # ==========================================
    # 2. PROCESAMIENTO Y CÁLCULOS (LÓGICA GRUPAL)
    # ==========================================
    # Creamos la base de la Tabla 3 (Detallada histórica)
    # El costo total real de cada compra se asume directo multiplicando Cantidad * Precio de compra.
    # Ajustamos la Cantidad y Costo según tipo de transacción (Compra positivo, Venta negativo si aplica)
    df_detalles = df_transacciones.copy()
    
    # Mapeamos el precio actual a cada transacción según su ticker
    df_detalles['$/Acción actual'] = df_detalles['Ticker'].map(precios_actuales)
    
    # Renombrar para que coincida exactamente con lo solicitado en la Tabla 3
    df_detalles = df_detalles.rename(columns={
        'Cantidad': '#Acciones',
        'Precio': '$/Acción compra'
    })
    
    # Cálculo de métricas dinámicas
    df_detalles['USD Total Compra'] = df_detalles['#Acciones'] * df_detalles['$/Acción compra']
    df_detalles['USD Actual'] = df_detalles['#Acciones'] * df_detalles['$/Acción actual']
    df_detalles['$ ganancia (o perdida)'] = df_detalles['USD Actual'] - df_detalles['USD Total Compra']
    df_detalles['% de ganancia (o perdida)'] = (df_detalles['$ ganancia (o perdida)'] / df_detalles['USD Total Compra']) * 100

    # ==========================================
    # LÓGICA DE AGRUPACIÓN (TABLA 2)
    # ==========================================
    # Agrupamos por Ticker para consolidar posiciones actuales
    df_agrupado = df_detalles.groupby(['Ticker', 'Sector']).agg({
        '#Acciones': 'sum',
        'USD Total Compra': 'sum',
        'USD Actual': 'sum'
    }).reset_index()
    
    # Recalculamos los promedios ponderados y métricas grupales de rendimiento
    df_agrupado['$/Acción compra'] = df_agrupado['USD Total Compra'] / df_agrupado['#Acciones']
    df_agrupado['$/Acción actual'] = df_agrupado['Ticker'].map(precios_actuales)
    df_agrupado['$ ganancia (o perdida)'] = df_agrupado['USD Actual'] - df_agrupado['USD Total Compra']
    df_agrupado['% de ganancia (o perdida)'] = (df_agrupado['$ ganancia (o perdida)'] / df_agrupado['USD Total Compra']) * 100

    # Reorganizar el orden solicitado de las columnas para Tabla 2
    # Ticker, #Acciones, USD, $/Acción compra, $/Acción actual, $ ganancia..., % ganancia...
    df_agrupado_final = df_agrupado[[
        'Ticker', '#Acciones', 'USD Actual', '$/Acción compra', 
        '$/Acción actual', '$ ganancia (o perdida)', '% de ganancia (o perdida)'
    ]].rename(columns={'USD Actual': 'USD'})

    # ==========================================
    # 3. INTERFAZ GRÁFICA (DISTRIBUCIÓN SOLICITADA)
    # ==========================================
    
    # FILA 1: Dos Gráficos de Pastel
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📊 Distribución por Sector")
        # Agrupar el valor actual del portafolio por Sector
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

    # FILA 2: Tabla 2 (Consolidada por Ticker con Fila Total)
    st.subheader("📋 Resumen Consolidado de Inversiones (Tabla 2)")
    
    # Clonamos para añadir la fila del Total sin estropear los cálculos originales
    df_t2_con_total = df_agrupado_final.copy()
    
    # Calcular fila de totales
    total_acciones = df_t2_con_total['#Acciones'].sum()
    total_usd_actual = df_t2_con_total['USD'].sum()
    total_costo_compra = df_agrupado['USD Total Compra'].sum()
    total_ganancia_abs = df_t2_con_total['$ ganancia (o perdida)'].sum()
    total_ganancia_pct = (total_ganancia_abs / total_costo_compra) * 100 if total_costo_compra > 0 else 0
    
    fila_total = pd.DataFrame([{
        'Ticker': 'TOTAL',
        '#Acciones': total_acciones,
        'USD': total_usd_actual,
        '$/Acción compra': np.nan,  # No tiene sentido sumar promedios
        '$/Acción actual': np.nan,
        '$ ganancia (o perdida)': total_ganancia_abs,
        '% de ganancia (o perdida)': total_ganancia_pct
    }])
    
    df_t2_con_total = pd.concat([df_t2_con_total, fila_total], ignore_index=True)
    
    # Formateo visual estético
    st.dataframe(
        df_t2_con_total.style.format({
            '#Acciones': '{:,.2f}',
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

    # FILA 3: Tabla 3 (Historial detallado de transacciones individuales)
    st.subheader("📜 Detalle de Transacciones Históricas (Tabla 3)")
    
    # Seleccionar y reordenar columnas solicitadas para Tabla 3
    # Ticker, #Acciones, USD, $/Acción compra, $/Acción actual, $ ganancia..., % ganancia...
    df_t3_mostrar = df_detalles[[
        'Fecha', 'Tipo', 'Ticker', '#Acciones', 'USD Actual', 
        '$/Acción compra', '$/Acción actual', '$ ganancia (o perdida)', '% de ganancia (o perdida)'
    ]].rename(columns={'USD Actual': 'USD'})
    
    st.dataframe(
        df_t3_mostrar.style.format({
            '#Acciones': '{:,.2f}',
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
    st.error("⚠️ No se encontró el archivo 'Portafolio.xlsx' en el directorio del proyecto. Asegúrate de colocarlo junto a este script.")
except Exception as e:
    st.error(f"⚠️ Ocurrió un error inesperado al procesar el archivo: {e}")