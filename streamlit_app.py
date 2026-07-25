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
SANAL_CUZDAN_DOSYASI = "sanal_cuzdan_arsiv.json"

VARSAYILAN_AYARLAR = {
    "varliklar": ["AAPL", "BTC-USD", "ETH-USD", "SPY", "THYAO.IS"],
    "zaman_dilimi": "1h",
    "bot_sikligi_dk": 60,
}

VARSAYILAN_SANAL_CUZDAN = {
    "nakit": 10000.0,
    "baslangic_nakit": 10000.0,
    "pozisyonlar": {},  # {varlik: {"adet": x, "maliyet": y, "tarih": z}}
    "gecmis_islemler": []
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


def sanal_cuzdan_yukle():
    if not os.path.exists(SANAL_CUZDAN_DOSYASI):
        with open(SANAL_CUZDAN_DOSYASI, "w") as f:
            json.dump(VARSAYILAN_SANAL_CUZDAN, f)
        return VARSAYILAN_SANAL_CUZDAN
    try:
        with open(SANAL_CUZDAN_DOSYASI, "r") as f:
            return json.load(f)
    except:
        return VARSAYILAN_SANAL_CUZDAN


def sanal_cuzdan_kaydet(cuzdan_verisi):
    with open(SANAL_CUZDAN_DOSYASI, "w") as f:
        json.dump(cuzdan_verisi, f)


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


# --- OTONOM SANAL CÜZDAN AL-SAT MOTORU ---
def otonom_islem_calistir():
    cuzdan = sanal_cuzdan_yukle()
    ayarlar = ayarlari_yukle()
    varliklar = ayarlar.get("varliklar", [])
    zaman_dilimi = ayarlar.get("zaman_dilimi", "1h")
    
    islem_raporu = ""
    degisiklik_oldu = False

    for varlik in varliklar:
        df = veri_cek(varlik, aralik=zaman_dilimi)
        if df is not None and not df.empty:
            df_analiz = hesapla_teknikler(df)
            p_sinyal = sinyal_kontrol(df_analiz)
            guncel_fiyat = df_analiz["close"].iloc[-1]
            tarih_str = str(df_analiz["tarih"].iloc[-1])

            sinyal_ust = p_sinyal.upper()
            
            # AL SİNYALİ VE NAKİT VARSA
            if ("AL" in sinyal_ust or "YÜKSELİŞ" in sinyal_ust) and varlik not in cuzdan["pozisyonlar"]:
                harcanacak_nakit = cuzdan["nakit"] * 0.25  # Her işlemde nakdin %25'i
                if harcanacak_nakit > 10:
                    adet = harcanacak_nakit / guncel_fiyat
                    cuzdan["nakit"] -= harcanacak_nakit
                    cuzdan["pozisyonlar"][varlik] = {
                        "adet": adet,
                        "maliyet": guncel_fiyat,
                        "tarih": tarih_str
                    }
                    islem_raporu += f"🟢 **[OTONOM AL]** `{varlik}` | Fiyat: `{guncel_fiyat:.2f}` | Tutar: `{harcanacak_nakit:.2f} $`\n"
                    cuzdan["gecmis_islemler"].append({
                        "islem": "AL",
                        "varlik": varlik,
                        "fiyat": guncel_fiyat,
                        "tarih": tarih_str,
                        "tutar": harcanacak_nakit
                    })
                    degisiklik_oldu = True

            # SAT SİNYALİ VE POZİSYON VARSA
            elif ("SAT" in sinyal_ust or "DÜŞÜŞ" in sinyal_ust) and varlik in cuzdan["pozisyonlar"]:
                poz = cuzdan["pozisyonlar"][varlik]
                satis_degeri = poz["adet"] * guncel_fiyat
                kar_zarar = satis_degeri - (poz["adet"] * poz["maliyet"])
                cuzdan["nakit"] += satis_degeri
                
                islem_raporu += f"🔴 **[OTONOM SAT]** `{varlik}` | Fiyat: `{guncel_fiyat:.2f}` | K/Z: `{kar_zarar:+.2f} $`\n"
                cuzdan["gecmis_islemler"].append({
                    "islem": "SAT",
                    "varlik": varlik,
                    "fiyat": guncel_fiyat,
                    "tarih": tarih_str,
                    "tutar": satis_degeri,
                    "kar_zarar": kar_zarar
                })
                del cuzdan["pozisyonlar"][varlik]
                degisiklik_oldu = True

    if degisiklik_oldu:
        sanal_cuzdan_kaydet(cuzdan)

    return islem_raporu, cuzdan


# --- DETAYLI TEKNİK ANALİZ VE YORUM OLUŞTURUCU ---
def detayli_analiz_ve_yorum_olustur(varlik, df_t_analiz, p_analiz, p_sinyal):
    fiyat = p_analiz["fiyat"]
    d1 = p_analiz["destek"]
    r1 = p_analiz["direnc"]

    s1 = d1
    s2 = s1 * 0.985
    s3 = s1 * 0.970

    r1_val = r1
    r2 = r1_val * 1.015
    r3 = r1_val * 1.030

    stop_loss = s1 if s1 < fiyat else fiyat * 0.97
    take_profit = r1_val if r1_val > fiyat else fiyat * 1.05

    is_fake = df_t_analiz.iloc[-1].get("sahte_sinyal", False)
    gecis_tarihi = df_t_analiz.iloc[-1].get("tarih", "-")

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

    if is_fake:
        sahte_yorum = "⚠️ *SİNYAL UYARISI:* Sahte/Tuzak sinyal tespit edildi! Hacim veya yardımcı indikatör doğrulaması zayıf."
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

            # Otonom işlem turunu çalıştır
            otonom_rapor, cuzdan_sonuc = otonom_islem_calistir()

            if varliklar:
                telegram_toplu_mesaj = f"📊 *Otomatik Analiz ve Otonom Cüzdan Raporu* (Periyot: {zaman_dilimi})\n\n"
                
                if otonom_rapor:
                    telegram_toplu_mesaj += f"🤖 *Otonom Al-Sat Hareketleri:*\n{otonom_rapor}\n-------------------\n"

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
        "🤖 Otonom Sanal Cüzdan",
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
            st.info("Henüz özel olarak eklenmiş ek bir varlık bulunmuyor.")
        else:
            for kod in ozel_kodlar:
                if st.checkbox(f"Özel Varlık: {kod}", value=(kod in secilenler), key=f"ozel_{kod}"):
                    secilenler.add(kod)
                else:
                    secilenler.discard(kod)

    st.divider()
    st.subheader("🔎 İnternetten Varlık Arama ve Ekleme")
    arama_sorgusu = st.text_input("Arama Kelimesi veya Kısaltma", key="arama_input")

    if st.button("🔍 İnternette Ara"):
        if arama_sorgusu:
            with st.spinner("Varlık aranıyor..."):
                st.session_state["arama_sonuclari"] = internette_varlik_ara(arama_sorgusu)

    if "arama_sonuclari" in st.session_state and st.session_state["arama_sonuclari"]:
        st.markdown("---")
        secenekler = {f"{item['symbol']} — {item['name']} ({item['exchange']})": item['symbol'] for item in st.session_state["arama_sonuclari"]}
        secilen_etiket = st.selectbox("Bulunan Sonuçlar:", list(secenekler.keys()), key="secilen_arama_sonucu")
        
        if st.button("➕ Seçilen Varlığı Listeye Ekle", type="primary"):
            secilen_kod = secenekler[secilen_etiket]
            secilenler.add(secilen_kod)
            aktif_ayarlar["varliklar"] = sorted(list(secilenler))
            ayarlari_kaydet(aktif_ayarlar)
            st.success(f"{secilen_kod} başarıyla eklendi!")
            st.session_state["arama_sonuclari"] = []
            time.sleep(0.5)
            st.rerun()

    st.divider()
    if st.button("💾 SEÇİMLERİ SABİTLE VE KAYDET", use_container_width=True, type="primary"):
        aktif_ayarlar["varliklar"] = sorted(list(secilenler))
        ayarlari_kaydet(aktif_ayarlar)
        st.success("Seçtiğiniz varlıklar kaydedildi!")
        time.sleep(1)
        st.rerun()

elif sayfa == "⚙️ Bot Ayarları":
    st.title("⚙️ Bot ve Zaman Dilimi Ayarları")
    zaman_dilimleri = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]
    mevcut_zaman_dilimi = aktif_ayarlar.get("zaman_dilimi", "1h")
    
    secilen_zaman_dilimi = st.selectbox(
        "Veri Zaman Dilimi (Periyot)",
        zaman_dilimleri,
        index=zaman_dilimleri.index(mevcut_zaman_dilimi) if mevcut_zaman_dilimi in zaman_dilimleri else 4
    )

    mevcut_siklik = aktif_ayarlar.get("bot_sikligi_dk", 60)
    secilen_siklik = st.number_input("Otomatik Telegram Bildirim Sıklığı (Dakika)", min_value=1, value=int(mevcut_siklik), step=1)

    st.divider()
    if st.button("💾 Ayarları Kaydet", type="primary", use_container_width=True):
        aktif_ayarlar["zaman_dilimi"] = secilen_zaman_dilimi
        aktif_ayarlar["bot_sikligi_dk"] = int(secilen_siklik)
        ayarlari_kaydet(aktif_ayarlar)
        st.success("Bot ayarları güncellendi!")
        time.sleep(1)
        st.rerun()

