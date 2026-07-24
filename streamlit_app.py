import streamlit as st
import requests
import threading
import time
from data_sources import veri_cek
from indicators import hesapla_teknikler, sinyal_kontrol, piyasa_analizi_yap
from utils import donusum_noktalari_hesapla
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
import plotly.graph_objects as go
import pandas as pd

st.set_page_config(page_title="Finansal Analiz Paneli", layout="wide")

# Modern Stil
st.markdown("""<style>.stApp { background-color: #0e1117; }</style>""", unsafe_allow_html=True)

# ==============================================================================
# TELEGRAM BİLDİRİM FONKSİYONU
# ==============================================================================
def telegram_bildirim_gonder(mesaj):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": mesaj,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload)
        return response.json()
    except Exception as e:
        print(f"Telegram bildirimi gönderilemedi: {e}")

# ==============================================================================
# ARKA PLANDA ÇALIŞAN 7/24 SAATLİK OTOMATİK BOT (THREADING)
# ==============================================================================
def otomatik_saatlik_tarama():
    time.sleep(15)  # Uygulama açıldıktan 15 saniye sonra ilk döngüyü başlatır
    while True:
        try:
            varliklar_listesi = ["AAPL", "BTC-USD", "EURUSD=X", "ISMEN.IS", "THYAO.IS"]
            ozet_mesaj = "🚨 *Otomatik Saatlik Pozisyon & Stop-Loss Raporu*\n\n"
            
            for varlik in varliklar_listesi:
                df_t = veri_cek(varlik, aralik="1h")
                if df_t is not None and not df_t.empty:
                    df_t_analiz = hesapla_teknikler(df_t)
                    p_analiz = donusum_noktalari_hesapla(df_t_analiz)
                    p_sinyal = sinyal_kontrol(df_t_analiz)
                    
                    if "AL" in p_sinyal.upper():
                        pozisyon = "🟢 *LONG*"
                        stop_loss = p_analiz['destek'] * 0.99
                    elif "SAT" in p_sinyal.upper():
                        pozisyon = "🔴 *SHORT*"
                        stop_loss = p_analiz['direnc'] * 1.01
                    else:
                        pozisyon = "⚪ *NÖTR*"
                        stop_loss = p_analiz['destek'] * 0.98
                        
                    ozet_mesaj += f"• *{varlik}*: Fiyat: `{p_analiz['fiyat']:.2f}` | Tavsiye: {pozisyon} | Stop-Loss: `{stop_loss:.2f}`\n"
                else:
                    ozet_mesaj += f"• *{varlik}*: Veri alınamadı!\n"
                    
            telegram_bildirim_gonder(ozet_mesaj)
        except Exception as e:
            print(f"Arka plan bot döngü hatası: {e}")
            
        time.sleep(3600)  # Her 1 saatte (3600 saniye) bir tekrar çalışır

# Botun tek bir kez arka planda çalışmasını sağlayan global kontrol
if "arkaplan_bot_aktif" not in globals():
    globals()["arkaplan_bot_aktif"] = True
    bot_thread = threading.Thread(target=otomatik_saatlik_tarama, daemon=True)
    bot_thread.start()
# ==============================================================================

# Session State Başlatma
if "varliklar" not in st.session_state:
    st.session_state.varliklar = ["AAPL", "BTC-USD", "EURUSD=X", "ISMEN.IS", "THYAO.IS"]

if "aktif_varlik" not in st.session_state:
    st.session_state.aktif_varlik = st.session_state.varliklar[0]

if "aktif_sekme" not in st.session_state:
    st.session_state.aktif_sekme = "🔍 Tekli Analiz & Varlık Ekle"

# Sidebar - Varlık Yönetimi ve Görünüm Seçimi
st.sidebar.title("📊 Piyasa Paneli")

