
indicators_py = '''import numpy as np
import pandas as pd


def hesapla_teknikler(df):
    """
    Teknik indikatörleri hesaplar: RSI, MACD, Bollinger, EMA, Hacim Ortalaması.
    """
    if df is None or len(df) < 50:
        return df
    
    df = df.copy()
    
    # ─── EMA (Üssel Hareketli Ortalama) ───
    df["ema_20"] = df["close"].ewm(span=20, adjust=False).mean()
    df["ema_50"] = df["close"].ewm(span=50, adjust=False).mean()
    
    # ─── RSI ───
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / (loss + 1e-10)
    df["rsi"] = 100 - (100 / (1 + rs))
    
    # ─── Bollinger Bantları ───
    df["bollinger_orta"] = df["close"].rolling(window=20).mean()
    std = df["close"].rolling(window=20).std()
    df["bollinger_ust"] = df["bollinger_orta"] + (std * 2)
    df["bollinger_alt"] = df["bollinger_orta"] - (std * 2)
    
    # ─── MACD ───
    exp1 = df["close"].ewm(span=12, adjust=False).mean()
    exp2 = df["close"].ewm(span=26, adjust=False).mean()
    df["macd"] = exp1 - exp2
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
    df["macd_histogram"] = df["macd"] - df["macd_signal"]
    
    # MACD durumu metni
    df["macd_durumu"] = "NÖTR"
    df.loc[df["macd"] > df["macd_signal"], "macd_durumu"] = "YUKARI"
    df.loc[df["macd"] < df["macd_signal"], "macd_durumu"] = "AŞAĞI"
    
    # ─── Hacim Ortalaması (Sahte sinyal filtresi için) ───
    df["volume_sma_20"] = df["volume"].rolling(window=20).mean()
    
    # ─── Sinyal Üretimi (Gelişmiş) ───
    df["sinyal_tarihsel"] = 0
    
    # AL koşulları: RSI < 35 + MACD yukarı kesiyor + Fiyat EMA20 üzerinde
    al_kosul = (
        (df["rsi"] < 35) & 
        (df["macd"] > df["macd_signal"]) & 
        (df["macd"].shift(1) <= df["macd_signal"].shift(1))
    )
    df.loc[al_kosul, "sinyal_tarihsel"] = 1
    
    # SAT koşulları: RSI > 65 + MACD aşağı kesiyor + Fiyat EMA20 altında
    sat_kosul = (
        (df["rsi"] > 65) & 
        (df["macd"] < df["macd_signal"]) & 
        (df["macd"].shift(1) >= df["macd_signal"].shift(1))
    )
    df.loc[sat_kosul, "sinyal_tarihsel"] = -1
    
    # ─── Sahte Sinyal Kontrolü (Hacim + Trend Uyumsuzluğu) ───
    df["sahte_sinyal"] = False
    
    # AL sinyali ama hacim düşük (trend teyidi yok)
    df.loc[
        (df["sinyal_tarihsel"] == 1) & 
        (df["volume"] < df["volume_sma_20"] * 0.6),
        "sahte_sinyal"
    ] = True
    
    # SAT sinyali ama hacim düşük
    df.loc[
        (df["sinyal_tarihsel"] == -1) & 
        (df["volume"] < df["volume_sma_20"] * 0.6),
        "sahte_sinyal"
    ] = True
    
    # AL sinyali ama fiyat EMA50 altında (düşüş trendinde AL tuzağı)
    df.loc[
        (df["sinyal_tarihsel"] == 1) & 
        (df["close"] < df["ema_50"]),
        "sahte_sinyal"
    ] = True
    
    # SAT sinyali ama fiyat EMA50 üzerinde (yükseliş trendinde SAT tuzağı)
    df.loc[
        (df["sinyal_tarihsel"] == -1) & 
        (df["close"] > df["ema_50"]),
        "sahte_sinyal"
    ] = True
    
    return df


def sinyal_kontrol(df):
    """
    Son satıra göre sinyal durumunu döndürür.
    """
    if df is None or df.empty:
        return "Veri Yok"
    
    son_satir = df.iloc[-1]
    sinyal = son_satir.get("sinyal_tarihsel", 0)
    sahte = son_satir.get("sahte_sinyal", False)
    rsi = son_satir.get("rsi", 50)
    macd = son_satir.get("macd_durumu", "NÖTR")
    
    if sahte:
        if sinyal == 1:
            return f"⚠️ Sahte AL (RSI:{rsi:.1f}, MACD:{macd})"
        elif sinyal == -1:
            return f"⚠️ Sahte SAT (RSI:{rsi:.1f}, MACD:{macd})"
        return "⚠️ Zayıf Sinyal"
    
    if sinyal == 1:
        return f"🟢 AL (RSI:{rsi:.1f}, MACD:{macd})"
    elif sinyal == -1:
        return f"🔴 SAT (RSI:{rsi:.1f}, MACD:{macd})"
    
    return f"⚪ NÖTR (RSI:{rsi:.1f}, MACD:{macd})"


def piyasa_analizi_yap(df):
    """
    Basit piyasa analizi özeti döndürür.
    """
    if df is None or df.empty:
        return {"fiyat": 0, "durum": "Veri yok"}
    
    son = df.iloc[-1]
    fiyat = float(son["close"])
    rsi = float(son.get("rsi", 50))
    ema20 = float(son.get("ema_20", fiyat))
    ema50 = float(son.get("ema_50", fiyat))
    
    trend = "YUKARI" if ema20 > ema50 else "AŞAĞI" if ema20 < ema50 else "YATAY"
    
    return {
        "fiyat": fiyat,
        "rsi": rsi,
        "trend": trend,
        "durum": f"Fiyat: {fiyat:.2f}, Trend: {trend}, RSI: {rsi:.1f}"
    }
'''

with open("/mnt/agents/output/indicators.py", "w", encoding="utf-8") as f:
    f.write(indicators_py)

print("✅ indicators.py oluşturuldu")
