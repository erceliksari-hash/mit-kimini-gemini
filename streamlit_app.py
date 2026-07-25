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
    "varliklar": ["AAPL", "BTC-USD", "SPY", "THYAO.IS"],
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


# --- İNTERNETTEN VARLIK ARAMA FONKSİYONU ---
def internette_varlik_ara(sorgu):
    try:
        url = f"https://query2.finance.yahoo.com/v1/finance/search?q={sorgu}"
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=5)
        data = response.json()
        quotes = data.get("quotes", [])
        sonuclar = []
        for q in quotes:
            symbol = q.get("symbol")
            shortname = q.get("shortname", q.get("longname", symbol))
            exchange = q.get("exchDisp", q.get("exchange", ""))
            if symbol:
                sonuclar.append({
                    "symbol": symbol,
                    "name": shortname,
                    "exchange": exchange,
                })
        return sonuclar
    except:
        return []


# --- DETAYLI TEKNİK ANALİZ VE YORUM OLUŞTURUCU ---
def detayli_analiz_ve_yorum_olustur(varlik, df_t_analiz, p_analiz, p_sinyal):
    fiyat = p_analiz["fiyat"]
    d1 = p_analiz["destek"]
    r1 = p_analiz["direnc"]

    # Çoklu Destek (S1, S2, S3) ve Direnç (R1, R2, R3) Seviyeleri
    s1 = d1
    s2 = s1 * 0.985
    s3 = s1 * 0.970

    r1_val = r1
    r2 = r1_val * 1.015
    r3 = r1_val * 1.030

    # Stop-Loss ve Take-Profit
    stop_loss = s1 if s1 < fiyat else fiyat * 0.97
    take_profit = r1_val if r1_val > fiyat else fiyat * 1.05

    is_fake = df_t_analiz.iloc[-1].get("sahte_sinyal", False)
    gecis_tarihi = df_t_analiz.iloc[-1].get("tarih", "-")

    # Trend ve Geçiş Seviyesi Yorumlama
    sinyal_ust = p_sinyal.upper()
    if "AL" in sinyal_ust or "YÜKSELİŞ" in sinyal_ust:
        trend_yorum = "📈 *Yükseliş Trendi Hâkim.* Fiyat yukarı yönlü direnç bölgelerini test ediyor."
        gecis_yorum = f"Yükseliş Teyit Eşiği: `{r1_val:.2f}` üzeri tutunma."
    elif "SAT" in sinyal_ust or "DÜŞÜŞ" in sinyal_ust:
        trend_yorum = "📉 *Düşüş Baskısı Hâkim.* Satış baskısı devam ediyor, destekler takip edilmeli."
        gecis_yorum = f"Düşüş Derinleşme Eşiği: `{s1:.2f}` altı kırılım."
    else:
        trend_yorum = "⚖️ *Yatay / Belirsiz Seyir.* Konsolidasyon alanı içerisinde hareket ediyor."
        gecis_yorum = f"Kırılım Seviyeleri: `{r1_val:.2f}` Üstü Yükseliş | `{s1:.2f}` Altı Düşüş"

    # Sahte Sinyal Yorumlama
    if is_fake:
        sahte_yorum = "⚠️ *SİNYAL UYARISI:* Sahte/Tuzak sinyal tespit edildi! Hacim veya yardımcı indikatör doğrulaması zayıf. Temkinli olunmalı."
    else:
        sahte_yorum = "✅ *GÜVENİLİR SİNYAL:* İndikatör ve hacim teyidi mevcut."

    rapor_metni = (
        f"🔹 *{varlik}*\n"
        f"   • *Fiyat:* `{fiyat:.2f}` | *Durum:* `{p_sinyal}`\n"
        f"   • *Geçiş Zamanı:* `{gecis_tarihi}`\n"
        f"   • *Destekler:* S1: `{s1:.2f}` | S2: `{s2:.2f}` | S3: `{s3:.2f}`\n"
        f"   • *Dirençler:* R1: `{r1_val:.2f}` | R2: `{r2:.2f}` | R3: `{r3:.2f}`\n"
        f"   • *Stop-Loss (SL):* `{stop_loss:.2f}` | *Take-Profit (TP):* `{take_profit:.2f}`\n"
        f"   • *Geçiş Seviyesi Yorumu:* {gecis_yorum}\n"
        f"   • *Teknik Değerlendirme:* {trend_yorum}\n"
        f"   • *Sinyal Kalitesi:* {sahte_yorum}\n\n"
    )
    return rapor_metni


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
            varliklar = sorted(ayarlar.get("varliklar", []))
            zaman_dilimi = ayarlar.get("zaman_dilimi", "1h")
            bekleme_suresi = ayarlar.get("bot_sikligi_dk", 60) * 60

            if varliklar:
                telegram_toplu_mesaj = f"📊 *Otomatik Detaylı Sinyal ve Teknik Analiz Raporu* (Periyot: {zaman_dilimi})\n\n"
                for varlik in varliklar:
                    df_t = veri_cek(varlik, aralik=zaman_dilimi)
                    if df_t is not None and not df_t.empty:
                        df_t_analiz = hesapla_teknikler(df_t)
                        p_analiz = donusum_noktalari_hesapla(df_t_analiz)
                        p_sinyal = sinyal_kontrol(df_t_analiz)

                        telegram_toplu_mesaj += detayli_analiz_ve_yorum_olustur(
                            varlik, df_t_analiz, p_analiz, p_sinyal
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

HAZIR_VARLIKLAR = {
    "BIST 100 Kapsamlı Liste": {
        "AKBNK (Akbank)": "AKBNK.IS",
        "ALARK (Alarko Holding)": "ALARK.IS",
        "ARCLK (Arçelik)": "ARCLK.IS",
        "ASELS (Aselsan)": "ASELS.IS",
        "BIMAS (BİM Mağazalar)": "BIMAS.IS",
        "ENKAI (Enka İnşaat)": "ENKAI.IS",
        "EREGL (Ereğli Demir Çelik)": "EREGL.IS",
        "FROTO (Ford Otosan)": "FROTO.IS",
        "GARAN (Garanti BBVA)": "GARAN.IS",
        "GUBRF (Gübre Fabrikaları)": "GUBRF.IS",
        "HALKB (Halkbank)": "HALKB.IS",
        "HEKTS (Hektaş)": "HEKTS.IS",
        "ISMEN (İş Yatırım)": "ISMEN.IS",
        "KCHOL (Koç Holding)": "KCHOL.IS",
        "KOZAL (Koza Altın)": "KOZAL.IS",
        "KRDMD (Kardemir D)": "KRDMD.IS",
        "MGROS (Migros Ticaret)": "MGROS.IS",
        "ODAS (Odaş Elektrik)": "ODAS.IS",
        "OYAKC (Oyak Çimento)": "OYAKC.IS",
        "PETKM (Petkim)": "PETKM.IS",
        "PGSUS (Pegasus)": "PGSUS.IS",
        "SAHOL (Sabancı Holding)": "SAHOL.IS",
        "SASA (Sasa Polyester)": "SASA.IS",
        "SOKM (Şok Marketler)": "SOKM.IS",
        "TCELL (Turkcell)": "TCELL.IS",
        "THYAO (Türk Hava Yolları)": "THYAO.IS",
        "TKFEN (Tekfen Holding)": "TKFEN.IS",
        "TOASO (Tofaş)": "TOASO.IS",
        "TSKB (T.S.K.B.)": "TSKB.IS",
        "TTKOM (Türk Telekom)": "TTKOM.IS",
        "TUPRS (Tüpraş)": "TUPRS.IS",
        "VAKBN (VakıfBank)": "VAKBN.IS",
        "VESTL (Vestel)": "VESTL.IS",
        "YKBNK (Yapı Kredi)": "YKBNK.IS",
        "ZOREN (Zorlu Enerji)": "ZOREN.IS",
    },
    "Kripto (İlk 50 / Popüler)": {
        "Aave (AAVE)": "AAVE-USD",
        "Algorand (ALGO)": "ALGO-USD",
        "Aptos (APT)": "APT-USD",
        "Arbitrum (ARB)": "ARB-USD",
        "Avalanche (AVAX)": "AVAX-USD",
        "Axie Infinity (AXS)": "AXS-USD",
        "Bitcoin (BTC)": "BTC-USD",
        "Bonk (BONK)": "BONK-USD",
        "Cardano (ADA)": "ADA-USD",
        "Celestia (TIA)": "TIA-USD",
        "Chainlink (LINK)": "LINK-USD",
        "Cosmos (ATOM)": "ATOM-USD",
        "Decentraland (MANA)": "MANA-USD",
        "Dogecoin (DOGE)": "DOGE-USD",
        "Ethereum (ETH)": "ETH-USD",
        "Ethereum Classic (ETC)": "ETC-USD",
        "Fantom (FTM)": "FTM-USD",
        "Fetch.ai (FET)": "FET-USD",
        "Filecoin (FIL)": "FIL-USD",
        "Floki (FLOKI)": "FLOKI-USD",
        "Hedera (HBAR)": "HBAR-USD",
        "Immutable (IMX)": "IMX-USD",
        "Injective (INJ)": "INJ-USD",
        "Internet Computer (ICP)": "ICP-USD",
        "Kaspa (KAS)": "KAS-USD",
        "Litecoin (LTC)": "LTC-USD",
        "Maker (MKR)": "MKR-USD",
        "Near Protocol (NEAR)": "NEAR-USD",
        "Optimism (OP)": "OP-USD",
        "Pepe (PEPE)": "PEPE-USD",
        "Polkadot (DOT)": "DOT-USD",
        "Polygon (MATIC / POL)": "MATIC-USD",
        "Render (RNDR)": "RNDR-USD",
        "Ripple (XRP)": "XRP-USD",
        "Sei (SEI)": "SEI-USD",
        "Shiba Inu (SHIB)": "SHIB-USD",
        "Solana (SOL)": "SOL-USD",
        "Stacks (STX)": "STX-USD",
        "Stellar (XLM)": "XLM-USD",
        "Sui (SUI)": "SUI-USD",
        "The Graph (GRT)": "GRT-USD",
        "The Sandbox (SAND)": "SAND-USD",
        "Theta Network (THETA)": "THETA-USD",
        "Uniswap (UNI)": "UNI-USD",
        "VeChain (VET)": "VET-USD",
    },
    "Küresel Emtialar ve Fonlar": {
        "Altın (Gold Ons)": "GC=F",
        "Brent Petrol": "BZ=F",
        "Doğalgaz (Natural Gas)": "NG=F",
        "Gümüş (Silver Ons)": "SI=F",
        "Ham Petrol (Crude Oil)": "CL=F",
        "Invesco QQQ (Nasdaq 100 ETF)": "QQQ",
        "iShares Gold Trust (GLD)": "GLD",
        "iShares Silver Trust (SLV)": "SLV",
        "Vanguard S&P 500 ETF (VOO)": "VOO",
        "Vanguard Total Stock Market (VTI)": "VTI",
    },
    "NASDAQ Liderleri": {
        "Adobe (ADBE)": "ADBE",
        "Advanced Micro Devices (AMD)": "AMD",
        "Alphabet / Google (GOOGL)": "GOOGL",
        "Amazon (AMZN)": "AMZN",
        "Amgen (AMGN)": "AMGN",
        "Apple (AAPL)": "AAPL",
        "Automatic Data Processing (ADP)": "ADP",
        "Booking Holdings (BKNG)": "BKNG",
        "Broadcom (AVGO)": "AVGO",
        "Cisco Systems (CSCO)": "CSCO",
        "Costco (COST)": "COST",
        "Gilead Sciences (GILD)": "GILD",
        "Intel (INTC)": "INTC",
        "Intuitive Surgical (ISRG)": "ISRG",
        "Lam Research (LRCX)": "LRCX",
        "Meta Platforms (META)": "META",
        "Micron Technology (MU)": "MU",
        "Microsoft (MSFT)": "MSFT",
        "Mondelez (MDLZ)": "MDLZ",
        "Netflix (NFLX)": "NFLX",
        "NVIDIA (NVDA)": "NVIDIA",
        "Palo Alto Networks (PANW)": "PANW",
        "PayPal (PYPL)": "PYPL",
        "PepsiCo (PEP)": "PEP",
        "Qualcomm (QCOM)": "QCOM",
        "Starbucks (SBUX)": "SBUX",
        "Synopsys (SNPS)": "SNPS",
        "T-Mobile (TMUS)": "TMUS",
        "Tesla (TSLA)": "TSLA",
        "Texas Instruments (TXN)": "TXN",
    },
    "S&P 500 Liderleri": {
        "Abbott Laboratories (ABBT / ABT)": "ABT",
        "AbbVie (ABBV)": "ABBV",
        "Accenture (ACN)": "ACN",
        "Bank of America (BAC)": "BAC",
        "Berkshire Hathaway (BRK-B)": "BRK-B",
        "Chevron (CVX)": "CVX",
        "Coca-Cola (KO)": "KO",
        "Danaher (DHR)": "DHR",
        "Exxon Mobil (XOM)": "XOM",
        "Home Depot (HD)": "HD",
        "Johnson & Johnson (JNJ)": "JNJ",
        "JPMorgan Chase (JPM)": "JPM",
        "Mastercard (MA)": "MA",
        "McDonald's (MCD)": "MCD",
        "Merck & Co (MRK)": "MRK",
        "Nike (NKE)": "NKE",
        "Pfizer (PFE)": "PFE",
        "Philip Morris (PM)": "PM",
        "Procter & Gamble (PG)": "PG",
        "S&P 500 ETF (SPY)": "SPY",
        "Thermo Fisher Scientific (TMO)": "TMO",
        "UnitedHealth (UNH)": "UNH",
        "Visa (V)": "V",
        "Walmart (WMT)": "WMT",
        "Walt Disney (DIS)": "DIS",
        "Wells Fargo (WFC)": "WFC",
    },
}

if sayfa == "📚 Varlık Havuzu":
    st.title("📚 Varlık Havuzu ve Piyasalar")
    secilenler = set(aktif_ayarlar["varliklar"])

    st.subheader("📋 Aktif Varlık Listesi ve Yönetimi (Silme İşlemi)")
    st.markdown("Şu an sabit olarak takip edilen varlıklarınız aşağıdadır. İstemediğiniz bir varlığı yanındaki **❌ Çıkar** butonuna basarak anında listeden silebilirsiniz.")
    
    if not secilenler:
        st.info("Aktif listenizde hiç varlık bulunmuyor.")
    else:
        aktif_liste_sirali = sorted(list(secilenler))
        silinecekler_listesi = []
        
        cols = st.columns(4)
        for i, v_kod in enumerate(aktif_liste_sirali):
            with cols[i % 4]:
                if st.button(f"❌ Çıkar: {v_kod}", key=f"sil_aktif_{v_kod}", use_container_width=True):
                    silinecekler_listesi.append(v_kod)
        
        if silinecekler_listesi:
            for s_kod in silinecekler_listesi:
                secilenler.discard(s_kod)
            aktif_ayarlar["varliklar"] = sorted(list(secilenler))
            ayarlari_kaydet(aktif_ayarlar)
            st.success("Seçilen varlık listeden başarıyla çıkarıldı ve sabitlendi!")
            time.sleep(0.5)
            st.rerun()

    st.divider()

    tab_bist, tab_kripto, tab_emtia, tab_nasdaq, tab_sp500, tab_ozel = st.tabs([
        "🇹🇷 BIST 100",
        "🪙 Kripto (İlk 50)",
        "🛢️ Fonlar & Emtialar",
        "💻 NASDAQ",
        "📈 S&P 500",
        "⭐ Özel Varlıklar",
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

    with tab_emtia:
        st.subheader("Küresel Emtialar ve Fonlar / ETF'ler")
        for isim, kod in HAZIR_VARLIKLAR[kategoriler_listesi[2]].items():
            if st.checkbox(isim, value=(kod in secilenler), key=f"hef_{kod}"):
                secilenler.add(kod)
            else:
                secilenler.discard(kod)

    with tab_nasdaq:
        st.subheader("NASDAQ Teknoloji Liderleri")
        for isim, kod in HAZIR_VARLIKLAR[kategoriler_listesi[3]].items():
            if st.checkbox(isim, value=(kod in secilenler), key=f"hn_{kod}"):
                secilenler.add(kod)
            else:
                secilenler.discard(kod)

    with tab_sp500:
        st.subheader("S&P 500 Liderleri ve ETF")
        for isim, kod in HAZIR_VARLIKLAR[kategoriler_listesi[4]].items():
            if st.checkbox(isim, value=(kod in secilenler), key=f"hs_{kod}"):
                secilenler.add(kod)
            else:
                secilenler.discard(kod)

    with tab_ozel:
        st.subheader("⭐ Özel Olarak Eklediğiniz Varlıklar")
        tum_hazir_kodlar = {kod for kat in HAZIR_VARLIKLAR.values() for kod in kat.values()}
        ozel_kodlar = sorted([k for k in secilenler if k not in tum_hazir_kodlar])
        
        if not ozel_kodlar:
            st.info("Henüz özel olarak eklenmiş ek bir varlık bulunmuyor. Aşağıdaki alandan yeni özel varlık aratıp ekleyebilirsiniz.")
        else:
            for kod in ozel_kodlar:
                if st.checkbox(f"Özel Varlık: {kod}", value=(kod in secilenler), key=f"ozel_{kod}"):
                    secilenler.add(kod)
                else:
                    secilenler.discard(kod)

    st.divider()
    st.subheader("🔎 İnternetten Varlık Arama ve Ekleme")
    st.markdown("Bir varlığın adını, kısaltmasını veya onu andıran bir kelimeyi yazın (Örn: *Apple*, *Garanti*, *Ethereum*), sistem doğru kodu internetten bulsun.")
    
    if "arama_sonuclari" not in st.session_state:
        st.session_state["arama_sonuclari"] = []

    arama_sorgusu = st.text_input("Arama Kelimesi veya Kısaltma", key="arama_input")

    col_ara1, col_ara2 = st.columns([1, 4])
    with col_ara1:
        if st.button("🔍 İnternette Ara"):
            if arama_sorgusu:
                with st.spinner("Varlık aranıyor..."):
                    st.session_state["arama_sonuclari"] = internette_varlik_ara(arama_sorgusu)
                    if not st.session_state["arama_sonuclari"]:
                        st.warning("Eşleşen varlık bulunamadı.")

    if st.session_state["arama_sonuclari"]:
        st.markdown("---")
        secenekler = {f"{item['symbol']} — {item['name']} ({item['exchange']})": item['symbol'] for item in st.session_state["arama_sonuclari"]}
        secilen_etiket = st.selectbox("Bulunan Sonuçlar:", list(secenekler.keys()), key="secilen_arama_sonucu")
        
        if st.button("➕ Seçilen Varlığı Listeye Ekle", type="primary"):
            secilen_kod = secenekler[secilen_etiket]
            secilenler.add(secilen_kod)
            aktif_ayarlar["varliklar"] = sorted(list(secilenler))
            ayarlari_kaydet(aktif_ayarlar)
            st.success(f"{secilen_kod} başarıyla eklendi ve kaydedildi!")
            st.session_state["arama_sonuclari"] = []
            time.sleep(0.5)
            st.rerun()

    st.divider()
    if st.button(
        "💾 SEÇİMLERİ SABİTLE VE KAYDET",
        use_container_width=True,
        type="primary",
    ):
        aktif_ayarlar["varliklar"] = sorted(list(secilenler))
        ayarlari_kaydet(aktif_ayarlar)
        st.success(
            "Seçtiğiniz varlıklar alfabetik olarak sıralandı, sabitlendi ve kaydedildi!"
        )
        time.sleep(1)
        st.rerun()

elif sayfa == "⚙️ Bot Ayarları":
    st.title("⚙️ Bot ve Zaman Dilimi Ayarları")
    st.markdown("Otomatik tarama botunun çalışma sıklığını ve analiz periyodunu buradan yapılandırabilirsiniz.")

    zaman_dilimleri = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]
    mevcut_zaman_dilimi = aktif_ayarlar.get("zaman_dilimi", "1h")
    
    secilen_zaman_dilimi = st.selectbox(
        "Veri Zaman Dilimi (Periyot)",
        zaman_dilimleri,
        index=zaman_dilimleri.index(mevcut_zaman_dilimi) if mevcut_zaman_dilimi in zaman_dilimleri else 4
    )

    mevcut_siklik = aktif_ayarlar.get("bot_sikligi_dk", 60)
    secilen_siklik = st.number_input(
        "Otomatik Telegram Bildirim Sıklığı (Dakika)",
        min_value=1,
        value=int(mevcut_siklik),
        step=1
    )

    st.divider()
    if st.button("💾 Ayarları Kaydet", type="primary", use_container_width=True):
        aktif_ayarlar["zaman_dilimi"] = secilen_zaman_dilimi
        aktif_ayarlar["bot_sikligi_dk"] = int(secilen_siklik)
        ayarlari_kaydet(aktif_ayarlar)
        st.success("Bot ayarları başarıyla güncellendi!")
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
            mevcut_havuz = sorted(aktif_ayarlar.get("varliklar", ["BTC-USD"]))
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

        for v_kod, v_veri in sorted(aktif_portfoy.items()):
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

    mevcut_varliklar = sorted(aktif_ayarlar.get("varliklar", ["BTC-USD"]))
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
        "📈 Sabit Varlık Sinyal Listesi, Çoklu Destek/Direnç ve Detaylı Teknik Yorum"
    )
    mevcut_varliklar = sorted(aktif_ayarlar.get("varliklar", []))

    if not mevcut_varliklar:
        st.warning("Lütfen Varlık Havuzundan varlık seçin ve sabitleyin.")
    else:
        if "secilen_aktif_grafik" not in st.session_state or st.session_state["secilen_aktif_grafik"] not in mevcut_varliklar:
            st.session_state["secilen_aktif_grafik"] = mevcut_varliklar[0]

        st.subheader(
            "📋 Sabit Liste Sinyalleri, Destek-Direnç Kademeleri ve Yorum Raporu"
        )

        telegram_toplu_mesaj = f"📊 *Sabit Liste Toplu Sinyal ve Detaylı Teknik Rapor* (Periyot: {aktif_ayarlar['zaman_dilimi']})\n\n"

        for varlik in mevcut_varliklar:
            df_temp = veri_cek(varlik, aralik=aktif_ayarlar["zaman_dilimi"])
            if df_temp is not None and not df_temp.empty:
                df_t_analiz = hesapla_teknikler(df_temp)
                p_analiz = donusum_noktalari_hesapla(df_t_analiz)
                p_sinyal = sinyal_kontrol(df_t_analiz)

                detay_metni = detayli_analiz_ve_yorum_olustur(
                    varlik, df_t_analiz, p_analiz, p_sinyal
                )
                telegram_toplu_mesaj += detay_metni

                col_info, col_btn = st.columns([4, 1])
                with col_info:
                    st.markdown(detay_metni)
                with col_btn:
                    st.markdown("<br>", unsafe_allow_html=True)
                    if st.button(
                        f"📊 Grafiği İncele",
                        key=f"btn_list_{varlik}",
                        use_container_width=True,
                    ):
                        st.session_state["secilen_aktif_grafik"] = varlik
                        st.rerun()
                st.divider()

        if st.button(
            "📤 Tüm Sabit Listenin Detaylı Analizini Telegram'a Şimdi Gönder",
            type="primary",
            use_container_width=True,
        ):
            telegram_bildirim_gonder(telegram_toplu_mesaj)
            st.success(
                "Sabit listedeki tüm varlıkların detaylı analizi ve yorumları Telegram'a başarıyla gönderildi!"
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
