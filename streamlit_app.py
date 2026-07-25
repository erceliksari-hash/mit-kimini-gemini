import datetime
import json
import os
import threading
import time
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
import streamlit as st

# Proje Modülleri Entegrasyonu
from config import TELEGRAM_CHAT_ID, TELEGRAM_TOKEN
from data_sources import veri_cek
from indicators import (
    hesapla_teknikler,
    piyasa_analizi_yap,
    sinyal_kontrol,
)
from utils import donusum_noktalari_hesapla

st.set_page_config(
    page_title="Pro Finans Paneli & Adaptif Bot", layout="wide"
)
st.markdown(
    """<style>.stApp { background-color: #0e1117; }</style>""",
    unsafe_allow_html=True,
)

# --- DOSYA VE AYAR YAPISI ---
AYAR_DOSYASI = "ayarlar.json"
PORTFOY_DOSYASI = "portfoy_arsiv.json"
SANAL_PORTFOY_DOSYASI = "sanal_portfoy.json"

VARSAYILAN_AYARLAR = {
    "varliklar": [
        "BTC-USD",
        "ETH-USD",
        "EURUSD=X",
        "GBPUSD=X",
        "THYAO.IS",
        "AAPL",
        "NVDA",
    ],
    "zaman_dilimi": "1h",
    "bot_sikligi_dk": 60,
    "oto_trade_aktif": True,
}

VARSAYILAN_SANAL_PORTFOY = {
    "bakiye": 10000.0,
    "baslangic_bakiye": 10000.0,
    "baslangic_tarihi": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
    "pozisyonlar": {},
    "islem_gecmisi": [],
    "soguma_listesi": {},
}


# --- DOSYA YÖNETİMİ FONKSİYONLARI ---
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


def portfoy_yukle():
    if not os.path.exists(PORTFOY_DOSYASI):
        return {}
    try:
        with open(PORTFOY_DOSYASI, "r") as f:
            return json.load(f)
    except:
        return {}


def portfoy_kaydet(portfoy_verisi):
    with open(PORTFOY_DOSYASI, "w") as f:
        json.dump(portfoy_verisi, f)


def sanal_portfoy_yukle():
    if not os.path.exists(SANAL_PORTFOY_DOSYASI):
        with open(SANAL_PORTFOY_DOSYASI, "w") as f:
            json.dump(VARSAYILAN_SANAL_PORTFOY, f)
        return VARSAYILAN_SANAL_PORTFOY
    try:
        with open(SANAL_PORTFOY_DOSYASI, "r") as f:
            return json.load(f)
    except:
        return VARSAYILAN_SANAL_PORTFOY


def sanal_portfoy_kaydet(sanal_verisi):
    with open(SANAL_PORTFOY_DOSYASI, "w") as f:
        json.dump(sanal_verisi, f)


def telegram_bildirim_gonder(mesaj):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": mesaj,
        "parse_mode": "Markdown",
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except:
        pass


# --- DETAYLI ANALİZ VE YORUM OLUŞTURUCU ---
def detayli_analiz_ve_yorum_olustur(varlik, df_t_analiz, p_analiz, p_sinyal):
    fiyat = p_analiz["fiyat"]
    d1 = p_analiz["destek"]
    r1 = p_analiz["direnc"]

    stop_loss = d1 if d1 < fiyat else fiyat * 0.97
    take_profit = r1 if r1 > fiyat else fiyat * 1.05

    is_fake = df_t_analiz.iloc[-1].get("sahte_sinyal", False)
    sinyal_ust = str(p_sinyal).upper()

    if "AL" in sinyal_ust or "YÜKSELİŞ" in sinyal_ust:
        trend_yorum = "📈 *Yükseliş Trendi Hâkim.* Bot LONG yönlü fırsatları değerlendiriyor."
    elif "SAT" in sinyal_ust or "DÜŞÜŞ" in sinyal_ust:
        trend_yorum = (
            "📉 *Düşüş Baskısı Hâkim.* Bot SHORT yönlü fırsatları değerlendiriyor."
        )
    else:
        trend_yorum = (
            "⚖️ *Yatay / Belirsiz Seyir.* Konsolidasyon alanında beklemede."
        )

    sahte_yorum = (
        "⚠️ *Sahte Sinyal Riski Var!*"
        if is_fake
        else "✅ *Güvenilir Sinyal Teyidi Var.*"
    )

    rapor_metni = (
        f"🔹 *{varlik}*\n"
        f"   • *Fiyat:* `{fiyat:.4f}` | *Sinyal:* `{p_sinyal}`\n"
        f"   • *Destek:* `{d1:.4f}` | *Direnç:* `{r1:.4f}`\n"
        f"   • *Öngörülen SL:* `{stop_loss:.4f}` | *TP:* `{take_profit:.4f}`\n"
        f"   • *Analiz Yorumu:* {trend_yorum}\n"
        f"   • *Kalite:* {sahte_yorum}\n\n"
    )
    return rapor_metni


