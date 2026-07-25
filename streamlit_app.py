import datetime
import json
import os
import threading
import time
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
import streamlit as st

from config import TELEGRAM_CHAT_ID, TELEGRAM_TOKEN
from data_sources import veri_cek
from indicators import (
    hesapla_teknikler,
    piyasa_analizi_yap,
    sinyal_kontrol,
)
from utils import donusum_noktalari_hesapla

st.set_page_config(page_title="Pro Finans Paneli", layout="wide")
st.markdown(
    """<style>.stApp { background-color: #0e1117; }</style>""",
    unsafe_allow_html=True,
)

# --- AYAR VE VERİ YÖNETİMİ ---
AYAR_DOSYASI = "ayarlar.json"
PORTFOY_DOSYASI = "portfoy_arsiv.json"
VARSAYILAN_AYARLAR = {
    "varliklar": ["BTC-USD", "THYAO.IS", "AAPL", "SPY"],
    "zaman_dilimi": "1h",
    "bot_sikligi_dk": 60,
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


# --- TELEGRAM BOT VE OTOMATİK RAPORLAMA ---
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


def otomatik_tarama_botu():
    time.sleep(15)
    while True:
        try:
            ayarlar = ayarlari_yukle()
            varliklar = ayarlar.get("varliklar", [])
            zaman_dilimi = ayarlar.get("zaman_dilimi", "1h")
            bekleme_suresi = ayarlar.get("bot_sikligi_dk", 60) * 60

            if varliklar:
                telegram_toplu_mesaj = f"📊 *Otomatik Sinyal, Stop-Loss ve TP Raporu* (Periyot: {zaman_dilimi})\n\n"
                for varlik in varliklar:
                    df_t = veri_cek(varlik, aralik=zaman_dilimi)
                    if df_t is not None and not df_t.empty:
                        df_t_analiz = hesapla_teknikler(df_t)
                        p_analiz = donusum_noktalari_hesapla(df_t_analiz)
                        p_sinyal = sinyal_kontrol(df_t_analiz)

                        fiyat = p_analiz["fiyat"]
                        destek = p_analiz["destek"]
                        direnc = p_analiz["direnc"]
                        stop_loss = destek if destek < fiyat else fiyat * 0.97
                        take_profit = direnc if direnc > fiyat else fiyat * 1.05

                        is_fake = df_t_analiz.iloc[-1].get("sahte_sinyal", False)
                        gecis_tarihi = df_t_analiz.iloc[-1].get("tarih", "-")

                        telegram_toplu_mesaj += (
                            f"🔹 *{varlik}*\n"
                            f"   • Fiyat: `{fiyat:.2f}`\n"
                            f"   • Durum: `{p_sinyal}`\n"
                            f"   • Geçiş Zamanı: `{gecis_tarihi}`\n"
                            f"   • Stop-Loss (SL): `{stop_loss:.2f}`\n"
                            f"   • Take-Profit (TP): `{take_profit:.2f}`\n"
                            f"   • Sahte Sinyal: `{'Evet ⚠️' if is_fake else 'Hayır ✅'}`\n\n"
                        )
                telegram_bildirim_gonder(telegram_toplu_mesaj)
        except:
            pass
        time.sleep(bekleme_suresi)


if "arkaplan_bot_aktif" not in globals():
    globals()["arkaplan_bot_aktif"] = True
    threading.Thread(target=otomatik_tarama_botu, daemon=True).start()


# --- BACKTEST MOTORU ---
def calistir_backtest(df):
    sermaye = 10000
    bakiye = sermaye
    pozisyon = 0
    giris_fiyati = 0
    islemler = []

    for index, row in df.iterrows():
        if row["sinyal_tarihsel"] == 1 and pozisyon == 0:
            pozisyon = 1
            giris_fiyati = row["close"]
            giris_tarihi = row["tarih"]
        elif row["sinyal_tarihsel"] == -1 and pozisyon == 1:
            pozisyon = 0
            cikis_fiyati = row["close"]
            cikis_tarihi = row["tarih"]

            oran = (cikis_fiyati - giris_fiyati) / giris_fiyati
            kar_zarar_tutari = bakiye * oran
            bakiye += kar_zarar_tutari

            durum = "Başarılı ✅" if kar_zarar_tutari > 0 else "Başarısız ❌"
            islemler.append({
                "Giriş Tarihi": giris_tarihi,
                "Çıkış Tarihi": cikis_tarihi,
                "Giriş Fiyatı": round(giris_fiyati, 4),
                "Çıkış Fiyatı": round(cikis_fiyati, 4),
                "İşlem PnL ($)": round(kar_zarar_tutari, 2),
                "Durum": durum,
            })

    toplam_islem = len(islemler)
    basarili_islem = sum(1 for i in islemler if i["İşlem PnL ($)"] > 0)
    win_rate = (
        (basarili_islem / toplam_islem * 100) if toplam_islem > 0 else 0
    )
    net_kar_yuzde = ((bakiye - sermaye) / sermaye) * 100

    return {
        "son_bakiye": bakiye,
        "toplam_islem": toplam_islem,
        "win_rate": win_rate,
        "net_kar_yuzde": net_kar_yuzde,
        "islemler": islemler,
    }


# --- STREAMLIT UI ---
aktif_ayarlar = ayarlari_yukle()
aktif_portfoy = portfoy_yukle()

st.sidebar.title("🤖 Pro Asistan")
sayfa = st.sidebar.radio(
    "Menü Seçimi",
    [
        "📚 Varlık Havuzu",
        "📈 Canlı Analiz & Sinyaller",
        "💼 Portföy Yönetimi",
        "⏳ Geriye Dönük Test",
        "⚙️ Bot Ayarları",
    ],
)
st.sidebar.divider()

# VARLIK LİSTELERİ (Küresel Emtialar ve Fonlar / ETF'ler Eklendi)
HAZIR_VARLIKLAR = {
    "BIST 100 Kapsamlı Liste": {
        "THYAO (Türk Hava Yolları)": "THYAO.IS",
        "GARAN (Garanti BBVA)": "GARAN.IS",
        "ISMEN (İş Yatırım)": "ISMEN.IS",
        "ASELS (Aselsan)": "ASELS.IS",
        "EREGL (Ereğli Demir Çelik)": "EREGL.IS",
        "KCHOL (Koç Holding)": "KCHOL.IS",
        "SAHOL (Sabancı Holding)": "SAHOL.IS",
        "TUPRS (Tüpraş)": "TUPRS.IS",
        "BIMAS (BİM Mağazalar)": "BIMAS.IS",
        "AKBNK (Akbank)": "AKBNK.IS",
        "FROTO (Ford Otosan)": "FROTO.IS",
        "PGSUS (Pegasus)": "PGSUS.IS",
        "PETKM (Petkim)": "PETKM.IS",
        "SASA (Sasa Polyester)": "SASA.IS",
        "HEKTS (Hektaş)": "HEKTS.IS",
        "YKBNK (Yapı Kredi)": "YKBNK.IS",
        "TOASO (Tofaş)": "TOASO.IS",
        "ARCLK (Arçelik)": "ARCLK.IS",
        "ENKAI (Enka İnşaat)": "ENKAI.IS",
        "ODAS (Odaş Elektrik)": "ODAS.IS",
        "MGROS (Migros Ticaret)": "MGROS.IS",
        "KRDMD (Kardemir D)": "KRDMD.IS",
        "TCELL (Turkcell)": "TCELL.IS",
        "TTKOM (Türk Telekom)": "TTKOM.IS",
        "OYAKC (Oyak Çimento)": "OYAKC.IS",
        "KOZAL (Koza Altın)": "KOZAL.IS",
        "SOKM (Şok Marketler)": "SOKM.IS",
        "VESTL (Vestel)": "VESTL.IS",
        "ALARK (Alarko Holding)": "ALARK.IS",
        "GUBRF (Gübre Fabrikaları)": "GUBRF.IS",
        "TKFEN (Tekfen Holding)": "TKFEN.IS",
        "HALKB (Halkbank)": "HALKB.IS",
        "VAKBN (VakıfBank)": "VAKBN.IS",
        "TSKB (T.S.K.B.)": "TSKB.IS",
        "ZOREN (Zorlu Enerji)": "ZOREN.IS",
    },
    "Kripto (İlk 50 / Popüler)": {
        "Bitcoin (BTC)": "BTC-USD",
        "Ethereum (ETH)": "ETH-USD",
        "Solana (SOL)": "SOL-USD",
        "Ripple (XRP)": "XRP-USD",
        "Cardano (ADA)": "ADA-USD",
        "Avalanche (AVAX)": "AVAX-USD",
        "Dogecoin (DOGE)": "DOGE-USD",
        "Polkadot (DOT)": "DOT-USD",
        "Chainlink (LINK)": "LINK-USD",
        "Polygon (MATIC / POL)": "MATIC-USD",
        "Uniswap (UNI)": "UNI-USD",
        "Litecoin (LTC)": "LTC-USD",
        "Near Protocol (NEAR)": "NEAR-USD",
        "Cosmos (ATOM)": "ATOM-USD",
        "Aptos (APT)": "APT-USD",
        "Sui (SUI)": "SUI-USD",
        "Arbitrum (ARB)": "ARB-USD",
        "Optimism (OP)": "OP-USD",
        "Ethereum Classic (ETC)": "ETC-USD",
        "Filecoin (FIL)": "FIL-USD",
        "Internet Computer (ICP)": "ICP-USD",
        "Immutable (IMX)": "IMX-USD",
        "Render (RNDR)": "RNDR-USD",
        "Injective (INJ)": "INJ-USD",
        "Celestia (TIA)": "TIA-USD",
        "Stacks (STX)": "STX-USD",
        "The Graph (GRT)": "GRT-USD",
        "Sei (SEI)": "SEI-USD",
        "Fetch.ai (FET)": "FET-USD",
        "Kaspa (KAS)": "KAS-USD",
        "Hedera (HBAR)": "HBAR-USD",
        "Stellar (XLM)": "XLM-USD",
        "Algorand (ALGO)": "ALGO-USD",
        "VeChain (VET)": "VET-USD",
        "Theta Network (THETA)": "THETA-USD",
        "Fantom (FTM)": "FTM-USD",
        "Decentraland (MANA)": "MANA-USD",
        "The Sandbox (SAND)": "SAND-USD",
        "Axie Infinity (AXS)": "AXS-USD",
        "Aave (AAVE)": "AAVE-USD",
        "Maker (MKR)": "MKR-USD",
        "Shiba Inu (SHIB)": "SHIB-USD",
        "Pepe (PEPE)": "PEPE-USD",
        "Floki (FLOKI)": "FLOKI-USD",
        "Bonk (BONK)": "BONK-USD",
    },
    "NASDAQ Liderleri": {
        "Apple (AAPL)": "AAPL",
        "Microsoft (MSFT)": "MSFT",
        "Alphabet / Google (GOOGL)": "GOOGL",
        "Amazon (AMZN)": "AMZN",
        "NVIDIA (NVDA)": "NVDA",
        "Tesla (TSLA)": "TSLA",
        "Meta Platforms (META)": "META",
        "Netflix (NFLX)": "NFLX",
        "Advanced Micro Devices (AMD)": "AMD",
        "Intel (INTC)": "INTC",
        "Qualcomm (QCOM)": "QCOM",
        "Adobe (ADBE)": "ADBE",
        "PayPal (PYPL)": "PYPL",
        "PepsiCo (PEP)": "PEP",
        "Costco (COST)": "COST",
        "Broadcom (AVGO)": "AVGO",
        "Cisco Systems (CSCO)": "CSCO",
        "T-Mobile (TMUS)": "TMUS",
        "Texas Instruments (TXN)": "TXN",
        "Amgen (AMGN)": "AMGN",
        "Starbucks (SBUX)": "SBUX",
        "Mondelez (MDLZ)": "MDLZ",
        "Automatic Data Processing (ADP)": "ADP",
        "Gilead Sciences (GILD)": "GILD",
        "Intuitive Surgical (ISRG)": "ISRG",
        "Booking Holdings (BKNG)": "BKNG",
        "Micron Technology (MU)": "MU",
        "Lam Research (LRCX)": "LRCX",
        "Palo Alto Networks (PANW)": "PANW",
        "Synopsys (SNPS)": "SNPS",
    },
    "S&P 500 Liderleri": {
        "S&P 500 ETF (SPY)": "SPY",
        "Berkshire Hathaway (BRK-B)": "BRK-B",
        "JPMorgan Chase (JPM)": "JPM",
        "Visa (V)": "V",
        "UnitedHealth (UNH)": "UNH",
        "Johnson & Johnson (JNJ)": "JNJ",
        "Exxon Mobil (XOM)": "XOM",
        "Walmart (WMT)": "WMT",
        "Mastercard (MA)": "MA",
        "Procter & Gamble (PG)": "PG",
        "Home Depot (HD)": "HD",
        "Walt Disney (DIS)": "DIS",
        "Bank of America (BAC)": "BAC",
        "Chevron (CVX)": "CVX",
        "AbbVie (ABBV)": "ABBV",
        "Pfizer (PFE)": "PFE",
        "Coca-Cola (KO)": "KO",
        "Merck & Co (MRK)": "MRK",
        "Thermo Fisher Scientific (TMO)": "TMO",
        "Abbott Laboratories (ABBT / ABT)": "ABT",
        "Accenture (ACN)": "ACN",
        "Wells Fargo (WFC)": "WFC",
        "McDonald's (MCD)": "MCD",
        "Danaher (DHR)": "DHR",
        "Nike (NKE)": "NKE",
        "Philip Morris (PM)": "PM",
    },
    "Küresel Emtialar ve Fonlar": {
        "Altın (Gold Ons)": "GC=F",
        "Gümüş (Silver Ons)": "SI=F",
        "Ham Petrol (Crude Oil)": "CL=F",
        "Brent Petrol": "BZ=F",
        "Doğalgaz (Natural Gas)": "NG=F",
        "Vanguard S&P 500 ETF (VOO)": "VOO",
        "Vanguard Total Stock Market (VTI)": "VTI",
        "Invesco QQQ (Nasdaq 100 ETF)": "QQQ",
        "iShares Gold Trust (GLD)": "GLD",
        "iShares Silver Trust (SLV)": "SLV",
    }
}

if sayfa == "📚 Varlık Havuzu":
    st.title("📚 Varlık Havuzu ve Piyasalar")
    secilenler = set(aktif_ayarlar["varliklar"])

    tab_bist, tab_kripto, tab_nasdaq, tab_sp500, tab_emtia_fon = st.tabs([
        "🇹🇷 BIST 100",
        "🪙 Kripto (İlk 50)",
        "💻 NASDAQ",
        "📈 S&P 500",
        "🛢️ Fonlar & Emtialar",
    ])

    kategoriler_listesi = list(HAZIR_VARLIKLAR.keys())

    with tab_bist:
        st.subheader("BIST 100 Kapsamlı Seçkisi")
        for isim, kod in HAZIR_VARLIKLAR[kategoriler_listesi[0]].items():
            if st.checkbox(isim, value=(kod in secilenler), key=f"hb_{kod}"):
                secilenler.add(kod)
            else:
                secilenler.discard(kod)

    with tab_kripto:
        st.subheader("Kripto Para Piyasası (İlk 50 / Popüler)")
        for isim, kod in HAZIR_VARLIKLAR[kategoriler_listesi[1]].items():
            if st.checkbox(isim, value=(kod in secilenler), key=f"hk_{kod}"):
                secilenler.add(kod)
            else:
                secilenler.discard(kod)

    with tab_nasdaq:
        st.subheader("NASDAQ Teknoloji Liderleri")
        for isim, kod in HAZIR_VARLIKLAR[kategoriler_listesi[2]].items():
            if st.checkbox(isim, value=(kod in secilenler), key=f"hn_{kod}"):
                secilenler.add(kod)
            else:
                secilenler.discard(kod)

    with tab_sp500:
        st.subheader("S&P 500 Liderleri ve ETF")
        for isim, kod in HAZIR_VARLIKLAR[kategoriler_listesi[3]].items():
            if st.checkbox(isim, value=(kod in secilenler), key=f"hs_{kod}"):
                secilenler.add(kod)
            else:
                secilenler.discard(kod)

    with tab_emtia_fon:
        st.subheader("Küresel Emtialar ve Fonlar / ETF'ler")
        for isim, kod in HAZIR_VARLIKLAR[kategoriler_listesi[4]].items():
            if st.checkbox(isim, value=(kod in secilenler), key=f"hef_{kod}"):
                secilenler.add(kod)
            else:
                secilenler.discard(kod)

    st.divider()
    manuel = (
        st.text_input(
            "🎯 Listede olmayan başka bir varlık eklemek isterseniz kodunu"
            " yazın (Örn: TSLA, ETH-USD vb.)"
        )
        .upper()
        .strip()
    )
    if st.button("➕ Özel Varlık Ekle") and manuel:
        secilenler.add(manuel)
        st.success(f"{manuel} eklendi!")

    st.divider()
    if st.button(
        "💾 SEÇİMLERİ SABİTLE VE KAYDET",
        use_container_width=True,
        type="primary",
    ):
        aktif_ayarlar["varliklar"] = list(secilenler)
        ayarlari_kaydet(aktif_ayarlar)
        st.success(
            "Seçtiğiniz varlıklar listeye sabitlendi ve kaydedildi! Tüm analizler"
            " bu sabit liste üzerinden gerçekleştirilecektir."
        )
        time.sleep(1)
        st.rerun()

elif sayfa == "💼 Portföy Yönetimi":
    st.title("💼 Portföy Yönetimi ve Detaylı Analiz")

    with st.expander(
        "➕ Yeni İşlem / Varlık Ekle (Tarih, Bütçe ve Lot Hesaplama)",
        expanded=True,
    ):
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            mevcut_havuz = aktif_ayarlar.get("varliklar", ["BTC-USD"])
            p_varlik = st.selectbox("Varlık Seç", mevcut_havuz)
        with col2:
            p_tarih = st.date_input("Alım Tarihi", value=datetime.date.today())
        with col3:
            p_harcanan = st.number_input(
                "Harcanan Tutar (Örn: 3000)",
                min_value=0.0,
                value=3000.0,
                format="%.2f",
            )
        with col4:
            p_maliyet = st.number_input(
                "Alış Fiyatı (Birim)", min_value=0.0, format="%.4f"
            )
        with col5:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("Kaydet", use_container_width=True, type="primary"):
                if p_maliyet > 0:
                    p_adet = p_harcanan / p_maliyet
                    aktif_portfoy[p_varlik] = {
                        "tarih": str(p_tarih),
                        "harcanan": p_harcanan,
                        "maliyet": p_maliyet,
                        "adet": p_adet,
                    }
                    portfoy_kaydet(aktif_portfoy)
                    st.success(f"Kayıt eklendi! Karşılığı: {p_adet:.4f} Lot")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("Alış fiyatı 0'dan büyük olmalıdır!")

    st.divider()
    st.subheader("📊 Portföy Canlı Durumu ve Günlük Değişimler")
    if not aktif_portfoy:
        st.info("Henüz portföyünüze veri eklemediniz.")
    else:
        toplam_portfoy_maliyeti = 0
        toplam_portfoy_guncel_degeri = 0
        silinecekler = []

        for v_kod, v_veri in aktif_portfoy.items():
            df_canli = veri_cek(v_kod, aralik="1h")
            if df_canli is not None and len(df_canli) >= 2:
                anlik_fiyat = df_canli["close"].iloc[-1]
                onceki_fiyat = df_canli["close"].iloc[-2]

                tarih = v_veri.get("tarih", "Bilinmiyor")
                harcanan = v_veri.get(
                    "harcanan", v_veri.get("maliyet", 0) * v_veri.get("adet", 0)
                )
                maliyet = v_veri["maliyet"]
                adet = v_veri["adet"]

                guncel_deger = anlik_fiyat * adet
                toplam_kar = guncel_deger - harcanan
                toplam_kar_yuzde = (
                    ((anlik_fiyat - maliyet) / maliyet) * 100 if maliyet > 0 else 0
                )

                gunluk_fark_tutar = (anlik_fiyat - onceki_fiyat) * adet
                gunluk_fark_yuzde = (
                    ((anlik_fiyat - onceki_fiyat) / onceki_fiyat) * 100
                    if onceki_fiyat > 0
                    else 0
                )

                toplam_portfoy_maliyeti += harcanan
                toplam_portfoy_guncel_degeri += guncel_deger

                t_renk = "green" if toplam_kar >= 0 else "red"
                g_renk = "green" if gunluk_fark_tutar >= 0 else "red"

                c1, c2, c3, c4, c5 = st.columns([1.5, 1.5, 1.5, 1.5, 0.8])
                with c1:
                    st.markdown(f"### {v_kod}")
                    st.caption(f"📅 Tarih: {tarih} | Lot: `{adet:.4f}`")
                with c2:
                    st.markdown(f"**Harcanan:** `{harcanan:.2f}`")
                    st.markdown(f"**Güncel Değer:** `{guncel_deger:.2f}`")
                with c3:
                    st.markdown(f"**Toplam K/Z:**")
                    st.markdown(
                        f"<span style='color:{t_renk};"
                        f" font-weight:bold;'>{toplam_kar:+.2f}"
                        f" (%{toplam_kar_yuzde:+.2f})</span>",
                        unsafe_allow_html=True,
                    )
                with c4:
                    st.markdown(f"**Günlük K/Z:**")
                    st.markdown(
                        f"<span style='color:{g_renk};"
                        f" font-weight:bold;'>{gunluk_fark_tutar:+.2f}"
                        f" (%{gunluk_fark_yuzde:+.2f})</span>",
                        unsafe_allow_html=True,
                    )
                with c5:
                    st.markdown("<br>", unsafe_allow_html=True)
                    if st.button("🗑️ Sil", key=f"sil_{v_kod}"):
                        silinecekler.append(v_kod)
                st.divider()

        for s in silinecekler:
            del aktif_portfoy[s]
            portfoy_kaydet(aktif_portfoy)
            st.rerun()

        st.subheader("Genel Portföy Özeti")
        toplam_fark = toplam_portfoy_guncel_degeri - toplam_portfoy_maliyeti
        genel_renk = "normal" if toplam_fark >= 0 else "inverse"

        t1, t2, t3 = st.columns(3)
        t1.metric("Toplam Harcanan (Maliyet)", f"{toplam_portfoy_maliyeti:.2f}")
        t2.metric("Portföy Güncel Değeri", f"{toplam_portfoy_guncel_degeri:.2f}")
        t3.metric(
            "Genel Toplam Kâr / Zarar",
            f"{toplam_fark:+.2f}",
            delta_color=genel_renk,
        )

elif sayfa == "⏳ Geriye Dönük Test":
    st.title("⏳ Strateji Testi (Backtest)")
    st.markdown(
        "Seçtiğiniz varlık ve zaman diliminde bot stratejisinin geçmiş"
        " kârlılığını test edin. **Başlangıç Bakiyesi: 10,000 $**"
    )

    mevcut_varliklar = aktif_ayarlar.get("varliklar", ["BTC-USD"])
    test_edilecek = st.selectbox("Test Edilecek Varlık", mevcut_varliklar)

    if st.button("🚀 Backtest'i Başlat", type="primary"):
        with st.spinner(
            f"{test_edilecek} için geçmiş veriler taranıyor ve simülasyon"
            " yapılıyor..."
        ):
            df_test = veri_cek(test_edilecek, aralik=aktif_ayarlar["zaman_dilimi"])
            if df_test is not None and not df_test.empty:
                df_test_analiz = hesapla_teknikler(df_test)
                sonuclar = calistir_backtest(df_test_analiz)

                st.divider()
                st.subheader(
                    f"📊 {test_edilecek} Backtest Sonuçları (Periyot:"
                    f" {aktif_ayarlar['zaman_dilimi']})"
                )

                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Net Kâr Yüzdesi", f"%{sonuclar['net_kar_yuzde']:.2f}")
                c2.metric("Toplam İşlem", str(sonuclar["toplam_islem"]))
                c3.metric("Başarı Oranı (Win Rate)", f"%{sonuclar['win_rate']:.1f}")
                c4.metric("Son Bakiye", f"{sonuclar['son_bakiye']:.2f} $")

                if sonuclar["islemler"]:
                    st.markdown("### 📝 İşlem Geçmişi (Log)")
                    df_islemler = pd.DataFrame(sonuclar["islemler"])
                    st.dataframe(df_islemler, use_container_width=True)
                else:
                    st.warning(
                        "Bu periyotta stratejiye uygun herhangi bir Al/Sat kesişimi"
                        " bulunamadı."
                    )
            else:
                st.error("Veri çekilemedi. Lütfen daha sonra tekrar deneyin.")

elif sayfa == "📈 Canlı Analiz & Sinyaller":
    st.title(
        "📈 Sabit Varlık Sinyal Listesi, Geçiş Zamanları, Stop-Loss ve TP Kontrolü"
    )
    mevcut_varliklar = aktif_ayarlar.get("varliklar", [])

    if not mevcut_varliklar:
        st.warning("Lütfen Varlık Havuzundan varlık seçin ve sabitleyin.")
    else:
        if "secilen_aktif_grafik" not in st.session_state:
            st.session_state["secilen_aktif_grafik"] = mevcut_varliklar[0]

        st.subheader(
            "📋 Sabit Liste Sinyalleri, Geçiş Zamanları, Stop-Loss ve Take-Profit"
            " Seviyeleri"
        )

        telegram_toplu_mesaj = f"📊 *Sabit Liste Toplu Sinyal, Stop-Loss ve TP Raporu* (Periyot: {aktif_ayarlar['zaman_dilimi']})\n\n"

        for varlik in mevcut_varliklar:
            df_temp = veri_cek(varlik, aralik=aktif_ayarlar["zaman_dilimi"])
            if df_temp is not None and not df_temp.empty:
                df_t_analiz = hesapla_teknikler(df_temp)
                p_analiz = donusum_noktalari_hesapla(df_t_analiz)
                p_sinyal = sinyal_kontrol(df_t_analiz)

                fiyat = p_analiz["fiyat"]
                destek = p_analiz["destek"]
                direnc = p_analiz["direnc"]
                stop_loss = destek if destek < fiyat else fiyat * 0.97
                take_profit = direnc if direnc > fiyat else fiyat * 1.05

                is_fake = df_t_analiz.iloc[-1].get("sahte_sinyal", False)
                gecis_tarihi = df_t_analiz.iloc[-1].get("tarih", "-")

                if is_fake:
                    durum_metni = (
                        "⚠️ **SAHTE/ZAYIF SİNYAL TESPİT EDİLDİ!** (Düşük Güven)"
                    )
                elif "AL" in p_sinyal.upper():
                    durum_metni = (
                        f"🚀 **YÜKSELİŞTE (LONG)** | Geçiş Zamanı: `{gecis_tarihi}`"
                    )
                elif "SAT" in p_sinyal.upper():
                    durum_metni = (
                        f"⚠️ **DÜŞÜŞTE (SHORT)** | Geçiş Zamanı: `{gecis_tarihi}`"
                    )
                else:
                    durum_metni = "⚖️ **NÖTR / Yatay Seyir**"

                telegram_toplu_mesaj += (
                    f"🔹 *{varlik}*\n"
                    f"   • Fiyat: `{fiyat:.2f}`\n"
                    f"   • Durum: `{p_sinyal}`\n"
                    f"   • Geçiş Zamanı: `{gecis_tarihi}`\n"
                    f"   • Stop-Loss (SL): `{stop_loss:.2f}`\n"
                    f"   • Take-Profit (TP): `{take_profit:.2f}`\n"
                    f"   • Sahte Sinyal: `{'Evet ⚠️' if is_fake else 'Hayır ✅'}`\n\n"
                )

                col_info, col_btn = st.columns([4, 1])
                with col_info:
                    st.markdown(
                        f"🔹 **{varlik}** | Fiyat: `{fiyat:.2f}` | Durum: {durum_metni} |"
                        f" **SL:** `{stop_loss:.2f}` | **TP:** `{take_profit:.2f}`"
                    )
                with col_btn:
                    if st.button(
                        f"📊 Grafiği İncele",
                        key=f"btn_list_{varlik}",
                        use_container_width=True,
                    ):
                        st.session_state["secilen_aktif_grafik"] = varlik
                        st.rerun()

        st.divider()
        if st.button(
            "📤 Tüm Sabit Listenin Özetini (SL ve TP Dahil) Telegram'a Şimdi"
            " Gönder",
            type="primary",
            use_container_width=True,
        ):
            telegram_bildirim_gonder(telegram_toplu_mesaj)
            st.success(
                "Sabit listedeki tüm varlıkların analizi (Stop-Loss ve Kar Al"
                " seviyeleriyle birlikte) Telegram'a başarıyla gönderildi!"
            )

        st.divider()
        st.header(
            "📊 Gelişmiş Grafik İncelemesi ve İnteraktif Modlar:"
            f" `{st.session_state['secilen_aktif_grafik']}`"
        )

        col_mod1, col_mod2 = st.columns(2)
        with col_mod1:
            grafik_modu = st.selectbox(
                "Grafik Fare Modu (Etkileşim):",
                [
                    "🔍 Zoom (Yakınlaştır/Uzaklaştır)",
                    "✋ Kaydırma / Pan (Grafiği Sürükle)",
                ],
            )
        drag_mode_val = "pan" if "Kaydırma" in grafik_modu else "zoom"

        st.info(
            "💡 **İpucu:** Fare tekerleğiyle (Scroll) her zaman zoom yapabilir,"
            " yukarıdaki menüden veya butonlardan modu değiştirebilirsin."
        )

        ek_gostergeler = st.multiselect(
            "Gösterilecek İndikatörler",
            [
                "Bollinger Bantları",
                "Özel İndikatörüm",
                "RSI (Alt Grafik)",
                "MACD (Alt Grafik)",
            ],
            default=["Bollinger Bantları"],
        )

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
            if satir_sayisi == 1:
                row_heights = [1]

            fig = make_subplots(
                rows=satir_sayisi,
                cols=1,
                shared_xaxes=True,
                vertical_spacing=0.03,
                row_heights=row_heights,
            )

            # 1. Mum Grafik (Candlestick)
            fig.add_trace(
                go.Candlestick(
                    x=df_analiz["tarih"],
                    open=df_analiz["open"],
                    high=df_analiz["high"],
                    low=df_analiz["low"],
                    close=df_analiz["close"],
                    name="Fiyat",
                ),
                row=1,
                col=1,
            )

            # --- SİNYAL İŞARETLERİ (AL / SAT - LONG / SHORT) ---
            if "sinyal_tarihsel" in df_analiz.columns:
                df_al = df_analiz[df_analiz["sinyal_tarihsel"] == 1]
                df_sat = df_analiz[df_analiz["sinyal_tarihsel"] == -1]

                if not df_al.empty:
                    fig.add_trace(
                        go.Scatter(
                            x=df_al["tarih"],
                            y=df_al["low"] * 0.99,
                            mode="markers+text",
                            text=["AL (Long)" for _ in range(len(df_al))],
                            textposition="bottom center",
                            marker=dict(symbol="triangle-up", size=14, color="#00FF7F"),
                            name="Yükselişe Geçiş (AL)",
                        ),
                        row=1,
                        col=1,
                    )

                if not df_sat.empty:
                    fig.add_trace(
                        go.Scatter(
                            x=df_sat["tarih"],
                            y=df_sat["high"] * 1.01,
                            mode="markers+text",
                            text=["SAT (Short)" for _ in range(len(df_sat))],
                            textposition="top center",
                            marker=dict(symbol="triangle-down", size=14, color="#FF4500"),
                            name="Düşüşe Geçiş (SAT)",
                        ),
                        row=1,
                        col=1,
                    )

            fig.add_hline(
                y=analiz["destek"],
                line_dash="dot",
                line_color="green",
                annotation_text="Destek (SL Referansı)",
                row=1,
                col=1,
            )
            fig.add_hline(
                y=analiz["direnc"],
                line_dash="dot",
                line_color="red",
                annotation_text="Direnç (TP Referansı)",
                row=1,
                col=1,
            )

            if "Bollinger Bantları" in ek_gostergeler:
                fig.add_trace(
                    go.Scatter(
                        x=df_analiz["tarih"],
                        y=df_analiz["bollinger_ust"],
                        name="Bol. Üst",
                        line=dict(color="rgba(173,216,230,0.5)", width=1, dash="dash"),
                    ),
                    row=1,
                    col=1,
                )
                fig.add_trace(
                    go.Scatter(
                        x=df_analiz["tarih"],
                        y=df_analiz["bollinger_alt"],
                        name="Bol. Alt",
                        fill="tonexty",
                        fillcolor="rgba(173,216,230,0.1)",
                        line=dict(color="rgba(173,216,230,0.5)", width=1, dash="dash"),
                    ),
                    row=1,
                    col=1,
                )

            guncel_satir = 2
            if "RSI (Alt Grafik)" in ek_gostergeler:
                fig.add_trace(
                    go.Scatter(
                        x=df_analiz["tarih"],
                        y=df_analiz["rsi"],
                        name="RSI",
                        line=dict(color="purple", width=1.5),
                    ),
                    row=guncel_satir,
                    col=1,
                )
                guncel_satir += 1

            if "MACD (Alt Grafik)" in ek_gostergeler:
                fig.add_trace(
                    go.Scatter(
                        x=df_analiz["tarih"],
                        y=df_analiz["macd"],
                        name="MACD",
                        line=dict(color="blue"),
                    ),
                    row=guncel_satir,
                    col=1,
                )

            fig.update_layout(
                template="plotly_dark",
                height=650 if satir_sayisi == 1 else 850,
                margin=dict(l=0, r=0, t=30, b=0),
                xaxis_rangeslider_visible=False,
                dragmode=drag_mode_val,
                hovermode="x unified",
            )

            st.plotly_chart(
                fig,
                use_container_width=True,
                config={
                    "scrollZoom": True,
                    "displayModeBar": True,
                    "modeBarButtonsToAdd": [
                        "pan2d",
                        "zoom2d",
                        "zoomIn2d",
                        "zoomOut2d",
                        "autoScale2d",
                        "resetScale2d",
                        "drawline",
                    ]
                }
            )
