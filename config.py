import os
from dotenv import load_dotenv

# .env dosyasını yükle (yerel geliştirme için)
load_dotenv()

# Telegram Ayarları (Güvenlik: .env veya ortam değişkeninden okur)
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# Gemini AI API Anahtarı
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# Varsayılan Ayarlar
DEFAULT_SETTINGS = {
    "varliklar": ["BTC-USD", "ETH-USD", "SOL-USD", "AAPL", "THYAO.IS"],
    "zaman_dilimi": "1d",
    "bot_sikligi_dk": 360,
    "risk_ayarlari": {
        "sl_yuzde": 1.5,
        "tp_yuzde": 3.0,
        "risk_orani": 0.25,
        "max_pozisyon": 4
    }
}

# Dosya Yolları
AYAR_DOSYASI = "ayarlar.json"
PORTFOY_DOSYASI = "portfoy_arsiv.json"
SANAL_CUZDAN_DOSYASI = "sanal_cuzdan_arsiv.json"
