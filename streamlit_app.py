import streamlit as st
import requests
import threading
import time
import json
import os
import plotly.graph_objects as go
import pandas as pd

from data_sources import veri_cek
from indicators import hesapla_teknikler, sinyal_kontrol, piyasa_analizi_yap
from utils import donusum_noktalari_hesapla
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

st.set_page_config(page_title="Pro Finans Paneli", layout="wide")
st.markdown("""<style>.stApp { background-color: #0e1117; }</style>""", unsafe_allow_html=True)

# ==============================================================================
# JSON AYAR YÖNETİMİ (ARAYÜZ VE BOT ARASINDAKİ KÖPRÜ)
# ==============================================================================
AYAR_DOSYASI = "ayarlar.json"
VARSAYILAN_AYARLAR = {
    "varliklar": ["BTC-USD", "THYAO.IS", "AAPL"],
    "zaman_dilimi": "1h",
    "bot_sikligi_dk": 60
}

def ayarlari_yukle():
    if not os.path.exists(AYAR_DOSYASI):
        with open(AYAR_DOSYASI, "w") as f:
            json.dump(VARSAYILAN_AYARLAR, f)
        return VARSAYILAN_AYARLAR
    try:
        with open(AYAR_DOSYASI, "r") as f:
            return json.load(f)
    except:
        return VARSAYILAN_AYARLAR

def ayarlari_kaydet(ayarlar):
    with open(AYAR_DOSYASI, "w") as f:
        json.dump(ayarlar, f)

# ==============================================================================
# TELEGRAM BİLDİRİM FONKSİYONU
# ==============================================================================
def telegram_bildirim_gonder(mesaj):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": mesaj, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Telegram hatası: {e}")

# ==============================================================================
# AKILLI ARKA PLAN BOTU (JSON OKUYUCU)
# ==============================================================================
def otomatik_tarama_botu():
    time.sleep(15)  # Başlangıç gecikmesi
    while True:
        try:
            ayarlar = ayarlari_yukle()
            varliklar = ayarlar.get("varliklar", [])
            zaman_dilimi = ayarlar.get("zaman_dilimi", "1h")
            bekleme_suresi = ayarlar.get("bot_sikligi_dk", 60) * 60
            
            if not varliklar:
                time.sleep(bekleme_suresi)
                continue
                
            ozet_mesaj = f"🚨 *Otomatik Portföy Raporu* (Periyot: {zaman_dilimi})\n\n"
            
            for varlik in varliklar:
                df_t = veri_cek(varlik, aralik=zaman_dilimi)
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
                        
                    ozet_mesaj += f"• *{varlik}*: Fiyat: `{p_analiz['fiyat']:.2f}` | {pozisyon} | SL: `{sl:.2f}`\n"
                else:
                    ozet_mesaj += f"• *{varlik}*: Veri hatası!\n"
                    
            telegram_bildirim_gonder(ozet_mesaj)
        except Exception as e:
            print(f"Bot döngü hatası: {e}")
            
        # Dinamik olarak bekler (Kullanıcı 15dk yaparsa 15dk sonra uyanır)
        time.sleep(bekleme_suresi)

if "arkaplan_bot_aktif" not in globals():
    globals()["arkaplan_bot_aktif"] = True
    bot_thread = threading.Thread(target=otomatik_tarama_botu, daemon=True)
    bot_thread.start()

# ==============================================================================
# STREAMLIT ARAYÜZ (UI)
# ==============================================================================
aktif_ayarlar = ayarlari_yukle()

st.sidebar.title("🤖 Pro Asistan")
sayfa = st.sidebar.radio("Menü Seçimi", ["📚 Varlık Havuzu", "📈 Canlı Analiz & Portföy", "⚙️ Bot Ayarları"])
st.sidebar.divider()