sayfa_secenekleri = ["🔍 Tekli Analiz & Varlık Ekle", "🚀 Toplu Portföy Taraması"]
current_index = sayfa_secenekleri.index(st.session_state.aktif_sekme) if st.session_state.aktif_sekme in sayfa_secenekleri else 0

sayfa = st.sidebar.radio("Görünüm Seçin", sayfa_secenekleri, index=current_index)

if sayfa != st.session_state.aktif_sekme:
    st.session_state.aktif_sekme = sayfa
    st.rerun()

aralik = st.sidebar.selectbox(
    "Zaman Dilimi", 
    ["15m", "1h", "4h", "1d", "1wk", "1mo"], 
    format_func=lambda x: {
        "15m": "15 Dakikalık",
        "1h": "1 Saatlik",
        "4h": "4 Saatlik",
        "1d": "Günlük",
        "1wk": "1 Haftalık",
        "1mo": "1 Aylık"
    }[x]
)

st.sidebar.divider()

hazir_listeler = {
    "BIST Hisseleri": {
        "ISMEN (İş Yatırım)": "ISMEN.IS",
        "THYAO (Türk Hava Yolları)": "THYAO.IS",
        "GARAN (Garanti BBVA)": "GARAN.IS",
        "ASELS (Aselsan)": "ASELS.IS",
        "EREGL (Ereğli Demir Çelik)": "EREGL.IS",
        "ASTOR (Astor Enerji)": "ASTOR.IS",
        "BIMAS (BİM Mağazalar)": "BIMAS.IS",
        "AKBNK (Akbank)": "AKBNK.IS",
        "KCHOL (Koç Holding)": "KCHOL.IS",
        "TUPRS (Tüpraş)": "TUPRS.IS"
    },
    "Kripto Para": {
        "Bitcoin (BTC)": "BTC-USD",
        "Ethereum (ETH)": "ETH-USD",
        "Solana (SOL)": "SOL-USD",
        "Ripple (XRP)": "XRP-USD",
        "Cardano (ADA)": "ADA-USD"
    },
    "Global & Forex": {
        "Apple (AAPL)": "AAPL",
        "Tesla (TSLA)": "TSLA",
        "Microsoft (MSFT)": "MSFT",
        "EUR/USD": "EURUSD=X",
        "USD/TRY": "USDTRY=X"
    }
}

