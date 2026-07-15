import streamlit as st
import yfinance as yf

@st.cache_data(ttl=3600)
def veri_cek(sembol):
    try:
        df = yf.download(sembol, period="1mo", auto_adjust=True, progress=False)
        # Sütunları düzelt (MultiIndex sorununu engellemek için)
        if hasattr(df.columns, 'get_level_values'):
            df.columns = df.columns.get_level_values(0)
            
        if df is None or df.empty:
            return None
        return df
    except Exception as e:
        return None