# --- PİYASA REJİMİ VE VOLATİLİTE TESPİTİ ---
def piyasa_rejimini_tespit_et(df):
    if len(df) < 20:
        return "NÖTR", 0.02, 0.04

    fiyat = df["close"].iloc[-1]
    sma_20 = df["sma_20"].iloc[-1] if "sma_20" in df.columns else fiyat
    ema_50 = df["ema_50"].iloc[-1] if "ema_50" in df.columns else fiyat

    degisim = df["close"].pct_change().dropna()
    volatilite = degisim.tail(14).std()

    if fiyat > sma_20 > ema_50 and volatilite > 0.008:
        rejim = "GÜÇLÜ_BOĞA"
        sl_oran = 0.02
        tp_oran = 0.06
    elif fiyat < sma_20 < ema_50 and volatilite > 0.008:
        rejim = "GÜÇLÜ_AYI"
        sl_oran = 0.02
        tp_oran = 0.06
    else:
        rejim = "YATAY_DÜŞÜK_VOLATİLİTE"
        sl_oran = 0.015
        tp_oran = 0.025

    return rejim, sl_oran, tp_oran


# --- ADAPTİF OTONOM TRADE MOTORU ---
def adaptif_sanal_trade_isle(varlik, df_t_analiz, p_analiz, p_sinyal):
    ayarlar = ayarlari_yukle()
    if not ayarlar.get("oto_trade_aktif", True):
        return

    sanal = sanal_portfoy_yukle()
    fiyat = p_analiz["fiyat"]
    is_fake = df_t_analiz.iloc[-1].get("sahte_sinyal", False)
    pozisyonlar = sanal.get("pozisyonlar", {})
    soguma_listesi = sanal.get("soguma_listesi", {})
    bakiye = sanal.get("bakiye", 10000.0)
    simdi_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    if varlik in soguma_listesi:
        if time.time() < soguma_listesi[varlik]:
            return
        else:
            del sanal["soguma_listesi"][varlik]

    sinyal_ust = str(p_sinyal).upper()
    rejim, sl_oran, tp_oran = piyasa_rejimini_tespit_et(df_t_analiz)

    if varlik in pozisyonlar:
        poz = pozisyonlar[varlik]
        yon = poz.get("yon", "LONG")
        maliyet = poz["maliyet"]
        adet = poz["adet"]
        sl = poz.get("sl")
        tp = poz.get("tp")

        satis_nedeni = None
        pnl = 0.0

        if yon == "LONG":
            if fiyat <= sl:
                satis_nedeni = "🛑 Stop-Loss Tetiklendi (LONG)"
            elif fiyat >= tp:
                satis_nedeni = "🎯 Take-Profit Tetiklendi (LONG)"
            elif "SAT" in sinyal_ust or "DÜŞÜŞ" in sinyal_ust:
                satis_nedeni = "📉 Sinyal Dönüşü (LONG Kapatıldı)"

            if satis_nedeni:
                pnl = (fiyat - maliyet) * adet
                gelir = (maliyet * adet) + pnl
                sanal["bakiye"] += gelir

        elif yon == "SHORT":
            if fiyat >= sl:
                satis_nedeni = "🛑 Stop-Loss Tetiklendi (SHORT)"
            elif fiyat <= tp:
                satis_nedeni = "🎯 Take-Profit Tetiklendi (SHORT)"
            elif "AL" in sinyal_ust or "YÜKSELİŞ" in sinyal_ust:
                satis_nedeni = "📈 Sinyal Dönüşü (SHORT Kapatıldı)"

            if satis_nedeni:
                pnl = (maliyet - fiyat) * adet
                gelir = (maliyet * adet) + pnl
                sanal["bakiye"] += gelir

        if satis_nedeni:
            harcanan = maliyet * adet
            pnl_yuzde = (pnl / harcanan) * 100 if harcanan > 0 else 0
            del sanal["pozisyonlar"][varlik]

            if pnl < 0 and "Stop-Loss" in satis_nedeni:
                sanal["soguma_listesi"][varlik] = time.time() + (3 * 3600)

            islem_log = {
                "tarih": simdi_str,
                "varlik": varlik,
                "yon": yon,
                "tip": "KAPATMA",
                "neden": satis_nedeni,
                "fiyat": fiyat,
                "pnl": round(pnl, 2),
                "pnl_yuzde": round(pnl_yuzde, 2),
                "rejim": rejim,
            }
            sanal["islem_gecmisi"].append(islem_log)
            sanal_portfoy_kaydet(sanal)

            tg_msg = (
                f"🧠 *ADAPTİF BOT: POZİSYON KAPATILDI*\n\n"
                f"📌 *Varlık:* `{varlik}` ({yon})\n"
                f"📋 *Neden:* {satis_nedeni}\n"
                f"📊 *Rejim:* `{rejim}`\n"
                f"💵 *Giriş:* `{maliyet:.4f}` | *Çıkış:* `{fiyat:.4f}`\n"
                f"💰 *Kâr / Zarar:* `{pnl:+.2f} $` (%{pnl_yuzde:+.2f})\n"
                f"🏦 *Kasa Bakiye:* `{sanal['bakiye']:.2f} $`"
            )
            telegram_bildirim_gonder(tg_msg)

    else:
        if is_fake:
            return

        yeni_yon = None
        if "AL" in sinyal_ust or "YÜKSELİŞ" in sinyal_ust:
            yeni_yon = "LONG"
            sl = fiyat * (1 - sl_oran)
            tp = fiyat * (1 + tp_oran)
        elif "SAT" in sinyal_ust or "DÜŞÜŞ" in sinyal_ust:
            yeni_yon = "SHORT"
            sl = fiyat * (1 + sl_oran)
            tp = fiyat * (1 - tp_oran)

        if yeni_yon and bakiye >= 100.0:
            kullanilacak_oran = 0.30 if rejim != "GÜÇLÜ_BOĞA" else 0.40
            ayrilan_butce = bakiye * kullanilacak_oran
            adet = ayrilan_butce / fiyat

            sanal["bakiye"] -= ayrilan_butce
            sanal["pozisyonlar"][varlik] = {
                "yon": yeni_yon,
                "maliyet": fiyat,
                "adet": adet,
                "tarih": simdi_str,
                "sl": sl,
                "tp": tp,
            }

            islem_log = {
                "tarih": simdi_str,
                "varlik": varlik,
                "yon": yeni_yon,
                "tip": "GİRİŞ",
                "neden": f"🤖 Adaptif Analiz ({rejim})",
                "fiyat": fiyat,
                "pnl": 0.0,
                "rejim": rejim,
            }
            sanal["islem_gecmisi"].append(islem_log)
            sanal_portfoy_kaydet(sanal)

            tg_msg = (
                f"🧠 *ADAPTİF BOT: İŞLEM AÇILDI*\n\n"
                f"📌 *Varlık:* `{varlik}` ({yeni_yon})\n"
                f"🌐 *Piyasa Rejimi:* `{rejim}`\n"
                f"💵 *Giriş Fiyatı:* `{fiyat:.4f}`\n"
                f"🛡️ *Adaptif SL:* `{sl:.4f}` (%%{sl_oran*100:.1f})\n"
                f"🎯 *Adaptif TP:* `{tp:.4f}` (%%{tp_oran*100:.1f})\n"
                f"💰 *Kalan Bakiye:* `{sanal['bakiye']:.2f} $`"
            )
            telegram_bildirim_gonder(tg_msg)


