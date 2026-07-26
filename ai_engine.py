import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

# ai_memory opsiyonel import (dosya eksikse hata vermez)
try:
    from ai_memory import ai_prompt_gelistir, karar_kaydet, basari_istatistikleri
    AI_MEMORY_AVAILABLE = True
except ImportError:
    AI_MEMORY_AVAILABLE = False
    print("[AI] ai_memory.py bulunamadı, hafıza özellikleri devre dışı.")

api_key = os.environ.get("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)

# Güncel model adları (fallback sırasıyla).
#
# NOT (önemli): gemini-1.5-* ailesi ve gemini-pro Google tarafından
# tamamen kapatıldı (istekler 404 dönüyor). Eski liste her çağrıda
# baştan sona başarısız olup botu sürekli "AI Fallback" moduna
# düşürüyordu. Liste, Google'ın Temmuz 2026 itibarıyla desteklediği
# modellerle güncellendi. "gemini-flash-latest" Google'ın otomatik
# güncellenen takma adı olduğundan öncelikli denenir; GEMINI_MODEL ortam
# değişkeni ile ilk denenecek model dışarıdan da zorlanabilir.
_ONCELIKLI_MODEL = os.environ.get("GEMINI_MODEL")

GEMINI_MODELS = [m for m in [
    _ONCELIKLI_MODEL,
    "gemini-flash-latest",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
] if m]


_WORKING_MODEL_NAME = None
_BASARISIZ_MODELLER = set()


def _model_dene(model_name, prompt):
    """Modeli gerçek istekle dener; başarılıysa (model, yanıt) döner."""
    model = genai.GenerativeModel(model_name)
    response = model.generate_content(prompt)
    return model, response


def _ai_istek_gonder(prompt):
    """
    Model listesindeki modelleri sırayla dener. Önceki sürümde her model
    için ayrı bir "test" isteği (generate_content("Hi", max_output_tokens=1))
    atılıp SONRA asıl prompt tekrar gönderiliyordu; bu her soğuk başlangıçta
    gereksiz API çağrısı/maliyet demekti. Burada doğrudan asıl istekle
    denenir, başarısız olan model bir dahaki sefere tekrar denenmesin diye
    süreç içinde hatırlanır (cache).
    """
    global _WORKING_MODEL_NAME

    if not api_key:
        raise RuntimeError("GEMINI_API_KEY tanımlı değil")

    # Daha önce çalıştığı bilinen modeli önce dene.
    denenecekler = GEMINI_MODELS
    if _WORKING_MODEL_NAME and _WORKING_MODEL_NAME in GEMINI_MODELS:
        denenecekler = [_WORKING_MODEL_NAME] + [
            m for m in GEMINI_MODELS if m != _WORKING_MODEL_NAME
        ]

    son_hata = None
    for model_name in denenecekler:
        if model_name in _BASARISIZ_MODELLER:
            continue
        try:
            model, response = _model_dene(model_name, prompt)
            _WORKING_MODEL_NAME = model_name
            return response
        except Exception as e:
            son_hata = e
            _BASARISIZ_MODELLER.add(model_name)
            print(f"[AI] Model {model_name} başarısız: {e}")
            continue

    raise RuntimeError(f"Tüm Gemini modelleri başarısız oldu. Son hata: {son_hata}")


def ai_akilli_karar_ver(varlik, fiyat, d1, r1, p_sinyal, rsi=50.0, macd_durumu="NÖTR",
                        trend="YATAY", hacim_durumu="NORMAL", haber_sentiment=None,
                        hafiza_kullan=True, sinyal_turu="TEKNİK"):
    """Gemini AI ile varlık analizi yapar."""
    try:
        if not api_key:
            return _fallback_karar(p_sinyal, "GEMINI_API_KEY tanımlı değil")

        # Haber sentiment bilgisi
        haber_bolumu = ""
        if haber_sentiment:
            haber_bolumu = f"""
📰 HABER SENTIMENT ANALİZİ:
• Genel Durum: {haber_sentiment.get('durum', 'Bilinmiyor')}
• Ortalama Skor: {haber_sentiment.get('ortalama_sentiment', 0):+.1f}/100
• Özet: {haber_sentiment.get('ozet', 'Veri yok')[:200]}
"""

        # AI Hafıza bilgisi (opsiyonel)
        hafiza_bolumu = ""
        if hafiza_kullan and AI_MEMORY_AVAILABLE:
            try:
                istatistikler = basari_istatistikleri()
                hafiza_bolumu = ai_prompt_gelistir(varlik, "BEKLE", istatistikler)
            except Exception as e:
                print(f"[AI] Hafıza okunamadı: {e}")

        prompt = f"""Sen profesyonel bir finansal analist ve quantitative trader'sın. 
Aşağıdaki verileri objektif şekilde analiz ederek kesin bir işlem kararı ver.

📊 VARLIK BİLGİLERİ:
• Sembol: {varlik}
• Anlık Fiyat: {fiyat:.4f}
• Destek (S1): {d1:.4f}
• Direnç (R1): {r1:.4f}

📈 TEKNİK GÖSTERGELER:
• RSI: {rsi:.1f} (0=aşırı satım, 100=aşırı alım)
• MACD Durumu: {macd_durumu}
• EMA Trendi: {trend}
• Hacim Durumu: {hacim_durumu}
• Sistem Sinyali: {p_sinyal}
{haber_bolumu}
{hafiza_bolumu}

🎯 KURALLAR:
1. RSI < 30 ve MACD yukarı kesiyorsa AL değerlendirilebilir
2. RSI > 70 ve MACD aşağı kesiyorsa SAT değerlendirilebilir
3. Fiyat destek altındaysa STOP (SAT) düşünülebilir
4. Fiyat direnç üzerindeyse KAR AL (SAT) düşünülebilir
5. Sahte sinyal uyarısı varsa BEKLE
6. Trend aksi yöndeyse BEKLE
7. Haber sentiment AŞIRI NEGATİF ise ALMA (riskli)
8. Haber sentiment AŞIRI POZİTİF ise SATMA (fomo)

Lütfen şu formatta KESİN ve NET yanıt ver:
KARAR: [AL / SAT / BEKLE]
GÜVEN: [%0-100]
GEREKÇE: [2 cümle, profesyonel ve net açıklama]
STRATEJI: [SL: X.XX | TP: Y.YY]
"""

        response = _ai_istek_gonder(prompt)
        yanit = response.text.strip()

        karar = "BEKLE"
        yanit_upper = yanit.upper()
        if "KARAR: AL" in yanit_upper or "KARAR:AL" in yanit_upper:
            karar = "AL"
        elif "KARAR: SAT" in yanit_upper or "KARAR:SAT" in yanit_upper:
            karar = "SAT"

        # Kararı hafızaya kaydet (opsiyonel)
        if AI_MEMORY_AVAILABLE:
            try:
                karar_kaydet(varlik=varlik, karar=karar, fiyat=fiyat,
                            sinyal_turu=sinyal_turu, notlar=yanit[:200])
            except Exception as e:
                print(f"[AI] Karar hafızaya kaydedilemedi: {e}")

        return karar, yanit

    except Exception as e:
        return _fallback_karar(p_sinyal, str(e))


def _fallback_karar(p_sinyal, hata_mesaji):
    """AI API hatası durumunda teknik sinyale göre karar ver."""
    sinyal_ust = p_sinyal.upper()

    if "AL" in sinyal_ust and "SAHTE" not in sinyal_ust:
        return "AL", f"[AI Fallback] Teknik sinyal AL. Hata: {hata_mesaji}"
    elif "SAT" in sinyal_ust and "SAHTE" not in sinyal_ust:
        return "SAT", f"[AI Fallback] Teknik sinyal SAT. Hata: {hata_mesaji}"

    return "BEKLE", f"[AI Fallback] BEKLE modu. Hata: {hata_mesaji}"
