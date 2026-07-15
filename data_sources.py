import yfinance as yf
import streamlit as st

@st.cache_data(ttl=3600)
def veri_cek(sembol):
    try:
        df = yf.download(sembol, period="1mo", progress=False)
        return df if not df.empty else None
    except:
        return None
