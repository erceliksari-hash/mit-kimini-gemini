import pandas as pd
import numpy as np

def donusum_noktalari_hesapla(df):
    # Temel boşluk kontrolü
    if df is None or df.empty or 'Close' not in df.columns:
        return {"destek": 0.0, "direnc": 0.0, "fiyat": 0.0}

    # Sadece Close sütununu al (Series olduğundan emin ol)
    close_series = df['Close']
    son_20 = close_series.tail(20)

    # Değerleri hesapla
    # .min() ve .max() bazen Seri dönebilir, bu yüzden .item() veya float() ile zorluyoruz
    destek_val = son_20.min()
    direnc_val = son_20.max()
    fiyat_val = close_series.iloc[-1]

    # Yardımcı fonksiyon: Değer Seri bile olsa onu tek sayıya çevirir
    def to_float(val):
        try:
            # Eğer val bir Seri ise, içindeki ilk değeri al veya tek sayıya düşür
            if isinstance(val, (pd.Series, pd.DataFrame)):
                val = val.iloc[0]
            return float(val)
        except (ValueError, TypeError, IndexError):
            return 0.0

    return {
        "destek": to_float(destek_val),
        "direnc": to_float(direnc_val),
        "fiyat": to_float(fiyat_val)
    }
