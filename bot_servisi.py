#!/usr/bin/env python3
"""
Otonom Akıllı Ticaret Botu - Render + GitHub Actions Uyumlu
- Teknik analiz + AI karar motoru
- Otonom sanal cüzdan yönetimi (SL/TP)
- Telegram raporlama
- Render free plan uyku modu desteği
"""

import os
import sys
import json
import time
import urllib.request
import urllib.parse
from datetime import datetime

import pandas as pd

from config import (
    TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, GEMINI_API_KEY,
    AYAR_DOSYASI, SANAL_CUZDAN_DOSYASI, DEFAULT_SETTINGS
)
from data_sources import veri_cek
from indicators import hesapla_teknikler, sinyal_kontrol, piyasa_analizi_yap
from ai_engine import ai_akilli_karar_ver
from utils import donusum_noktalari_hesapla, strateji_hesapla


# ═══════════════════════════════════════════════════════
# RENDER ORTAM KONTROLÜ
# ═══════════════════════════════════════════════════════

IS_RENDER = os.environ.get("RENDER", "false").lower() == "true"
IS_GITHUB_ACTIONS = os.environ.get("GITHUB_ACTIONS", "false").lower() == "true"


def log(mesaj):
    """Ortama göre log yazdırır."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {mesaj}", flush=True)


# ═══════════════════════════════════════════════════════
# TELEGRAM BİLDİRİM
# ═══════════════════════════════════════════════════════

def telegram_bildir(mesaj):
    """Telegram üzerinden Markdown formatlı mesaj gönderir."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        log("[UYARI] Telegram token/chat_id eksik.")
        return False

    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        max_len = 4000
        mesajlar = [mesaj[i:i+max_len] for i in range(0, len(mesaj), max_len)]

        for m in mesajlar:
            data = urllib.parse.urlencode({
                "chat_id": TELEGRAM_CHAT_ID,
                "text": m,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True
            }).encode("utf-8")

            req = urllib.request.Request(url, data=data, method="POST")
            with urllib.request.urlopen(req, timeout=15) as response:
                pass

        return True

    except Exception as e:
        log(f"[TELEGRAM HATASI] {e}")
        return False


# ═══════════════════════════════════════════════════════
# AYAR / CÜZDAN YÖNETİMİ
# ═══════════════════════════════════════════════════════

