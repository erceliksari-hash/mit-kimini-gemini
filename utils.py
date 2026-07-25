import pandas as pd


def donusum_noktalari_hesapla(df_analiz):
    """Basit destek ve direnç noktalarını hesaplar."""
    if df_analiz is None or df_analiz.empty:
        return {"fiyat": 0, "destek": 0, "direnc": 0}

    son_fiyat = float(df_analiz["close"].iloc[-1])
    
    # Veri sayısı 20'den azsa hata vermemesi için dinamik window veya min/max alınır
    window_boyutu = min(20, len(df_analiz))
    
    destek = float(df_analiz["low"].rolling(window=window_boyutu).min().iloc[-1])
    direnc = float(df_analiz["high"].rolling(window=window_boyutu).max().iloc[-1])

    return {"fiyat": son_fiyat, "destek": destek, "direnc": direnc}
