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
    "varliklar": ["BTC-USD", "ETH-USD", "SOL-USD", "AAPL", "THYAO.IS"],
    "zaman_dilimi": "1h",
    "bot_sikligi_dk": 60,
}

VARSAYILAN_SANAL_CUZDAN = {
    "nakit": 10000.0,
    "baslangic_nakit": 10000.0,
    "pozisyonlar": {},  # {varlik: {"adet": x, "maliyet": y, "stop_loss": sl, "take_profit": tp, "tarih": z}}
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


# --- OTONOM SANAL CÜZDAN AL-SAT MOTORU (1:2 R/R - %1.5 SL / %3.0 TP) ---
def otonom_islem_calistir():
    cuzdan = sanal_cuzdan_yukle()
    ayarlar = ayarlari_yukle()
    varliklar = ayarlar.get("varliklar", [])
    zaman_dilimi = ayarlar.get("zaman_dilimi", "1h")
    
    islem_raporu = ""
    degisiklik_oldu = False

    # 1. Önce açık olan pozisyonları kontrol et (Stop-Loss veya Take-Profit tetiklenmiş mi?)
    acik_pozisyonlar = list(cuzdan["pozisyonlar"].keys())
    
    for varlik in acik_pozisyonlar:
        df = veri_cek(varlik, aralik=zaman_dilimi)
        if df is not None and not df.empty:
            guncel_fiyat = df["close"].iloc[-1]
            tarih_str = str(df["tarih"].iloc[-1])
            poz = cuzdan["pozisyonlar"][varlik]
            
            sl = poz["stop_loss"]
            tp = poz["take_profit"]
            
            kapatma_nedeni = None
            if guncel_fiyat <= sl:
                kapatma_nedeni = "STOP-LOSS (%1.5 Zarar Kes)"
            elif guncel_fiyat >= tp:
                kapatma_nedeni = "TAKE-PROFIT (%3.0 Kâr Al)"
            else:
                # Teknik sinyal tersine döndüyse de kapat
                df_analiz = hesapla_teknikler(df)
                p_sinyal = sinyal_kontrol(df_analiz)
                if "SAT" in p_sinyal.upper() or "DÜŞÜŞ" in p_sinyal.upper():
                    kapatma_nedeni = "TEKNİK SAT SİNYALİ"

            if kapatma_nedeni:
                satis_degeri = poz["adet"] * guncel_fiyat
                kar_zarar = satis_degeri - (poz["adet"] * poz["maliyet"])
                cuzdan["nakit"] += satis_degeri
                
                islem_raporu += f"🔴 **[OTONOM KAPATMA - {kapatma_nedeni}]** `{varlik}` | Fiyat: `{guncel_fiyat:.2f}` | K/Z: `{kar_zarar:+.2f} $`\n"
                cuzdan["gecmis_islemler"].append({
                    "islem": f"KAPAT ({kapatma_nedeni})",
                    "varlik": varlik,
                    "fiyat": guncel_fiyat,
                    "tarih": tarih_str,
                    "tutar": satis_degeri,
                    "kar_zarar": kar_zarar
                })
                del cuzdan["pozisyonlar"][varlik]
                degisiklik_oldu = True

    # 2. Yeni alım fırsatlarını tara
    for varlik in varliklar:
        if varlik in cuzdan["pozisyonlar"]:
            continue  # Zaten açık pozisyon varsa yeni açma
            
        df = veri_cek(varlik, aralik=zaman_dilimi)
        if df is not None and not df.empty:
            df_analiz = hesapla_teknikler(df)
            p_sinyal = sinyal_kontrol(df_analiz)
            guncel_fiyat = df_analiz["close"].iloc[-1]
            tarih_str = str(df_analiz["tarih"].iloc[-1])
            sinyal_ust = p_sinyal.upper()
            
            if "AL" in sinyal_ust or "YÜKSELİŞ" in sinyal_ust:
                harcanacak_nakit = cuzdan["nakit"] * 0.25  # Nakdin %25'i ile işlem
                if harcanacak_nakit > 10:
                    adet = harcanacak_nakit / guncel_fiyat
                    sl_deger = guncel_fiyat * 0.985  # %1.5 Stop-Loss
                    tp_deger = guncel_fiyat * 1.030  # %3.0 Take-Profit
                    
                    cuzdan["nakit"] -= harcanacak_nakit
                    cuzdan["pozisyonlar"][varlik] = {
                        "adet": adet,
                        "maliyet": guncel_fiyat,
                        "stop_loss": sl_deger,
                        "take_profit": tp_deger,
                        "tarih": tarih_str
                    }
                    islem_raporu += f"🟢 **[OTONOM AL]** `{varlik}` | Fiyat: `{guncel_fiyat:.2f}` | SL: `{sl_deger:.2f}` | TP: `{tp_deger:.2f}`\n"
                    cuzdan["gecmis_islemler"].append({
                        "islem": "AL",
                        "varlik": varlik,
                        "fiyat": guncel_fiyat,
                        "tarih": tarih_str,
                        "tutar": harcanacak_nakit
                    })
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

    stop_loss = s1 if s1 < fiyat else fiyat * 0.985
    take_profit = r1_val if r1_val > fiyat else fiyat * 1.030

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
        sahte_yorum = "⚠️ *SİNYAL UYARISI:* Sahte/Tuzak sinyal tespit edildi!"
    else:
        sahte_yorum = "✅ *GÜVENİLİR SİNYAL:* İndikatör ve hacim teyidi mevcut."

    rapor_metni = (
        f"🔹 *{varlik}*\n"
        f"   • *Fiyat:* `{fiyat:.2f}` | *Durum:* `{p_sinyal}`\n"
        f"   • *Geçiş Zamanı:* `{gecis_tarihi}`\n"
        f"   • *Destekler:* S1: `{s1:.2f}` | S2: `{s2:.2f}` | S3: `{s3:.2f}`\n"
        f"   • *Dirençler:* R1: `{r1_val:.2f}` | R2: `{r2:.2f}` | R3: `{r3:.2f}`\n"
        f"   • *Strateji (1:2 R/R):* SL: `{stop_loss:.2f}` (%1.5) | TP: `{take_profit:.2f}` (%3.0)\n"
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

            otonom_rapor, cuzdan_sonuc = otonom_islem_calistir()

            if varliklar:
                telegram_toplu_mesaj = f"📊 *Otomatik Analiz ve Otonom Cüzdan Raporu (1:2 R/R)*\n\n"
                
                if otonom_rapor:
                    telegram_toplu_mesaj += f"🤖 *Otonom Al-Sat / SL-TP Hareketleri:*\n{otonom_rapor}\n-------------------\n"

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
        "AGHOL (Anadolu Grubu Holding)": "AGHOL.IS",
        "AHGAZ (Ahlatcı Doğalgaz)": "AHGAZ.IS",
        "AKCNS (Akçansa)": "AKCNS.IS",
        "AKFGY (Akfen GYO)": "AKFGY.IS",
        "AKSA (Aksa Akrilik)": "AKSA.IS",
        "AKSEN (Aksa Enerji)": "AKSEN.IS",
        "ALARK (Alarko Holding)": "ALARK.IS",
        "ALBRK (Albaraka Türk)": "ALBRK.IS",
        "ALFAS (Alfa Solar Enerji)": "ALFAS.IS",
        "ARCLK (Arçelik)": "ARCLK.IS",
        "ASELS (Aselsan)": "ASELS.IS",
        "ASTOR (Astor Enerji)": "ASTOR.IS",
        "BERA (Bera Holding)": "BERA.IS",
        "BIMAS (Bim Mağazalar)": "BIMAS.IS",
        "BRYAT (Borusan Yatırım)": "BRYAT.IS",
        "BUCIM (Bursa Çimento)": "BUCIM.IS",
        "CANTE (Çan2 Termik)": "CANTE.IS",
        "CCOLA (Coca-Cola İçecek)": "CCOLA.IS",
        "CEMTS (Çemtaş)": "CEMTS.IS",
        "CIMSA (Çimsa)": "CIMSA.IS",
        "CWENE (CW Enerji)": "CWENE.IS",
        "DOAS (Doğuş Otomotiv)": "DOAS.IS",
        "DOHOL (Doğan Holding)": "DOHOL.IS",
        "ECILC (Eczacıbaşı İlaç)": "ECILC.IS",
        "EGEEN (Ege Endüstri)": "EGEEN.IS",
        "EKGYO (Emlak Konut GYO)": "EKGYO.IS",
        "ENJSA (Enerjisa Enerji)": "ENJSA.IS",
        "ENKAI (Enka İnşaat)": "ENKAI.IS",
        "EREGL (Ereğli Demir Çelik)": "EREGL.IS",
        "EUPWR (Europen Endüstri)": "EUPWR.IS",
        "FROTO (Ford Otosan)": "FROTO.IS",
        "GARAN (Garanti BBVA)": "GARAN.IS",
        "GESAN (Girişim Elektrik)": "GESAN.IS",
        "GLYHO (Global Yatırım Holding)": "GLYHO.IS",
        "GUBRF (Gübre Fabrikaları)": "GUBRF.IS",
        "GWIND (Galata Wind Enerji)": "GWIND.IS",
        "HALKB (Halkbank)": "HALKB.IS",
        "HEKTS (Hektaş)": "HEKTS.IS",
        "IPEKE (İpek Enerji)": "IPEKE.IS",
        "ISCTR (İş Bankası C)": "ISCTR.IS",
        "ISDMR (İskenderun Demir Çelik)": "ISDMR.IS",
        "ISGYO (İş GYO)": "ISGYO.IS",
        "KCAER (Kocaer Çelik)": "KCAER.IS",
        "KCHOL (Koç Holding)": "KCHOL.IS",
        "KMPUR (Kimteks Poliüretan)": "KMPUR.IS",
        "KONTR (Kontrolmatik Teknoloji)": "KONTR.IS",
        "KONYA (Konya Çimento)": "KONYA.IS",
        "KORDS (Kordsa Teknik Tekstil)": "KORDS.IS",
        "KOZAA (Koza Anadolu Metal)": "KOZAA.IS",
        "KOZAL (Koza Altın)": "KOZAL.IS",
        "KRDMD (Kardemir D)": "KRDMD.IS",
        "KZBGY (Kızılbük GYO)": "KZBGY.IS",
        "MAVI (Mavi Giyim)": "MAVI.IS",
        "MGROS (Migros Ticaret)": "MGROS.IS",
        "ODAS (Odaş Elektrik)": "ODAS.IS",
        "OYAKC (Oyak Çimento)": "OYAKC.IS",
        "PENTA (Penta Teknoloji)": "PENTA.IS",
        "PETKM (Petkim)": "PETKM.IS",
        "PGSUS (Pegasus)": "PGSUS.IS",
        "PSGYK (Pasifik GYO)": "PSGYK.IS",
        "QUAGR (Qua Granite)": "QUAGR.IS",
        "REEDR (Reeder Teknoloji)": "REEDR.IS",
        "SAHOL (Sabancı Holding)": "SAHOL.IS",
        "SASA (Sasa Polyester)": "SASA.IS",
        "SELEC (Selçuk Ecza Deposu)": "SELEC.IS",
        "SISE (Şişecam)": "SISE.IS",
        "SKBNK (Şekerbank)": "SKBNK.IS",
        "SMRTG (Smart Güneş Enerjisi)": "SMRTG.IS",
        "SOKM (Şok Marketler)": "SOKM.IS",
        "TAVHL (TAV Havalimanları)": "TAVHL.IS",
        "TCELL (Turkcell)": "TCELL.IS",
        "THYAO (Türk Hava Yolları)": "THYAO.IS",
        "TOASO (Tofaş Oto Fabrika)": "TOASO.IS",
        "TSKB (TSKB)": "TSKB.IS",
        "TTKOM (Türk Telekom)": "TTKOM.IS",
        "TTRAK (Türk Traktör)": "TTRAK.IS",
        "TUPRS (Tüpraş)": "TUPRS.IS",
        "ULKER (Ülker Bisküvi)": "ULKER.IS",
        "VAKBN (VakıfBank)": "VAKBN.IS",
        "VESBE (Vestel Beyaz Eşya)": "VESBE.IS",
        "VESTL (Vestel)": "VESTL.IS",
        "YEOTK (YEO Teknoloji)": "YEOTK.IS",
        "YKBNK (Yapı Kredi)": "YKBNK.IS",
        "ZOREN (Zorlu Enerji)": "ZOREN.IS"
    },
    "Kripto (İlk 100 / Popüler)": {
        "Bitcoin (BTC)": "BTC-USD",
        "Ethereum (ETH)": "ETH-USD",
        "Binance Coin (BNB)": "BNB-USD",
        "Solana (SOL)": "SOL-USD",
        "XRP (Ripple)": "XRP-USD",
        "Cardano (ADA)": "ADA-USD",
        "Avalanche (AVAX)": "AVAX-USD",
        "Dogecoin (DOGE)": "DOGE-USD",
        "Polkadot (DOT)": "DOT-USD",
        "Tron (TRX)": "TRX-USD",
        "Chainlink (LINK)": "LINK-USD",
        "Polygon (MATIC / POL)": "MATIC-USD",
        "Near Protocol (NEAR)": "NEAR-USD",
        "Uniswap (UNI)": "UNI-USD",
        "Bitcoin Cash (BCH)": "BCH-USD",
        "Litecoin (LTC)": "LTC-USD",
        "Internet Computer (ICP)": "ICP-USD",
        "Aptos (APT)": "APT-USD",
        "Filecoin (FIL)": "FIL-USD",
        "Hedera (HBAR)": "HBAR-USD",
        "Stacks (STX)": "STX-USD",
        "Lido DAO (LDO)": "LDO-USD",
        "Shiba Inu (SHIB)": "SHIB-USD",
        "Stellar (XLM)": "XLM-USD",
        "Cosmos (ATOM)": "ATOM-USD",
        "Optimism (OP)": "OP-USD",
        "Injective (INJ)": "INJ-USD",
        "Kaspa (KAS)": "KAS-USD",
        "Arbitrum (ARB)": "ARB-USD",
        "Render (RENDER)": "RENDER-USD",
        "Celestia (TIA)": "TIA-USD",
        "Sui (SUI)": "SUI-USD",
        "Sei (SEI)": "SEI-USD",
        "Ethereum Classic (ETC)": "ETC-USD",
        "The Graph (GRT)": "GRT-USD",
        "Maker (MKR)": "MKR-USD",
        "Theta Network (THETA)": "THETA-USD",
        "Fantom (FTM)": "FTM-USD",
        "Flow (FLOW)": "FLOW-USD",
        "Algorand (ALGO)": "ALGO-USD",
        "Quant (QNT)": "QNT-USD",
        "Tezos (XTZ)": "XTZ-USD",
        "Chiliz (CHZ)": "CHZ-USD",
        "Aave (AAVE)": "AAVE-USD",
        "Curve DAO (CRV)": "CRV-USD",
        "Axie Infinity (AXS)": "AXS-USD",
        "The Sandbox (SAND)": "SAND-USD",
        "Decentraland (MANA)": "MANA-USD",
        "Gala (GALA)": "GALA-USD",
        "MultiversX (EGLD)": "EGLD-USD"
    },
    "Küresel Emtialar ve Forex": {
        "Altın (Gold Ons)": "GC=F",
        "Brent Petrol": "BZ=F",
        "Ham Petrol (WTI)": "CL=F",
        "Gümüş (Silver Ons)": "SI=F",
        "Platin (Platinum)": "PL=F",
        "Paladyum (Palladium)": "PA=F",
        "Doğalgaz (Natural Gas)": "NG=F",
        "Bakır (Copper)": "HG=F",
        "Buğday (Wheat)": "ZW=F",
        "Mısır (Corn)": "ZC=F",
        "Soya Fasulyesi (Soybean)": "ZS=F",
        "Kakao (Cocoa)": "CC=F",
        "Kahve (Coffee)": "KC=F",
        "Şeker (Sugar)": "SB=F",
        "Pamuk (Cotton)": "CT=F",
        "EUR/USD": "EURUSD=X",
        "GBP/USD": "GBPUSD=X",
        "USD/JPY": "USDJPY=X",
        "AUD/USD": "AUDUSD=X",
        "USD/CAD": "USDCAD=X",
        "USD/CHF": "USDCHF=X",
        "NZD/USD": "NZDUSD=X",
        "EUR/GBP": "EURGBP=X",
        "EUR/JPY": "EURJPY=X",
        "GBP/JPY": "GBPJPY=X",
        "USD/TRY": "USDTRY=X",
        "EUR/TRY": "EURTRY=X",
        "GBP/TRY": "GBPTRY=X"
    },
    "NASDAQ & S&P 500 Liderleri": {
        "Apple (AAPL)": "AAPL",
        "Microsoft (MSFT)": "MSFT",
        "NVIDIA (NVDA)": "NVDA",
        "Amazon (AMZN)": "AMZN",
        "Alphabet Class A (GOOGL)": "GOOGL",
        "Meta Platforms (META)": "META",
        "Tesla (TSLA)": "TSLA",
        "Berkshire Hathaway (BRK-B)": "BRK-B",
        "Eli Lilly (LLY)": "LLY",
        "Broadcom (AVGO)": "AVGO",
        "Visa (V)": "V",
        "JPMorgan Chase (JPM)": "JPM",
        "Walmart (WMT)": "WMT",
        "Exxon Mobil (XOM)": "XOM",
        "Mastercard (MA)": "MA",
        "UnitedHealth (UNH)": "UNH",
        "Costco (COST)": "COST",
        "Johnson & Johnson (JNJ)": "JNJ",
        "Procter & Gamble (PG)": "PG",
        "Home Depot (HD)": "HD",
        "Netflix (NFLX)": "NFLX",
        "Advanced Micro Devices (AMD)": "AMD",
        "Merck & Co (MRK)": "MRK",
        "AbbVie (ABBV)": "ABBV",
        "Salesforce (CRM)": "CRM",
        "Bank of America (BAC)": "BAC",
        "Chevron (CVX)": "CVX",
        "Coca-Cola (KO)": "KO",
        "PepsiCo (PEP)": "PEP",
        "Thermo Fisher Scientific (TMO)": "TMO",
        "Adobe (ADBE)": "ADBE",
        "Linde (LIN)": "LIN",
        "Wells Fargo (WFC)": "WFC",
        "McDonald's (MCD)": "MCD",
        "Cisco Systems (CSCO)": "CSCO",
        "Accenture (ACN)": "ACN",
        "Abbott Laboratories (ABT)": "ABT",
        "IBM (IBM)": "IBM",
        "Walt Disney (DIS)": "DIS",
        "QUALCOMM (QCOM)": "QCOM",
        "Applied Materials (AMAT)": "AMAT",
        "Intel (INTC)": "INTC",
        "Texas Instruments (TXN)": "TXN",
        "Amgen (AMGN)": "Amgen",
        "S&P 500 ETF (SPY)": "SPY",
        "Nasdaq 100 ETF (QQQ)": "QQQ"
    },
}

