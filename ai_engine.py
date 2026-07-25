import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

api_key = os.environ.get("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)


def ai_akilli_karar_ver(varlik, fiyat, d1, r1, p_sinyal, rsi=50.0, macd_durumu="NÖTR", trend="YATAY", hacim_durumu="NORMAL"):
    """
    Gemini AI ile varlık analizi yapar.

    Parametreler:
        varlik: Varlık kodu
        fiyat: Anlık fiyat
        d1: Destek seviyesi
        r1: Direnç seviyesi
        p_sinyal: Teknik sinyal metni
        rsi: RSI değeri (varsayılan: 50)
        macd_durumu: MACD durumu (varsayılan: NÖTR)
        trend: EMA20/50 trendi (varsayılan: YATAY)
        hacim_durumu: Hacim durumu (varsayılan: NORMAL)
    """
    try:
        if not api_key:
            return _fallback_karar(p_sinyal, "API anahtarı bulunamadı")

        model = genai.GenerativeModel('gemini-1.5-flash')

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

🎯 KURALLAR:
1. RSI < 30 ve MACD yukarı kesiyorsa AL değerlendirilebilir
2. RSI > 70 ve MACD aşağı kesiyorsa SAT değerlendirilebilir
3. Fiyat destek altındaysa STOP (SAT) düşünülebilir
4. Fiyat direnç üzerindeyse KAR AL (SAT) düşünülebilir
5. Sahte sinyal uyarısı varsa BEKLE
6. Trend aksi yöndeyse BEKLE

Lütfen şu formatta KESİN ve NET yanıt ver:
KARAR: [AL / SAT / BEKLE]
GÜVEN: [%0-100]
GEREKÇE: [2 cümle, profesyonel ve net açıklama]
STRATEJI: [SL: X.XX | TP: Y.YY]
"""

        response = model.generate_content(prompt)
        yanit = response.text.strip()

        # Karar çıkarımı
        karar = "BEKLE"
        if "KARAR: AL" in yanit.upper() or "KARAR:AL" in yanit.upper():
            karar = "AL"
        elif "KARAR: SAT" in yanit.upper() or "KARAR:SAT" in yanit.upper():
            karar = "SAT"

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
