from ai_engine import ai_akilli_karar_ver
import datetime
import json
import os
import time
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
import streamlit as st

from config import (
    TELEGRAM_TOKEN, TELEGRAM_CHAT_ID,
    AYAR_DOSYASI, PORTFOY_DOSYASI, SANAL_CUZDAN_DOSYASI,
    DEFAULT_SETTINGS
)
from data_sources import veri_cek
from indicators import hesapla_teknikler, piyasa_analizi_yap, sinyal_kontrol
from utils import donusum_noktalari_hesapla, strateji_hesapla

st.set_page_config(page_title="Pro Finans Paneli", layout="wide")
st.markdown(
    """<style>.stApp { background-color: #0e1117; }</style>""",
    unsafe_allow_html=True,
)

# ═══════════════════════════════════════════════════════
# AYAR / VERİ YÖNETİMİ
# ═══════════════════════════════════════════════════════

def ayarlari_yukle():
    if not os.path.exists(AYAR_DOSYASI):
        with open(AYAR_DOSYASI, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_SETTINGS, f, indent=2, ensure_ascii=False)
        return DEFAULT_SETTINGS.copy()
    try:
        with open(AYAR_DOSYASI, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return DEFAULT_SETTINGS.copy()


def ayarlari_kaydet(ayarlar):
    with open(AYAR_DOSYASI, "w", encoding="utf-8") as f:
        json.dump(ayarlar, f, indent=2, ensure_ascii=False)


def portfoy_yukle():
    if not os.path.exists(PORTFOY_DOSYASI):
        return {}
    try:
        with open(PORTFOY_DOSYASI, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}


def portfoy_kaydet(portfoy_verisi):
    with open(PORTFOY_DOSYASI, "w", encoding="utf-8") as f:
        json.dump(portfoy_verisi, f, indent=2, ensure_ascii=False)


def sanal_cuzdan_yukle():
    if not os.path.exists(SANAL_CUZDAN_DOSYASI):
        varsayilan = {
            "nakit": 10000.0,
            "baslangic_nakit": 10000.0,
            "pozisyonlar": {},
            "gecmis_islemler": []
        }
        with open(SANAL_CUZDAN_DOSYASI, "w", encoding="utf-8") as f:
            json.dump(varsayilan, f, indent=2, ensure_ascii=False)
        return varsayilan
    try:
        with open(SANAL_CUZDAN_DOSYASI, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"nakit": 10000.0, "baslangic_nakit": 10000.0, "pozisyonlar": {}, "gecmis_islemler": []}


def sanal_cuzdan_kaydet(cuzdan_verisi):
    with open(SANAL_CUZDAN_DOSYASI, "w", encoding="utf-8") as f:
        json.dump(cuzdan_verisi, f, indent=2, ensure_ascii=False)


# ═══════════════════════════════════════════════════════
# İNTERNETTEN VARLIK ARAMA
# ═══════════════════════════════════════════════════════

def internette_varlik_ara(sorgu):
    try:
        url = f"https://query2.finance.yahoo.com/v1/finance/search?q={sorgu}"
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=10)
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
    except Exception as e:
        st.error(f"Arama hatası: {e}")
        return []


# ═══════════════════════════════════════════════════════
# OTONOM SANAL CÜZDAN MOTORU
# ═══════════════════════════════════════════════════════

