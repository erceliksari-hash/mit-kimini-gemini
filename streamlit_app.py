import streamlit as st
import requests
import threading
import time
import json
import os
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd

from data_sources import veri_cek
from indicators import hesapla_teknikler, sinyal_kontrol, piyasa_analizi_yap
from utils import donusum_noktalari_hesapla
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

st.set_page_config(page_title="Pro Finans Paneli", layout="wide")
st.markdown("""<style>.stApp { background-color: #0e1117; }</style>""", unsafe_allow_html=True)

# --- AYAR YÖNETİMİ ---
AYAR_DOSYASI = "ayarlar.json"
VARSAYILAN_AYARLAR = {"varliklar": ["BTC-USD", "THYAO.IS", "AAPL"], "zaman_dilimi": "1h", "bot_sikligi_dk": 60}

def ayarlari_yukle():
    if not os.path.exists(AYAR_DOSYASI):
        with open(AYAR_DOSYASI, "w") as f:
            json.dump(VARSAYILAN_AYARLAR, f)
        return VARSAYILAN_AYARLAR
    try:
        with open(AYAR_DOSYASI, "r") as f:
            return json.load(f)
    except: return VARSAYILAN_AYARLAR

def ayarlari_kaydet(ayarlar):
    with open(AYAR_DOSYASI, "w") as f:
        json.dump(ayarlar, f)

# --- TELEGRAM BOT VE BİLDİRİM ---
def telegram_bildirim_gonder(mesaj):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID: return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": mesaj, "parse_mode": "Markdown"}
    try: requests.post(url, json=payload)
    except: pass

def otomatik_tarama_botu():
    time.sleep(15) 
    while True:
        try:
            ayarlar = ayarlari_yukle()
            varliklar = ayarlar.get("varliklar", [])
            zaman_dilimi = ayarlar.get("zaman_dilimi", "1h")
            bekleme_suresi = ayarlar.get("bot_sikligi_dk", 60) * 60
            
            if varliklar:
                ozet_mesaj = f"🚨 *Otomatik Portföy Raporu* (Periyot: {zaman_dilimi})\n\n"
                for varlik in varliklar:
                    df_t = veri_cek(varlik, aralik=zaman_dilimi)
                    if df_t is not None and not df_t.empty:
                        df_t_analiz = hesapla_teknikler(df_t)
                        p_analiz = donusum_noktalari_hesapla(df_t_analiz)
                        p_sinyal = sinyal_kontrol(df_t_analiz)
                        
                        if "AL" in p_sinyal.upper(): pozisyon, sl = "🟢 *LONG*", p_analiz['destek'] * 0.99
                        elif "SAT" in p_sinyal.upper(): pozisyon, sl = "🔴 *SHORT*", p_analiz['direnc'] * 1.01
                        else: pozisyon, sl = "⚪ *NÖTR*", p_analiz['destek'] * 0.98
                            
                        ozet_mesaj += f"• *{varlik}*: Fiyat: `{p_analiz['fiyat']:.2f}` | {pozisyon} | SL: `{sl:.2f}`\n"
                telegram_bildirim_gonder(ozet_mesaj)
        except: pass
        time.sleep(bekleme_suresi)

if "arkaplan_bot_aktif" not in globals():
    globals()["arkaplan_bot_aktif"] = True
    threading.Thread(target=otomatik_tarama_botu, daemon=True).start()

# --- STREAMLIT UI ---
aktif_ayarlar = ayarlari_yukle()
st.sidebar.title("🤖 Pro Asistan")
sayfa = st.sidebar.radio("Menü Seçimi", ["📚 Varlık Havuzu", "📈 Canlı Analiz & Portföy", "⚙️ Bot Ayarları"])
st.sidebar.divider()