# --- OTOMATİK TARAMA BOTU THREAD ---
def otomatik_tarama_botu():
    time.sleep(5)
    while True:
        try:
            ayarlar = ayarlari_yukle()
            varliklar = sorted(ayarlar.get("varliklar", []))
            zaman_dilimi = ayarlar.get("zaman_dilimi", "1h")
            bekleme_suresi = ayarlar.get("bot_sikligi_dk", 60) * 60

            if varliklar:
                telegram_toplu_mesaj = f"📊 *Otonom Tarama & Sinyal Raporu* ({zaman_dilimi})\n\n"
                for varlik in varliklar:
                    df_t = veri_cek(varlik, aralik=zaman_dilimi)
                    if df_t is not None and not df_t.empty:
                        df_t_analiz = hesapla_teknikler(df_t)
                        p_analiz = donusum_noktalari_hesapla(df_t_analiz)
                        p_sinyal = sinyal_kontrol(df_t_analiz)

                        adaptif_sanal_trade_isle(
                            varlik, df_t_analiz, p_analiz, p_sinyal
                        )

                        telegram_toplu_mesaj += detayli_analiz_ve_yorum_olustur(
                            varlik, df_t_analiz, p_analiz, p_sinyal
                        )

                telegram_bildirim_gonder(telegram_toplu_mesaj)
        except Exception as e:
            pass
        time.sleep(bekleme_suresi)