def otonom_islem_calistir(ayarlar=None, cuzdan=None):
    """Bot servisiyle aynı mantıkta çalışan otonom motor."""
    if ayarlar is None:
        ayarlar = ayarlari_yukle()
    if cuzdan is None:
        cuzdan = sanal_cuzdan_yukle()

    varliklar = ayarlar.get("varliklar", [])
    zaman_dilimi = ayarlar.get("zaman_dilimi", "1d")
    risk = ayarlar.get("risk_ayarlari", DEFAULT_SETTINGS["risk_ayarlari"])

    sl_yuzde = risk.get("sl_yuzde", 1.5)
    tp_yuzde = risk.get("tp_yuzde", 3.0)
    risk_orani = risk.get("risk_orani", 0.25)
    max_pozisyon = risk.get("max_pozisyon", 4)

    islem_raporu = ""
    degisiklik_oldu = False

    # 1. Açık pozisyonları kontrol et
    acik_pozisyonlar = list(cuzdan["pozisyonlar"].keys())

    for varlik in acik_pozisyonlar:
        df = veri_cek(varlik, aralik=zaman_dilimi)
        if df is None or df.empty:
            continue

        guncel_fiyat = float(df["close"].iloc[-1])
        tarih_str = str(df["tarih"].iloc[-1])
        poz = cuzdan["pozisyonlar"][varlik]

        sl = poz["stop_loss"]
        tp = poz["take_profit"]

        df_analiz = hesapla_teknikler(df)
        p_analiz = donusum_noktalari_hesapla(df_analiz)
        p_sinyal = sinyal_kontrol(df_analiz)

        analiz = piyasa_analizi_yap(df_analiz)
        ai_karar, ai_aciklama = ai_akilli_karar_ver(
            varlik=varlik,
            fiyat=guncel_fiyat,
            d1=p_analiz["destek"],
            r1=p_analiz["direnc"],
            p_sinyal=p_sinyal,
            rsi=analiz.get("rsi", 50),
            macd_durumu=analiz.get("macd_durumu", "NÖTR"),
            trend=analiz.get("trend", "YATAY")
        )

        kapatma_nedeni = None
        if guncel_fiyat <= sl:
            kapatma_nedeni = f"STOP-LOSS (%{sl_yuzde})"
        elif guncel_fiyat >= tp:
            kapatma_nedeni = f"TAKE-PROFIT (%{tp_yuzde})"
        elif ai_karar == "SAT":
            kapatma_nedeni = "AI SAT SİNYALİ"

        if kapatma_nedeni:
            satis_degeri = poz["adet"] * guncel_fiyat
            maliyet_tutar = poz["adet"] * poz["maliyet"]
            kar_zarar = satis_degeri - maliyet_tutar
            cuzdan["nakit"] += satis_degeri

            emoji = "🟢" if kar_zarar >= 0 else "🔴"
            islem_raporu += f"{emoji} **[KAPATMA - {kapatma_nedeni}]** `{varlik}` | Fiyat: `{guncel_fiyat:.4f}` | K/Z: `{kar_zarar:+.2f}$`\n"

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

    # 2. Yeni alım fırsatları
    acik_sayisi = len(cuzdan["pozisyonlar"])

    for varlik in varliklar:
        if varlik in cuzdan["pozisyonlar"] or acik_sayisi >= max_pozisyon:
            continue

        df = veri_cek(varlik, aralik=zaman_dilimi)
        if df is None or df.empty:
            continue

        df_analiz = hesapla_teknikler(df)
        p_analiz = donusum_noktalari_hesapla(df_analiz)
        p_sinyal = sinyal_kontrol(df_analiz)
        guncel_fiyat = float(df_analiz["close"].iloc[-1])
        tarih_str = str(df_analiz["tarih"].iloc[-1])

        analiz = piyasa_analizi_yap(df_analiz)
        ai_karar, ai_aciklama = ai_akilli_karar_ver(
            varlik=varlik,
            fiyat=guncel_fiyat,
            d1=p_analiz["destek"],
            r1=p_analiz["direnc"],
            p_sinyal=p_sinyal,
            rsi=analiz.get("rsi", 50),
            macd_durumu=analiz.get("macd_durumu", "NÖTR"),
            trend=analiz.get("trend", "YATAY")
        )

        sahte_var = "SAHTE" in p_sinyal.upper() or "⚠️" in p_sinyal

        if ai_karar == "AL" and not sahte_var:
            harcanacak_nakit = cuzdan["nakit"] * risk_orani
            if harcanacak_nakit > 10 and cuzdan["nakit"] >= harcanacak_nakit:
                adet = harcanacak_nakit / guncel_fiyat
                strateji = strateji_hesapla(guncel_fiyat, p_analiz["destek"], p_analiz["direnc"], sl_yuzde, tp_yuzde)

                cuzdan["nakit"] -= harcanacak_nakit
                cuzdan["pozisyonlar"][varlik] = {
                    "adet": adet,
                    "maliyet": guncel_fiyat,
                    "stop_loss": strateji["stop_loss"],
                    "take_profit": strateji["take_profit"],
                    "tarih": tarih_str,
                    "rr_orani": strateji["rr_orani"]
                }

                islem_raporu += f"🟢 **[AL - AI ONAYLI]** `{varlik}` | Fiyat: `{guncel_fiyat:.4f}` | SL: `{strateji['stop_loss']:.4f}` | TP: `{strateji['take_profit']:.4f}`\n"
                cuzdan["gecmis_islemler"].append({
                    "islem": "AL",
                    "varlik": varlik,
                    "fiyat": guncel_fiyat,
                    "tarih": tarih_str,
                    "tutar": harcanacak_nakit,
                    "adet": adet
                })
                acik_sayisi += 1
                degisiklik_oldu = True

    if degisiklik_oldu:
        sanal_cuzdan_kaydet(cuzdan)

    return islem_raporu, cuzdan


# ═══════════════════════════════════════════════════════
# TELEGRAM BİLDİRİM
# ═══════════════════════════════════════════════════════

