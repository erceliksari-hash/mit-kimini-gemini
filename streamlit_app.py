from ai_engine import ai_akilli_karar_ver
import datetime
import json
import os
import re
import time
import urllib.request
import urllib.parse
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

# NOT: news_sentiment.py ve multi_timeframe.py projede opsiyonel eklentiler.
# Eskiden bunlar zorunlu import edildiği için dosyalar mevcut değilse
# (örn. Render'a deploy edilirken unutulduysa) uygulama HİÇ açılmıyordu.
# ai_memory.py ile aynı desene çekildi: eksikse özellik sadece o sekmede
# devre dışı kalır, uygulamanın geri kalanı çalışmaya devam eder.
try:
    from news_sentiment import varlik_haber_analizi, tum_varliklar_haber_raporu
    NEWS_SENTIMENT_AVAILABLE = True
except ImportError:
    NEWS_SENTIMENT_AVAILABLE = False
    def varlik_haber_analizi(*args, **kwargs): return None
    def tum_varliklar_haber_raporu(*args, **kwargs): return "📰 Haber modülü (news_sentiment.py) yüklenmedi."

try:
    from multi_timeframe import coklu_zaman_dilimi_analiz, coklu_tf_rapor
    MULTI_TIMEFRAME_AVAILABLE = True
except ImportError:
    MULTI_TIMEFRAME_AVAILABLE = False
    def coklu_zaman_dilimi_analiz(*args, **kwargs): return None
    def coklu_tf_rapor(*args, **kwargs): return "⏱️ Çoklu zaman dilimi modülü (multi_timeframe.py) yüklenmedi."

try:
    from ai_memory import hafiza_yukle, basari_istatistikleri, ogrenme_raporu_olustur, kararlari_degerlendir
except ImportError:
    # ai_memory.py eksikse boş fonksiyonlar
    def hafiza_yukle(): return {"kararlar": []}
    def basari_istatistikleri(): return {"toplam_karar": 0, "genel_basarisi": 0, "al_basarisi": 0, "sat_basarisi": 0, "bekle_basarisi": 0, "varlik_basarisi": {}}
    def ogrenme_raporu_olustur(): return "🧠 AI Hafıza modülü henüz yüklenmedi."
    def kararlari_degerlendir(): pass


# ═══════════════════════════════════════════════════════
# AYAR / VERİ YÖNETİMİ
# ═══════════════════════════════════════════════════════
#
# NOT: Bu bölüm daha önce ayrı bir trading_engine.py modülündeydi. Deploy'da
# o dosyanın unutulması "ModuleNotFoundError: No module named 'trading_engine'"
# hatasına yol açtığından, bağımlılığı ortadan kaldırmak için tekrar bu
# dosyanın içine alındı. Aynı fonksiyonların bir kopyası bot_servisi.py
# içinde de var — birini değiştirirseniz diğerini de güncelleyin.

def _json_yukle(dosya_yolu, varsayilan_uretici):
    if os.path.exists(dosya_yolu):
        try:
            with open(dosya_yolu, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return varsayilan_uretici()


def _json_kaydet(dosya_yolu, veri):
    with open(dosya_yolu, "w", encoding="utf-8") as f:
        json.dump(veri, f, indent=2, ensure_ascii=False)


def ayarlari_yukle():
    return _json_yukle(AYAR_DOSYASI, lambda: DEFAULT_SETTINGS.copy())


def ayarlari_kaydet(ayarlar):
    _json_kaydet(AYAR_DOSYASI, ayarlar)


def portfoy_yukle():
    return _json_yukle(PORTFOY_DOSYASI, dict)


def portfoy_kaydet(portfoy_verisi):
    _json_kaydet(PORTFOY_DOSYASI, portfoy_verisi)


def _varsayilan_cuzdan():
    return {
        "nakit": 10000.0,
        "baslangic_nakit": 10000.0,
        "pozisyonlar": {},
        "gecmis_islemler": []
    }


def sanal_cuzdan_yukle():
    ilk_kez = not os.path.exists(SANAL_CUZDAN_DOSYASI)
    cuzdan = _json_yukle(SANAL_CUZDAN_DOSYASI, _varsayilan_cuzdan)
    if ilk_kez:
        sanal_cuzdan_kaydet(cuzdan)
    return cuzdan


def sanal_cuzdan_kaydet(cuzdan_verisi):
    _json_kaydet(SANAL_CUZDAN_DOSYASI, cuzdan_verisi)


# ═══════════════════════════════════════════════════════
# TELEGRAM BİLDİRİM
# ═══════════════════════════════════════════════════════

_MD_OZEL_KARAKTERLER = re.compile(r'([_*\[\]`])')


def markdown_guvenli(metin):
    """Telegram Markdown mesajının kırılmaması için özel karakterleri kaçışlar."""
    if not metin:
        return ""
    return _MD_OZEL_KARAKTERLER.sub(r'\ ', str(metin))


def telegram_bildirim_gonder(mesaj):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        st.warning("Telegram token/chat_id ayarlanmamış.")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    max_len = 4000
    mesajlar = [mesaj[i:i + max_len] for i in range(0, len(mesaj), max_len)]
    basarili = True
    for m in mesajlar:
        try:
            requests.post(url, json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": m,
                "parse_mode": "Markdown",
            }, timeout=10)
        except Exception as e:
            st.error(f"Telegram hatası: {e}")
            basarili = False
    return basarili


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
# BACKTEST MOTORU
# ═══════════════════════════════════════════════════════

