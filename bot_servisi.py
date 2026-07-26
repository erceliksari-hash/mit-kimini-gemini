#!/usr/bin/env python3
"""
Otonom Akıllı Ticaret Botu - Render + GitHub Actions Uyumlu
- Teknik analiz + AI karar motoru
- Otonom sanal cüzdan yönetimi (SL/TP)
- Telegram raporlama
- Render free plan uyku modu desteği

NOT: Ayar/cüzdan yönetimi, otonom motor, Telegram gönderimi ve backtest
artık trading_engine.py içinde; bu dosya sadece "hangi modda nasıl
çalıştırılır"ı yönetir. Böylece streamlit_app.py ile mantık ikilenmesi
(ve aralarında sessizce oluşan sürüklenme) ortadan kalkar.
"""

import sys
import time
from datetime import datetime

from data_sources import veri_cek
from indicators import hesapla_teknikler, sinyal_kontrol, piyasa_analizi_yap
from utils import donusum_noktalari_hesapla
from trading_engine import (
    log, IS_RENDER,
    ayarlari_yukle, sanal_cuzdan_yukle,
    otonom_islem_calistir, telegram_bildir, calistir_backtest,
)
from ai_engine import ai_akilli_karar_ver


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


def _render_bekleme(toplam_saniye, bekleme_dk):
    """
    Render free plan'ın uyku moduna geçmemesi için 60 sn'lik adımlarla bekler
    ve düzenli heartbeat loglar.

    NOT: Önceki sürümde burada `kal_uysu` (tanımsız değişken) kullanılıyordu;
    bu yüzden döngü her seferinde NameError ile patlıyordu ve dıştaki genel
    `except` bunu yakalayıp 60 sn sonra piyasa_turu_raporu()'nu HEMEN tekrar
    çağırıyordu. Sonuç: bot, ayarlanan 360 dakika yerine fiilen ~1 dakikada
    bir tarama yapıyordu (gereksiz API/Telegram trafiği). Aşağıda düzeltildi.
    """
    kalan = 0
    while kalan < toplam_saniye:
        time.sleep(60)
        kalan += 60
        log(f"[RENDER] Heartbeat... ({kalan // 60}/{bekleme_dk} dk)")


def surekli_mod(bekleme_dk=360):
    """Render Worker / Yerel sunucu için sürekli mod."""
    log(f"🤖 Sürekli Mod (Bekleme: {bekleme_dk} dk)")
    log("Durdurmak için Ctrl+C")

    while True:
        try:
            piyasa_turu_raporu()

            if IS_RENDER:
                log("[RENDER] Bir sonraki tarama için bekleniyor...")
                _render_bekleme(bekleme_dk * 60, bekleme_dk)
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
            rapor += f"⚠️ `{varlik}`: Veri yok\n\n"
            continue

        df_analiz = hesapla_teknikler(df)
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
