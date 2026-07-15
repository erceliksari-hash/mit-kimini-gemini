import pandas as pd

def sma(seri, period):
    return seri.rolling(window=period).mean()

def ema(seri, period):
    return seri.ewm(span=period, adjust=False).mean()

def rsi(seri, period=14):
    delta = seri.diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def macd(seri, fast=12, slow=26, signal=9):
    macd_line = ema(seri, fast) - ema(seri, slow)
    signal_line = ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram

def bollinger(seri, period=20, std_dev=2):
    orta = sma(seri, period)
    std = seri.rolling(window=period).std()
    return orta + (std * std_dev), orta, orta - (std * std_dev)
