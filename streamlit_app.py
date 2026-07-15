import streamlit as st
from data_sources import veri_cek
from indicators import hesapla_teknikler
from utils import donusum_noktalari_hesapla

st.set_page_config(page_title="Finans Veri Ajani", layout="wide")

# Veri Seçimi
sembol = st.sidebar.selectbox("Varlık Seçin", ["AAPL", "BTC-USD", "THYAO.IS", "EURUSD=X"])

# İşlem Akışı
df = veri_cek(sembol)

if df is not None:
    df_analiz = hesapla_teknikler(df)
    analiz = donusum_noktalari_hesapla(df_analiz)
    
    st.title(f"{sembol} Analizi")
    col1, col2, col3 = st.columns(3)
    col1.metric("Fiyat", f"{analiz['fiyat']:.2f}")
    col2.metric("Destek", f"{analiz['destek']:.2f}")
    col3.metric("Direnç", f"{analiz['direnc']:.2f}")
    
    st.line_chart(df_analiz[['Close', 'SMA_20']])
else:
    st.error("Veri alınamadı, lütfen tekrar deneyin.")