if "arkaplan_bot_aktif" not in globals():
    globals()["arkaplan_bot_aktif"] = True
    threading.Thread(target=otomatik_tarama_botu, daemon=True).start()


# --- PLOTLY GRAFİK OLUŞTURUCU ---
def grafik_olustur(df, varlik_kodu, drag_mode="zoom"):
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.7, 0.3],
        subplot_titles=(
            f"{varlik_kodu} Fiyat Grafiği ve İndikatörler",
            "RSI (14)",
        ),
    )
    x_axis = df["tarih"] if "tarih" in df.columns else df.index

    fig.add_trace(
        go.Candlestick(
            x=x_axis,
            open=df["open"],
            high=df["high"],
            low=df["low"],
            close=df["close"],
            name="Fiyat",
        ),
        row=1,
        col=1,
    )
    if "sma_20" in df.columns:
        fig.add_trace(
            go.Scatter(
                x=x_axis,
                y=df["sma_20"],
                mode="lines",
                name="SMA 20",
                line=dict(color="orange", width=1),
            ),
            row=1,
            col=1,
        )
    if "ema_50" in df.columns:
        fig.add_trace(
            go.Scatter(
                x=x_axis,
                y=df["ema_50"],
                mode="lines",
                name="EMA 50",
                line=dict(color="cyan", width=1),
            ),
            row=1,
            col=1,
        )
    if "rsi" in df.columns:
        fig.add_trace(
            go.Scatter(
                x=x_axis,
                y=df["rsi"],
                mode="lines",
                name="RSI",
                line=dict(color="magenta", width=1.5),
            ),
            row=2,
            col=1,
        )
        fig.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1)
        fig.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1)

    fig.update_layout(
        template="plotly_dark",
        dragmode=drag_mode,
        xaxis_rangeslider_visible=False,
        height=600,
        margin=dict(l=20, r=20, t=40, b=20),
    )
    return fig


# --- STREAMLIT ARAYÜZ (UI) ---
aktif_ayarlar = ayarlari_yukle()
aktif_portfoy = portfoy_yukle()
sanal_portfoy = sanal_portfoy_yukle()

st.sidebar.title("🤖 Pro Asistan & Adaptif Bot")
sayfa = st.sidebar.radio(
    "Menü Seçimi",
    [
        "🧪 1 Haftalık Adaptif Deney",
        "📈 Canlı Analiz & Grafik İncele",
        "📚 Varlık Havuzu Yönetimi",
        "💼 Manuel Portföy Yönetimi",
        "⚙️ Bot Ayarları",
    ],
)
st.sidebar.divider()