# --- GÖRÜNÜM 1: TEKLİ ANALİZ VE EKLEME ---
if st.session_state.aktif_sekme == "🔍 Tekli Analiz & Varlık Ekle":
    st.sidebar.subheader("🔍 Varlık Ekle")
    
    with st.sidebar.form(key="kod_ekleme_formu"):
        arama_input = st.text_input("Varlık / Hisse Kodu Ara", placeholder="Örn: ISMEN.IS, TSLA").upper().strip()
        submit_kod = st.form_submit_button("➕ Kod ile Ekle")
        
    if submit_kod:
        if arama_input:
            mevcut_buyuk = [v.upper() for v in st.session_state.varliklar]
            if arama_input not in mevcut_buyuk:
                test_df = veri_cek(arama_input, aralik=aralik)
                if test_df is not None and not test_df.empty:
                    st.session_state.varliklar.append(arama_input)
                    st.session_state.aktif_varlik = arama_input
                    if "aktif_varlik_selectbox" in st.session_state:
                        del st.session_state["aktif_varlik_selectbox"]
                    st.sidebar.success(f"'{arama_input}' eklendi ve seçildi!")
                    st.rerun()
                else:
                    st.sidebar.error("Veri alınamadı! Kodu kontrol edin.")
            else:
                st.sidebar.warning("Bu varlık zaten listenizde var.")
        else:
            st.sidebar.warning("Lütfen bir kod girin.")

    st.sidebar.divider()
    st.sidebar.caption("Veya Hazır Listeden Seçip Ekle:")

    secilen_kategori = st.sidebar.selectbox("Kategori", list(hazir_listeler.keys()))
    varlik_dict = hazir_listeler[secilen_kategori]
    secilen_isim = st.sidebar.selectbox("Popüler Varlıklar", list(varlik_dict.keys()))
    secilen_kod = varlik_dict[secilen_isim]

    if st.sidebar.button("➕ Seçileni Listeye Ekle"):
        if secilen_kod not in [v.upper() for v in st.session_state.varliklar]:
            st.session_state.varliklar.append(secilen_kod)
        st.session_state.aktif_varlik = secilen_kod
        if "aktif_varlik_selectbox" in st.session_state:
            del st.session_state["aktif_varlik_selectbox"]
        st.rerun()

    st.sidebar.divider()

    if st.session_state.aktif_varlik not in st.session_state.varliklar:
        st.session_state.aktif_varlik = st.session_state.varliklar[0]

    default_index = st.session_state.varliklar.index(st.session_state.aktif_varlik)

    secilen_varlik = st.sidebar.selectbox(
        "Analiz Edilecek Varlık", 
        st.session_state.varliklar, 
        index=default_index,
        key="aktif_varlik_selectbox"
    )

    if secilen_varlik != st.session_state.aktif_varlik:
        st.session_state.aktif_varlik = secilen_varlik
        st.rerun()

    if st.sidebar.button("🗑️ Seçili Varlığı Sil"):
        if len(st.session_state.varliklar) > 1:
            st.session_state.varliklar.remove(secilen_varlik)
            st.session_state.aktif_varlik = st.session_state.varliklar[0]
            if "aktif_varlik_selectbox" in st.session_state:
                del st.session_state["aktif_varlik_selectbox"]
            st.rerun()
        else:
            st.sidebar.error("Listede en az bir varlık kalmalıdır.")

    df = veri_cek(secilen_varlik, aralik=aralik)

    if df is not None and not df.empty:
        df_analiz = hesapla_teknikler(df)
        analiz = donusum_noktalari_hesapla(df_analiz)
        sinyal = sinyal_kontrol(df_analiz)
        
        if "AL" in sinyal.upper():
             pozisyon = "🟢 *LONG Pozisyon Al*"
             stop_loss = analiz['destek'] * 0.99
        elif "SAT" in sinyal.upper():
            pozisyon = "🔴 *SHORT Pozisyon Al*"
            stop_loss = analiz['direnc'] * 1.01
        else:
            pozisyon = "⚪ *Nötr / Bekle*"
            stop_loss = analiz['destek'] * 0.98

        st.title(f"{secilen_varlik} | Piyasa Analizi")
        st.markdown(piyasa_analizi_yap(df_analiz, sinyal))
        
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Fiyat", f"{analiz['fiyat']:.2f}")
        c2.metric("Destek", f"{analiz['destek']:.2f}")
        c3.metric("Direnç", f"{analiz['direnc']:.2f}")
        c4.metric("Stop-Loss", f"{stop_loss:.2f}")
        c5.metric("Pozisyon", sinyal)

        if st.button("📢 Bu Analizi Telegram'a Gönder"):
            mesaj = f"📊 *Manuel Tekli Pozisyon Analizi*\n\n*Varlık:* `{secilen_varlik}`\n*Fiyat:* `{analiz['fiyat']:.2f}`\n*Tavsiye:* {pozisyon}\n*Stop-Loss:* `{stop_loss:.2f}`\n*Destek:* `{analiz['destek']:.2f}` | *Direnç:* `{analiz['direnc']:.2f}`"
            telegram_bildirim_gonder(mesaj)
            st.success("Analiz Telegram'a başarıyla gönderildi!")

        fig = go.Figure()
        fig.add_trace(go.Candlestick(x=df_analiz['tarih'], open=df_analiz['open'], high=df_analiz['high'], low=df_analiz['low'], close=df_analiz['close'], name='Fiyat'))
        fig.add_trace(go.Scatter(x=df_analiz['tarih'], y=df_analiz['sma_20'], name='SMA 20', line=dict(color='orange', width=1.5)))
        fig.add_trace(go.Scatter(x=df_analiz['tarih'], y=df_analiz['sma_50'], name='SMA 50', line=dict(color='blue', width=1.5)))

        for i in range(1, len(df_analiz)):
            fiyat = df_analiz['close'].iloc[i]
            if df_analiz['sma_20'].iloc[i-1] <= df_analiz['sma_50'].iloc[i-1] and df_analiz['sma_20'].iloc[i] > df_analiz['sma_50'].iloc[i]:
                fig.add_annotation(x=df_analiz['tarih'].iloc[i], y=df_analiz['low'].iloc[i], text=f"LONG (SL)<br>{fiyat:.2f}", bgcolor="green", font=dict(color="white"), showarrow=True, ay=30)
            elif df_analiz['sma_20'].iloc[i-1] >= df_analiz['sma_50'].iloc[i-1] and df_analiz['sma_20'].iloc[i] < df_analiz['sma_50'].iloc[i]:
                fig.add_annotation(x=df_analiz['tarih'].iloc[i], y=df_analiz['high'].iloc[i], text=f"SHORT (SL)<br>{fiyat:.2f}", bgcolor="red", font=dict(color="white"), showarrow=True, ay=-30)

        fig.update_layout(template="plotly_dark", height=600)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning(f"⚠️ **{secilen_varlik}** için veri alınamadı.")