HAZIR_VARLIKLAR = {
    "BIST 30 Hisseleri": {"THYAO (Türk Hava Yolları)": "THYAO.IS", "ISMEN (İş Yatırım)": "ISMEN.IS", "GARAN (Garanti BBVA)": "GARAN.IS", "ASELS (Aselsan)": "ASELS.IS", "EREGL (Ereğli)": "EREGL.IS", "ASTOR (Astor)": "ASTOR.IS", "KCHOL (Koç)": "KCHOL.IS", "TUPRS (Tüpraş)": "TUPRS.IS"},
    "Kripto Paralar": {"Bitcoin": "BTC-USD", "Ethereum": "ETH-USD", "Solana": "SOL-USD", "Ripple": "XRP-USD", "Cardano": "ADA-USD", "Avalanche": "AVAX-USD", "Dogecoin": "DOGE-USD", "Chainlink": "LINK-USD"},
    "Global & Emtia": {"Apple": "AAPL", "Tesla": "TSLA", "Microsoft": "MSFT", "Nvidia": "NVDA", "Altın (ONS)": "GC=F", "EUR/USD": "EURUSD=X", "USD/TRY": "USDTRY=X"}
}

if sayfa == "📚 Varlık Havuzu":
    st.title("📚 Varlık Havuzu")
    secilenler = set(aktif_ayarlar["varliklar"])
    
    c1, c2, c3 = st.columns(3)
    kats = list(HAZIR_VARLIKLAR.keys())
    for col, kat in zip([c1, c2, c3], kats):
        with col:
            st.subheader(kat)
            for isim, kod in HAZIR_VARLIKLAR[kat].items():
                if st.checkbox(isim, value=(kod in secilenler), key=kod): secilenler.add(kod)
                else: secilenler.discard(kod)
    st.divider()
    manuel = st.text_input("🎯 Aradığınız varlık listede yoksa kodunu girin (Örn: FROTO.IS)").upper().strip()
    if st.button("➕ Özel Varlık Ekle") and manuel:
        secilenler.add(manuel)
        st.success(f"{manuel} eklendi!")
        
    st.divider()
    if st.button("💾 SEÇİMLERİ KAYDET VE BOTA İLET", use_container_width=True, type="primary"):
        aktif_ayarlar["varliklar"] = list(secilenler)
        ayarlari_kaydet(aktif_ayarlar)
        st.success("Listeniz güncellendi!")
        time.sleep(1)
        st.rerun()

