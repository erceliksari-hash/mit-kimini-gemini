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

# --- AYAR VE VERİ YÖNETİMİ (Kalıcı Arşivleme) ---
AYAR_DOSYASI = "ayarlar.json"
PORTFOY_DOSYASI = "portfoy_arsiv.json"
VARSAYILAN_AYARLAR = {"varliklar": ["BTC-USD", "THYAO.IS", "AAPL"], "zaman_dilimi": "1h", "bot_sikligi_dk": 60}

def ayarlari_yukle():
    if not os.path.exists(AYAR_DOSYASI):
        with open(AYAR_DOSYASI, "w") as f: json.dump(VARSAYILAN_AYARLAR, f)
        return VARSAYILAN_AYARLAR
    try:
        with open(AYAR_DOSYASI, "r") as f: return json.load(f)
    except: return VARSAYILAN_AYARLAR

def ayarlari_kaydet(ayarlar):
    with open(AYAR_DOSYASI, "w") as f: json.dump(ayarlar, f)

def portfoy_yukle():
    if not os.path.exists(PORTFOY_DOSYASI): return {}
    try:
        with open(PORTFOY_DOSYASI, "r") as f: return json.load(f)
    except: return {}

def portfoy_kaydet(portfoy_verisi):
    with open(PORTFOY_DOSYASI, "w") as f: json.dump(portfoy_verisi, f)

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
                ozet_mesaj = f"🚨 *Otomatik Sinyal Raporu* (Periyot: {zaman_dilimi})\n\n"
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
aktif_portfoy = portfoy_yukle()

st.sidebar.title("🤖 Pro Asistan")
sayfa = st.sidebar.radio("Menü Seçimi", ["📚 Varlık Havuzu", "📈 Canlı Analiz & Sinyaller", "💼 Portföy Yönetimi", "⚙️ Bot Ayarları"])
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

elif sayfa == "💼 Portföy Yönetimi":
    st.title("💼 Portföy Yönetimi ve Anlık Durum")
    
    # Yeni Varlık Ekleme Alanı
    with st.expander("➕ Portföye Yeni Varlık / İşlem Ekle", expanded=True):
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            mevcut_havuz = aktif_ayarlar.get("varliklar", ["BTC-USD"])
            p_varlik = st.selectbox("Varlık Seç", mevcut_havuz)
        with col2:
            p_maliyet = st.number_input("Ortalama Alım Fiyatı", min_value=0.0, format="%.4f")
        with col3:
            p_adet = st.number_input("Adet / Lot Miktarı", min_value=0.0, format="%.4f")
        with col4:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("Kaydet / Güncelle", use_container_width=True, type="primary"):
                aktif_portfoy[p_varlik] = {"maliyet": p_maliyet, "adet": p_adet}
                portfoy_kaydet(aktif_portfoy)
                st.success("Portföy Arşivine Kaydedildi!")
                time.sleep(1)
                st.rerun()

    st.divider()
    
    # Mevcut Portföy Analizi (Canlı Fiyatlarla)
    st.subheader("📊 Aktif Varlıklarınızın Anlık Analizi")
    if not aktif_portfoy:
        st.info("Henüz portföyünüze veri girmediniz. Yukarıdan alım yaptığınız varlıkları ekleyebilirsiniz.")
    else:
        toplam_portfoy_maliyeti = 0
        toplam_portfoy_guncel_degeri = 0
        
        silinecekler = []
        for v_kod, v_veri in aktif_portfoy.items():
            df_canli = veri_cek(v_kod, aralik="15m")
            if df_canli is not None and not df_canli.empty:
                anlik_fiyat = df_canli['close'].iloc[-1]
                maliyet = v_veri["maliyet"]
                adet = v_veri["adet"]
                
                yatirilan_tutar = maliyet * adet
                guncel_tutar = anlik_fiyat * adet
                fark = guncel_tutar - yatirilan_tutar
                yuzde_degisim = ((anlik_fiyat - maliyet) / maliyet) * 100 if maliyet > 0 else 0
                
                toplam_portfoy_maliyeti += yatirilan_tutar
                toplam_portfoy_guncel_degeri += guncel_tutar
                
                renk = "green" if fark >= 0 else "red"
                ikon = "📈" if fark >= 0 else "📉"
                
                c_sol, c_orta, c_sag, c_btn = st.columns([2, 2, 2, 1])
                with c_sol:
                    st.markdown(f"### {v_kod}")
                    st.caption(f"Adet: {adet} | Maliyet: {maliyet:.2f}")
                with c_orta:
                    st.markdown(f"**Anlık Fiyat:** `{anlik_fiyat:.2f}`")
                    st.markdown(f"**Güncel Değer:** `{guncel_tutar:.2f}`")
                with c_sag:
                    st.markdown(f"<h4 style='color:{renk};'>{ikon} {fark:+.2f} (%{yuzde_degisim:+.2f})</h4>", unsafe_allow_html=True)
                with c_btn:
                    if st.button("🗑️ Sil", key=f"sil_{v_kod}"):
                        silinecekler.append(v_kod)
                st.divider()
                
        for s in silinecekler:
            del aktif_portfoy[s]
            portfoy_kaydet(aktif_portfoy)
            st.rerun()

        # Genel Toplamlar
        st.subheader("Genel Portföy Özeti")
        toplam_fark = toplam_portfoy_guncel_degeri - toplam_portfoy_maliyeti
        genel_renk = "normal" if toplam_fark >= 0 else "inverse"
        
        t1, t2, t3 = st.columns(3)
        t1.metric("Toplam Yatırım (Maliyet)", f"{toplam_portfoy_maliyeti:.2f}")
        t2.metric("Portföy Güncel Değeri", f"{toplam_portfoy_guncel_degeri:.2f}")
        t3.metric("Toplam Kâr / Zarar", f"{toplam_fark:+.2f}", delta_color=genel_renk)

