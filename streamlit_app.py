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

# Proje Modülleri
from config import TELEGRAM_CHAT_ID, TELEGRAM_TOKEN
from data_sources import veri_cek
from indicators import (
    hesapla_teknikler,
    piyasa_analizi_yap,
    sinyal_kontrol,
)
from utils import donusum_noktalari_hesapla

st.set_page_config(
    page_title="Pro Finans & Adaptif Otonom Bot", layout="wide"
)
st.markdown(
    """<style>.stApp { background-color: #0e1117; }</style>""",
    unsafe_allow_html=True,
)

# --- DOSYA VE AYAR YAPISI ---
AYAR_DOSYASI = "ayarlar.json"
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
    "soguma_listesi": {},  # Ardışık kayıplarda geçici engellenen varlıklar
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


# --- PİYASA REJİMİ VE VOLATİLİTE HESAPLAYICI (ADAPTİF STRATEJİ) ---
def piyasa_rejimini_tespit_et(df):
    """Piyasanın trend mi yoksa yatay mı olduğunu analiz edip risk ve kâr oranlarını belirler."""
    if len(df) < 20:
        return "NÖTR", 0.02, 0.04

    fiyat = df["close"].iloc[-1]
    sma_20 = df["sma_20"].iloc[-1] if "sma_20" in df.columns else fiyat
    ema_50 = df["ema_50"].iloc[-1] if "ema_50" in df.columns else fiyat

    # Volatilite tahmini (ATR/Fiyat veya Kapanış Değişim Standart Sapması)
    degisim = df["close"].pct_change().dropna()
    volatilite = degisim.tail(14).std()

    # Trend Gücü Tespiti
    if fiyat > sma_20 > ema_50 and volatilite > 0.008:
        rejim = "GÜÇLÜ_BOĞA"
        sl_oran = 0.02  # %2 Stop
        tp_oran = 0.06  # %6 Kâr Al (Trend avantajından faydalanma)
    elif fiyat < sma_20 < ema_50 and volatilite > 0.008:
        rejim = "GÜÇLÜ_AYI"
        sl_oran = 0.02  # %2 Stop
        tp_oran = 0.06  # %6 Kâr Al (Short fırsatı)
    else:
        rejim = "YATAY_DÜŞÜK_VOLATİLİTE"
        sl_oran = 0.015  # %1.5 Dar Stop
        tp_oran = 0.025  # %2.5 Hızlı Kâr Al

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

    # Soğuma Süresi Kontrolü (Hatalı/Kayıplı varlıkların engellenmesi)
    if varlik in soguma_listesi:
        if time.time() < soguma_listesi[varlik]:
            return  # Soğuma süresi bitmedi, işlem pas geçiliyor
        else:
            del sanal["soguma_listesi"][varlik]

    sinyal_ust = str(p_sinyal).upper()
    rejim, sl_oran, tp_oran = piyasa_rejimini_tespit_et(df_t_analiz)

    # 1. POZİSYON KAPATMA VE PERFORMANS DEĞERLENDİRME
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
                satis_nedeni = "🛑 Stop-Loss Tetiklendi"
            elif fiyat >= tp:
                satis_nedeni = "🎯 Adaptif Take-Profit Ulaşıldı"
            elif "SAT" in sinyal_ust or "DÜŞÜŞ" in sinyal_ust:
                satis_nedeni = "📉 Sinyal Dönüşü (LONG Kapatıldı)"

            if satis_nedeni:
                pnl = (fiyat - maliyet) * adet
                gelir = (maliyet * adet) + pnl
                sanal["bakiye"] += gelir

        elif yon == "SHORT":
            if fiyat >= sl:
                satis_nedeni = "🛑 Stop-Loss Tetiklendi"
            elif fiyat <= tp:
                satis_nedeni = "🎯 Adaptif Take-Profit Ulaşıldı"
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

            # Kayıp Yönlü İyileştirme: Stop olunduysa varlığı 3 saat soğumaya al
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

    # 2. YENİ ADAPTİF POZİSYON AÇILIŞI
    else:
        if is_fake:
            return  # Yanlış/Sahte sinyaller elenir

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
            # Rejime göre esnek pozisyon büyüklüğü
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
                for varlik in varliklar:
                    df_t = veri_cek(varlik, aralik=zaman_dilimi)
                    if df_t is not None and not df_t.empty:
                        df_t_analiz = hesapla_teknikler(df_t)
                        p_analiz = donusum_noktalari_hesapla(df_t_analiz)
                        p_sinyal = sinyal_kontrol(df_t_analiz)

                        adaptif_sanal_trade_isle(
                            varlik, df_t_analiz, p_analiz, p_sinyal
                        )

        except Exception as e:
            pass
        time.sleep(bekleme_suresi)


