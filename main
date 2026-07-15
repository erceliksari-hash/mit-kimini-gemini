import streamlit as st
import yfinance as yf
import requests
import pandas as pd
import numpy as np
from datetime import datetime

# ============================================
# SESSION STATE & YAPILANDIRMA
# ============================================
st.set_page_config(page_title="Finans Veri Ajani Pro", page_icon="📊", layout="wide")

def init_session_state():
    if "takip_listesi" not in st.session_state:
        st.session_state.takip_listesi = [
            {"sembol": "AAPL", "isim": "Apple", "tur": "Hisse (ABD)"},
            {"sembol": "THYAO.IS", "isim": "Turk Hava Yollari", "tur": "BIST 100"},
            {"sembol": "BTC-USD", "isim": "Bitcoin", "tur": "Kripto"}
        ]
    if "portfoy" not in st.session_state:
        st.session_state.portfoy = {}
    if "aktif_sembol" not in st.session_state:
        st.session_state.aktif_sembol = "AAPL"

init_session_state()

# ============================================
# KUTUPHANE SINIFI (Mevcut yapıyı korudum)
# ============================================
class InvestingComKutuphane:
    def get_all(self):
        return {
            "BIST 100": [("THYAO.IS", "THY"), ("GARAN.IS", "Garanti"), ("XU100.IS", "BIST 100")],
            "Hisse (ABD)": [("AAPL", "Apple"), ("MSFT", "Microsoft"), ("NVDA", "NVIDIA")],
            "Kripto": [("BTC-USD", "Bitcoin"), ("ETH-USD", "Ethereum")],
            "Forex": [("USDTRY=X", "USD/TRY"), ("EURUSD=X", "EUR/USD")]
        }

# ============================================
# MOTOR SINIFI (Hız ve Bildirim Entegrasyonu)
# ============================================
class FinansMotoru:
    @staticmethod
    @st.cache_data(ttl=600)
    def veri_indir(sembol: str, periyot: str = "1y"):
        try:
            df = yf.download(sembol, period=periyot, interval="1d", progress=False)
            return df if not df.empty else None
        except:
            return None

    @staticmethod
    def teknik_hesapla(df: pd.DataFrame):
        df['SMA_20'] = df['Close'].rolling(window=20).mean()
        df['SMA_50'] = df['Close'].rolling(window=50).mean()
        delta = df['Close'].diff()
        gain = (delta.clip(lower=0)).rolling(window=14).mean()
        loss = (-delta.clip(upper=0)).rolling(window=14).mean()
        df['RSI'] = 100 - (100 / (1 + (gain / loss)))
        return df

    @staticmethod
    def ai_yorum(df: pd.DataFrame):
        son_fiyat = df['Close'].iloc[-1]
        rsi = df['RSI'].iloc[-1]
        if rsi > 70: return "⚠️ Aşırı alım bölgesi. Dikkatli olun!"
        if rsi < 30: return "✅ Aşırı satım bölgesi. Alım fırsatı olabilir."
        return "📈 Piyasa dengeli seyrediyor."

    @staticmethod
    def telegram_bildir(mesaj: str):
        # Buraya kendi bot bilgilerinizi girin
        TOKEN = "TELEGRAM_BOT_TOKENINIZ"
        CHAT_ID = "CHAT_IDNIZ"
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        try:
            requests.get(url, params={"chat_id": CHAT_ID, "text": mesaj}, timeout=5)
        except:
            pass

# ============================================
# SIDEBAR
# ============================================
st.sidebar.title("🔍 Veri Ajanı")
kategori = st.sidebar.selectbox("Piyasa", list(InvestingComKutuphane().get_all().keys()))
varliklar = InvestingComKutuphane().get_all()[kategori]
secim = st.sidebar.selectbox("Varlık Seçin", [v[1] for v in varliklar])
st.session_state.aktif_sembol = [v[0] for v in varliklar if v[1] == secim][0]

# ============================================
# ANA EKRAN
# ============================================
st.title(f"📊 {secim} Analiz Paneli")
df = FinansMotoru.veri_indir(st.session_state.aktif_sembol)

if df is not None:
    df = FinansMotoru.teknik_hesapla(df)
    
    # Metrikler
    c1, c2 = st.columns(2)
    c1.metric("Son Fiyat", f"{df['Close'].iloc[-1]:.2f}")
    c2.metric("RSI", f"{df['RSI'].iloc[-1]:.2f}")
    
    # AI Yorum ve Bildirim
    yorum = FinansMotoru.ai_yorum(df)
    st.info(f"🧠 Ajan Yorumu: {yorum}")
    
    if st.button("Bildirimi Telegram'a Gönder"):
        FinansMotoru.telegram_bildir(f"{secim} için güncel durum: {yorum}")
        st.success("Bildirim gönderildi!")
    
    # Portföy
    adet = st.number_input("Adet", min_value=1)
    if st.button("Portföye Ekle"):
        st.session_state.portfoy[st.session_state.aktif_sembol] = adet
        st.success("Portföye eklendi.")

else:
    st.error("Veri alınamadı.")