# === SAYFA 1: ADAPTİF DENEY PANELSİ ===
if sayfa == "🧪 1 Haftalık Adaptif Deney":
    st.title("🧪 Adaptif ve Öğrenen Cüzdan Deneyi")
    st.info(
        "💡 **Sistem Mantığı:** Bot, piyasa rejimini analiz ederek Long/Short pozisyonları açar, Stop/Kâr hedeflerini dinamik belirler ve Telegram'a raporlar."
    )

    toplam_sanal_portfoy_degeri = sanal_portfoy["bakiye"]
    acik_pozisyonlar = sanal_portfoy.get("pozisyonlar", {})

    for v_kod, v_poz in acik_pozisyonlar.items():
        df_c = veri_cek(v_kod, aralik="1h")
        anlik_f = (
            df_c["close"].iloc[-1]
            if df_c is not None and not df_c.empty
            else v_poz["maliyet"]
        )
        yon = v_poz.get("yon", "LONG")

        if yon == "LONG":
            pnl = (anlik_f - v_poz["maliyet"]) * v_poz["adet"]
        else:
            pnl = (v_poz["maliyet"] - anlik_f) * v_poz["adet"]

        toplam_sanal_portfoy_degeri += (v_poz["maliyet"] * v_poz["adet"]) + pnl

    baslangic = sanal_portfoy.get("baslangic_bakiye", 10000.0)
    toplam_pnl = toplam_sanal_portfoy_degeri - baslangic
    toplam_pnl_yuzde = (toplam_pnl / baslangic) * 100

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Kullanılabilir Nakit", f"{sanal_portfoy['bakiye']:.2f} $")
    k2.metric("Toplam Varlık Değeri", f"{toplam_sanal_portfoy_degeri:.2f} $")
    k3.metric(
        "Net Kâr / Zarar",
        f"{toplam_pnl:+.2f} $",
        delta=f"%{toplam_pnl_yuzde:+.2f}",
    )
    k4.metric("Açık Pozisyon Sayısı", str(len(acik_pozisyonlar)))

    st.divider()

    c_bot1, c_bot2 = st.columns(2)
    with c_bot1:
        oto_durum = aktif_ayarlar.get("oto_trade_aktif", True)
        yeni_durum = st.toggle("🤖 Otonom Trade Motoru Aktif", value=oto_durum)
        if yeni_durum != oto_durum:
            aktif_ayarlar["oto_trade_aktif"] = yeni_durum
            ayarlari_kaydet(aktif_ayarlar)
            st.rerun()

    with c_bot2:
        if st.button(
            "🔄 Deneyi Yeniden Başlat ($10,000 SIFIRLA)", type="secondary"
        ):
            yeni_deney = VARSAYILAN_SANAL_PORTFOY.copy()
            yeni_deney["baslangic_tarihi"] = datetime.datetime.now().strftime(
                "%Y-%m-%d %H:%M"
            )
            sanal_portfoy_kaydet(yeni_deney)
            st.success("Deney sıfırlandı ve 1 haftalık sayaç başladı!")
            st.rerun()

    st.caption(
        f"📅 Deney Başlangıç Tarihi: **{sanal_portfoy.get('baslangic_tarihi', 'Bilinmiyor')}**"
    )

    st.divider()
    st.subheader("📌 Bot Tarafından Yönetilen Açık Pozisyonlar")

    if not acik_pozisyonlar:
        st.info(
            "Şu an açık pozisyon bulunmuyor. Bot piyasayı ve varlık fırsatlarını tarıyor..."
        )
    else:
        poz_listesi = []
        for v_kod, v_poz in acik_pozisyonlar.items():
            df_c = veri_cek(v_kod, aralik="1h")
            anlik_f = (
                df_c["close"].iloc[-1]
                if df_c is not None and not df_c.empty
                else v_poz["maliyet"]
            )
            yon = v_poz.get("yon", "LONG")

            if yon == "LONG":
                k_z = (anlik_f - v_poz["maliyet"]) * v_poz["adet"]
                k_z_pct = ((anlik_f - v_poz["maliyet"]) / v_poz["maliyet"]) * 100
            else:
                k_z = (v_poz["maliyet"] - anlik_f) * v_poz["adet"]
                k_z_pct = ((v_poz["maliyet"] - anlik_f) / v_poz["maliyet"]) * 100

            poz_listesi.append({
                "Varlık": v_kod,
                "İşlem Yönü": yon,
                "Giriş Tarihi": v_poz["tarih"],
                "Giriş Fiyatı": round(v_poz["maliyet"], 4),
                "Anlık Fiyat": round(anlik_f, 4),
                "Lot Adedi": round(v_poz["adet"], 4),
                "Adaptif SL": round(v_poz.get("sl", 0), 4),
                "Adaptif TP": round(v_poz.get("tp", 0), 4),
                "Kâr / Zarar ($)": round(k_z, 2),
                "Kâr / Zarar (%)": f"%{k_z_pct:+.2f}",
            })
        st.dataframe(pd.DataFrame(poz_listesi), use_container_width=True)

    st.divider()
    st.subheader("📜 Otonom İşlem Logu ve Raporları")
    st.dataframe(
        pd.DataFrame(sanal_portfoy.get("islem_gecmisi", [])[::-1]),
        use_container_width=True,
    )