def calistir_backtest(df, baslangic_sermaye=10000):
    """Teknik sinyalleri kullanarak long-only backtest simülasyonu yapar."""
    bakiye = baslangic_sermaye
    pozisyon = 0
    giris_fiyati = 0.0
    giris_tarihi = None
    islemler = []

    if df is None or df.empty:
        return {"son_bakiye": bakiye, "toplam_islem": 0, "win_rate": 0, "net_kar_yuzde": 0, "islemler": []}

    for _, row in df.iterrows():
        sinyal = row.get("sinyal_tarihsel", 0)
        sahte = row.get("sahte_sinyal", False)

        if sinyal == 1 and not sahte and pozisyon == 0:
            pozisyon = 1
            giris_fiyati = float(row["close"])
            giris_tarihi = row["tarih"]

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
    net_kar_yuzde = ((bakiye - baslangic_sermaye) / baslangic_sermaye) * 100

    return {
        "son_bakiye": bakiye,
        "toplam_islem": toplam_islem,
        "win_rate": win_rate,
        "net_kar_yuzde": net_kar_yuzde,
        "islemler": islemler,
    }


st.set_page_config(page_title="Pro Finans Paneli", layout="wide")
st.markdown(
    """<style>.stApp { background-color: #0e1117; }</style>""",
    unsafe_allow_html=True,
)


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
        f"    • Fiyat: `{fiyat:.4f}` | Durum: `{p_sinyal}`\n"
        f"    • AI Kararı: `{ai_karar}`\n"
        f"    • RSI: `{rsi:.1f}` | MACD: `{macd}` | Trend: `{trend}`\n"
        f"    • Destekler: S1:`{s1:.4f}` S2:`{s2:.4f}` S3:`{s3:.4f}`\n"
        f"    • Dirençler: R1:`{r1:.4f}` R2:`{r2:.4f}` R3:`{r3:.4f}`\n"
        f"    • Strateji: SL:`{strateji['stop_loss']:.4f}` | TP:`{strateji['take_profit']:.4f}` | R/R:`{strateji['rr_orani']:.2f}`\n"
        f"    • AI Gerekçe: {markdown_guvenli(ai_aciklama[:200])}...\n"
        f"    • Sinyal Kalitesi: {sahte_yorum}\n\n"
    )
    return rapor_metni


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
        "📰 Haber & Sentiment",
        "📊 Çoklu Zaman Dilimi",
        "🧠 AI Hafıza & Öğrenme",
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

        # ─── TOPLU ANALİZ BUTONU ───
        st.subheader("📊 Toplu Varlık Analizi")
        if st.button("🔍 Tüm Varlıkları Analiz Et", type="primary", use_container_width=True):
            with st.spinner(f"{len(varliklar)} varlık analiz ediliyor..."):
                toplu_rapor = "📊 *TOPLU VARLIK ANALİZİ*\n"
                toplu_rapor += f"📅 `{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}`\n\n"

                for v in varliklar:
                    try:
                        df_v = veri_cek(v, aralik=zaman_dilimi)
                        if df_v is None or df_v.empty:
                            toplu_rapor += f"⚠️ `{v}`: Veri alınamadı\n\n"
                            continue

                        df_v_a = hesapla_teknikler(df_v)
                        p_v = donusum_noktalari_hesapla(df_v_a)
                        p_v_s = sinyal_kontrol(df_v_a)

                        son_v = df_v_a.iloc[-1]
                        rsi_v = son_v.get("rsi", 50)
                        macd_v = son_v.get("macd_durumu", "NÖTR")
                        ema20_v = son_v.get("ema_20", p_v["fiyat"])
                        ema50_v = son_v.get("ema_50", p_v["fiyat"])
                        trend_v = "YUKARI" if ema20_v > ema50_v else "AŞAĞI" if ema20_v < ema50_v else "YATAY"

                        ai_k_v, _ = ai_akilli_karar_ver(
                            varlik=v, fiyat=p_v["fiyat"],
                            d1=p_v["destek"], r1=p_v["direnc"],
                            p_sinyal=p_v_s, rsi=rsi_v,
                            macd_durumu=macd_v, trend=trend_v
                        )

                        trend_emoji = "📈" if trend_v == "YUKARI" else "📉" if trend_v == "AŞAĞI" else "⚖️"
                        toplu_rapor += (
                            f"🔹 *{v}* {trend_emoji}\n"
                            f"    Fiyat: `{p_v['fiyat']:.4f}` | AI: `{ai_k_v}` | Sinyal: `{p_v_s}`\n"
                            f"    RSI: `{rsi_v:.1f}` | MACD: `{macd_v}` | Trend: `{trend_v}`\n"
                            f"    S: `{p_v['s1']:.2f}` | R: `{p_v['r1']:.2f}`\n\n"
                        )
                    except Exception as e:
                        toplu_rapor += f"❌ `{v}`: Hata - {str(e)[:50]}\n\n"

                st.success("Analiz tamamlandı!")
                st.markdown(toplu_rapor.replace("\n", "  \n"))

                if st.button("📱 Telegram'a Gönder", key="toplu_tg"):
                    telegram_bildirim_gonder(toplu_rapor)
                    st.success("Telegram'a gönderildi!")

        st.divider()

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

                # Grafik çizimi
                st.subheader("📉 Fiyat ve İndikatör Grafiği")
                fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_heights=[0.7, 0.3])
                fig.add_trace(go.Candlestick(
                    x=df_analiz["tarih"],
                    open=df_analiz["open"],
                    high=df_analiz["high"],
                    low=df_analiz["low"],
                    close=df_analiz["close"],
                    name="Fiyat"
                ), row=1, col=1)

                if "ema_20" in df_analiz.columns:
                    fig.add_trace(go.Scatter(x=df_analiz["tarih"], y=df_analiz["ema_20"], line=dict(color="orange", width=1.5), name="EMA 20"), row=1, col=1)
                if "ema_50" in df_analiz.columns:
                    fig.add_trace(go.Scatter(x=df_analiz["tarih"], y=df_analiz["ema_50"], line=dict(color="blue", width=1.5), name="EMA 50"), row=1, col=1)

                fig.add_trace(go.Scatter(x=df_analiz["tarih"], y=df_analiz["rsi"], line=dict(color="purple", width=1.5), name="RSI"), row=2, col=1)
                fig.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1)
                fig.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1)

                fig.update_layout(height=600, xaxis_rangeslider_visible=False, template="plotly_dark", margin=dict(l=10, r=10, t=30, b=10))
                st.plotly_chart(fig, use_container_width=True)


