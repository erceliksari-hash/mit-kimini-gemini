import pandas as pd

def hesapla_teknikler(df):
    close = df['Close']
    df['SMA_20'] = close.rolling(window=20).mean()
    df['RSI'] = 100 - (100 / (1 + (close.diff().clip(lower=0).rolling(14).mean() / (-close.diff().clip(upper=0).rolling(14).mean()))))
    return df