# HAZIR VARLIK KÜTÜPHANESİ
HAZIR_VARLIKLAR = {
    "BIST 30 Hisseleri": {
        "THYAO (Türk Hava Yolları)": "THYAO.IS", "ISMEN (İş Yatırım)": "ISMEN.IS", 
        "GARAN (Garanti BBVA)": "GARAN.IS", "ASELS (Aselsan)": "ASELS.IS",
        "EREGL (Ereğli D.Ç.)": "EREGL.IS", "ASTOR (Astor Enerji)": "ASTOR.IS",
        "KCHOL (Koç Holding)": "KCHOL.IS", "TUPRS (Tüpraş)": "TUPRS.IS"
    },
    "Kripto Paralar": {
        "Bitcoin": "BTC-USD", "Ethereum": "ETH-USD", "Solana": "SOL-USD",
        "Ripple": "XRP-USD", "Cardano": "ADA-USD", "Avalanche": "AVAX-USD",
        "Dogecoin": "DOGE-USD", "Chainlink": "LINK-USD"
    },
    "Global & Emtia & Forex": {
        "Apple": "AAPL", "Tesla": "TSLA", "Microsoft": "MSFT", 
        "Nvidia": "NVDA", "Altın (ONS)": "GC=F", "EUR/USD": "EURUSD=X",
        "USD/TRY": "USDTRY=X"
    }
}

# --- MENÜ 1: VARLIK HAVUZU ---
if sayfa == "📚 Varlık Havuzu":
    st.title("📚 Varlık Havuzu (Market)")
    st.markdown("Takip etmek istediğiniz varlıkları aşağıdan seçerek portföyünüze ekleyebilirsiniz. Bot bu listeyi tarayacaktır.")
    
    secilenler_havuzu = set(aktif_ayarlar["varliklar"])
    
    col1, col2, col3 = st.columns(3)
    kategoriler = list(HAZIR_VARLIKLAR.keys())
    
    # BIST Kolonu
    with col1:
        st.subheader("🇹🇷 BIST 30")
        for isim, kod in HAZIR_VARLIKLAR[kategoriler[0]].items():
            if st.checkbox(isim, value=(kod in secilenler_havuzu), key=kod):
                secilenler_havuzu.add(kod)
            else:
                secilenler_havuzu.discard(kod)
                
    # Kripto Kolonu
    with col2:
        st.subheader("🪙 Kripto Para")
        for isim, kod in HAZIR_VARLIKLAR[kategoriler[1]].items():
            if st.checkbox(isim, value=(kod in secilenler_havuzu), key=kod):
                secilenler_havuzu.add(kod)
            else:
                secilenler_havuzu.discard(kod)
                
    # Global Kolonu
    with col3:
        st.subheader("🌎 Global & Forex")
        for isim, kod in HAZIR_VARLIKLAR[kategoriler[2]].items():
            if st.checkbox(isim, value=(kod in secilenler_havuzu), key=kod):
                secilenler_havuzu.add(kod)
            else:
                secilenler_havuzu.discard(kod)
                
    st.divider()
    
    # Manuel Ekleme Alanı
    st.markdown("🎯 **Aradığınız varlık listede yoksa manuel ekleyin:** (Örn: GOOGL, AKBNK.IS)")
    manuel_kod = st.text_input("Varlık Kodu").upper().strip()
    if st.button("➕ Özel Varlık Ekle") and manuel_kod:
        secilenler_havuzu.add(manuel_kod)
        st.success(f"{manuel_kod} eklendi! Listeyi kaydetmeyi unutmayın.")
        
    st.divider()
    if st.button("💾 SEÇİMLERİ KAYDET VE BOTA İLET", use_container_width=True, type="primary"):
        aktif_ayarlar["varliklar"] = list(secilenler_havuzu)
        ayarlari_kaydet(aktif_ayarlar)
        st.success("Varlık listeniz başarıyla güncellendi! Bot artık bu listeyi tarayacak.")
        time.sleep(1)
        st.rerun()