# ─── SAYFA 3: HABER & SENTIMENT ───
elif sayfa == "📰 Haber & Sentiment":
    st.title("📰 Haber Analizi ve Piyasa Duygu Durumu")
    if not NEWS_SENTIMENT_AVAILABLE:
        st.warning("⚠️ `news_sentiment.py` modülü yüklü değil. Bu sekme şu an devre dışıdır.")
    else:
        varliklar = aktif_ayarlar.get("varliklar", [])
        if not varliklar:
            st.warning("Varlık havuzunda varlık bulunmuyor.")
        else:
            sec_v = st.selectbox("Haber Analizi Yapılacak Varlık", varliklar, key="haber_v")
            if st.button("📰 Haber Analizini Başlat", type="primary"):
                with st.spinner("Haberler taranıyor ve duygu analizi yapılıyor..."):
                    rapor = varlik_haber_analizi(sec_v)
                st.markdown(rapor)


# ─── SAYFA 4: ÇOKLU ZAMAN DİLİMİ ───
elif sayfa == "📊 Çoklu Zaman Dilimi":
    st.title("📊 Çoklu Zaman Dilimi Analizi")
    if not MULTI_TIMEFRAME_AVAILABLE:
        st.warning("⚠️ `multi_timeframe.py` modülü yüklü değil. Bu sekme şu an devre dışıdır.")
    else:
        varliklar = aktif_ayarlar.get("varliklar", [])
        if not varliklar:
            st.warning("Varlık havuzunda varlık bulunmuyor.")
        else:
            sec_v = st.selectbox("Çoklu Zaman Dilimi İçin Varlık", varliklar, key="mtf_v")
            if st.button("⏱️ Çoklu TF Analizi Çalıştır", type="primary"):
                with st.spinner("Farklı zaman dilimleri analiz ediliyor..."):
                    rapor = coklu_tf_rapor(sec_v)
                st.markdown(rapor)


