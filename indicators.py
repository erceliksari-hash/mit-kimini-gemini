import numpy as np
import pandas as pd


def hesapla_teknikler(df):
  """Teknik indikatörleri hesaplar ve df'ye ekler."""
  df["sma_20"] = df["close"].rolling(window=20).mean()
  df["sma_50"] = df["close"].rolling(window=50).mean()

  df["std"] = df["close"].rolling(window=20).std()
  df["bollinger_ust"] = df["sma_20"] + (df["std"] * 2)
  df["bollinger_alt"] = df["sma_20"] - (df["std"] * 2)

  delta = df["close"].diff()
  gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
  loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
  rs = gain / loss
  df["rsi"] = 100 - (100 / (1 + rs))

  ema_12 = df["close"].ewm(span=12, adjust=False).mean()
  ema_26 = df["close"].ewm(span=26, adjust=False).mean()
  df["macd"] = ema_12 - ema_26
  df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()

  df["ozel_indikator"] = df["sma_20"]

  df["sinyal_tarihsel"] = 0
  df.loc[
      (df["sma_20"] > df["sma_50"])
      & (df["sma_20"].shift(1) <= df["sma_50"].shift(1)),
      "sinyal_tarihsel",
  ] = 1
  df.loc[
      (df["sma_20"] < df["sma_50"])
      & (df["sma_20"].shift(1) >= df["sma_50"].shift(1)),
      "sinyal_tarihsel",
  ] = -1

  return df


def sinyal_kontrol(df_analiz):
  """En güncel sinyali döndürür."""
  son_sinyaller = df_analiz[df_analiz["sinyal_tarihsel"] != 0]
  if son_sinyaller.empty:
    return "⚪ NÖTR"

  son_sinyal = son_sinyaller["sinyal_tarihsel"].iloc[-1]
  if son_sinyal == 1:
    return "🟢 AL (LONG)"
  elif son_sinyal == -1:
    return "🔴 SAT (SHORT)"
  else:
    return "⚪ NÖTR"


def piyasa_analizi_yap(df_analiz, sinyal):
  """Ekranda gösterilecek kısa analiz metni."""
  rsi_degeri = df_analiz["rsi"].iloc[-1]
  if rsi_degeri > 70:
    rsi_durumu = "Aşırı Alım (Düzeltme Gelebilir)"
  elif rsi_degeri < 30:
    rsi_durumu = "Aşırı Satım (Tepki Gelebilir)"
  else:
    rsi_durumu = "Normal Bölge"

  return f"**Teknik Yorum:** Güncel sinyal **{sinyal}**. RSI değeri `{rsi_degeri:.2f}` ile {rsi_durumu} aşamasında."