# === SAYFA 2: CANLI ANALİZ VE GRAFİK İNCELEME ===
elif sayfa == "📈 Canlı Analiz & Grafik İncele":
    st.title("📈 Canlı Teknik Analiz ve İnteraktif Grafikler")
    mevcut_varliklar = sorted(aktif_ayarlar.get("varliklar", []))

    if mevcut_varliklar:
        if (
            "secilen_aktif_grafik" not in st.session_state
            or st.session_state["secilen_aktif_grafik"] not in mevcut_varliklar
        ):
            st.session_state["secilen_aktif_grafik"] = mevcut_varliklar[0]

        for varlik in mevcut_varliklar:
            df_temp = veri_cek(varlik, aralik=aktif_ayarlar["zaman_dilimi"])
            if df_temp is not None and not df_temp.empty:
                df_t_analiz = hesapla_teknikler(df_temp)
                p_analiz = donusum_noktalari_hesapla(df_t_analiz)
                p_sinyal = sinyal_kontrol(df_t_analiz)

                detay_metni = detayli_analiz_ve_yorum_olustur(
                    varlik, df_t_analiz, p_analiz, p_sinyal
                )

                col_info, col_btn = st.columns([4, 1])
                with col_info:
                    st.markdown(detay_metni)
                with col_btn:
                    if st.button(
                        f"📊 Grafiği Aç",
                        key=f"btn_list_{varlik}",
                        use_container_width=True,
                    ):
                        st.session_state["secilen_aktif_grafik"] = varlik
                        st.rerun()
                st.divider()

        st.header(
            f"📊 Detaylı Grafik İncelemesi: `{st.session_state['secilen_aktif_grafik']}`"
        )
        df_grafik = veri_cek(
            st.session_state["secilen_aktif_grafik"],
            aralik=aktif_ayarlar["zaman_dilimi"],
        )
        if df_grafik is not None and not df_grafik.empty:
            df_grafik_analiz = hesapla_teknikler(df_grafik)
            fig = grafik_olustur(
                df_grafik_analiz, st.session_state["secilen_aktif_grafik"]
            )
            st.plotly_chart(fig, use_container_width=True)

# === SAYFA 3: VARLIK HAVUZU YÖNETİMİ ===
elif sayfa == "📚 Varlık Havuzu Yönetimi":
    st.title("📚 Varlık Havuzu Yönetimi")
    st.write(
        "Kripto (BTC-USD), Forex (EURUSD=X) ve Borsa Hisselerini (THYAO.IS, AAPL) buradan ekleyip çıkarabilirsiniz."
    )

    mevcut = aktif_ayarlar.get("varliklar", [])
    col_add, col_del = st.columns(2)

    with col_add:
        st.subheader("➕ Yeni Varlık Ekle")
        yeni_v = st.text_input("Varlık Kodu (Örn: SOL-USD, GARAN.IS, GBPUSD=X):")
        if st.button("Havuza Ekle") and yeni_v:
            yeni_kod = yeni_v.strip().upper()
            if yeni_kod not in mevcut:
                mevcut.append(yeni_kod)
                aktif_ayarlar["varliklar"] = mevcut
                ayarlari_kaydet(aktif_ayarlar)
                st.success(f"{yeni_kod} havuza eklendi!")
                st.rerun()

    with col_del:
        st.subheader("➖ Varlık Çıkar")
        if mevcut:
            silinecek_v = st.selectbox("Çıkarılacak Varlık:", mevcut)
            if st.button("Havuzdan Çıkar") and silinecek_v:
                mevcut.remove(silinecek_v)
                aktif_ayarlar["varliklar"] = mevcut
                ayarlari_kaydet(aktif_ayarlar)
                st.warning(f"{silinecek_v} havuzdan çıkarıldı.")
                st.rerun()

    st.divider()
    st.subheader("📋 Şu An Takip Edilen Tüm Varlıklar")
    for v_kod in sorted(mevcut):
        st.write(f"• `{v_kod}`")

