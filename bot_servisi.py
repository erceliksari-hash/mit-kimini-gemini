import time
import pandas as pd
import yfinance as yf
from datetime import datetime
from ai_engine import ai_akilli_karar_ver

def varlik_verilerini_cek(varlik):
    try:
        # Kripto sembol format uyarlaması (BTC/USDT -> BTC-USD)
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
        
        # Temel RSI ve Seviye Hesaplama
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))
        
        df['Support'] = df['Close'] * 0.98
        df['Resistance'] = df['Close'] * 1.02
        df['MACD_Status'] = 'NÖTR'
        df['Signal'] = 'BEKLE'
        return df
    except Exception as e:
        print(f"Teknik analiz hesaplama hatası: {e}")
        return df

def otonom_bot_dongusu():
    print("🤖 Otonom Sanal Cüzdan Botu Başlatıldı (7/24 Modu)...")
    
    takip_listesi = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT"]
    
    print(f"\n--- Yeni Otonom Tur Başlıyor: {datetime.now()} ---")
    
    for varlik in takip_listesi:
        # 1. Anlık Veri Çekimi
        df = varlik_verilerini_cek(varlik)
        if df is None or df.empty:
            print(f"Uyarı: {varlik} için veri alınamadı, atlanıyor.")
            continue
        
        # 2. Teknik Analiz Hesaplama
        analiz_df = teknik_analiz_hesapla(df)
        if analiz_df is None or analiz_df.empty:
            print(f"Uyarı: {varlik} için teknik analiz oluşturulamadı.")
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
        
        # 3. Yapay Zekadan Otonom Karar Alınması
        karar, gerekce = ai_akilli_karar_ver(
            varlik=varlik, 
            fiyat=fiyat, 
            d1=d1, 
            r1=r1, 
            p_sinyal=p_sinyal, 
            rsi=rsi, 
            macd_durumu=macd
        )
        
        print(f"Varlık: {varlik} | Fiyat: {fiyat} | Karar: {karar}")
        print(f"Gerekçe: {gerekce}")

if __name__ == "__main__":
    otonom_bot_dongusu()
