import yfinance as yf
import pandas as pd

def veri_cek(sembol, aralik="1h"):
    """Belirtilen sembol için yfinance üzerinden veri çeker."""
    try:
        # yfinance kısıtlamaları: kısa zaman dilimleri için 60 günlük sınır vardır
        periyot = "60d" if aralik in ["15m", "30m", "1h"] else "1y"
        df = yf.download(sembol, period=periyot, interval=aralik, progress=False)
        
        if df.empty:
            return None
            
        df.reset_index(inplace=True)
        # Sütun isimlerini standartlaştırma
        df.rename(columns={
            'Datetime': 'tarih', 
            'Date': 'tarih', 
            'Open': 'open', 
            'High': 'high', 
            'Low': 'low', 
            'Close': 'close', 
            'Volume': 'volume'
        }, inplace=True)
        
        # Eğer yfinance multi-index döndürürse düzleştir
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [col[0] for col in df.columns]
            
        return df
    except Exception as e:
        return None
