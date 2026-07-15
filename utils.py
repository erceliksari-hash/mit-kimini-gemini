import pandas as pd
import numpy as np

def donusum_noktalari_hesapla(df):
    # Verinin boş olup olmadığını kontrol et
    if df is None or df.empty or 'Close' not in df.columns:
        return {"destek": 0.0, "direnc": 0.0, "fiyat": 0.0}

    close = df['Close']
    son_20 = close.tail(20)

    # .min() ve .max() sonuçlarını kontrol et
    destek = son_20.min()
    direnc = son_20.max()
    fiyat = close.iloc[-1]

    # Eğer değerler NaN ise 0.0 döndür
    return {
        "destek": float(destek) if pd.notna(destek) else 0.0,
        "direnc": float(direnc) if pd.notna(direnc) else 0.0,
        "fiyat": float(fiyat) if pd.notna(fiyat) else 0.0
    }
