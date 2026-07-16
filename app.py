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
st.markdown("Análisis dinámico con sectores e información financiera en tiempo real desde Yahoo Finance.")
st.divider()

# ==========================================
# 1. FUNCIÓN PARA CARGAR DATOS Y LLAMAR LA API
# ==========================================
@st.cache_data(ttl=1800)  # Caché de 30 minutos para optimizar llamadas
def procesar_portafolio_con_api(ruta_csv):
    # Leer el CSV directamente
    df_transacciones = pd.read_csv(ruta_csv)
    
    # Estandarizar nombres de columnas y strings
    df_transacciones['Ticker'] = df_transacciones['Ticker'].str.strip().str.upper()
    df_transacciones['Fecha'] = pd.to_datetime(df_transacciones['Fecha']).dt.date
    df_transacciones['Tipo'] = df_transacciones['Tipo'].str.strip()
    
    # Obtener tickers únicos
    tickers_unicos = df_transacciones['Ticker'].unique().tolist()
    
    precios_actuales = {}
    sectores = {}
    
    # --- CORRECCIÓN DE LA API ---
    # Descargamos los precios actuales en un solo bloque (lote) para evitar bloqueos por rate-limiting
    try:
        datos_mercado = yf.download(tickers_unicos, period="1d")['Close']
        for ticker in tickers_unicos:
            try:
                # Si solo hay un ticker, 'datos_mercado' será una Serie de Pandas. 
                # Si hay varios tickers, será un DataFrame de Pandas.
                if isinstance(datos_mercado, pd.Series):
                    precio = float(datos_mercado.iloc[-1])
                else:
                    # Obtenemos el último valor no nulo de la columna del ticker
                    precio = float(datos_mercado[ticker].dropna().iloc[-1])
                precios_actuales[ticker] = precio
            except Exception:
                # Si falla al extraer el precio del lote, dejamos 0.0 de manera segura
                precios_actuales[ticker] = 0.0
    except Exception as e:
        st.warning(f"Error al descargar precios en lote: {e}. Se intentará de forma individual.")
        for ticker in tickers_unicos:
            precios_actuales[ticker] = 0.0

    # Ahora consultamos de forma individual el Sector para no sobrecargar de peticiones pesadas la API de .info
    for ticker in tickers_unicos:
        try:
            ticker_obj = yf.Ticker(ticker)
            # .info es una petición muy pesada. La protegemos con un try/except interno.
            info = ticker_obj.info
            if info:
                sector = info.get('sector') or info.get('category') or 'Otros/ETF'
            else:
                sector = 'Otros/ETF'
            sectores[ticker] = sector
            
            # Salvaguarda por si falló la descarga en lote para este ticker en particular
            if precios_actuales.get(ticker, 0.0) == 0.0:
                precio_fallback = info.get('currentPrice') or info.get('previousClose')
                if precio_fallback:
                    precios_actuales[ticker] = float(precio_fallback)
        except Exception:
            # Si se cae la API .info para este activo, el flujo principal no se detiene
            sectores[ticker] = 'Otros/ETF'
            if ticker not in precios_actuales:
                precios_actuales[ticker] = 0.0

    return df_transacciones, precios_actuales, sectores

# Intentar cargar y procesar usando el nombre del CSV
try:
    df_transacciones, precios_actuales, sectores = procesar_portafolio_con_api("Portafolio.xlsx - Transacciones.csv")
    
    # ==========================================
    # 2. PROCESAMIENTO Y CÁLCULOS
    # ==========================================
    df_detalles = df_transacciones.copy()
    
    # Mapeamos la información obtenida desde la API de forma segura (.get evita errores de KeyError)
    df_detalles['Sector'] = df_detalles['Ticker'].map(sectores).fillna('Otros/ETF')
    df_detalles['$/Acción actual'] = df_detalles['Ticker'].map(precios_actuales).fillna(0.0)
    
    # Renombrar columnas para coincidir exactamente con el estándar solicitado
    df_detalles = df_detalles.rename(columns={
        'Acciones': '#Acciones',
        '$/Acción': '$/Acción compra',
        'USD': 'USD Total Compra'
    })
    
    # Cálculos de mercado en tiempo real
    df_detalles['USD Actual'] = df_detalles['#Acciones'] * df_detalles['$/Acción actual']
    df_detalles['$ ganancia (o perdida)'] = df_detalles['USD Actual'] - df_detalles['USD Total Compra']
    df_detalles['% de ganancia (o perdida)'] = (df_detalles['$ ganancia (o perdida)'] / df_detalles['USD Total Compra']) * 100

    # ==========================================
    # LÓGICA DE AGRUPACIÓN (TABLA 2)
    # ==========================================
    df_agrupado = df_detalles.groupby(['Ticker', 'Sector']).agg({
        '#Acciones': 'sum',
        'USD Total Compra': 'sum',
        'USD Actual': 'sum'
    }).reset_index()
    
    # Recalculamos métricas grupales de rendimiento ponderado para la cartera consolidada
    df_agrupado['$/Acción compra'] = df_agrupado['USD Total Compra'] / df_agrupado['#Acciones']
    df_agrupado['$/Acción actual'] = df_agrupado['Ticker'].map(precios_actuales).fillna(0.0)
    df_agrupado['$ ganancia (o perdida)'] = df_agrupado['USD Actual'] - df_agrupado['USD Total Compra']
    df_agrupado['% de ganancia (o perdida)'] = (df_agrupado['$ ganancia (o perdida)'] / df_agrupado['USD Total Compra']) * 100

    # Formar estructura final para Tabla 2
    df_agrupado_final = df_agrupado[[
        'Ticker', '#Acciones', 'USD Actual', '$/Acción compra', 
        '$/Acción actual', '$ ganancia (o perdida)', '% de ganancia (o perdida)'
    ]].rename(columns={'USD Actual': 'USD'})

    # ==========================================
    # 3. VISUALIZACIONES (FILA 1)
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
    
    # Totales globales de la cartera
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
    # TABLA 3: Transacciones Históricas Completas
    # ==========================================
    st.subheader("📜 Detalle de Transacciones Históricas (Tabla 3)")
    
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
    st.error("⚠️ No se encontró el archivo 'Portafolio.xlsx - Transacciones.csv'. Asegúrate de guardarlo con ese nombre exacto junto a app.py.")
except Exception as e:
    st.error(f"⚠️ Ocurrió un error inesperado al procesar el archivo: {e}")
