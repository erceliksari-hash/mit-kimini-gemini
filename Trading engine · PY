#!/usr/bin/env python3
"""
Ortak İşlem Motoru
-------------------
bot_servisi.py ve streamlit_app.py tarafından PAYLAŞILAN çekirdek mantık.

Neden bu dosya var?
Eskiden ayar/cüzdan yönetimi, otonom al-sat motoru, Telegram gönderimi ve
backtest fonksiyonları hem bot_servisi.py hem streamlit_app.py içinde
BİREBİR kopyalanmıştı. Bu, biri güncellenip diğeri unutulduğunda (nitekim
öyle olmuş: iki dosyadaki otonom_islem_calistir fonksiyonları birbirinden
küçük farklarla ayrışmıştı) sessiz hatalara yol açar. Tek doğruluk kaynağı
burada tutulur.
"""

import os
import json
import re
import urllib.request
import urllib.parse
from datetime import datetime

from config import (
    TELEGRAM_TOKEN, TELEGRAM_CHAT_ID,
    AYAR_DOSYASI, PORTFOY_DOSYASI, SANAL_CUZDAN_DOSYASI,
    DEFAULT_SETTINGS
)
from data_sources import veri_cek
from indicators import hesapla_teknikler, sinyal_kontrol, piyasa_analizi_yap
from ai_engine import ai_akilli_karar_ver
from utils import donusum_noktalari_hesapla, strateji_hesapla

IS_RENDER = os.environ.get("RENDER", "false").lower() == "true"
IS_GITHUB_ACTIONS = os.environ.get("GITHUB_ACTIONS", "false").lower() == "true"


def log(mesaj):
    """Zaman damgalı log satırı yazdırır (stdout flush edilir, Render/Actions loglarında kaybolmaz)."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {mesaj}", flush=True)


# ═══════════════════════════════════════════════════════
# DOSYA G/Ç YARDIMCILARI
# ═══════════════════════════════════════════════════════
#
# NOT: Önceki sürümlerde "except:" (çıplak except) kullanılıyordu; bu,
# KeyboardInterrupt / SystemExit dahil HER şeyi yutar ve hata sebebi asla
# loglanmazdı. Burada sadece beklenen hatalar (bozuk JSON, dosya izni vb.)
# yakalanır ve nedeni loglanır.

def _json_yukle(dosya_yolu, varsayilan_uretici):
    if os.path.exists(dosya_yolu):
        try:
            with open(dosya_yolu, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            log(f"[JSON OKUMA HATASI] {dosya_yolu}: {e}")
    return varsayilan_uretici()


def _json_kaydet(dosya_yolu, veri):
    try:
        with open(dosya_yolu, "w", encoding="utf-8") as f:
            json.dump(veri, f, indent=2, ensure_ascii=False)
        return True
    except OSError as e:
        log(f"[JSON YAZMA HATASI] {dosya_yolu}: {e}")
        return False


def ayarlari_yukle():
    return _json_yukle(AYAR_DOSYASI, lambda: DEFAULT_SETTINGS.copy())


def ayarlari_kaydet(ayarlar):
    return _json_kaydet(AYAR_DOSYASI, ayarlar)


def portfoy_yukle():
    return _json_yukle(PORTFOY_DOSYASI, dict)


def portfoy_kaydet(portfoy_verisi):
    return _json_kaydet(PORTFOY_DOSYASI, portfoy_verisi)


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
    return _json_kaydet(SANAL_CUZDAN_DOSYASI, cuzdan_verisi)


# ═══════════════════════════════════════════════════════
# TELEGRAM BİLDİRİM
# ═══════════════════════════════════════════════════════

# Telegram'ın (legacy) Markdown modu bu karakterleri özel kabul eder.
# AI'nin ürettiği serbest metin bunlardan içeriyorsa mesaj gönderimi
# tamamen başarısız olabiliyordu (400 Bad Request). Telegram'a giden
# serbest metinlerde bu fonksiyon kullanılmalı.
_MD_OZEL_KARAKTERLER = re.compile(r'([_*\[\]`])')


def markdown_guvenli(metin):
    """Telegram Markdown mesajının kırılmaması için özel karakterleri kaçışlar."""
    if not metin:
        return ""
    return _MD_OZEL_KARAKTERLER.sub(r'\\\1', str(metin))


def telegram_bildir(mesaj):
    """Telegram üzerinden Markdown formatlı mesaj gönderir (4000 karakter üstünü böler)."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        log("[UYARI] Telegram token/chat_id eksik.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    max_len = 4000
    mesajlar = [mesaj[i:i + max_len] for i in range(0, len(mesaj), max_len)]

    basarili = True
    for m in mesajlar:
        try:
            data = urllib.parse.urlencode({
                "chat_id": TELEGRAM_CHAT_ID,
                "text": m,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True
            }).encode("utf-8")
            req = urllib.request.Request(url, data=data, method="POST")
            with urllib.request.urlopen(req, timeout=15) as response:
                if response.status >= 300:
                    log(f"[TELEGRAM HATASI] HTTP {response.status}")
                    basarili = False
        except Exception as e:
            log(f"[TELEGRAM HATASI] {e}")
            basarili = False

    return basarili