elif sayfa == "🤖 Otonom Sanal Cüzdan":
    st.title("🤖 Otonom Sanal Cüzdan (Paper Trading Simülasyonu)")
    st.markdown("Sistem, aktif varlık listendeki coin/hisse senetlerini analiz ederek **yükselişlerde (AL)** sanal bütçeyle alım yapar, **düşüşlerde (SAT)** pozisyon kapatarak kâr/zarar hesabı tutar. Bu süreç arka planda Telegram'a da raporlanır.")

    cuzdan_data = sanal_cuzdan_yukle()

    col_b1, col_b2, col_b3 = st.columns(3)
    
    # Anlık değer hesaplama
    toplam_pozisyon_degeri = 0
    for v_kod, poz in cuzdan_data["pozisyonlar"].items():
        df_c = veri_cek(v_kod, aralik=aktif_ayarlar["zaman_dilimi"])
        if df_c is not None and not df_c.empty:
            anlik_f = df_c["close"].iloc[-1]
            toplam_pozisyon_degeri += poz["adet"] * anlik_f

    toplam_servet = cuzdan_data["nakit"] + toplam_pozisyon_degeri
    net_kazanc = toplam_servet - cuzdan_data["baslangic_nakit"]
    net_kazanc_yuzde = (net_kazanc / cuzdan_data["baslangic_nakit"]) * 100

    col_b1.metric("Toplam Varlık (Servet)", f"{toplam_servet:.2f} $", f"%{net_kazanc_yuzde:+.2f}")
    col_b2.metric("Nakit Bakiye", f"{cuzdan_data['nakit']:.2f} $")
    col_b3.metric("Açık Pozisyon Değeri", f"{toplam_pozisyon_degeri:.2f} $")

    st.divider()
    col_islem1, col_islem2 = st.columns([2, 2])
    with col_islem1:
        if st.button("🔄 Otonom Turu Şimdi Çalıştır (Manuel Test)", type="primary", use_container_width=True):
            with st.spinner("Piyasa taranıyor ve otonom al-sat kararları uygulanıyor..."):
                rapor, yeni_cuzdan = otonom_islem_calistir()
                if rapor:
                    st.success("Otonom işlemler gerçekleştirildi!")
                    st.markdown(rapor)
                else:
                    st.info("Mevcut sinyallere göre yeni bir işlem tetiklenmedi (Koşullar sağlanmadı).")
                time.sleep(1)
                st.rerun()
    with col_islem2:
        if st.button("🗑️ Sanal Cüzdanı Sıfırla (10,000 $)", use_container_width=True):
            sanal_cuzdan_kaydet(VARSAYILAN_SANAL_CUZDAN)
            st.success("Sanal cüzdan sıfırlandı.")
            time.sleep(1)
            st.rerun()

    st.subheader("📂 Açık Sanal Pozisyonlar")
    if not cuzdan_data["pozisyonlar"]:
        st.info("Şu an açık olan herhangi bir sanal pozisyon bulunmuyor. Sinyaller olumluya döndüğünde bot otomatik alım yapacaktır.")
    else:
        for v_kod, poz in cuzdan_data["pozisyonlar"].items():
            df_curr = veri_cek(v_kod, aralik=aktif_ayarlar["zaman_dilimi"])
            curr_fiyat = df_curr["close"].iloc[-1] if df_curr is not None and not df_curr.empty else poz["maliyet"]
            deger = poz["adet"] * curr_fiyat
            maliyet_tutar = poz["adet"] * poz["maliyet"]
            kar_ zarar = deger - maliyet_tutar
            kar_zarar_yuzde = ((curr_fiyat - poz["maliyet"]) / poz["maliyet"]) * 100
            
            c_renk = "green" if kar_zarar >= 0 else "red"
            
            st.markdown(f"**Varlık:** `{v_kod}` | **Alış Tarihi:** `{poz['tarih']}`")
            st.markdown(f"• Alış Maliyeti: `{poz['maliyet']:.2f}` | Anlık Fiyat: `{curr_fiyat:.2f}` | Lot: `{poz['adet']:.4f}`")
            st.markdown(f"• Anlık Değer: `{deger:.2f} $` | K/Z: <span style='color:{c_renk}; font-weight:bold;'>{kar_zarar:+.2f} $ (%{kar_zarar_yuzde:+.2f})</span>", unsafe_allow_html=True)
            st.divider()

    st.subheader("📜 Otonom İşlem Geçmişi (Log)")
    if not cuzdan_data["gecmis_islemler"]:
        st.info("Henüz geçmiş işlem kaydı yok.")
    else:
        df_gecmis = pd.DataFrame(cuzdan_data["gecmis_islemler"])
        st.dataframe(df_gecmis, use_container_width=True)

