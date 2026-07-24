import pandas as pd
import numpy as np

def hesapla_teknikler(df):
    # SMA (Hareketli Ortalamalar)
    df['sma_20'] = df['close'].rolling(window=20).mean()
    df['sma_50'] = df['close'].rolling(window=50).mean()

    # RSI (Göreceli Güç Endeksi)
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))

    # YENİ: Bollinger Bantları (20 Periyot, 2 Standart Sapma)
    df['bollinger_ust'] = df['sma_20'] + 2 * df['close'].rolling(window=20).std()
    df['bollinger_alt'] = df['sma_20'] - 2 * df['close'].rolling(window=20).std()

    # YENİ: MACD (12, 26, 9)
    exp1 = df['close'].ewm(span=12, adjust=False).mean()
    exp2 = df['close'].ewm(span=26, adjust=False).mean()
    df['macd'] = exp1 - exp2
    df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()

    # YENİ: Grafikte İşaretlenecek Tarihsel Long/Short Sinyalleri 
    # SMA 20, SMA 50'yi yukarı keserse AL (1), aşağı keserse SAT (-1)
    df['sinyal_tarihsel'] = 0
    df.loc[(df['sma_20'] > df['sma_50']) & (df['sma_20'].shift(1) <= df['sma_50'].shift(1)), 'sinyal_tarihsel'] = 1
    df.loc[(df['sma_20'] < df['sma_50']) & (df['sma_20'].shift(1) >= df['sma_50'].shift(1)), 'sinyal_tarihsel'] = -1

    return df

def sinyal_kontrol(df):
    son = df.iloc[-1]
    if son['sma_20'] > son['sma_50']:
        return "Güçlü AL (Uptrend)"
    elif son['sma_20'] < son['sma_50']:
        return "Güçlü SAT (Downtrend)"
    return "NÖTR"

def piyasa_analizi_yap(df, sinyal):
    son_rsi = df['rsi'].iloc[-1]
    analiz = f"📈 **Piyasa Özeti:**\n- Sistem Sinyali: **{sinyal}**\n- RSI (14): **{son_rsi:.2f}** "
    if son_rsi > 70: 
        analiz += "(Aşırı Alım - Yüksek Risk, Kar Alışları Gelebilir)"
    elif son_rsi < 30: 
        analiz += "(Aşırı Satım - Fırsat Bölgesi Olabilir)"
    else: 
        analiz += "(Normal Bölge)"
    return analiz