if "arkaplan_bot_aktif" not in globals():
    globals()["arkaplan_bot_aktif"] = True
    threading.Thread(target=otomatik_tarama_botu, daemon=True).start()


# --- STREAMLIT ARAYÜZ (UI) ---
aktif_ayarlar = ayarlari_yukle()
sanal_portfoy = sanal_portfoy_yukle()

st.sidebar.title("🧠 Adaptif Otonom Asistan")
sayfa = st.sidebar.radio(
    "Menü Seçimi",
    [
        "🧪 Adaptif Deney Paneli",
        "📈 Canlı Piyasa Taraması",
        "📚 Varlık Havuzu (Kripto/Forex/Hisse)",
        "⚙️ Bot Ayarları",
    ],
)
st.sidebar.divider()

if sayfa == "🧪 Adaptif Deney Paneli":
    st.title("🧪 Adaptif ve Öğrenen Cüzdan Deneyi")
    st.info(
        "💡 **Sistem Modu:** Dinamik Risk/Ödül Oranı, Piyasa Rejim Tespiti ve Hata Engelleme (Soğuma) Sistemi Aktif."
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
    k4.metric("Açık Pozisyonlar", str(len(acik_pozisyonlar)))

    st.divider()

    st.subheader("📌 Açık Pozisyonlar ve Adaptif Limitler")
    if not acik_pozisyonlar:
        st.info(
            "Henüz pozisyon açılmadı. Bot piyasa rejimini ve varlık fırsatlarını gözlemliyor..."
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
                "Yön": yon,
                "Giriş Fiyatı": round(v_poz["maliyet"], 4),
                "Anlık Fiyat": round(anlik_f, 4),
                "Adaptif Stop (SL)": round(v_poz.get("sl", 0), 4),
                "Adaptif Hedef (TP)": round(v_poz.get("tp", 0), 4),
                "Kâr / Zarar ($)": round(k_z, 2),
                "Kâr / Zarar (%)": f"%{k_z_pct:+.2f}",
            })
        st.dataframe(pd.DataFrame(poz_listesi), use_container_width=True)

    st.divider()
    st.subheader("📜 Öğrenen Algoritma İşlem Kayıtları")
    st.dataframe(
        pd.DataFrame(sanal_portfoy.get("islem_gecmisi", [])[::-1]),
        use_container_width=True,
    )

elif sayfa == "📚 Varlık Havuzu (Kripto/Forex/Hisse)":
    st.title("📚 Varlık Havuzu Yönetimi")
    st.write(
        "Botun taramasını istediğin tüm **Kripto (BTC-USD), Forex (EURUSD=X) ve Borsa Hisselerini (THYAO.IS, AAPL)** buraya ekleyebilirsin."
    )

    mevcut = aktif_ayarlar.get("varliklar", [])
    yeni_varlik = st.text_input(
        "Yeni Varlık Sembolü Ekle (Örn: SOL-USD, GBPUSD=X, GARAN.IS):"
    )

    if st.button("Havuz Ekle") and yeni_varlik:
        if yeni_varlik.upper() not in mevcut:
            mevcut.append(yeni_varlik.upper())
            aktif_ayarlar["varliklar"] = mevcut
            ayarlari_kaydet(aktif_ayarlar)
            st.success(f"{yeni_varlik.upper()} havuza eklendi!")
            st.rerun()

    st.write("Current Takip Listesi:", mevcut)
