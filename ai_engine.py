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

# Güncel model adları (fallback sırasıyla)
GEMINI_MODELS = [
    "gemini-1.5-flash-latest",
    "gemini-1.5-flash",
    "gemini-1.5-pro-latest",
    "gemini-1.5-pro",
    "gemini-pro",
]


def _get_available_model():
    """Çalışan bir Gemini modeli bulur."""
    if not api_key:
        return None

    for model_name in GEMINI_MODELS:
        try:
            model = genai.GenerativeModel(model_name)
            model.generate_content("Hi", generation_config={"max_output_tokens": 1})
            print(f"[AI] Model bulundu: {model_name}")
            return model_name
        except Exception as e:
            print(f"[AI] Model {model_name} başarısız: {e}")
            continue

    return None


_WORKING_MODEL = None

def get_model():
    """Cache'lenmiş çalışan modeli döndürür."""
    global _WORKING_MODEL
    if _WORKING_MODEL is None:
        model_name = _get_available_model()
        if model_name:
            _WORKING_MODEL = genai.GenerativeModel(model_name)
    return _WORKING_MODEL


def ai_akilli_karar_ver(varlik, fiyat, d1, r1, p_sinyal, rsi=50.0, macd_durumu="NÖTR", 
                        trend="YATAY", hacim_durumu="NORMAL", haber_sentiment=None, 
                        hafiza_kullan=True, sinyal_turu="TEKNİK"):
    """Gemini AI ile varlık analizi yapar."""
    try:
        model = get_model()
        if not model:
            return _fallback_karar(p_sinyal, "API anahtarı bulunamadı veya tüm modeller başarısız")

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
            except:
                pass

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

        response = model.generate_content(prompt)
        yanit = response.text.strip()

        karar = "BEKLE"
        if "KARAR: AL" in yanit.upper() or "KARAR:AL" in yanit.upper():
            karar = "AL"
        elif "KARAR: SAT" in yanit.upper() or "KARAR:SAT" in yanit.upper():
            karar = "SAT"

        # Kararı hafızaya kaydet (opsiyonel)
        if AI_MEMORY_AVAILABLE:
            try:
                karar_kaydet(varlik=varlik, karar=karar, fiyat=fiyat, 
                            sinyal_turu=sinyal_turu, notlar=yanit[:200])
            except:
                pass

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