elif sayfa == "💼 Portföy Yönetimi":
    st.title("💼 Portföy Yönetimi ve Detaylı Analiz")

    with st.expander("➕ Yeni İşlem / Varlık Ekle", expanded=True):
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            mevcut_havuz = sorted(aktif_ayarlar.get("varliklar", ["BTC-USD"]))
            p_varlik = st.selectbox("Varlık Seç", mevcut_havuz)
        with col2:
            p_tarih = st.date_input("Alım Tarihi", value=datetime.date.today())
        with col3:
            p_harcanan = st.number_input("Harcanan Tutar", min_value=0.0, value=3000.0, format="%.2f")
        with col4:
            p_maliyet = st.number_input("Alış Fiyatı (Birim)", min_value=0.0, format="%.4f")
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
                    st.success(f"Kayıt eklendi! Lot: {p_adet:.4f}")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("Alış fiyatı 0'dan büyük olmalıdır!")

    st.divider()
    st.subheader("📊 Portföy Canlı Durumu")
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
                harcanan = v_veri.get("harcanan", v_veri.get("maliyet", 0) * v_veri.get("adet", 0))
                maliyet = v_veri["maliyet"]
                adet = v_veri["adet"]

                guncel_deger = anlik_fiyat * adet
                toplam_kar = guncel_deger - harcanan
                toplam_kar_yuzde = ((anlik_fiyat - maliyet) / maliyet) * 100 if maliyet > 0 else 0

                gunluk_fark_tutar = (anlik_fiyat - onceki_fiyat) * adet
                gunluk_fark_yuzde = ((anlik_fiyat - onceki_fiyat) / onceki_fiyat) * 100 if onceki_fiyat > 0 else 0

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
                    st.markdown(f"<span style='color:{t_renk}; font-weight:bold;'>{toplam_kar:+.2f} (%{toplam_kar_yuzde:+.2f})</span>", unsafe_allow_html=True)
                with c4:
                    st.markdown(f"**Günlük K/Z:**")
                    st.markdown(f"<span style='color:{g_renk}; font-weight:bold;'>{gunluk_fark_tutar:+.2f} (%{gunluk_fark_yuzde:+.2f})</span>", unsafe_allow_html=True)
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
        t1, t2, t3 = st.columns(3)
        t1.metric("Toplam Harcanan (Maliyet)", f"{toplam_portfoy_maliyeti:.2f}")
        t2.metric("Portföy Güncel Değeri", f"{toplam_portfoy_guncel_degeri:.2f}")
        t3.metric("Genel Toplam Kâr / Zarar", f"{toplam_fark:+.2f}")