def telegram_bildirim_gonder(mesaj):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        st.warning("Telegram token/chat_id ayarlanmamış.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": mesaj,
        "parse_mode": "Markdown",
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        st.error(f"Telegram hatası: {e}")


# ═══════════════════════════════════════════════════════
# DETAYLI ANALİZ YORUMU
# ═══════════════════════════════════════════════════════

def detayli_analiz_ve_yorum_olustur(varlik, df_t_analiz, p_analiz, p_sinyal):
    fiyat = p_analiz["fiyat"]

    s1, s2, s3 = p_analiz["s1"], p_analiz["s2"], p_analiz["s3"]
    r1, r2, r3 = p_analiz["r1"], p_analiz["r2"], p_analiz["r3"]

    son = df_t_analiz.iloc[-1]
    rsi = son.get("rsi", 50)
    macd = son.get("macd_durumu", "NÖTR")
    ema20 = son.get("ema_20", fiyat)
    ema50 = son.get("ema_50", fiyat)
    trend = "YUKARI" if ema20 > ema50 else "AŞAĞI" if ema20 < ema50 else "YATAY"

    analiz = piyasa_analizi_yap(df_t_analiz)
    ai_karar, ai_aciklama = ai_akilli_karar_ver(
        varlik=varlik,
        fiyat=fiyat,
        d1=p_analiz["destek"],
        r1=p_analiz["direnc"],
        p_sinyal=p_sinyal,
        rsi=rsi,
        macd_durumu=macd,
        trend=trend
    )

    strateji = strateji_hesapla(fiyat, p_analiz["destek"], p_analiz["direnc"])

    sahte_yorum = "✅ Güvenilir" if "⚠️" not in p_sinyal else "⚠️ Sahte Sinyal Uyarısı!"

    rapor_metni = (
        f"🔹 *{varlik}*\n"
        f"   • Fiyat: `{fiyat:.4f}` | Durum: `{p_sinyal}`\n"
        f"   • AI Kararı: `{ai_karar}`\n"
        f"   • RSI: `{rsi:.1f}` | MACD: `{macd}` | Trend: `{trend}`\n"
        f"   • Destekler: S1:`{s1:.4f}` S2:`{s2:.4f}` S3:`{s3:.4f}`\n"
        f"   • Dirençler: R1:`{r1:.4f}` R2:`{r2:.4f}` R3:`{r3:.4f}`\n"
        f"   • Strateji: SL:`{strateji['stop_loss']:.4f}` | TP:`{strateji['take_profit']:.4f}` | R/R:`{strateji['rr_orani']:.2f}`\n"
        f"   • AI Gerekçe: {ai_aciklama[:200]}...\n"
        f"   • Sinyal Kalitesi: {sahte_yorum}\n\n"
    )
    return rapor_metni


# ═══════════════════════════════════════════════════════
# BACKTEST MOTORU
# ═══════════════════════════════════════════════════════

def calistir_backtest(df):
    """Gelişmiş backtest: Teknik sinyalleri kullanarak simülasyon yapar."""
    sermaye = 10000
    bakiye = sermaye
    pozisyon = 0
    giris_fiyati = 0
    islemler = []

    for index, row in df.iterrows():
        sinyal = row.get("sinyal_tarihsel", 0)
        sahte = row.get("sahte_sinyal", False)

        # AL: Sinyal AL ve sahte değil
        if sinyal == 1 and not sahte and pozisyon == 0:
            pozisyon = 1
            giris_fiyati = float(row["close"])
            giris_tarihi = row["tarih"]

        # SAT: Sinyal SAT ve sahte değil
        elif sinyal == -1 and not sahte and pozisyon == 1:
            pozisyon = 0
            cikis_fiyati = float(row["close"])
            cikis_tarihi = row["tarih"]

            oran = (cikis_fiyati - giris_fiyati) / giris_fiyati
            kar_zarar_tutari = bakiye * oran
            bakiye += kar_zarar_tutari

            durum = "✅ Başarılı" if kar_zarar_tutari > 0 else "❌ Başarısız"
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
    win_rate = (basarili_islem / toplam_islem * 100) if toplam_islem > 0 else 0
    net_kar_yuzde = ((bakiye - sermaye) / sermaye) * 100

    return {
        "son_bakiye": bakiye,
        "toplam_islem": toplam_islem,
        "win_rate": win_rate,
        "net_kar_yuzde": net_kar_yuzde,
        "islemler": islemler,
    }


# ═══════════════════════════════════════════════════════
# HAZIR VARLIK LİSTELERİ
# ═══════════════════════════════════════════════════════

HAZIR_VARLIKLAR = {
    "BIST 100 Kapsamlı Liste": {
        "AKBNK (Akbank)": "AKBNK.IS",
        "AGHOL (Anadolu Grubu)": "AGHOL.IS",
        "AHGAZ (Ahlatcı Doğalgaz)": "AHGAZ.IS",
        "AKCNS (Akçansa)": "AKCNS.IS",
        "AKFGY (Akfen GYO)": "AKFGY.IS",
        "AKSA (Aksa Akrilik)": "AKSA.IS",
        "AKSEN (Aksa Enerji)": "AKSEN.IS",
        "ALARK (Alarko)": "ALARK.IS",
        "ALBRK (Albaraka)": "ALBRK.IS",
        "ALFAS (Alfa Solar)": "ALFAS.IS",
        "ARCLK (Arçelik)": "ARCLK.IS",
        "ASELS (Aselsan)": "ASELS.IS",
        "ASTOR (Astor Enerji)": "ASTOR.IS",
        "BERA (Bera)": "BERA.IS",
        "BIMAS (Bim)": "BIMAS.IS",
        "BRYAT (Borusan)": "BRYAT.IS",
        "BUCIM (Bursa Çimento)": "BUCIM.IS",
        "CANTE (Çan2 Termik)": "CANTE.IS",
        "CCOLA (Coca-Cola)": "CCOLA.IS",
        "CEMTS (Çemtaş)": "CEMTS.IS",
        "CIMSA (Çimsa)": "CIMSA.IS",
        "CWENE (CW Enerji)": "CWENE.IS",
        "DOAS (Doğuş Otomotiv)": "DOAS.IS",
        "DOHOL (Doğan)": "DOHOL.IS",
        "ECILC (Eczacıbaşı)": "ECILC.IS",
        "EGEEN (Ege Endüstri)": "EGEEN.IS",
        "EKGYO (Emlak Konut)": "EKGYO.IS",
        "ENJSA (Enerjisa)": "ENJSA.IS",
        "ENKAI (Enka)": "ENKAI.IS",
        "EREGL (Ereğli)": "EREGL.IS",
        "EUPWR (Europen)": "EUPWR.IS",
        "FROTO (Ford Otosan)": "FROTO.IS",
        "GARAN (Garanti)": "GARAN.IS",
        "GESAN (Girişim Elektrik)": "GESAN.IS",
        "GLYHO (Global)": "GLYHO.IS",
        "GUBRF (Gübre)": "GUBRF.IS",
        "GWIND (Galata Wind)": "GWIND.IS",
        "HALKB (Halkbank)": "HALKB.IS",
        "HEKTS (Hektaş)": "HEKTS.IS",
        "IPEKE (İpek Enerji)": "IPEKE.IS",
        "ISCTR (İş Bankası)": "ISCTR.IS",
        "ISDMR (İskenderun)": "ISDMR.IS",
        "ISGYO (İş GYO)": "ISGYO.IS",
        "KCAER (Kocaer)": "KCAER.IS",
        "KCHOL (Koç)": "KCHOL.IS",
        "KMPUR (Kimteks)": "KMPUR.IS",
        "KONTR (Kontrolmatik)": "KONTR.IS",
        "KONYA (Konya Çimento)": "KONYA.IS",
        "KORDS (Kordsa)": "KORDS.IS",
        "KOZAA (Koza Anadolu)": "KOZAA.IS",
        "KOZAL (Koza Altın)": "KOZAL.IS",
        "KRDMD (Kardemir)": "KRDMD.IS",
        "KZBGY (Kızılbük)": "KZBGY.IS",
        "MAVI (Mavi)": "MAVI.IS",
        "MGROS (Migros)": "MGROS.IS",
        "ODAS (Odaş)": "ODAS.IS",
        "OYAKC (Oyak Çimento)": "OYAKC.IS",
        "PENTA (Penta)": "PENTA.IS",
        "PETKM (Petkim)": "PETKM.IS",
        "PGSUS (Pegasus)": "PGSUS.IS",
        "PSGYK (Pasifik GYO)": "PSGYK.IS",
        "QUAGR (Qua Granite)": "QUAGR.IS",
        "REEDR (Reeder)": "REEDR.IS",
        "SAHOL (Sabancı)": "SAHOL.IS",
        "SASA (Sasa)": "SASA.IS",
        "SELEC (Selçuk Ecza)": "SELEC.IS",
        "SISE (Şişecam)": "SISE.IS",
        "SKBNK (Şekerbank)": "SKBNK.IS",
        "SMRTG (Smart Güneş)": "SMRTG.IS",
        "SOKM (Şok)": "SOKM.IS",
        "TAVHL (TAV)": "TAVHL.IS",
        "TCELL (Turkcell)": "TCELL.IS",
        "THYAO (THY)": "THYAO.IS",
        "TOASO (Tofaş)": "TOASO.IS",
        "TSKB (TSKB)": "TSKB.IS",
        "TTKOM (Türk Telekom)": "TTKOM.IS",
        "TTRAK (Türk Traktör)": "TTRAK.IS",
        "TUPRS (Tüpraş)": "TUPRS.IS",
        "ULKER (Ülker)": "ULKER.IS",
        "VAKBN (VakıfBank)": "VAKBN.IS",
        "VESBE (Vestel Beyaz)": "VESBE.IS",
        "VESTL (Vestel)": "VESTL.IS",
        "YEOTK (YEO)": "YEOTK.IS",
        "YKBNK (Yapı Kredi)": "YKBNK.IS",
        "ZOREN (Zorlu Enerji)": "ZOREN.IS"
    },
    "Kripto (Popüler)": {
        "Bitcoin (BTC)": "BTC-USD",
        "Ethereum (ETH)": "ETH-USD",
        "Binance Coin (BNB)": "BNB-USD",
        "Solana (SOL)": "SOL-USD",
        "XRP (Ripple)": "XRP-USD",
        "Cardano (ADA)": "ADA-USD",
        "Avalanche (AVAX)": "AVAX-USD",
        "Dogecoin (DOGE)": "DOGE-USD",
        "Polkadot (DOT)": "DOT-USD",
        "Chainlink (LINK)": "LINK-USD",
        "Near (NEAR)": "NEAR-USD",
        "Uniswap (UNI)": "UNI-USD",
        "Bitcoin Cash (BCH)": "BCH-USD",
        "Litecoin (LTC)": "LTC-USD",
        "Aptos (APT)": "APT-USD",
        "Filecoin (FIL)": "FIL-USD",
        "Hedera (HBAR)": "HBAR-USD",
        "Shiba Inu (SHIB)": "SHIB-USD",
        "Cosmos (ATOM)": "ATOM-USD",
        "Injective (INJ)": "INJ-USD",
        "Render (RENDER)": "RENDER-USD",
        "Sui (SUI)": "SUI-USD",
        "Ethereum Classic (ETC)": "ETC-USD",
        "The Graph (GRT)": "GRT-USD",
        "Maker (MKR)": "MKR-USD",
        "Aave (AAVE)": "AAVE-USD",
        "Axie (AXS)": "AXS-USD",
        "The Sandbox (SAND)": "SAND-USD",
        "Decentraland (MANA)": "MANA-USD",
        "Gala (GALA)": "GALA-USD",
    },
    "Küresel Emtialar ve Forex": {
        "Altın (GC=F)": "GC=F",
        "Brent Petrol (BZ=F)": "BZ=F",
        "Ham Petrol (CL=F)": "CL=F",
        "Gümüş (SI=F)": "SI=F",
        "Platin (PL=F)": "PL=F",
        "Paladyum (PA=F)": "PA=F",
        "Doğalgaz (NG=F)": "NG=F",
        "Bakır (HG=F)": "HG=F",
        "EUR/USD": "EURUSD=X",
        "GBP/USD": "GBPUSD=X",
        "USD/JPY": "USDJPY=X",
        "USD/TRY": "USDTRY=X",
        "EUR/TRY": "EURTRY=X",
        "GBP/TRY": "GBPTRY=X",
    },
    "NASDAQ & S&P 500": {
        "Apple (AAPL)": "AAPL",
        "Microsoft (MSFT)": "MSFT",
        "NVIDIA (NVDA)": "NVDA",
        "Amazon (AMZN)": "AMZN",
        "Alphabet (GOOGL)": "GOOGL",
        "Meta (META)": "META",
        "Tesla (TSLA)": "TSLA",
        "Berkshire (BRK-B)": "BRK-B",
        "Broadcom (AVGO)": "AVGO",
        "Visa (V)": "V",
        "JPMorgan (JPM)": "JPM",
        "Walmart (WMT)": "WMT",
        "Netflix (NFLX)": "NFLX",
        "AMD (AMD)": "AMD",
        "Salesforce (CRM)": "CRM",
        "Adobe (ADBE)": "ADBE",
        "S&P 500 (SPY)": "SPY",
        "Nasdaq 100 (QQQ)": "QQQ",
    },
    "Avrupa Borsaları": {
        "SAP (SAP.DE)": "SAP.DE",
        "Siemens (SIE.DE)": "SIE.DE",
        "Allianz (ALV.DE)": "ALV.DE",
        "Airbus (AIR.PA)": "AIR.PA",
        "Deutsche Telekom (DTE.DE)": "DTE.DE",
        "Mercedes (MBG.DE)": "MBG.DE",
        "BMW (BMW.DE)": "BMW.DE",
        "Volkswagen (VOW3.DE)": "VOW3.DE",
        "BASF (BAS.DE)": "BAS.DE",
        "Infineon (IFX.DE)": "IFX.DE",
        "Adidas (ADS.DE)": "ADS.DE",
        "LVMH (MC.PA)": "MC.PA",
        "TotalEnergies (TTE.PA)": "TTE.PA",
        "ASML (ASML.AS)": "ASML.AS",
        "Nestle (NESN.SW)": "NESN.SW",
        "Roche (ROG.SW)": "ROG.SW",
        "Novartis (NOVN.SW)": "NOVN.SW",
    }
}


# ═══════════════════════════════════════════════════════
# STREAMLIT UI
# ═══════════════════════════════════════════════════════

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


# ─── SAYFA 1: VARLIK HAVUZU ───
if sayfa == "📚 Varlık Havuzu":
    st.title("📚 Varlık Havuzu ve Piyasalar")
    secilenler = set(aktif_ayarlar.get("varliklar", []))

    st.subheader("📋 Aktif Varlık Listesi")
    if not secilenler:
        st.info("Aktif listenizde hiç varlık bulunmuyor.")
    else:
        aktif_liste = sorted(list(secilenler))
        silinecekler = []
        cols = st.columns(4)
        for i, v_kod in enumerate(aktif_liste):
            with cols[i % 4]:
                if st.button(f"❌ {v_kod}", key=f"sil_{v_kod}", use_container_width=True):
                    silinecekler.append(v_kod)

        if silinecekler:
            for s in silinecekler:
                secilenler.discard(s)
            aktif_ayarlar["varliklar"] = sorted(list(secilenler))
            ayarlari_kaydet(aktif_ayarlar)
            st.success("Varlık(lar) listeden çıkarıldı!")
            time.sleep(0.5)
            st.rerun()

    st.divider()

    tab_bist, tab_kripto, tab_emtia, tab_abd, tab_avrupa, tab_ozel = st.tabs([
        "🇹🇷 BIST", "🪙 Kripto", "🛢️ Emtia & Forex", "📈 ABD", "🇪🇺 Avrupa", "⭐ Özel"
    ])

    kategoriler = list(HAZIR_VARLIKLAR.keys())

    with tab_bist:
        for isim, kod in HAZIR_VARLIKLAR[kategoriler[0]].items():
            if st.checkbox(isim, value=(kod in secilenler), key=f"hb_{kod}"):
                secilenler.add(kod)
            else:
                secilenler.discard(kod)

    with tab_kripto:
        for isim, kod in HAZIR_VARLIKLAR[kategoriler[1]].items():
            if st.checkbox(isim, value=(kod in secilenler), key=f"hk_{kod}"):
                secilenler.add(kod)
            else:
                secilenler.discard(kod)

    with tab_emtia:
        for isim, kod in HAZIR_VARLIKLAR[kategoriler[2]].items():
            if st.checkbox(isim, value=(kod in secilenler), key=f"he_{kod}"):
                secilenler.add(kod)
            else:
                secilenler.discard(kod)

    with tab_abd:
        for isim, kod in HAZIR_VARLIKLAR[kategoriler[3]].items():
            if st.checkbox(isim, value=(kod in secilenler), key=f"hn_{kod}"):
                secilenler.add(kod)
            else:
                secilenler.discard(kod)

    with tab_avrupa:
        for isim, kod in HAZIR_VARLIKLAR[kategoriler[4]].items():
            if st.checkbox(isim, value=(kod in secilenler), key=f"hav_{kod}"):
                secilenler.add(kod)
            else:
                secilenler.discard(kod)

    with tab_ozel:
        tum_hazir = {kod for kat in HAZIR_VARLIKLAR.values() for kod in kat.values()}
        ozel_kodlar = sorted([k for k in secilenler if k not in tum_hazir])
        if not ozel_kodlar:
            st.info("Özel varlık bulunmuyor.")
        else:
            for kod in ozel_kodlar:
                if st.checkbox(f"Özel: {kod}", value=True, key=f"oz_{kod}"):
                    secilenler.add(kod)
                else:
                    secilenler.discard(kod)

    st.divider()
    st.subheader("🔎 İnternetten Varlık Arama")
    arama = st.text_input("Arama Kelimesi veya Kısaltma", key="arama_input")

    if st.button("🔍 Ara"):
        if arama:
            with st.spinner("Aranıyor..."):
                st.session_state["arama_sonuclari"] = internette_varlik_ara(arama)

    if "arama_sonuclari" in st.session_state and st.session_state["arama_sonuclari"]:
        secenekler = {f"{item['symbol']} — {item['name']} ({item['exchange']})": item['symbol'] 
                      for item in st.session_state["arama_sonuclari"]}
        secilen_etiket = st.selectbox("Sonuçlar:", list(secenekler.keys()), key="secilen_arama")

        if st.button("➕ Listeye Ekle", type="primary"):
            secilenler.add(secenekler[secilen_etiket])
            aktif_ayarlar["varliklar"] = sorted(list(secilenler))
            ayarlari_kaydet(aktif_ayarlar)
            st.success(f"{secenekler[secilen_etiket]} eklendi!")
            st.session_state["arama_sonuclari"] = []
            time.sleep(0.5)
            st.rerun()

    st.divider()
    if st.button("💾 SEÇİMLERİ KAYDET", use_container_width=True, type="primary"):
        aktif_ayarlar["varliklar"] = sorted(list(secilenler))
        ayarlari_kaydet(aktif_ayarlar)
        st.success("Kaydedildi!")
        time.sleep(1)
        st.rerun()


# ─── SAYFA 2: CANLI ANALİZ ───
elif sayfa == "📈 Canlı Analiz & Sinyaller":
    st.title("📈 Canlı Teknik Analiz, Grafik ve AI Kararları")
    varliklar = aktif_ayarlar.get("varliklar", [])
    zaman_dilimi = aktif_ayarlar.get("zaman_dilimi", "1d")

    if not varliklar:
        st.warning("Varlık havuzunda hiç varlık yok. Önce 'Varlık Havuzu' sayfasından ekleyin.")
    else:
        secilen_varlik = st.selectbox("Analiz Edilecek Varlık", varliklar)

        if secilen_varlik:
            with st.spinner("Veri çekiliyor..."):
                df = veri_cek(secilen_varlik, aralik=zaman_dilimi)

            if df is not None and not df.empty:
                df_analiz = hesapla_teknikler(df)
                p_analiz = donusum_noktalari_hesapla(df_analiz)
                p_sinyal = sinyal_kontrol(df_analiz)

                fiyat = p_analiz["fiyat"]
                d1 = p_analiz["destek"]
                r1 = p_analiz["direnc"]

                son = df_analiz.iloc[-1]
                rsi = son.get("rsi", 50)
                macd = son.get("macd_durumu", "NÖTR")
                ema20 = son.get("ema_20", fiyat)
                ema50 = son.get("ema_50", fiyat)
                trend = "YUKARI" if ema20 > ema50 else "AŞAĞI" if ema20 < ema50 else "YATAY"

                ai_karar, ai_aciklama = ai_akilli_karar_ver(
                    varlik=secilen_varlik,
                    fiyat=fiyat,
                    d1=d1,
                    r1=r1,
                    p_sinyal=p_sinyal,
                    rsi=rsi,
                    macd_durumu=macd,
                    trend=trend
                )

                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Anlık Fiyat", f"{fiyat:.4f}")
                col2.metric("Teknik Sinyal", p_sinyal)
                col3.metric("AI Kararı", ai_karar)
                col4.metric("Destek / Direnç", f"S:{d1:.2f} | R:{r1:.2f}")

                st.info(f"🤖 **AI Gerekçesi:** {ai_aciklama}")

                # Pivot seviyeleri
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.caption("Destekler")
                    st.write(f"S1: `{p_analiz['s1']:.4f}`")
                    st.write(f"S2: `{p_analiz['s2']:.4f}`")
                    st.write(f"S3: `{p_analiz['s3']:.4f}`")
                with c2:
                    st.caption("Pivot")
                    st.write(f"`{p_analiz['pivot']:.4f}`")
                with c3:
                    st.caption("Dirençler")
                    st.write(f"R1: `{p_analiz['r1']:.4f}`")
                    st.write(f"R2: `{p_analiz['r2']:.4f}`")
                    st.write(f"R3: `{p_analiz['r3']:.4f}`")

                st.subheader("📊 Mum Grafik ve İndikatörler")
                fig = make_subplots(
                    rows=3, cols=1,
                    shared_xaxes=True,
                    vertical_spacing=0.05,
                    row_heights=[0.6, 0.2, 0.2],
                    subplot_titles=("Fiyat", "Hacim", "RSI")
                )

                # Mum grafiği
                fig.add_trace(go.Candlestick(
                    x=df_analiz['tarih'],
                    open=df_analiz['open'],
                    high=df_analiz['high'],
                    low=df_analiz['low'],
                    close=df_analiz['close'],
                    name="Fiyat"
                ), row=1, col=1)

                # EMA'lar
                if 'ema_20' in df_analiz.columns:
                    fig.add_trace(go.Scatter(
                        x=df_analiz['tarih'], y=df_analiz['ema_20'],
                        line=dict(color='orange', width=1.5), name="EMA 20"
                    ), row=1, col=1)
                if 'ema_50' in df_analiz.columns:
                    fig.add_trace(go.Scatter(
                        x=df_analiz['tarih'], y=df_analiz['ema_50'],
                        line=dict(color='blue', width=1.5), name="EMA 50"
                    ), row=1, col=1)

                # Bollinger
                if 'bollinger_ust' in df_analiz.columns:
                    fig.add_trace(go.Scatter(
                        x=df_analiz['tarih'], y=df_analiz['bollinger_ust'],
                        line=dict(color='gray', width=1, dash='dash'), name="BB Üst"
                    ), row=1, col=1)
                    fig.add_trace(go.Scatter(
                        x=df_analiz['tarih'], y=df_analiz['bollinger_alt'],
                        line=dict(color='gray', width=1, dash='dash'), name="BB Alt"
                    ), row=1, col=1)

                # Hacim
                if 'volume' in df_analiz.columns:
                    fig.add_trace(go.Bar(
                        x=df_analiz['tarih'], y=df_analiz['volume'],
                        marker_color='cyan', name="Hacim", opacity=0.5
                    ), row=2, col=1)

                # RSI
                if 'rsi' in df_analiz.columns:
                    fig.add_trace(go.Scatter(
                        x=df_analiz['tarih'], y=df_analiz['rsi'],
                        line=dict(color='purple', width=1.5), name="RSI"
                    ), row=3, col=1)
                    fig.add_hline(y=70, line_dash="dash", line_color="red", row=3, col=1)
                    fig.add_hline(y=30, line_dash="dash", line_color="green", row=3, col=1)
                    fig.add_hline(y=50, line_dash="dot", line_color="gray", row=3, col=1)

                fig.update_layout(
                    height=800,
                    template="plotly_dark",
                    margin=dict(l=10, r=10, t=50, b=10),
                    showlegend=True
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.error("Veri çekilemedi veya boş.")


# ─── SAYFA 3: OTONOM CÜZDAN ───
elif sayfa == "🤖 Otonom Sanal Cüzdan":
    st.title("🤖 Otonom Sanal Cüzdan")
    st.markdown("Bot; AI kararları + teknik analiz ile otomatik alım-satım yapar.")

    cuzdan_data = sanal_cuzdan_yukle()
    risk = aktif_ayarlar.get("risk_ayarlari", DEFAULT_SETTINGS["risk_ayarlari"])

    col_b1, col_b2, col_b3 = st.columns(3)

    toplam_pozisyon_degeri = 0
    for v_kod, poz in cuzdan_data["pozisyonlar"].items():
        df_c = veri_cek(v_kod, aralik=aktif_ayarlar.get("zaman_dilimi", "1d"))
        if df_c is not None and not df_c.empty:
            toplam_pozisyon_degeri += poz["adet"] * float(df_c["close"].iloc[-1])

    toplam_servet = cuzdan_data["nakit"] + toplam_pozisyon_degeri
    net_kazanc = toplam_servet - cuzdan_data["baslangic_nakit"]
    net_kazanc_yuzde = (net_kazanc / cuzdan_data["baslangic_nakit"]) * 100 if cuzdan_data["baslangic_nakit"] > 0 else 0

    col_b1.metric("Toplam Servet", f"{toplam_servet:.2f} $", f"%{net_kazanc_yuzde:+.2f}")
    col_b2.metric("Nakit", f"{cuzdan_data['nakit']:.2f} $")
    col_b3.metric("Pozisyon Değeri", f"{toplam_pozisyon_degeri:.2f} $")

    st.divider()
    col_i1, col_i2 = st.columns([2, 2])
    with col_i1:
        if st.button("🔄 Otonom Turu Çalıştır", type="primary", use_container_width=True):
            with st.spinner("Piyasa taranıyor..."):
                rapor, yeni_cuzdan = otonom_islem_calistir()
                if rapor:
                    st.success("İşlemler gerçekleştirildi!")
                    st.markdown(rapor.replace("\n", "  \n"))
                else:
                    st.info("Yeni işlem veya SL/TP tetiklenmedi.")
                time.sleep(1)
                st.rerun()
    with col_i2:
        if st.button("🗑️ Cüzdanı Sıfırla (10,000$)", use_container_width=True):
            sanal_cuzdan_kaydet({
                "nakit": 10000.0,
                "baslangic_nakit": 10000.0,
                "pozisyonlar": {},
                "gecmis_islemler": []
            })
            st.success("Cüzdan sıfırlandı.")
            time.sleep(1)
            st.rerun()

    st.subheader("📂 Açık Pozisyonlar")
    if not cuzdan_data["pozisyonlar"]:
        st.info("Açık pozisyon yok.")
    else:
        for v_kod, poz in cuzdan_data["pozisyonlar"].items():
            df_curr = veri_cek(v_kod, aralik=aktif_ayarlar.get("zaman_dilimi", "1d"))
            curr_fiyat = float(df_curr["close"].iloc[-1]) if df_curr is not None and not df_curr.empty else poz["maliyet"]
            deger = poz["adet"] * curr_fiyat
            maliyet_tutar = poz["adet"] * poz["maliyet"]
            kar_zarar = deger - maliyet_tutar
            kar_zarar_yuzde = ((curr_fiyat - poz["maliyet"]) / poz["maliyet"]) * 100 if poz["maliyet"] > 0 else 0

            c_renk = "green" if kar_zarar >= 0 else "red"

            st.markdown(f"**{v_kod}** | Alış: `{poz['tarih']}`")
            st.markdown(f"• Maliyet: `{poz['maliyet']:.4f}` | Anlık: `{curr_fiyat:.4f}` | Lot: `{poz['adet']:.6f}`")
            st.markdown(f"• SL: `{poz['stop_loss']:.4f}` | TP: `{poz['take_profit']:.4f}` | R/R: `{poz.get('rr_orani', 0):.2f}`")
            st.markdown(f"• Değer: `{deger:.2f}$` | K/Z: <span style='color:{c_renk};font-weight:bold;'>{kar_zarar:+.2f}$ (%{kar_zarar_yuzde:+.2f})</span>", unsafe_allow_html=True)
            st.divider()

    st.subheader("📜 İşlem Geçmişi")
    if not cuzdan_data["gecmis_islemler"]:
        st.info("Geçmiş işlem yok.")
    else:
        df_gecmis = pd.DataFrame(cuzdan_data["gecmis_islemler"])
        st.dataframe(df_gecmis, use_container_width=True)


# ─── SAYFA 4: PORTFÖY YÖNETİMİ ───
elif sayfa == "💼 Portföy Yönetimi":
    st.title("💼 Gerçek / Manuel Portföy Takibi")
    portfoy_data = portfoy_yukle()

    st.subheader("Portföye Varlık Ekle")
    p_varlik = st.text_input("Varlık Kodu (Örn: THYAO.IS, BTC-USD)")
    p_lot = st.number_input("Lot / Adet", min_value=0.0, value=1.0, step=0.01)
    p_maliyet = st.number_input("Ortalama Maliyet", min_value=0.0, value=100.0, step=0.1)

    if st.button("💾 Kaydet", type="primary"):
        if p_varlik:
            portfoy_data[p_varlik.upper()] = {"lot": p_lot, "maliyet": p_maliyet}
            portfoy_kaydet(portfoy_data)
            st.success(f"{p_varlik.upper()} kaydedildi!")
            time.sleep(1)
            st.rerun()

    st.divider()
    st.subheader("Mevcut Portföy")
    if not portfoy_data:
        st.info("Portföy boş.")
    else:
        p_liste = []
        for v_kod, detay in portfoy_data.items():
            df_p = veri_cek(v_kod, aralik=aktif_ayarlar.get("zaman_dilimi", "1d"))
            anlik_f = float(df_p["close"].iloc[-1]) if df_p is not None and not df_p.empty else detay["maliyet"]
            toplam_deger = detay["lot"] * anlik_f
            maliyet_deger = detay["lot"] * detay["maliyet"]
            kar_zarar = toplam_deger - maliyet_deger
            kar_zarar_oran = (kar_zarar / maliyet_deger * 100) if maliyet_deger > 0 else 0

            p_liste.append({
                "Varlık": v_kod,
                "Lot": detay["lot"],
                "Maliyet": detay["maliyet"],
                "Anlık": round(anlik_f, 2),
                "Değer": round(toplam_deger, 2),
                "K/Z ($)": round(kar_zarar, 2),
                "K/Z (%)": round(kar_zarar_oran, 2)
            })
        df_portfoy = pd.DataFrame(p_liste)
        st.dataframe(df_portfoy, use_container_width=True)

        sil = st.selectbox("Silinecek Varlık", ["Seçiniz"] + list(portfoy_data.keys()))
        if st.button("🗑️ Sil") and sil != "Seçiniz":
            if sil in portfoy_data:
                del portfoy_data[sil]
                portfoy_kaydet(portfoy_data)
                st.success(f"{sil} silindi!")
                time.sleep(1)
                st.rerun()


# ─── SAYFA 5: BACKTEST ───
elif sayfa == "⏳ Geriye Dönük Test":
    st.title("⏳ Backtest Motoru")
    varliklar = aktif_ayarlar.get("varliklar", [])
    zaman_dilimi = aktif_ayarlar.get("zaman_dilimi", "1d")

    if not varliklar:
        st.warning("Varlık havuzu boş.")
    else:
        bt_varlik = st.selectbox("Varlık", varliklar, key="bt_var")
        if st.button("🚀 Çalıştır", type="primary"):
            with st.spinner("Simülasyon yapılıyor..."):
                df_bt = veri_cek(bt_varlik, aralik=zaman_dilimi)
                if df_bt is not None and not df_bt.empty:
                    df_bt_analiz = hesapla_teknikler(df_bt)
                    sonuc = calistir_backtest(df_bt_analiz)

                    col_bt1, col_bt2, col_bt3, col_bt4 = st.columns(4)
                    col_bt1.metric("Son Bakiye", f"{sonuc['son_bakiye']:.2f} $")
                    col_bt2.metric("Net Kâr (%)", f"%{sonuc['net_kar_yuzde']:+.2f}")
                    col_bt3.metric("Toplam İşlem", sonuc['toplam_islem'])
                    col_bt4.metric("Win Rate", f"%{sonuc['win_rate']:.1f}")

                    st.subheader("📋 İşlem Geçmişi")
                    if sonuc["islemler"]:
                        st.dataframe(pd.DataFrame(sonuc["islemler"]), use_container_width=True)
                    else:
                        st.info("İşlem bulunamadı.")
                else:
                    st.error("Yeterli veri yok.")


# ─── SAYFA 6: BOT AYARLARI ───
elif sayfa == "⚙️ Bot Ayarları":
    st.title("⚙️ Bot ve Zaman Dilimi Ayarları")

    zaman_dilimleri = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]
    mevcut_zd = aktif_ayarlar.get("zaman_dilimi", "1d")
    secilen_zd = st.selectbox(
        "Zaman Dilimi",
        zaman_dilimleri,
        index=zaman_dilimleri.index(mevcut_zd) if mevcut_zd in zaman_dilimleri else 6
    )

    mevcut_siklik = aktif_ayarlar.get("bot_sikligi_dk", 360)
    secilen_siklik = st.number_input("Bildirim Sıklığı (dk)", min_value=1, value=int(mevcut_siklik), step=1)

    st.subheader("🎯 Risk Ayarları")
    risk = aktif_ayarlar.get("risk_ayarlari", DEFAULT_SETTINGS["risk_ayarlari"])

    col_r1, col_r2, col_r3, col_r4 = st.columns(4)
    with col_r1:
        sl_yuzde = st.number_input("Stop-Loss (%)", min_value=0.1, max_value=10.0, 
                                    value=float(risk.get("sl_yuzde", 1.5)), step=0.1)
    with col_r2:
        tp_yuzde = st.number_input("Take-Profit (%)", min_value=0.1, max_value=20.0,
                                    value=float(risk.get("tp_yuzde", 3.0)), step=0.1)
    with col_r3:
        risk_orani = st.number_input("Risk Oranı (nakit %)", min_value=0.05, max_value=1.0,
                                      value=float(risk.get("risk_orani", 0.25)), step=0.05)
    with col_r4:
        max_poz = st.number_input("Max Pozisyon", min_value=1, max_value=20,
                                   value=int(risk.get("max_pozisyon", 4)), step=1)

    st.divider()
    if st.button("💾 Ayarları Kaydet", type="primary", use_container_width=True):
        aktif_ayarlar["zaman_dilimi"] = secilen_zd
        aktif_ayarlar["bot_sikligi_dk"] = int(secilen_siklik)
        aktif_ayarlar["risk_ayarlari"] = {
            "sl_yuzde": float(sl_yuzde),
            "tp_yuzde": float(tp_yuzde),
            "risk_orani": float(risk_orani),
            "max_pozisyon": int(max_poz)
        }
        ayarlari_kaydet(aktif_ayarlar)
        st.success("Ayarlar güncellendi!")
        time.sleep(1)
        st.rerun()