if sayfa == "📚 Varlık Havuzu":
    st.title("📚 Varlık Havuzu ve Piyasalar")
    secilenler = set(aktif_ayarlar["varliklar"])

    st.subheader("📋 Aktif Varlık Listesi ve Yönetimi (Silme İşlemi)")
    st.markdown("Takip edilen varlıklarınız aşağıdadır. İstemediğiniz bir varlığı **❌ Çıkar** butonuna basarak silebilirsiniz.")
    
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
            st.success("Seçilen varlık listeden çıkarıldı!")
            time.sleep(0.5)
            st.rerun()

    st.divider()

    tab_bist, tab_kripto, tab_emtia, tab_abd, tab_ozel = st.tabs([
        "🇹🇷 BIST",
        "🪙 Kripto",
        "🛢️ Emtia & Forex",
        "📈 ABD Liderleri",
        "⭐ Özel Varlıklar",
    ])

    kategoriler_listesi = list(HAZIR_VARLIKLAR.keys())

    with tab_bist:
        for isim, kod in HAZIR_VARLIKLAR[kategoriler_listesi[0]].items():
            if st.checkbox(isim, value=(kod in secilenler), key=f"hb_{kod}"):
                secilenler.add(kod)
            else:
                secilenler.discard(kod)

    with tab_kripto:
        for isim, kod in HAZIR_VARLIKLAR[kategoriler_listesi[1]].items():
            if st.checkbox(isim, value=(kod in secilenler), key=f"hk_{kod}"):
                secilenler.add(kod)
            else:
                secilenler.discard(kod)

    with tab_emtia:
        for isim, kod in HAZIR_VARLIKLAR[kategoriler_listesi[2]].items():
            if st.checkbox(isim, value=(kod in secilenler), key=f"hef_{kod}"):
                secilenler.add(kod)
            else:
                secilenler.discard(kod)

    with tab_abd:
        for isim, kod in HAZIR_VARLIKLAR[kategoriler_listesi[3]].items():
            if st.checkbox(isim, value=(kod in secilenler), key=f"hn_{kod}"):
                secilenler.add(kod)
            else:
                secilenler.discard(kod)

    with tab_ozel:
        tum_hazir_kodlar = {kod for kat in HAZIR_VARLIKLAR.values() for kod in kat.values()}
        ozel_kodlar = sorted([k for k in secilenler if k not in tum_hazir_kodlar])
        if not ozel_kodlar:
            st.info("Özel eklenmiş varlık bulunmuyor.")
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
            st.success(f"{secilen_kod} eklendi!")
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
    st.title("🤖 Otonom Sanal Cüzdan (1:2 Risk/Reward Stratejisi)")
    st.markdown("Bot; **%1.5 Stop-Loss** ve **%3.0 Take-Profit** kurallarıyla otomatik alım-satım yapar, riskleri minimize ederken kazançları büyütür.")

    cuzdan_data = sanal_cuzdan_yukle()

    col_b1, col_b2, col_b3 = st.columns(3)
    
    toplam_pozisyon_degeri = 0
    for v_kod, poz in cuzdan_data["pozisyonlar"].items():
        df_c = veri_cek(v_kod, aralik=aktif_ayarlar["zaman_dilimi"])
        if df_c is not None and not df_c.empty:
            anlik_f = df_c["close"].iloc[-1]
            toplam_pozisyon_degeri += poz["adet"] * anlik_f

    toplam_servet = cuzdan_data["nakit"] + toplam_pozisyon_degeri
    net_kazanc = toplam_servet - cuzdan_data["baslangic_nakit"]
    net_kazanc_yuzde = (net_kazanc / cuzdan_data["baslangic_nakit"]) * 100

    col_b1.metric("Toplam Servet", f"{toplam_servet:.2f} $", f"%{net_kazanc_yuzde:+.2f}")
    col_b2.metric("Nakit Bakiye", f"{cuzdan_data['nakit']:.2f} $")
    col_b3.metric("Açık Pozisyon Değeri", f"{toplam_pozisyon_degeri:.2f} $")

    st.divider()
    col_islem1, col_islem2 = st.columns([2, 2])
    with col_islem1:
        if st.button("🔄 Otonom Turu Şimdi Çalıştır (Manuel Test)", type="primary", use_container_width=True):
            with st.spinner("Piyasa taranıyor, SL/TP kontrolü yapılıyor..."):
                rapor, yeni_cuzdan = otonom_islem_calistir()
                if rapor:
                    st.success("Otonom işlemler gerçekleştirildi!")
                    st.markdown(rapor)
                else:
                    st.info("Mevcut barda yeni işlem veya SL/TP tetiklemesi olmadı.")
                time.sleep(1)
                st.rerun()
    with col_islem2:
        if st.button("🗑️ Sanal Cüzdanı Sıfırla (10,000 $)", use_container_width=True):
            sanal_cuzdan_kaydet(VARSAYILAN_SANAL_CUZDAN)
            st.success("Sanal cüzdan sıfırlandı.")
            time.sleep(1)
            st.rerun()

    st.subheader("📂 Açık Sanal Pozisyonlar (SL / TP Takibi)")
    if not cuzdan_data["pozisyonlar"]:
        st.info("Şu an açık pozisyon bulunmuyor.")
    else:
        for v_kod, poz in cuzdan_data["pozisyonlar"].items():
            df_curr = veri_cek(v_kod, aralik=aktif_ayarlar["zaman_dilimi"])
            curr_fiyat = df_curr["close"].iloc[-1] if df_curr is not None and not df_curr.empty else poz["maliyet"]
            deger = poz["adet"] * curr_fiyat
            maliyet_tutar = poz["adet"] * poz["maliyet"]
            kar_zarar = deger - maliyet_tutar
            kar_zarar_yuzde = ((curr_fiyat - poz["maliyet"]) / poz["maliyet"]) * 100
            
            c_renk = "green" if kar_zarar >= 0 else "red"
            
            st.markdown(f"**Varlık:** `{v_kod}` | **Alış Tarihi:** `{poz['tarih']}`")
            st.markdown(f"• Maliyet: `{poz['maliyet']:.2f}` | Anlık: `{curr_fiyat:.2f}` | Lot: `{poz['adet']:.4f}`")
            st.markdown(f"• **Stop-Loss:** `{poz['stop_loss']:.2f}` | **Take-Profit:** `{poz['take_profit']:.2f}`")
            st.markdown(f"• Değer: `{deger:.2f} $` | K/Z: <span style='color:{c_renk}; font-weight:bold;'>{kar_zarar:+.2f} $ (%{kar_zarar_yuzde:+.2f})</span>", unsafe_allow_html=True)
            st.divider()

    st.subheader("📜 Otonom İşlem Geçmişi (Log)")
    if not cuzdan_data["gecmis_islemler"]:
        st.info("Geçmiş işlem kaydı yok.")
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
        st.info("Portföyünüze veri eklemediniz.")
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
    st.markdown("Seçtiğiniz varlık ve zaman diliminde bot stratejisinin geçmiş kârlılığını test edin.")

    mevcut_varliklar = sorted(aktif_ayarlar.get("varliklar", ["BTC-USD"]))
    test_edilecek = st.selectbox("Test Edilecek Varlık", mevcut_varliklar)

    if st.button("🚀 Backtest'i Başlat", type="primary"):
        with st.spinner("Geçmiş veriler taranıyor..."):
            df_test = veri_cek(test_edilecek, aralik=aktif_ayarlar["zaman_dilimi"])
            if df_test is not None and not df_test.empty:
                df_test_analiz = hesapla_teknikler(df_test)
                sonuclar = calistir_backtest(df_test_analiz)

                st.divider()
                st.subheader(f"📊 {test_edilecek} Backtest Sonuçları")

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
                    st.warning("Bu periyotta işlem bulunamadı.")
            else:
                st.error("Veri çekilemedi.")

elif sayfa == "📈 Canlı Analiz & Sinyaller":
    st.title("📈 Sabit Varlık Sinyal Listesi, Çoklu Destek/Direnç ve Detaylı Teknik Yorum")
    mevcut_varliklar = sorted(aktif_ayarlar.get("varliklar", []))

    if not mevcut_varliklar:
        st.warning("Lütfen Varlık Havuzundan varlık seçin.")
    else:
        if "secilen_aktif_grafik" not in st.session_state or st.session_state["secilen_aktif_grafik"] not in mevcut_varliklar:
            st.session_state["secilen_aktif_grafik"] = mevcut_varliklar[0]

        st.subheader("📋 Sabit Liste Sinyalleri ve Teknik Rapor")

        telegram_toplu_mesaj = f"📊 *Sabit Liste Toplu Sinyal ve Teknik Rapor*\n\n"

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

        if st.button("📤 Tüm Sabit Listenin Analizini Telegram'a Gönder", type="primary", use_container_width=True):
            telegram_bildirim_gonder(telegram_toplu_mesaj)
            st.success("Analizler Telegram'a gönderildi!")

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
            st.error("Veri yüklenemedi.")
