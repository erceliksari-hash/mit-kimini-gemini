import os
from dotenv import load_dotenv
import google.generativeai as genai

# .env dosyasındaki ortam değişkenlerini otomatik olarak yükler (Yerel kullanım için)
load_dotenv()

# API anahtarını çevre değişkenlerinden güvenli bir şekilde alır (Render / Yerel)
api_key = os.environ.get("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)

def ai_akilli_karar_ver(varlik, fiyat, d1, r1, p_sinyal, rsi, macd_durumu):
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = f"""
        Sen profesyonel bir kripto, borsa ve emtia trader'ısın. Aşağıdaki verileri analiz ederek bu varlık için kesin bir işlem kararı ver.
        Sahte sinyallere ve tuzaklara karşı çok dikkatli ol.
        
        Varlık: {varlik}
        Anlık Fiyat: {fiyat}
        Teknik Sinyal Durumu: {p_sinyal}
        Destek Seviyesi: {d1}
        Direnç Seviyesi: {r1}
        RSI Değeri: {rsi}
        MACD Durumu: {macd_durumu}
        
        Lütfen şu formatta kısa ve net bir yanıt ver:
        KARAR: [AL / SAT / BEKLE]
        GEREKÇE: [1-2 cümlelik profesyonel açıklama]
        """
        response = model.generate_content(prompt)
        yanit = response.text.upper()
        
        if "KARAR: AL" in yanit:
            return "AL", response.text
        elif "KARAR: SAT" in yanit:
            return "SAT", response.text
        else:
            return "BEKLE", response.text
            
    except Exception as e:
        if "AL" in p_sinyal.upper() or "YÜKSELİŞ" in p_sinyal.upper():
            return "AL", f"API fallback (Hata nedeniyle teknik sinyal baz alındı): {str(e)}"
        return "BEKLE", f"Hata: {str(e)}"