elif sayfa == "📈 Canlı Analiz & Portföy":
    st.title("📈 Portföy Analiz Listesi ve Grafik İnceleme")
    mevcut_varliklar = aktif_ayarlar.get("varliklar", [])
    
    if not mevcut_varliklar:
        st.warning("Varlık Havuzundan seçim yapın.")
    else:
        st.markdown(f"Aktif Zaman Dilimi Periyodu: **{aktif_ayarlar['zaman_dilimi']}**")
        st.divider()

        # Aktif seçilen grafiği akılda tutmak için session state
        if "secilen_aktif_grafik" not in st.session_state:
            st.session_state["secilen_aktif_grafik"] = mevcut_varliklar[0]

        # 1. BÖLÜM: LİSTE HALİNDE TÜM VARLIKLAR VE ANALİZ AÇIKLAMALARI
        st.subheader("📋 Portföy Varlıkları ve Anlık Özetleri")
        
        for varlik in mevcut_varliklar:
            df_temp = veri_cek(varlik, aralik=aktif_ayarlar["zaman_dilimi"])
            if df_temp is not None and not df_temp.empty:
                df_t_analiz = hesapla_teknikler(df_temp)
                p_analiz = donusum_noktalari_hesapla(df_t_analiz)
                p_sinyal = sinyal_kontrol(df_t_analiz)
                
                col_info, col_btn = st.columns([4, 1])
                with col_info:
                    st.markdown(f"**🔹 {varlik}** | Fiyat: `{p_analiz['fiyat']:.2f}` | Sinyal: **{p_sinyal}** | Destek: `{p_analiz['destek']:.2f}` | Direnç: `{p_analiz['direnc']:.2f}`")
                with col_btn:
                    if st.button(f"📊 Grafiği İncele", key=f"btn_grafik_{varlik}", use_container_width=True):
                        st.session_state["secilen_aktif_grafik"] = varlik
            else:
                st.warning(f"🔹 {varlik}: Veri alınamadı.")

        st.divider()
        
        # 2. BÖLÜM: SEÇİLEN VARLIĞIN DETAYLI GRAFİK İNCELEMESİ
        st.header(f"📊 Detaylı Grafik İncelemesi: `{st.session_state['secilen_aktif_grafik']}`")

        ek_gostergeler = st.multiselect(
            "Grafik Üzerinde Gösterilecek İndikatörler",
            ["Bollinger Bantları", "Özel İndikatörüm", "RSI (Alt Grafik)", "MACD (Alt Grafik)"],
            default=["Bollinger Bantları", "Özel İndikatörüm"],
            key="multiselect_indicators"
        )

        aktif_secim = st.session_state["secilen_aktif_grafik"]
        df = veri_cek(aktif_secim, aralik=aktif_ayarlar["zaman_dilimi"])
        
        if df is not None and not df.empty:
            df_analiz = hesapla_teknikler(df)
            analiz = donusum_noktalari_hesapla(df_analiz)
            sinyal = sinyal_kontrol(df_analiz)
            
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Anlık Fiyat", f"{analiz['fiyat']:.2f}")
            c2.metric("Destek (SL)", f"{analiz['destek']:.2f}")
            c3.metric("Direnç (TP)", f"{analiz['direnc']:.2f}")
            c4.metric("Pozisyon Durumu", sinyal)
            
            # GRAFİK KATMANLARI
            satir_sayisi = 1
            row_heights = [0.7]
            if "RSI (Alt Grafik)" in ek_gostergeler:
                satir_sayisi += 1
                row_heights.append(0.2)
            if "MACD (Alt Grafik)" in ek_gostergeler:
                satir_sayisi += 1
                row_heights.append(0.2)
                
            if satir_sayisi == 1: row_heights = [1]
                
            fig = make_subplots(rows=satir_sayisi, cols=1, shared_xaxes=True, 
                                vertical_spacing=0.03, row_heights=row_heights)

            # Fiyat ve Ortalamalar
            fig.add_trace(go.Candlestick(x=df_analiz['tarih'], open=df_analiz['open'], high=df_analiz['high'], low=df_analiz['low'], close=df_analiz['close'], name='Fiyat'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df_analiz['tarih'], y=df_analiz['sma_20'], name='SMA 20', line=dict(color='orange', width=1.5)), row=1, col=1)
            fig.add_trace(go.Scatter(x=df_analiz['tarih'], y=df_analiz['sma_50'], name='SMA 50', line=dict(color='blue', width=1.5)), row=1, col=1)

            # Destek ve Direnç Çizgileri
            fig.add_hline(y=analiz['destek'], line_dash="dot", line_color="green", annotation_text="Güçlü Destek", row=1, col=1)
            fig.add_hline(y=analiz['direnc'], line_dash="dot", line_color="red", annotation_text="Güçlü Direnç", row=1, col=1)

            # Long / Short Noktaları
            al_noktalari = df_analiz[df_analiz['sinyal_tarihsel'] == 1]
            sat_noktalari = df_analiz[df_analiz['sinyal_tarihsel'] == -1]
            
            fig.add_trace(go.Scatter(x=al_noktalari['tarih'], y=al_noktalari['low'] * 0.98, mode='markers', name='AL (Long)', marker=dict(symbol='triangle-up', color='green', size=14)), row=1, col=1)
            fig.add_trace(go.Scatter(x=sat_noktalari['tarih'], y=sat_noktalari['high'] * 1.02, mode='markers', name='SAT (Short)', marker=dict(symbol='triangle-down', color='red', size=14)), row=1, col=1)

            # Bollinger Bantları
            if "Bollinger Bantları" in ek_gostergeler:
                fig.add_trace(go.Scatter(x=df_analiz['tarih'], y=df_analiz['bollinger_ust'], name='Bol. Üst', line=dict(color='rgba(173,216,230,0.5)', width=1, dash='dash')), row=1, col=1)
                fig.add_trace(go.Scatter(x=df_analiz['tarih'], y=df_analiz['bollinger_alt'], name='Bol. Alt', fill='tonexty', fillcolor='rgba(173,216,230,0.1)', line=dict(color='rgba(173,216,230,0.5)', width=1, dash='dash')), row=1, col=1)

            # Özel İndikatör Çizimi
            if "Özel İndikatörüm" in ek_gostergeler:
                fig.add_trace(go.Scatter(x=df_analiz['tarih'], y=df_analiz['ozel_indikator'], name='Özel İndikatör', line=dict.values(dict(color='yellow', width=1.5, dash='dash')) if hasattr(dict, 'values') else dict(color='yellow', width=1.5, dash='dash')), row=1, col=1)

            # Alt Grafikler (RSI, MACD)
            guncel_satir = 2
            if "RSI (Alt Grafik)" in ek_gostergeler:
                fig.add_trace(go.Scatter(x=df_analiz['tarih'], y=df_analiz['rsi'], name='RSI', line=dict(color='purple', width=1.5)), row=guncel_satir, col=1)
                fig.add_hline(y=70, line_dash="dot", line_color="red", row=guncel_satir, col=1)
                fig.add_hline(y=30, line_dash="dot", line_color="green", row=guncel_satir, col=1)
                guncel_satir += 1
                
            if "MACD (Alt Grafik)" in ek_gostergeler:
                fig.add_trace(go.Scatter(x=df_analiz['tarih'], y=df_analiz['macd'], name='MACD', line=dict(color='blue', width=1.5)), row=guncel_satir, col=1)
                fig.add_trace(go.Scatter(x=df_analiz['tarih'], y=df_analiz['macd_signal'], name='Sinyal', line=dict(color='orange', width=1.5)), row=guncel_satir, col=1)
                fig.add_trace(go.Bar(x=df_analiz['tarih'], y=df_analiz['macd'] - df_analiz['macd_signal'], name='Histogram', marker_color='gray'), row=guncel_satir, col=1)

            fig.update_layout(template="plotly_dark", height=600 if satir_sayisi == 1 else 850, margin=dict(l=0, r=0, t=30, b=0), xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)
            
            st.markdown(piyasa_analizi_yap(df_analiz, sinyal))
        else: st.error(f"{aktif_secim} için veri alınamadı.")

