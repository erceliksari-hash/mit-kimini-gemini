import yfinance as yf
import streamlit as st

@st.cache_data(ttl=300)
def veri_cek(sembol, periyot="1mo"):
    try:
        df = yf.download(sembol, period=periyot, interval="1d", progress=False)
        if df.empty:
            return None
        return df
    except Exception as e:
        st.error(f"Veri çekme hatası ({sembol}): {e}")
        return None