elif sayfa == "⏳ Geriye Dönük Test":
    st.title("⏳ Strateji Testi (Backtest)")
    st.markdown("Seçtiğiniz varlık ve zaman diliminde bot stratejisinin geçmiş kârlılığını test edin. **Başlangıç Bakiyesi: 10,000 $**")

    mevcut_varliklar = sorted(aktif_ayarlar.get("varliklar", ["BTC-USD"]))
    test_edilecek = st.selectbox("Test Edilecek Varlık", mevcut_varliklar)

    if st.button("🚀 Backtest'i Başlat", type="primary"):
        with st.spinner("Geçmiş veriler taranıyor ve simülasyon yapılıyor..."):
            df_test = veri_cek(test_edilecek, aralik=aktif_ayarlar["zaman_dilimi"])
            if df_test is not None and not df_test.empty:
                df_test_analiz = hesapla_teknikler(df_test)
                sonuclar = calistir_backtest(df_test_analiz)

                st.divider()
                st.subheader(f"📊 {test_edilecek} Backtest Sonuçları (Periyot: {aktif_ayarlar['zaman_dilimi']})")

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
                    st.warning("Bu periyotta stratejiye uygun işlem bulunamadı.")
            else:
                st.error("Veri çekilemedi.")

elif sayfa == "📈 Canlı Analiz & Sinyaller":
    st.title("📈 Sabit Varlık Sinyal Listesi, Çoklu Destek/Direnç ve Detaylı Teknik Yorum")
    mevcut_varliklar = sorted(aktif_ayarlar.get("varliklar", []))

    if not mevcut_varliklar:
        st.warning("Lütfen Varlık Havuzundan varlık seçin ve sabitleyin.")
    else:
        if "secilen_aktif_grafik" not in st.session_state or st.session_state["secilen_aktif_grafik"] not in mevcut_varliklar:
            st.session_state["secilen_aktif_grafik"] = mevcut_varliklar[0]

        st.subheader("📋 Sabit Liste Sinyalleri, Destek-Direnç Kademeleri ve Yorum Raporu")

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
                    if st.button(f"📊 Grafiği İncele", key=f"btn_list_{varlik}", use_container_width=True):
                        st.session_state["secilen_aktif_grafik"] = varlik
                        st.rerun()
                st.divider()

        if st.button("📤 Tüm Sabit Listenin Detaylı Analizini Telegram'a Şimdi Gönder", type="primary", use_container_width=True):
            telegram_bildirim_gonder(telegram_toplu_mesaj)
            st.success("Tüm analizler Telegram'a gönderildi!")

        st.divider()
        st.header(f"📊 Gelişmiş Grafik İncelemesi: `{st.session_state['secilen_aktif_grafik']}`")

        col_mod1, col_mod2 = st.columns(2)
        with col_mod1:
            grafik_modu = st.selectbox("Grafik Fare Modu:", ["🔍 Zoom", "✋ Kaydırma / Pan"])
        drag_mode_val = "pan" if "Kaydırma" in grafik_modu else "zoom"

        ek_gostergeler = st.multiselect(
            "Gösterilecek İndikatörler",
            ["Bollinger Bantları", "Özel İndikatörüm", "RSI (Alt Grafik)", "MACD (Alt Grafik)"],
            default=["Bollinger Bantları"],
        )

        aktif_secim = st.session_state["secilen_aktif_grafik"]
        df = veri_cek(aktif_secim, aralik=aktif_ayarlar["zaman_dilimi"])

        if df is not None and not df.empty:
            df_analiz = hesapla_teknikler(df)
            
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.7, 0.3])
            
            fig.add_trace(
                go.Candlestick(
                    x=df_analiz["tarih"],
                    open=df_analiz["open"],
                    high=df_analiz["high"],
                    low=df_analiz["low"],
                    close=df_analiz["close"],
                    name="Fiyat"
                ),
                row=1, col=1
            )
            
            if "Bollinger Bantları" in ek_gostergeler and "bb_ust" in df_analiz.columns:
                fig.add_trace(go.Scatter(x=df_analiz["tarih"], y=df_analiz["bb_ust"], line=dict(color="rgba(250, 0, 0, 0.5)", width=1), name="BB Üst"), row=1, col=1)
                fig.add_trace(go.Scatter(x=df_analiz["tarih"], y=df_analiz["bb_alt"], line=dict(color="rgba(0, 250, 0, 0.5)", width=1), name="BB Alt", fill='tonenexty'), row=1, col=1)
            
            if "Özel İndikatörüm" in ek_gostergeler and "ozel_gosterge" in df_analiz.columns:
                fig.add_trace(go.Scatter(x=df_analiz["tarih"], y=df_analiz["ozel_gosterge"], line=dict(color="orange", width=1.5), name="Özel İndikatör"), row=1, col=1)
            
            if "RSI (Alt Grafik)" in ek_gostergeler and "rsi" in df_analiz.columns:
                fig.add_trace(go.Scatter(x=df_analiz["tarih"], y=df_analiz["rsi"], line=dict(color="purple", width=1.5), name="RSI"), row=2, col=1)
                fig.add_hrect(y0=30, y1=70, fillcolor="gray", opacity=0.1, layer="below", line_width=0, row=2, col=1)
            
            elif "MACD (Alt Grafik)" in ek_gostergeler and "macd" in df_analiz.columns:
                fig.add_trace(go.Scatter(x=df_analiz["tarih"], y=df_analiz["macd"], line=dict(color="blue", width=1.5), name="MACD"), row=2, col=1)
                if "macd_signal" in df_analiz.columns:
                    fig.add_trace(go.Scatter(x=df_analiz["tarih"], y=df_analiz["macd_signal"], line=dict(color="orange", width=1.5), name="Signal"), row=2, col=1)
            
            fig.update_layout(
                template="plotly_dark",
                xaxis_rangeslider_visible=False,
                height=700,
                margin=dict(l=10, r=10, t=30, b=10)
            )
            
            st.plotly_chart(fig, use_container_width=True, config={"dragmode": drag_mode_val})
        else:
            st.error("Seçilen varlık için veri yüklenemedi.")