elif sayfa == "⚙️ Bot Ayarları":
    st.title("⚙️ Ayarlar")
    zaman_secenekleri = ["15m", "1h", "4h", "1d"]
    zaman_index = zaman_secenekleri.index(aktif_ayarlar.get("zaman_dilimi", "1h"))
    yeni_zaman = st.selectbox("Teknik Analiz Zaman Dilimi", zaman_secenekleri, index=zaman_index)
    
    sikliklar = {15: "15 Dakika", 30: "Yarım Saat", 60: "1 Saat", 120: "2 Saat", 240: "4 Saat"}
    mevcut_siklik = aktif_ayarlar.get("bot_sikligi_dk", 60)
    yeni_siklik_etiket = st.selectbox("Telegram Bildirim Sıklığı", list(sikliklar.values()), index=list(sikliklar.keys()).index(mevcut_siklik) if mevcut_siklik in sikliklar else 2)
    yeni_siklik = list(sikliklar.keys())[list(sikliklar.values()).index(yeni_siklik_etiket)]
    
    if st.button("💾 AYARLARI KAYDET", type="primary"):
        aktif_ayarlar["zaman_dilimi"], aktif_ayarlar["bot_sikligi_dk"] = yeni_zaman, yeni_siklik
        ayarlari_kaydet(aktif_ayarlar)
        st.success("Ayarlar başarıyla kaydedildi!")
        time.sleep(1)
        st.rerun()
