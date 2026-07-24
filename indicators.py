import pandas as pd
import numpy as np

def hesapla_teknikler(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["sma_20"] = df["close"].rolling(window=20, min_periods=1).mean()
    df["sma_50"] = df["close"].rolling(window=50, min_periods=1).mean()
    return df

def sinyal_kontrol(df: pd.DataFrame) -> str:
    if len(df) < 2: return "Beklemede"
    if df["sma_20"].iloc[-2] <= df["sma_50"].iloc[-2] and df["sma_20"].iloc[-1] > df["sma_50"].iloc[-1]:
        return "AL"
    elif df["sma_20"].iloc[-2] >= df["sma_50"].iloc[-2] and df["sma_20"].iloc[-1] < df["sma_50"].iloc[-1]:
        return "SAT"
    return "Beklemede"

def piyasa_analizi_yap(df: pd.DataFrame, sinyal: str) -> str:
    son_fiyat = df["close"].iloc[-1]
    sma20 = df["sma_20"].iloc[-1]
    sma50 = df["sma_50"].iloc[-1]
    trend = "Yükseliş" if sma20 > sma50 else "Düşüş"
    durum = "Pozitif" if son_fiyat > sma20 else "Negatif"
    
    return f"📊 **Teknik Analiz Özeti:** Genel Trend: **{trend}**. Fiyat, SMA 20'nin **{durum}** tarafında. Güncel Sinyal: **{sinyal}**."