def ayarlari_yukle():
    """ayarlar.json'dan ayarları okur."""
    if os.path.exists(AYAR_DOSYASI):
        try:
            with open(AYAR_DOSYASI, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            log(f"[AYAR HATASI] {e}")
    return DEFAULT_SETTINGS.copy()


def ayarlari_kaydet(ayarlar):
    """ayarlar.json'a ayarları yazar."""
    with open(AYAR_DOSYASI, "w", encoding="utf-8") as f:
        json.dump(ayarlar, f, indent=2, ensure_ascii=False)


def sanal_cuzdan_yukle():
    """Sanal cüzdanı yükler."""
    if os.path.exists(SANAL_CUZDAN_DOSYASI):
        try:
            with open(SANAL_CUZDAN_DOSYASI, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            log(f"[CÜZDAN HATASI] {e}")

    varsayilan = {
        "nakit": 10000.0,
        "baslangic_nakit": 10000.0,
        "pozisyonlar": {},
        "gecmis_islemler": []
    }
    sanal_cuzdan_kaydet(varsayilan)
    return varsayilan


def sanal_cuzdan_kaydet(cuzdan):
    """Sanal cüzdanı kaydeder."""
    with open(SANAL_CUZDAN_DOSYASI, "w", encoding="utf-8") as f:
        json.dump(cuzdan, f, indent=2, ensure_ascii=False)


# ═══════════════════════════════════════════════════════
# OTONOM İŞLEM MOTORU
# ═══════════════════════════════════════════════════════

def otonom_islem_calistir(ayarlar=None, cuzdan=None):
    """Otonom al-sat motorunu çalıştırır."""
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
            islem_raporu += f"{emoji} **[KAPATMA - {kapatma_nedeni}]** `{varlik}`\n"
            islem_raporu += f"   Fiyat: `{guncel_fiyat:.4f}` | K/Z: `{kar_zarar:+.2f}$`\n\n"

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
                strateji = strateji_hesapla(guncel_fiyat, p_analiz["destek"], p_analiz["direnc"], sl_yuzde, tp_yuzde)

                cuzdan["nakit"] -= harcanacak_nakit
                cuzdan["pozisyonlar"][varlik] = {
                    "adet": adet, "maliyet": guncel_fiyat,
                    "stop_loss": strateji["stop_loss"],
                    "take_profit": strateji["take_profit"],
                    "tarih": tarih_str, "rr_orani": strateji["rr_orani"]
                }

                islem_raporu += f"🟢 **[AL - AI ONAYLI]** `{varlik}`\n"
                islem_raporu += f"   Fiyat: `{guncel_fiyat:.4f}` | Lot: `{adet:.6f}`\n"
                islem_raporu += f"   SL: `{strateji['stop_loss']:.4f}` | TP: `{strateji['take_profit']:.4f}`\n\n"

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
# RAPOR OLUŞTURMA
# ═══════════════════════════════════════════════════════

def detayli_analiz_raporu(varlik, df_analiz, p_analiz, p_sinyal, ai_karar, ai_aciklama):
    """Tek varlık için detaylı analiz metni."""
    fiyat = p_analiz["fiyat"]
    son = df_analiz.iloc[-1]
    rsi = son.get("rsi", 50)
    macd = son.get("macd_durumu", "NÖTR")
    ema20 = son.get("ema_20", fiyat)
    ema50 = son.get("ema_50", fiyat)
    trend = "YUKARI 📈" if ema20 > ema50 else "AŞAĞI 📉" if ema20 < ema50 else "YATAY ⚖️"

    return (
        f"🔹 *{varlik}*\n"
        f"   💰 Fiyat: `{fiyat:.4f}` | Trend: {trend}\n"
        f"   📊 Sinyal: `{p_sinyal}`\n"
        f"   🤖 AI: `{ai_karar}`\n"
        f"   📈 RSI: `{rsi:.1f}` | MACD: `{macd}`\n"
        f"   🛡️ S: `{p_analiz['s1']:.4f}` `{p_analiz['s2']:.4f}` `{p_analiz['s3']:.4f}`\n"
        f"   🎯 R: `{p_analiz['r1']:.4f}` `{p_analiz['r2']:.4f}` `{p_analiz['r3']:.4f}`\n\n"
    )


def piyasa_turu_raporu():
    """Tüm varlıklar için piyasa turu raporu oluşturur ve Telegram'a gönderir."""
    ayarlar = ayarlari_yukle()
    varliklar = ayarlar.get("varliklar", [])
    zaman_dilimi = ayarlar.get("zaman_dilimi", "1d")

    if not varliklar:
        log("[UYARI] Takip listesi boş.")
        return

    zaman_damgasi = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    otonom_rapor, cuzdan = otonom_islem_calistir(ayarlar)

    # Cüzdan özetini hesapla
    toplam_poz_deger = 0
    for v_kod, poz in cuzdan["pozisyonlar"].items():
        df_c = veri_cek(v_kod, aralik=zaman_dilimi)
        if df_c is not None and not df_c.empty:
            toplam_poz_deger += poz["adet"] * float(df_c["close"].iloc[-1])

    toplam_servet = cuzdan["nakit"] + toplam_poz_deger
    baslangic = cuzdan["baslangic_nakit"]
    net_kz = toplam_servet - baslangic
    net_kz_yuzde = (net_kz / baslangic) * 100 if baslangic > 0 else 0

    rapor = (
        f"📊 *OTONOM PİYASA TURU*\n"
        f"📅 `{zaman_damgasi}` | Periyot: `{zaman_dilimi}`\n"
        f"💼 Servet: `{toplam_servet:.2f}$` | K/Z: `{net_kz:+.2f}$` (%{net_kz_yuzde:+.2f})\n"
        f"💵 Nakit: `{cuzdan['nakit']:.2f}$` | Poz: `{toplam_poz_deger:.2f}$`\n"
        f"📈 Açık: `{len(cuzdan['pozisyonlar'])}`\n"
        f"{'─' * 25}\n\n"
    )

    if otonom_rapor:
        rapor += f"🤖 *İŞLEMLER:*\n{otonom_rapor}"
        rapor += f"{'─' * 25}\n\n"

    rapor += "📈 *ANALİZ:*\n\n"

    for varlik in varliklar:
        df = veri_cek(varlik, aralik=zaman_dilimi)
        if df is None or df.empty:
            rapor += f"⚠️ `{varlik}`: Veri yok\n\n"
            continue

        df_analiz = hesapla_teknikler(df)
        p_analiz = donusum_noktalari_hesapla(df_analiz)
        p_sinyal = sinyal_kontrol(df_analiz)

        analiz = piyasa_analizi_yap(df_analiz)
        ai_karar, ai_aciklama = ai_akilli_karar_ver(
            varlik=varlik, fiyat=p_analiz["fiyat"],
            d1=p_analiz["destek"], r1=p_analiz["direnc"],
            p_sinyal=p_sinyal, rsi=analiz.get("rsi", 50),
            macd_durumu=analiz.get("macd_durumu", "NÖTR"),
            trend=analiz.get("trend", "YATAY")
        )

        rapor += detayli_analiz_raporu(varlik, df_analiz, p_analiz, p_sinyal, ai_karar, ai_aciklama)

    basarili = telegram_bildir(rapor)
    log(f"[RAPOR] Telegram gönderim: {'BAŞARILI' if basarili else 'BAŞARISIZ'}")
    log(f"[RAPOR] {len(varliklar)} varlık işlendi.")


# ═══════════════════════════════════════════════════════
# ANA ÇALIŞMA MODLARI
# ═══════════════════════════════════════════════════════

def tek_seferlik_mod():
    """GitHub Actions / Manuel tetikleme için."""
    log("🤖 Tek Seferlik Mod Başlatıldı...")
    piyasa_turu_raporu()
    log("✅ Tamamlandı.")


def surekli_mod(bekleme_dk=360):
    """Render Worker / Yerel sunucu için sürekli mod."""
    log(f"🤖 Sürekli Mod (Bekleme: {bekleme_dk} dk)")
    log("Durdurmak için Ctrl+C")

    while True:
        try:
            piyasa_turu_raporu()

            # Render free plan uyku modu kontrolü
            if IS_RENDER:
                log("[RENDER] Bir sonraki tarama için bekleniyor...")
                # Render'da 14 dakikada bir heartbeat gönder (uyku modunu önle)
                toplam_bekleme = bekleme_dk * 60
                kal_uyku = 0
                while kal_uyku < toplam_bekleme:
                    time.sleep(60)
                    kal_uyku += 60
                    log(f"[RENDER] Heartbeat... ({kal_uysu//60}/{bekleme_dk} dk)")
            else:
                log(f"⏳ Sonraki tarama: {bekleme_dk} dk sonra...")
                time.sleep(bekleme_dk * 60)

        except KeyboardInterrupt:
            log("🛑 Bot durduruldu.")
            break
        except Exception as e:
            log(f"[KRİTİK HATA] {e}")
            time.sleep(60)


def backtest_mod():
    """Tüm varlıklar için backtest çalıştırır."""
    log("📊 Backtest Modu Başlatıldı...")
    ayarlar = ayarlari_yukle()
    varliklar = ayarlar.get("varliklar", [])
    zaman_dilimi = ayarlar.get("zaman_dilimi", "1d")

    rapor = "📊 *BACKTEST RAPORU*\n\n"

    for varlik in varliklar:
        df = veri_cek(varlik, aralik=zaman_dilimi)
        if df is None or df.empty:
            continue

        df_analiz = hesapla_teknikler(df)
        # Backtest fonksiyonunu streamlit_app'ten al
        from streamlit_app import calistir_backtest
        sonuc = calistir_backtest(df_analiz)

        rapor += (
            f"🔹 *{varlik}*\n"
            f"   Bakiye: `{sonuc['son_bakiye']:.2f}$` | Kâr: `%{sonuc['net_kar_yuzde']:+.2f}`\n"
            f"   İşlem: `{sonuc['toplam_islem']}` | Win Rate: `%{sonuc['win_rate']:.1f}`\n\n"
        )

    telegram_bildir(rapor)
    log("✅ Backtest tamamlandı.")


if __name__ == "__main__":
    mode = "bot"
    bekleme = 360

    if len(sys.argv) > 1:
        if sys.argv[1] == "--surekli":
            mode = "surekli"
            bekleme = int(sys.argv[2]) if len(sys.argv) > 2 else 360
        elif sys.argv[1].startswith("--mode="):
            mode = sys.argv[1].split("=")[1]
        elif sys.argv[1] == "--backtest":
            mode = "backtest"

    if mode == "surekli":
        surekli_mod(bekleme)
    elif mode == "backtest":
        backtest_mod()
    elif mode == "rapor":
        piyasa_turu_raporu()
    else:
        tek_seferlik_mod()