# --- GÖRÜNÜM 2: TÜM LİSTEYİ TOPLU TARAMA VE LİSTE + GRAFİK BUTONU ---
elif st.session_state.aktif_sekme == "🚀 Toplu Portföy Taraması":
    st.title("🚀 Tüm Portföy Toplu Tarama Paneli")
    st.markdown(f"Şu anda takip edilen toplam **{len(st.session_state.varliklar)}** varlık taranmaktadır:")

    with st.expander("➕ Portföye Hızlı Varlık Ekle"):
        col_ekle1, col_ekle2 = st.columns([3, 1])
        with col_ekle1:
            toplu_arama_input = st.text_input("Varlık Kodu", placeholder="Örn: GOOGL, GARAN.IS", key="toplu_ekleme_input").upper().strip()
        with col_ekle2:
            st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
            toplu_ekle_btn = st.button("Listeye Ekle", key="toplu_ekle_action_btn")
            
        if toplu_ekle_btn:
            if toplu_arama_input:
                mevcut_buyuk = [v.upper() for v in st.session_state.varliklar]
                if toplu_arama_input not in mevcut_buyuk:
                    test_df = veri_cek(toplu_arama_input, aralik=aralik)
                    if test_df is not None and not test_df.empty:
                        st.session_state.varliklar.append(toplu_arama_input)
                        st.session_state.aktif_varlik = toplu_arama_input
                        if "aktif_varlik_selectbox" in st.session_state:
                            del st.session_state["aktif_varlik_selectbox"]
                        st.success(f"'{toplu_arama_input}' portföye başarıyla eklendi!")
                        st.rerun()
                    else:
                        st.error("Veri alınamadı! Kodu kontrol edin.")
                else:
                    st.warning("Bu varlık zaten listenizde mevcut.")
            else:
                st.warning("Lütfen geçerli bir kod girin.")

    col_b1, col_b2 = st.columns(2)
    with col_b1:
        if st.button("🔄 Tüm Listeyi Şimdi Yeniden Tara", key="toplu_yenile_btn"):
            st.rerun()
    with col_b2:
        if st.button("📤 Pozisyon ve Stop-Loss Taramasını Telegram'a Gönder", key="manuel_telegram_gonder_btn"):
            with st.spinner("Portföy taranıyor ve Stop-Loss seviyeleri hesaplanarak Telegram'a aktarılıyor..."):
                manuel_mesaj = "📊 *Manuel Pozisyon & Stop-Loss Raporu*\n\n"
                for varlik in st.session_state.varliklar:
                    df_t = veri_cek(varlik, aralik=aralik)
                    if df_t is not None and not df_t.empty:
                        df_t_analiz = hesapla_teknikler(df_t)
                        p_analiz = donusum_noktalari_hesapla(df_t_analiz)
                        p_sinyal = sinyal_kontrol(df_t_analiz)
                        
                        if "AL" in p_sinyal.upper():
                            pozisyon = "🟢 *LONG*"
                            sl = p_analiz['destek'] * 0.99
                        elif "SAT" in p_sinyal.upper():
                            pozisyon = "🔴 *SHORT*"
                            sl = p_analiz['direnc'] * 1.01
                        else:
                            pozisyon = "⚪ *NÖTR*"
                            sl = p_analiz['destek'] * 0.98
                            
                        manuel_mesaj += f"• *{varlik}*: Fiyat: `{p_analiz['fiyat']:.2f}` | Tavsiye: {pozisyon} | Stop-Loss: `{sl:.2f}`\n"
                telegram_bildirim_gonder(manuel_mesaj)
            st.success("Pozisyon ve Stop-Loss raporu manuel olarak Telegram'a gönderildi!")
        
    st.divider()
    st.subheader("📋 Portföy Varlıkları ve Stop-Loss İnceleme Listesi")
    st.markdown("Her bir varlığın pozisyon ve stop-loss seviyelerini aşağıda görebilir, **📈 Grafik** butonuna basarak detaylara geçebilirsiniz:")

    with st.spinner("Varlıklar taranıyor ve analizler hazırlanıyor..."):
        for varlik in st.session_state.varliklar:
            df_t = veri_cek(varlik, aralik=aralik)
            
            with st.container():
                col1, col2, col3, col4, col5, col6 = st.columns([2, 1.8, 1.8, 1.8, 2, 1.5])
                
                if df_t is not None and not df_t.empty:
                    df_t_analiz = hesapla_teknikler(df_t)
                    p_analiz = donusum_noktalari_hesapla(df_t_analiz)
                    p_sinyal = sinyal_kontrol(df_t_analiz)
                    
                    if "AL" in p_sinyal.upper():
                        p_text = "🟢 LONG"
                        sl_val = p_analiz['destek'] * 0.99
                    elif "SAT" in p_sinyal.upper():
                        p_text = "🔴 SHORT"
                        sl_val = p_analiz['direnc'] * 1.01
                    else:
                        p_text = "⚪ NÖTR"
                        sl_val = p_analiz['destek'] * 0.98
                    
                    col1.markdown(f"**{varlik}**")
                    col2.metric("Fiyat", f"{p_analiz['fiyat']:.2f}")
                    col3.text(f"Destek: {p_analiz['destek']:.2f}")
                    col4.text(f"Stop-Loss: {sl_val:.2f}")
                    col5.markdown(f"**{p_text}**")
                    
                    with col6:
                        if st.button("📈 Grafik", key=f"btn_grafik_{varlik}"):
                            st.session_state.aktif_varlik = varlik
                            st.session_state.aktif_sekme = "🔍 Tekli Analiz & Varlık Ekle"
                            if "aktif_varlik_selectbox" in st.session_state:
                                del st.session_state["aktif_varlik_selectbox"]
                            st.rerun()
                else:
                    col1.markdown(f"**{varlik}**")
                    col5.error("Veri Alınamadı")
                    with col6:
                        if st.button("📈 Grafik", key=f"btn_grafik_bos_{varlik}"):
                            st.session_state.aktif_varlik = varlik
                            st.session_state.aktif_sekme = "🔍 Tekli Analiz & Varlık Ekle"
                            if "aktif_varlik_selectbox" in st.session_state:
                                del st.session_state["aktif_varlik_selectbox"]
                            st.rerun()
                            
            st.divider()
