import os
import json
import urllib.request
import urllib.parse
import pandas as pd
import yfinance as yf
from datetime import datetime
from ai_engine import ai_akilli_karar_ver

def telegram_bildir(mesaj):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = urllib.parse.urlencode({"chat_id": chat_id, "text": mesaj, "parse_mode": "Markdown"}).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(req) as response:
            pass
    except Exception as e:
        print(f"Telegram bildirim hatası: {e}")

def varlik_listesini_yukle():
    try:
        if os.path.exists("secilen_varliklar.json"):
            with open("secilen_varliklar.json", "r", encoding="utf-8") as f:
                veri = json.load(f)
                return veri.get("varliklar", ["BTC/USDT", "ETH/USDT"])
    except Exception as e:
        print(f"Liste okuma hatası: {e}")
    return ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT"]

def varlik_verilerini_cek(varlik):
    try:
        symbol = varlik.replace("/", "-")
        if "USDT" in symbol:
            symbol = symbol.replace("USDT", "USD")
        
        df = yf.download(symbol, period="5d", interval="1h", progress=False)
        if df is None or df.empty:
            df = yf.download(symbol, period="1mo", interval="1d", progress=False)
            
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        return df
    except Exception as e:
        print(f"Veri çekme hatası ({varlik}): {e}")
        return None

def teknik_analiz_hesapla(df):
    try:
        df = df.copy()
        df['Close'] = df['Close'].astype(float)
        
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))
        
        df['Support'] = df['Close'].rolling(window=14).min() * 0.99
        df['Resistance'] = df['Close'].rolling(window=14).max() * 1.01
        df['MACD_Status'] = 'NÖTR'
        df['Signal'] = 'BEKLE'
        return df
    except Exception as e:
        print(f"Teknik analiz hesaplama hatası: {e}")
        return df

def otonom_bot_dongusu():
    print("🤖 Otonom Akıllı Ticaret Botu Başlatıldı...")
    
    takip_listesi = varlik_listesini_yukle()
    zaman_damgasi = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    rapor_metni = f"🤖 **Otonom Piyasa Turu**\n📅 Zaman: `{zaman_damgasi}`\n\n"
    
    for varlik in takip_listesi:
        df = varlik_verilerini_cek(varlik)
        if df is None or df.empty:
            continue
        
        analiz_df = teknik_analiz_hesapla(df)
        if analiz_df is None or analiz_df.empty:
            continue
        
        son_veri = analiz_df.iloc[-1]
        fiyat = float(son_veri['Close'])
        if fiyat == 0:
            continue
            
        d1 = float(son_veri.get('Support', fiyat * 0.98))
        r1 = float(son_veri.get('Resistance', fiyat * 1.02))
        rsi = float(son_veri.get('RSI', 50))
        macd = str(son_veri.get('MACD_Status', 'NÖTR'))
        p_sinyal = str(son_veri.get('Signal', 'BEKLE'))
        
        karar, gerekce = ai_akilli_karar_ver(
            varlik=varlik, 
            fiyat=fiyat, 
            d1=d1, 
            r1=r1, 
            p_sinyal=p_sinyal, 
            rsi=rsi, 
            macd_durumu=macd
        )
        
        rapor_metni += f"🔹 **{varlik}**\n"
        rapor_metni += f"💰 Fiyat: `{fiyat:.4f}`\n"
        rapor_metni += f"🎯 Hedef Direnç: `{r1:.4f}`\n"
        rapor_metni += f"📊 RSI: `{rsi:.1f}` | Karar: **{karar}**\n"
        rapor_metni += f"📝 {gerekce}\n\n"

    telegram_bildir(rapor_metni)

if __name__ == "__main__":
    otonom_bot_dongusu()
