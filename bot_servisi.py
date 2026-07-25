
bot_servisi_py = '''#!/usr/bin/env python3
"""
Otonom Akıllı Ticaret Botu
- Teknik analiz + AI karar motoru
- Otonom sanal cüzdan yönetimi (SL/TP)
- Telegram raporlama
- Hem tek seferlik (GitHub Actions) hem sürekli mod desteği
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
# TELEGRAM BİLDİRİM
# ═══════════════════════════════════════════════════════

def telegram_bildir(mesaj):
    """Telegram üzerinden Markdown formatlı mesaj gönderir."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("[UYARI] Telegram token/chat_id eksik. Bildirim gönderilemedi.")
        return False
    
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        
        # Mesaj 4096 karakteri aşarsa böl
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
        print(f"[TELEGRAM HATASI] {e}")
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
            print(f"[AYAR HATASI] {e}")
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
            print(f"[CÜZDAN HATASI] {e}")
    
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
    """
    Otonom al-sat motorunu çalıştırır.
    Açık pozisyonları kontrol eder (SL/TP/AI SAT) ve yeni fırsatları değerlendirir.
    
    Döndürür: (islem_raporu, guncel_cuzdan)
    """
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
    
    # ─── 1. AÇIK POZİSYONLARI KONTROL ET ───
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
        
        # Teknik analiz
        df_analiz = hesapla_teknikler(df)
        p_analiz = donusum_noktalari_hesapla(df_analiz)
        p_sinyal = sinyal_kontrol(df_analiz)
        
        # AI kararı
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
            kapatma_nedeni = f"STOP-LOSS (%{sl_yuzde} Zarar Kes)"
        elif guncel_fiyat >= tp:
            kapatma_nedeni = f"TAKE-PROFIT (%{tp_yuzde} Kâr Al)"
        elif ai_karar == "SAT":
            kapatma_nedeni = f"AI SAT SİNYALİ"
        
        if kapatma_nedeni:
            satis_degeri = poz["adet"] * guncel_fiyat
            maliyet_tutar = poz["adet"] * poz["maliyet"]
            kar_zarar = satis_degeri - maliyet_tutar
            kar_zarar_yuzde = (kar_zarar / maliyet_tutar) * 100 if maliyet_tutar > 0 else 0
            
            cuzdan["nakit"] += satis_degeri
            
            emoji = "🟢" if kar_zarar >= 0 else "🔴"
            islem_raporu += (
                f"{emoji} **[KAPATMA - {kapatma_nedeni}]** `{varlik}`\\n"
                f"   Fiyat: `{guncel_fiyat:.4f}` | K/Z: `{kar_zarar:+.2f}$` (%{kar_zarar_yuzde:+.2f})\\n\\n"
            )
            
            cuzdan["gecmis_islemler"].append({
                "islem": f"KAPAT ({kapatma_nedeni})",
                "varlik": varlik,
                "fiyat": guncel_fiyat,
                "tarih": tarih_str,
                "tutar": satis_degeri,
                "kar_zarar": kar_zarar,
                "kar_zarar_yuzde": kar_zarar_yuzde
            })
            
            del cuzdan["pozisyonlar"][varlik]
            degisiklik_oldu = True
    
    # ─── 2. YENİ ALIM FIRSATLARINI TARA ───
    acik_sayisi = len(cuzdan["pozisyonlar"])
    
    for varlik in varliklar:
        if varlik in cuzdan["pozisyonlar"]:
            continue
        if acik_sayisi >= max_pozisyon:
            break
        
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
        
        # AL koşulu: AI AL diyor VE sahte sinyal yok VE yeterli nakit var
        sahte_var = "SAHTE" in p_sinyal.upper() or "⚠️" in p_sinyal
        
        if ai_karar == "AL" and not sahte_var:
            harcanacak_nakit = cuzdan["nakit"] * risk_orani
            
            if harcanacak_nakit > 10 and cuzdan["nakit"] >= harcanacak_nakit:
                adet = harcanacak_nakit / guncel_fiyat
                
                strateji = strateji_hesapla(
                    guncel_fiyat, p_analiz["destek"], p_analiz["direnc"],
                    sl_yuzde=sl_yuzde, tp_yuzde=tp_yuzde
                )
                
                cuzdan["nakit"] -= harcanacak_nakit
                cuzdan["pozisyonlar"][varlik] = {
                    "adet": adet,
                    "maliyet": guncel_fiyat,
                    "stop_loss": strateji["stop_loss"],
                    "take_profit": strateji["take_profit"],
                    "tarih": tarih_str,
                    "rr_orani": strateji["rr_orani"]
                }
                
                islem_raporu += (
                    f"🟢 **[AL - AI ONAYLI]** `{varlik}`\\n"
                    f"   Fiyat: `{guncel_fiyat:.4f}` | Lot: `{adet:.6f}`\\n"
                    f"   SL: `{strateji['stop_loss']:.4f}` | TP: `{strateji['take_profit']:.4f}` | R/R: `{strateji['rr_orani']:.2f}`\\n\\n"
                )
                
                cuzdan["gecmis_islemler"].append({
                    "islem": "AL",
                    "varlik": varlik,
                    "fiyat": guncel_fiyat,
                    "tarih": tarih_str,
                    "tutar": harcanacak_nakit,
                    "adet": adet,
                    "stop_loss": strateji["stop_loss"],
                    "take_profit": strateji["take_profit"]
                })
                
                acik_sayisi += 1
                degisiklik_oldu = True
    
    if degisiklik_oldu:
        sanal_cuzdan_kaydet(cuzdan)
    
    return islem_raporu, cuzdan


# ═══════════════════════════════════════════════════════
# ANALİZ RAPORU OLUŞTURMA
# ═══════════════════════════════════════════════════════

def detayli_analiz_raporu(varlik, df_analiz, p_analiz, p_sinyal, ai_karar, ai_aciklama):
    """Tek bir varlık için detaylı analiz metni oluşturur."""
    fiyat = p_analiz["fiyat"]
    
    s1, s2, s3 = p_analiz["s1"], p_analiz["s2"], p_analiz["s3"]
    r1, r2, r3 = p_analiz["r1"], p_analiz["r2"], p_analiz["r3"]
    
    son = df_analiz.iloc[-1]
    rsi = son.get("rsi", 50)
    macd = son.get("macd_durumu", "NÖTR")
    ema20 = son.get("ema_20", fiyat)
    ema50 = son.get("ema_50", fiyat)
    
    trend = "YUKARI 📈" if ema20 > ema50 else "AŞAĞI 📉" if ema20 < ema50 else "YATAY ⚖️"
    
    rapor = (
        f"🔹 *{varlik}*\\n"
        f"   💰 Fiyat: `{fiyat:.4f}` | Trend: {trend}\\n"
        f"   📊 Sinyal: `{p_sinyal}`\\n"
        f"   🤖 AI Karar: `{ai_karar}`\\n"
        f"   📈 RSI: `{rsi:.1f}` | MACD: `{macd}`\\n"
        f"   🛡️ Destekler: S1:`{s1:.4f}` S2:`{s2:.4f}` S3:`{s3:.4f}`\\n"
        f"   🎯 Dirençler: R1:`{r1:.4f}` R2:`{r2:.4f}` R3:`{r3:.4f}`\\n"
        f"   📝 AI Gerekçe: {ai_aciklama[:150]}...\\n\\n"
    )
    return rapor


def piyasa_turu_raporu():
    """Tüm varlıklar için piyasa turu raporu oluşturur ve Telegram'a gönderir."""
    ayarlar = ayarlari_yukle()
    varliklar = ayarlar.get("varliklar", [])
    zaman_dilimi = ayarlar.get("zaman_dilimi", "1d")
    
    if not varliklar:
        print("[UYARI] Takip listesi boş.")
        return
    
    zaman_damgasi = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Otonom işlemleri çalıştır
    otonom_rapor, cuzdan = otonom_islem_calistir(ayarlar)
    
    # Rapor başlığı
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
        f"📊 *OTONOM PİYASA TURU*\\n"
        f"📅 `{zaman_damgasi}` | Zaman Dilimi: `{zaman_dilimi}`\\n"
        f"💼 Cüzdan: `{toplam_servet:.2f}$` | K/Z: `{net_kz:+.2f}$` (%{net_kz_yuzde:+.2f})\\n"
        f"💵 Nakit: `{cuzdan['nakit']:.2f}$` | Pozisyon: `{toplam_poz_deger:.2f}$`\\n"
        f"📈 Açık Pozisyon: `{len(cuzdan['pozisyonlar'])}`\\n"
        f"{'─' * 30}\\n\\n"
    )
    
    # Otonom işlem raporu
    if otonom_rapor:
        rapor += f"🤖 *OTONOM İŞLEMLER:*\\n{otonom_rapor}"
        rapor += f"{'─' * 30}\\n\\n"
    
    # Her varlık için analiz
    rapor += "📈 *TEKNİK ANALİZ ÖZETLERİ:*\\n\\n"
    
    for varlik in varliklar:
        df = veri_cek(varlik, aralik=zaman_dilimi)
        if df is None or df.empty:
            rapor += f"⚠️ `{varlik}`: Veri alınamadı\\n\\n"
            continue
        
        df_analiz = hesapla_teknikler(df)
        p_analiz = donusum_noktalari_hesapla(df_analiz)
        p_sinyal = sinyal_kontrol(df_analiz)
        
        analiz = piyasa_analizi_yap(df_analiz)
        ai_karar, ai_aciklama = ai_akilli_karar_ver(
            varlik=varlik,
            fiyat=p_analiz["fiyat"],
            d1=p_analiz["destek"],
            r1=p_analiz["direnc"],
            p_sinyal=p_sinyal,
            rsi=analiz.get("rsi", 50),
            macd_durumu=analiz.get("macd_durumu", "NÖTR"),
            trend=analiz.get("trend", "YATAY")
        )
        
        rapor += detayli_analiz_raporu(varlik, df_analiz, p_analiz, p_sinyal, ai_karar, ai_aciklama)
    
    # Telegram'a gönder
    basarili = telegram_bildir(rapor)
    if basarili:
        print(f"[BAŞARILI] Rapor gönderildi. ({len(varliklar)} varlık)")
    else:
        print("[HATA] Rapor gönderilemedi.")
    
    # Konsola da yaz
    print("\\n" + "=" * 50)
    print(rapor.replace("\\n", "\\n"))
    print("=" * 50)


# ═══════════════════════════════════════════════════════
# ANA ÇALIŞMA MODLARI
# ═══════════════════════════════════════════════════════

def tek_seferlik_mod():
    """GitHub Actions / Manuel tetikleme için tek seferlik çalıştırma."""
    print("🤖 Otonom Bot - Tek Seferlik Mod Başlatıldı...")
    piyasa_turu_raporu()
    print("✅ İşlem tamamlandı.")


def surekli_mod(bekleme_dk=60):
    """Sürekli çalışma modu (yerel sunucu için)."""
    print(f"🤖 Otonom Bot - Sürekli Mod Başlatıldı (Bekleme: {bekleme_dk} dk)...")
    print("Durdurmak için Ctrl+C")
    
    while True:
        try:
            piyasa_turu_raporu()
            print(f"\\n⏳ Sonraki tarama: {bekleme_dk} dakika sonra...\\n")
            time.sleep(bekleme_dk * 60)
        except KeyboardInterrupt:
            print("\\n🛑 Bot durduruldu.")
            break
        except Exception as e:
            print(f"[KRİTİK HATA] {e}")
            time.sleep(60)


if __name__ == "__main__":
    # Komut satırı argümanı kontrolü
    if len(sys.argv) > 1 and sys.argv[1] == "--surekli":
        bekleme = int(sys.argv[2]) if len(sys.argv) > 2 else 60
        surekli_mod(bekleme)
    else:
        tek_seferlik_mod()
'''

with open("/mnt/agents/output/bot_servisi.py", "w", encoding="utf-8") as f:
    f.write(bot_servisi_py)

print("✅ bot_servisi.py oluşturuldu")