# --- MENÜ 2: CANLI ANALİZ ---
elif sayfa == "📈 Canlı Analiz & Portföy":
    st.title("📈 Canlı Analiz & Portföy")
    
    mevcut_varliklar = aktif_ayarlar.get("varliklar", [])
    if not mevcut_varliklar:
        st.warning("Henüz portföyünüzde varlık yok. Lütfen 'Varlık Havuzu'ndan seçim yapın.")
    else:
        st.markdown(f"Güncel Zaman Dilimi: **{aktif_ayarlar['zaman_dilimi']}**")
        secili_grafik = st.selectbox("Grafik Analizi İçin Varlık Seçin", mevcut_varliklar)
        
        df = veri_cek(secili_grafik, aralik=aktif_ayarlar["zaman_dilimi"])
        if df is not None and not df.empty:
            df_analiz = hesapla_teknikler(df)
            analiz = donusum_noktalari_hesapla(df_analiz)
            sinyal = sinyal_kontrol(df_analiz)
            
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Fiyat", f"{analiz['fiyat']:.2f}")
            c2.metric("Destek (SL)", f"{analiz['destek']:.2f}")
            c3.metric("Direnç (TP)", f"{analiz['direnc']:.2f}")
            c4.metric("Pozisyon", sinyal)
            
            # Grafik Çizimi
            fig = go.Figure()
            fig.add_trace(go.Candlestick(x=df_analiz['tarih'], open=df_analiz['open'], high=df_analiz['high'], low=df_analiz['low'], close=df_analiz['close'], name='Fiyat'))
            fig.add_trace(go.Scatter(x=df_analiz['tarih'], y=df_analiz['sma_20'], name='SMA 20', line=dict(color='orange')))
            fig.add_trace(go.Scatter(x=df_analiz['tarih'], y=df_analiz['sma_50'], name='SMA 50', line=dict(color='blue')))
            fig.update_layout(template="plotly_dark", height=500, margin=dict(l=0, r=0, t=30, b=0))
            st.plotly_chart(fig, use_container_width=True)
            
            st.markdown(piyasa_analizi_yap(df_analiz, sinyal))
        else:
            st.error(f"{secili_grafik} için veri alınamadı. (Piyasa kapalı olabilir veya kod yanlış)")

# --- MENÜ 3: BOT AYARLARI ---
elif sayfa == "⚙️ Bot Ayarları":
    st.title("⚙️ Telegram Bot ve Analiz Ayarları")
    st.markdown("Botun çalışma sıklığını ve teknik analizin hangi zaman dilimine göre yapılacağını buradan belirleyin.")
    
    zaman_secenekleri = ["15m", "1h", "4h", "1d"]
    zaman_index = zaman_secenekleri.index(aktif_ayarlar.get("zaman_dilimi", "1h"))
    
    yeni_zaman = st.selectbox(
        "Teknik Analiz Zaman Dilimi (Mum Grafiği)", 
        zaman_secenekleri, 
        index=zaman_index,
        help="Bot destek/direnç noktalarını hesaplarken bu mum periyodunu baz alır."
    )
    
    siklik_secenekleri = {
        15: "15 Dakikada Bir Raporla",
        30: "Yarım Saatte Bir Raporla",
        60: "Saatte Bir Raporla (Önerilen)",
        120: "2 Saatte Bir Raporla",
        240: "4 Saatte Bir Raporla"
    }
    
    mevcut_siklik = aktif_ayarlar.get("bot_sikligi_dk", 60)
    siklik_degerleri = list(siklik_secenekleri.keys())
    siklik_index = siklik_degerleri.index(mevcut_siklik) if mevcut_siklik in siklik_degerleri else 2
    
    yeni_siklik_etiket = st.selectbox(
        "Telegram Bildirim Sıklığı", 
        list(siklik_secenekleri.values()), 
        index=siklik_index
    )
    
    yeni_siklik = list(siklik_secenekleri.keys())[list(siklik_secenekleri.values()).index(yeni_siklik_etiket)]
    
    st.divider()
    if st.button("💾 AYARLARI KAYDET", use_container_width=True, type="primary"):
        aktif_ayarlar["zaman_dilimi"] = yeni_zaman
        aktif_ayarlar["bot_sikligi_dk"] = yeni_siklik
        ayarlari_kaydet(aktif_ayarlar)
        st.success(f"Ayarlar kaydedildi! Bot bundan sonra her {yeni_siklik} dakikada bir {yeni_zaman} periyotlu analiz yapacak.")
        time.sleep(1.5)
        st.rerun()
