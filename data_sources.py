import yfinance as yf
import pandas as pd

def veri_cek(sembol, aralik="1d"):
    try:
        # Zaman dilimine göre güvenli periyot belirleme
        if aralik in ["15m", "1h"]:
            period = "59d"  # Yahoo Finance 15m/1h için maksimum 60 gün sınırı koyar
        elif aralik in ["4h"]:
            period = "60d"
        elif aralik in ["1d"]:
            period = "1y"
        elif aralik in ["1wk", "1mo"]:
            period = "5y"
        else:
            period = "6mo"
        
        ticker = yf.Ticker(sembol)
        df = ticker.history(period=period, interval=aralik)
        
        if df is None or df.empty:
            return None
            
        df = df.reset_index()
        df.columns = [c.lower() for c in df.columns]
        
        # Sütun isim standardizasyonu
        if 'datetime' in df.columns:
            df = df.rename(columns={'datetime': 'tarih'})
        elif 'date' in df.columns:
            df = df.rename(columns={'date': 'tarih'})
        elif 'index' in df.columns:
            df = df.rename(columns={'index': 'tarih'})
            
        # Gerekli sütunların varlığını kontrol et
        gerekli_sutunlar = ['tarih', 'open', 'high', 'low', 'close']
        for sutun in gerekli_sutunlar:
            if sutun not in df.columns:
                return None
                
        return df
    except Exception as e:
        print(f"Veri çekme hatası ({sembol}): {e}")
        return None