# ─── SAYFA 5: AI HAFIZA & ÖĞRENME ───
elif sayfa == "🧠 AI Hafıza & Öğrenme":
    st.title("🧠 AI Karar Hafızası ve Öğrenme İstatistikleri")
    st.markdown(ogrenme_raporu_olustur())

    istatistik = basari_istatistikleri()
    if istatistik.get("toplam_karar", 0) > 0:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Toplam Karar", istatistik["toplam_karar"])
        c2.metric("Genel Başarı", f"%{istatistik['genel_basarisi']:.1f}")
        c3.metric("AL Başarısı", f"%{istatistik['al_basarisi']:.1f}")
        c4.metric("SAT Başarısı", f"%{istatistik['sat_basarisi']:.1f}")
    else:
        st.info("Henüz değerlendirilmiş geçmiş AI kararı bulunmuyor.")


# ─── SAYFA 6: OTONOM SANAL CÜZDAN ───
elif sayfa == "🤖 Otonom Sanal Cüzdan":
    st.title("🤖 Otonom Sanal Cüzdan ve İşlem Takibi")
    cuzdan = sanal_cuzdan_yukle()

    col1, col2, col3 = st.columns(3)
    col1.metric("Mevcut Nakit", f"{cuzdan['nakit']:.2f} $")
    toplam_poz_deger = sum(p["adet"] * p["maliyet"] for p in cuzdan["pozisyonlar"].values())
    col2.metric("Pozisyonlardaki Tutar", f"{toplam_poz_deger:.2f} $")
    toplam_servet = cuzdan["nakit"] + toplam_poz_deger
    kar_zarar_genel = toplam_servet - cuzdan["baslangic_nakit"]
    col3.metric("Toplam Varlık", f"{toplam_servet:.2f} $", f"{kar_zarar_genel:+.2f} $")

    st.subheader("⚡ Otonom Motor Kontrolü")
    if st.button("🚀 Otonom Döngüyü Şimdi Çalıştır", type="primary"):
        with st.spinner("Piyasa taranıyor ve işlemler güncelleniyor..."):
            rapor, guncel_cuzdan = otonom_islem_calistir()
        if rapor:
            st.success("Otonom döngü tamamlandı!")
            st.markdown(rapor)
        else:
            st.info("Otonom döngü çalıştı ancak yeni işlem veya kapatma gerçekleşmedi.")

    st.subheader("📂 Açık Pozisyonlar")
    if not cuzdan["pozisyonlar"]:
        st.info("Açık pozisyon bulunmuyor.")
    else:
        poz_liste = []
        for v, p in cuzdan["pozisyonlar"].items():
            poz_liste.append({
                "Varlık": v,
                "Adet": f"{p['adet']:.4f}",
                "Maliyet": f"{p['maliyet']:.4f}",
                "Stop-Loss": f"{p['stop_loss']:.4f}",
                "Take-Profit": f"{p['take_profit']:.4f}",
                "Tarih": p["tarih"]
            })
        st.dataframe(pd.DataFrame(poz_liste), use_container_width=True)

    st.subheader("📜 Geçmiş İşlemler")
    if not cuzdan["gecmis_islemler"]:
        st.info("Geçmiş işlem bulunmuyor.")
    else:
        st.dataframe(pd.DataFrame(cuzdan["gecmis_islemler"]), use_container_width=True)