elif sayfa == "📈 Canlı Analiz & Sinyaller":
    st.title("📈 Portföy Sinyal Listesi ve Gelişmiş Grafik")
    mevcut_varliklar = aktif_ayarlar.get("varliklar", [])
    
    if not mevcut_varliklar:
        st.warning("Varlık Havuzundan seçim yapın.")
    else:
        if "secilen_aktif_grafik" not in st.session_state:
            st.session_state["secilen_aktif_grafik"] = mevcut_varliklar[0]

        st.subheader("📋 Sinyal ve Durum Özeti")
        for varlik in mevcut_varliklar:
            df_temp = veri_cek(varlik, aralik=aktif_ayarlar["zaman_dilimi"])
            if df_temp is not None and not df_temp.empty:
                df_t_analiz = hesapla_teknikler(df_temp)
                p_analiz = donusum_noktalari_hesapla(df_t_analiz)
                p_sinyal = sinyal_kontrol(df_t_analiz)
                
                if "AL" in p_sinyal.upper() or "UP" in p_sinyal.upper(): durum_metni = "🚀 **YÜKSELİŞTE (LONG Sinyali)**"
                elif "SAT" in p_sinyal.upper() or "DOWN" in p_sinyal.upper(): durum_metni = "⚠️ **DÜŞÜŞTE (SHORT Sinyali)**"
                else: durum_metni = "⚖️ **NÖTR / Yatay Seyir**"
                
                col_info, col_btn = st.columns([4, 1])
                with col_info:
                    st.markdown(f"🔹 **{varlik}** | Fiyat: `{p_analiz['fiyat']:.2f}` | Durum: {durum_metni} | Destek: `{p_analiz['destek']:.2f}`")
                with col_btn:
                    if st.button(f"📊 Grafiği İncele", key=f"btn_list_{varlik}", use_container_width=True):
                        st.session_state["secilen_aktif_grafik"] = varlik
                        st.rerun()
            else:
                st.warning(f"🔹 {varlik}: Veri alınamadı.")

        st.divider()
        st.header(f"📊 Gelişmiş Grafik İncelemesi: `{st.session_state['secilen_aktif_grafik']}`")
        st.info("💡 **İpucu:** Grafikte fare tekerleği ile zoom yapabilir, sağ üstteki menüden trend çizgisi çizebilirsiniz.")

        ek_gostergeler = st.multiselect("Gösterilecek İndikatörler", ["Bollinger Bantları", "Özel İndikatörüm", "RSI (Alt Grafik)", "MACD (Alt Grafik)"], default=["Bollinger Bantları"])

        aktif_secim = st.session_state["secilen_aktif_grafik"]
        df = veri_cek(aktif_secim, aralik=aktif_ayarlar["zaman_dilimi"])
        
        if df is not None and not df.empty:
            df_analiz = hesapla_teknikler(df)
            analiz = donusum_noktalari_hesapla(df_analiz)
            sinyal = sinyal_kontrol(df_analiz)
            
            satir_sayisi = 1
            row_heights = [0.7]
            if "RSI (Alt Grafik)" in ek_gostergeler:
                satir_sayisi += 1
                row_heights.append(0.2)
            if "MACD (Alt Grafik)" in ek_gostergeler:
                satir_sayisi += 1
                row_heights.append(0.2)
            if satir_sayisi == 1: row_heights = [1]
                
            fig = make_subplots(rows=satir_sayisi, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=row_heights)

            # Mum Grafik
            fig.add_trace(go.Candlestick(x=df_analiz['tarih'], open=df_analiz['open'], high=df_analiz['high'], low=df_analiz['low'], close=df_analiz['close'], name='Fiyat'), row=1, col=1)
            
            # Destek & Direnç
            fig.add_hline(y=analiz['destek'], line_dash="dot", line_color="green", annotation_text="Destek", row=1, col=1)
            fig.add_hline(y=analiz['direnc'], line_dash="dot", line_color="red", annotation_text="Direnç", row=1, col=1)

            if "Bollinger Bantları" in ek_gostergeler:
                fig.add_trace(go.Scatter(x=df_analiz['tarih'], y=df_analiz['bollinger_ust'], name='Bol. Üst', line=dict(color='rgba(173,216,230,0.5)', width=1, dash='dash')), row=1, col=1)
                fig.add_trace(go.Scatter(x=df_analiz['tarih'], y=df_analiz['bollinger_alt'], name='Bol. Alt', fill='tonexty', fillcolor='rgba(173,216,230,0.1)', line=dict(color='rgba(173,216,230,0.5)', width=1, dash='dash')), row=1, col=1)

            guncel_satir = 2
            if "RSI (Alt Grafik)" in ek_gostergeler:
                fig.add_trace(go.Scatter(x=df_analiz['tarih'], y=df_analiz['rsi'], name='RSI', line=dict(color='purple', width=1.5)), row=guncel_satir, col=1)
                guncel_satir += 1
                
            if "MACD (Alt Grafik)" in ek_gostergeler:
                fig.add_trace(go.Scatter(x=df_analiz['tarih'], y=df_analiz['macd'], name='MACD', line=dict(color='blue')), row=guncel_satir, col=1)

            # Grafik Arayüzü Geliştirmeleri (Zoom, Çizim, Crosshair)
            fig.update_layout(
                template="plotly_dark", 
                height=650 if satir_sayisi == 1 else 850, 
                margin=dict(l=0, r=0, t=30, b=0), 
                xaxis_rangeslider_visible=False,
                dragmode='zoom', # Varsayılan olarak zoom açık
                hovermode='x unified' # Aynı dikey çizgideki tüm değerleri gösterir
            )
            
            # config ile Streamlit üzerinde ekstra butonları aktifleştirme
            st.plotly_chart(
                fig, 
                use_container_width=True, 
                config={
                    'scrollZoom': True, # Fare tekerleği ile zoom
                    'displayModeBar': True,
                    'modeBarButtonsToAdd': ['drawline', 'drawopenpath', 'eraseshape'] # Çizim araçları
                }
            )

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
