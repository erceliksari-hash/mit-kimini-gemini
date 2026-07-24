import pandas as pd

def donusum_noktalari_hesapla(df: pd.DataFrame) -> dict:
    """
    Son mum verisine göre pivot, destek ve direnç seviyelerini hesaplar.
    """
    if df is None or df.empty:
        return {"fiyat": 0.0, "pivot": 0.0, "destek": 0.0, "direnc": 0.0}

    son_mum = df.iloc[-1]

    # Sütun isimleri data_sources.py'da küçük harfe çevrildiği için burada da küçük harf kullanıyoruz
    yuksek = son_mum["high"]
    dusuk = son_mum["low"]
    kapanis = son_mum["close"]

    pivot = (yuksek + dusuk + kapanis) / 3
    destek = (2 * pivot) - yuksek
    direnc = (2 * pivot) - dusuk

    return {
        "fiyat": round(float(kapanis), 2),
        "pivot": round(float(pivot), 2),
        "destek": round(float(destek), 2),
        "direnc": round(float(direnc), 2),
    }
