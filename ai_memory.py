#!/usr/bin/env python3
"""
AI Hafıza ve Öğrenme Modülü
- Geçmiş kararları kaydeder
- Başarı oranlarını analiz eder
- Strateji önerileri geliştirir
"""

import os
import json
from datetime import datetime, timedelta

AI_MEMORY_DOSYASI = "ai_hafiza.json"


def hafiza_yukle():
    """AI hafızasını yükler."""
    if os.path.exists(AI_MEMORY_DOSYASI):
        try:
            with open(AI_MEMORY_DOSYASI, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {
        "kararlar": [],
        "istatistikler": {
            "toplam_karar": 0,
            "basarili_al": 0,
            "basarisiz_al": 0,
            "basarili_sat": 0,
            "basarisiz_sat": 0,
            "bekle_dogru": 0,
            "bekle_yanlis": 0
        },
        "varlik_basarisi": {},
        "strateji_notlari": []
    }


def hafiza_kaydet(hafiza):
    """AI hafızasını kaydeder."""
    with open(AI_MEMORY_DOSYASI, "w", encoding="utf-8") as f:
        json.dump(hafiza, f, indent=2, ensure_ascii=False)


def karar_kaydet(varlik, karar, fiyat, hedef_fiyat=None, gerceklesen_fiyat=None, 
                 sinyal_turu="TEKNİK", notlar=""):
    """Bir kararı hafızaya kaydeder."""
    hafiza = hafiza_yukle()

    kayit = {
        "tarih": datetime.now().isoformat(),
        "varlik": varlik,
        "karar": karar,
        "fiyat": fiyat,
        "hedef_fiyat": hedef_fiyat,
        "gerceklesen_fiyat": gerceklesen_fiyat,
        "sinyal_turu": sinyal_turu,
        "notlar": notlar,
        "degerlendirildi": False,
        "basari": None
    }

    hafiza["kararlar"].append(kayit)
    hafiza["istatistikler"]["toplam_karar"] += 1
    hafiza_kaydet(hafiza)


def kararlari_degerlendir():
    """Açık kararları değerlendirir."""
    hafiza = hafiza_yukle()
    degisiklik = False

    for karar in hafiza["kararlar"]:
        if karar["degerlendirildi"] or karar["gerceklesen_fiyat"] is None:
            continue

        fiyat = karar["fiyat"]
        gerceklesen = karar["gerceklesen_fiyat"]
        karar_turu = karar["karar"]

        basari = False
        if karar_turu == "AL":
            basari = gerceklesen > fiyat
        elif karar_turu == "SAT":
            basari = gerceklesen < fiyat
        elif karar_turu == "BEKLE":
            degisim = abs(gerceklesen - fiyat) / fiyat
            basari = degisim < 0.02

        karar["basari"] = basari
        karar["degerlendirildi"] = True
        degisiklik = True

        if karar_turu == "AL":
            if basari:
                hafiza["istatistikler"]["basarili_al"] += 1
            else:
                hafiza["istatistikler"]["basarisiz_al"] += 1
        elif karar_turu == "SAT":
            if basari:
                hafiza["istatistikler"]["basarili_sat"] += 1
            else:
                hafiza["istatistikler"]["basarisiz_sat"] += 1
        elif karar_turu == "BEKLE":
            if basari:
                hafiza["istatistikler"]["bekle_dogru"] += 1
            else:
                hafiza["istatistikler"]["bekle_yanlis"] += 1

        varlik = karar["varlik"]
        if varlik not in hafiza["varlik_basarisi"]:
            hafiza["varlik_basarisi"][varlik] = {"toplam": 0, "basari": 0}
        hafiza["varlik_basarisi"][varlik]["toplam"] += 1
        if basari:
            hafiza["varlik_basarisi"][varlik]["basari"] += 1

    if degisiklik:
        hafiza_kaydet(hafiza)

    return hafiza


def basari_istatistikleri():
    """Başarı istatistiklerini hesaplar."""
    hafiza = kararlari_degerlendir()
    ist = hafiza["istatistikler"]

    al_toplam = ist["basarili_al"] + ist["basarisiz_al"]
    sat_toplam = ist["basarili_sat"] + ist["basarisiz_sat"]
    bekle_toplam = ist["bekle_dogru"] + ist["bekle_yanlis"]

    return {
        "toplam_karar": ist["toplam_karar"],
        "al_basarisi": (ist["basarili_al"] / al_toplam * 100) if al_toplam > 0 else 0,
        "sat_basarisi": (ist["basarili_sat"] / sat_toplam * 100) if sat_toplam > 0 else 0,
        "bekle_basarisi": (ist["bekle_dogru"] / bekle_toplam * 100) if bekle_toplam > 0 else 0,
        "genel_basarisi": (
            (ist["basarili_al"] + ist["basarili_sat"] + ist["bekle_dogru"]) / 
            max(ist["toplam_karar"], 1) * 100
        ),
        "varlik_basarisi": {
            v: {"oran": (d["basari"]/d["toplam"]*100) if d["toplam"] > 0 else 0, "toplam": d["toplam"]}
            for v, d in hafiza["varlik_basarisi"].items()
        }
    }


def ogrenme_raporu_olustur():
    """AI'nin öğrenme raporunu oluşturur."""
    hafiza = hafiza_yukle()
    ist = basari_istatistikleri()

    rapor = (
        f"🧠 *AI ÖĞRENME RAPORU*\n"
        f"📊 Toplam Karar: `{ist['toplam_karar']}`\n"
        f"🎯 Genel Başarı: `%{ist['genel_basarisi']:.1f}`\n"
        f"🟢 AL Başarısı: `%{ist['al_basarisi']:.1f}`\n"
        f"🔴 SAT Başarısı: `%{ist['sat_basarisi']:.1f}`\n"
        f"⚪ BEKLE Başarısı: `%{ist['bekle_basarisi']:.1f}`\n\n"
    )

    if ist["varlik_basarisi"]:
        rapor += "📈 *Varlık Bazlı Başarı:*\n"
        for v, d in sorted(ist["varlik_basarisi"].items(), 
                          key=lambda x: x[1]["oran"], reverse=True)[:10]:
            rapor += f"   `{v}`: `%{d['oran']:.1f}` ({d['toplam']} karar)\n"

    rapor += "\n💡 *AI STRATEJİ NOTLARI:*\n"

    if ist["al_basarisi"] > 70:
        rapor += "   ✅ AL sinyalleri güçlü. Daha agresif AL stratejisi denenebilir.\n"
    elif ist["al_basarisi"] < 40:
        rapor += "   ⚠️ AL sinyalleri zayıf. Daha katı AL koşulları uygulanmalı.\n"

    if ist["sat_basarisi"] > 70:
        rapor += "   ✅ SAT sinyalleri güçlü. Erken çıkış stratejisi iyi çalışıyor.\n"
    elif ist["sat_basarisi"] < 40:
        rapor += "   ⚠️ SAT sinyalleri zayıf. SL/TP seviyeleri gözden geçirilmeli.\n"

    if ist["bekle_basarisi"] > 70:
        rapor += "   ✅ BEKLE kararları doğru. Piyasa seçiciliği iyi.\n"

    return rapor


def ai_prompt_gelistir(varlik, mevcut_karar, istatistikler=None):
    """AI prompt'una geçmiş başarı istatistiklerini ekler."""
    if istatistikler is None:
        istatistikler = basari_istatistikleri()

    varlik_basarisi = istatistikler["varlik_basarisi"].get(varlik, {})
    varlik_oran = varlik_basarisi.get("oran", 50)

    return f"""
🧠 AI ÖĞRENME VERİLERİ:
• Bu varlıkta geçmiş başarı oranı: %{varlik_oran:.1f}
• Genel AL başarısı: %{istatistikler['al_basarisi']:.1f}
• Genel SAT başarısı: %{istatistikler['sat_basarisi']:.1f}
• Genel BEKLE başarısı: %{istatistikler['bekle_basarisi']:.1f}

NOT: Geçmiş başarı oranları yüksekse mevcut karara daha fazla güvenebilirsin.
Başarı oranları düşükse daha temkinli ol ve ek teyid ara.
"""