# === SAYFA 4: MANUEL PORTFÖY ===
elif sayfa == "💼 Manuel Portföy Yönetimi":
    st.title("💼 Gerçek / Manuel PortföY Takibi")
    st.write(
        "Gerçek varlıklarınızı ve aldığınız fiyatları buraya kaydedip canlı piyasaya göre kâr/zarar durumunuzu takip edebilirsiniz."
    )

    m_varlik = st.text_input("Varlık Sembolü (Örn: THYAO.IS):")
    m_maliyet = st.number_input("Alış Fiyatı:", min_value=0.0, format="%.4f")
    m_adet = st.number_input("Adet / Lot:", min_value=0.0, format="%.4f")

    if st.button("Manuel Portföye Ekle") and m_varlik and m_adet > 0:
        m_kod = m_varlik.strip().upper()
        aktif_portfoy[m_kod] = {"maliyet": m_maliyet, "adet": m_adet}
        portfoy_kaydet(aktif_portfoy)
        st.success(f"{m_kod} portföye eklendi!")
        st.rerun()

    st.divider()
    st.subheader("📊 Kayıtlı Portföyünüz")
    if aktif_portfoy:
        p_list = []
        for pk, pv in aktif_portfoy.items():
            df_p = veri_cek(pk, aralik="1d")
            anlik = (
                df_p["close"].iloc[-1]
                if df_p is not None and not df_p.empty
                else pv["maliyet"]
            )
            top_maliyet = pv["maliyet"] * pv["adet"]
            top_deger = anlik * pv["adet"]
            pnl_val = top_deger - top_maliyet

            p_list.append({
                "Varlık": pk,
                "Alış Fiyatı": pv["maliyet"],
                "Anlık Fiyat": anlik,
                "Adet": pv["adet"],
                "Toplam Değer ($/₺)": round(top_deger, 2),
                "Kâr / Zarar": round(pnl_val, 2),
            })
        st.dataframe(pd.DataFrame(p_list), use_container_width=True)
    else:
        st.info("Henüz manuel portföy kaydı girmediniz.")

# === SAYFA 5: AYARLAR ===
elif sayfa == "⚙️ Bot Ayarları":
    st.title("⚙️ Bot ve Sistem Ayarları")

    zaman_dilimleri = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]
    mevcut_zaman = aktif_ayarlar.get("zaman_dilimi", "1h")

    idx = (
        zaman_dilimleri.index(mevcut_zaman)
        if mevcut_zaman in zaman_dilimleri
        else 4
    )
    secilen_zaman = st.selectbox(
        "Analiz Periyodu (Mum Grafiği)", zaman_dilimleri, index=idx
    )
    secilen_siklik = st.number_input(
        "Bot Taraması Kaç Dakikada Bir Çalışsın? (Sıklık)",
        min_value=1,
        value=int(aktif_ayarlar.get("bot_sikligi_dk", 60)),
    )

    if st.button("Ayarları Kaydet"):
        aktif_ayarlar["zaman_dilimi"] = secilen_zaman
        aktif_ayarlar["bot_sikligi_dk"] = int(secilen_siklik)
        ayarlari_kaydet(aktif_ayarlar)
        st.success("Sistem ayarları başarıyla güncellendi!")
        st.rerun()
