import numpy as np
import pandas as pd


def hesapla_teknikler(df):
    if df is None or len(df) < 20:
        return df

    df = df.copy()

    # Temel İndikatörler (Bollinger, RSI, MACD vb.)
    delta = df["close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    
    # Sıfıra bölünme hatasını önlemek için epsilon eklendi
    rs = gain / (loss + 1e-10)
    df["rsi"] = 100 - (100 / (1 + rs))

    # Bollinger Bantları
    df["bollinger_orta"] = df["close"].rolling(window=20).mean()
    std = df["close"].rolling(window=20).std()
    df["bollinger_ust"] = df["bollinger_orta"] + (std * 2)
    df["bollinger_alt"] = df["bollinger_orta"] - (std * 2)

    # MACD
    exp1 = df["close"].ewm(span=12, adjust=False).mean()
    exp2 = df["close"].ewm(span=26, adjust=False).mean()
    df["macd"] = exp1 - exp2

    # Sinyal Üretimi
    df["sinyal_tarihsel"] = 0
    df.loc[df["rsi"] < 30, "sinyal_tarihsel"] = 1
    df.loc[df["rsi"] > 70, "sinyal_tarihsel"] = -1

    # Sahte Sinyal Kontrolü (Mantıksal çelişki giderildi)
    df["sahte_sinyal"] = False
    # Örn: AL sinyali varken RSI ani bir şekilde yüksek bölgelerde uyumsuzluk gösteriyorsa
    df.loc[(df["sinyal_tarihsel"] == 1) & (df["rsi"] > 50), "sahte_sinyal"] = True
    df.loc[(df["sinyal_tarihsel"] == -1) & (df["rsi"] < 50), "sahte_sinyal"] = True

    return df


def sinyal_kontrol(df):
    if df is None or df.empty:
        return "Nötr"
    son_satir = df.iloc[-1]
    if son_satir.get("sahte_sinyal", False):
        return "Sahte / Zayıf Sinyal Uyarısı"
    elif son_satir.get("sinyal_tarihsel", 0) == 1:
        return "AL (Yükseliş Trendi)"
    elif son_satir.get("sinyal_tarihsel", 0) == -1:
        return "SAT (Düşüş Trendi)"
    return "Nötr"


def piyasa_analizi_yap(df):
    if df is None or df.empty:
        return {}
    son_fiyat = float(df["close"].iloc[-1])
    return {"fiyat": son_fiyat, "durum": "Analiz tamamlandı."}