# ─── SAYFA 7: PORTFÖY YÖNETİMİ ───
elif sayfa == "💼 Portföy Yönetimi":
    st.title("💼 Portföy ve Varlık Dağılımı")
    st.info("Portföy yönetim ekranı üzerinden manuel ekleme/çıkarma yapabilirsiniz.")
    portfoy = portfoy_yukle()
    if not portfoy:
        st.info("Kayıtlı portföy kalemi bulunmuyor.")
    else:
        st.json(portfoy)


# ─── SAYFA 8: GERİYE DÖNÜK TEST ───
elif sayfa == "⏳ Geriye Dönük Test":
    st.title("⏳ Backtest (Geriye Dönük Test) Simülasyonu")
    varliklar = aktif_ayarlar.get("varliklar", [])
    if not varliklar:
        st.warning("Varlık havuzunda varlık yok.")
    else:
        bt_varlik = st.selectbox("Backtest Varlığı", varliklar, key="bt_v")
        bt_sermaye = st.number_input("Başlangıç Sermayesi ($)", value=10000, step=1000)

        if st.button("📊 Backtest Çalıştır", type="primary"):
            with st.spinner(f"{bt_varlik} için geçmiş veriler alınıp test ediliyor..."):
                df_bt = veri_cek(bt_varlik, aralik="1d")
                if df_bt is not None and not df_bt.empty:
                    df_bt_a = hesapla_teknikler(df_bt)
                    sonuc = calistir_backtest(df_bt_a, baslangic_sermaye=bt_sermaye)

                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("Son Bakiye", f"{sonuc['son_bakiye']:.2f} $")
                    c2.metric("Net Kâr / Zarar", f"%{sonuc['net_kar_yuzde']:.2f}")
                    c3.metric("Toplam İşlem", sonuc['toplam_islem'])
                    c4.metric("Kazanma Oranı (Win Rate)", f"%{sonuc['win_rate']:.1f}")

                    if sonuc["islemler"]:
                        st.subheader("📋 İşlem Detayları")
                        st.dataframe(pd.DataFrame(sonuc["islemler"]), use_container_width=True)
                    else:
                        st.info("Bu dönemde hiç işlem sinyali üretilmedi.")
                else:
                    st.error("Veri alınamadığı için backtest çalıştırılamadı.")


# ─── SAYFA 9: BOT AYARLARI ───
elif sayfa == "⚙️ Bot Ayarları":
    st.title("⚙️ Bot ve Risk Yönetimi Ayarları")

    zaman_dilimi = st.selectbox("Ana Zaman Dilimi", ["1m", "5m", "15m", "30m", "1h", "4h", "1d"], index=["1m", "5m", "15m", "30m", "1h", "4h", "1d"].index(aktif_ayarlar.get("zaman_dilimi", "1d")))

    risk = aktif_ayarlar.get("risk_ayarlari", DEFAULT_SETTINGS["risk_ayarlari"])
    sl_yuzde = st.number_input("Stop-Loss (%)", value=float(risk.get("sl_yuzde", 1.5)), step=0.1)
    tp_yuzde = st.number_input("Take-Profit (%)", value=float(risk.get("tp_yuzde", 3.0)), step=0.1)
    risk_orani = st.number_input("İşlem Başına Risk Oranı (Örn: 0.25 = %25)", value=float(risk.get("risk_orani", 0.25)), step=0.05)
    max_pozisyon = st.number_input("Maksimum Eş Zamanlı Pozisyon", value=int(risk.get("max_pozisyon", 4)), step=1)

    if st.button("💾 Ayarları Kaydet", type="primary"):
        aktif_ayarlar["zaman_dilimi"] = zaman_dilimi
        aktif_ayarlar["risk_ayarlari"] = {
            "sl_yuzde": sl_yuzde,
            "tp_yuzde": tp_yuzde,
            "risk_orani": risk_orani,
            "max_pozisyon": max_pozisyon
        }
        ayarlari_kaydet(aktif_ayarlar)
        st.success("Ayarlar başarıyla kaydedildi!")
        time.sleep(1)
        st.rerun()