# ═══════════════════════════════════════════════════════
# OTONOM İŞLEM MOTORU
# ═══════════════════════════════════════════════════════

def otonom_islem_calistir(ayarlar=None, cuzdan=None):
    """Otonom al-sat motorunu çalıştırır (açık pozisyonları kontrol eder + yeni fırsat arar)."""
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

    # 1. Açık pozisyonları kontrol et (SL / TP / AI SAT sinyali)
    acik_pozisyonlar = list(cuzdan["pozisyonlar"].keys())

    for varlik in acik_pozisyonlar:
        df = veri_cek(varlik, aralik=zaman_dilimi)
        if df is None or df.empty:
            log(f"[VERİ YOK] {varlik} için fiyat alınamadı, pozisyon kontrolü atlandı.")
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
            varlik=varlik, fiyat=guncel_fiyat,
            d1=p_analiz["destek"], r1=p_analiz["direnc"],
            p_sinyal=p_sinyal, rsi=analiz.get("rsi", 50),
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
            islem_raporu += (
                f"{emoji} **[KAPATMA - {kapatma_nedeni}]** `{varlik}`\n"
                f"   Fiyat: `{guncel_fiyat:.4f}` | K/Z: `{kar_zarar:+.2f}$`\n\n"
            )

            cuzdan["gecmis_islemler"].append({
                "islem": f"KAPAT ({kapatma_nedeni})",
                "varlik": varlik, "fiyat": guncel_fiyat,
                "tarih": tarih_str, "tutar": satis_degeri,
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
            varlik=varlik, fiyat=guncel_fiyat,
            d1=p_analiz["destek"], r1=p_analiz["direnc"],
            p_sinyal=p_sinyal, rsi=analiz.get("rsi", 50),
            macd_durumu=analiz.get("macd_durumu", "NÖTR"),
            trend=analiz.get("trend", "YATAY")
        )

        sahte_var = "SAHTE" in p_sinyal.upper() or "⚠️" in p_sinyal

        if ai_karar == "AL" and not sahte_var:
            harcanacak_nakit = cuzdan["nakit"] * risk_orani
            if harcanacak_nakit > 10 and cuzdan["nakit"] >= harcanacak_nakit:
                adet = harcanacak_nakit / guncel_fiyat
                strateji = strateji_hesapla(
                    guncel_fiyat, p_analiz["destek"], p_analiz["direnc"], sl_yuzde, tp_yuzde
                )

                cuzdan["nakit"] -= harcanacak_nakit
                cuzdan["pozisyonlar"][varlik] = {
                    "adet": adet, "maliyet": guncel_fiyat,
                    "stop_loss": strateji["stop_loss"],
                    "take_profit": strateji["take_profit"],
                    "tarih": tarih_str, "rr_orani": strateji["rr_orani"]
                }

                islem_raporu += (
                    f"🟢 **[AL - AI ONAYLI]** `{varlik}`\n"
                    f"   Fiyat: `{guncel_fiyat:.4f}` | Lot: `{adet:.6f}`\n"
                    f"   SL: `{strateji['stop_loss']:.4f}` | TP: `{strateji['take_profit']:.4f}`\n\n"
                )

                cuzdan["gecmis_islemler"].append({
                    "islem": "AL", "varlik": varlik,
                    "fiyat": guncel_fiyat, "tarih": tarih_str,
                    "tutar": harcanacak_nakit, "adet": adet
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
    """
    Teknik sinyalleri (indicators.hesapla_teknikler çıktısı) kullanarak
    basit, long-only bir backtest simülasyonu çalıştırır.
    """
    bakiye = baslangic_sermaye
    pozisyon = 0
    giris_fiyati = 0.0
    giris_tarihi = None
    islemler = []

    if df is None or df.empty:
        return {
            "son_bakiye": bakiye, "toplam_islem": 0,
            "win_rate": 0, "net_kar_yuzde": 0, "islemler": []
        }

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
