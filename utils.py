import pandas as pd


def donusum_noktalari_hesapla(df_analiz):
    """
    Gelişmiş destek ve direnç noktalarını hesaplar.
    Pivot noktaları, S1-S3 ve R1-R3 seviyelerini döndürür.
    """
    if df_analiz is None or df_analiz.empty:
        return {
            "fiyat": 0, "destek": 0, "direnc": 0,
            "s1": 0, "s2": 0, "s3": 0,
            "r1": 0, "r2": 0, "r3": 0
        }

    son_fiyat = float(df_analiz["close"].iloc[-1])

    # Son 20 barın low/high'ı (dinamik window)
    window = min(20, len(df_analiz))

    destek = float(df_analiz["low"].tail(window).min())
    direnc = float(df_analiz["high"].tail(window).max())

    # Pivot noktası hesaplama (son gün/kapanış bazlı)
    son_bar = df_analiz.iloc[-1]
    high = float(son_bar["high"])
    low = float(son_bar["low"])
    close = float(son_bar["close"])

    pivot = (high + low + close) / 3

    # Klasik Pivot Seviyeleri
    r1 = (2 * pivot) - low
    r2 = pivot + (high - low)
    r3 = high + 2 * (pivot - low)

    s1 = (2 * pivot) - high
    s2 = pivot - (high - low)
    s3 = low - 2 * (high - pivot)

    return {
        "fiyat": son_fiyat,
        "destek": destek,
        "direnc": direnc,
        "pivot": pivot,
        "s1": s1,
        "s2": s2,
        "s3": s3,
        "r1": r1,
        "r2": r2,
        "r3": r3
    }


def strateji_hesapla(fiyat, destek, direnc, sl_yuzde=1.5, tp_yuzde=3.0):
    """
    Risk/Oran bazlı stop-loss ve take-profit hesaplar.
    """
    stop_loss = max(destek * 0.995, fiyat * (1 - sl_yuzde / 100))
    take_profit = min(direnc * 1.005, fiyat * (1 + tp_yuzde / 100))

    risk = fiyat - stop_loss
    reward = take_profit - fiyat
    rr_orani = reward / risk if risk > 0 else 0

    return {
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "risk": risk,
        "reward": reward,
        "rr_orani": rr_orani
    }
