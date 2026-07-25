import numpy as np
import pandas as pd


def hesapla_teknikler(df):
  # Temel İndikatörler (Bollinger, RSI, MACD vb.)
  delta = df["close"].diff()
  gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
  loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
  rs = gain / loss
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

  # Basit Sinyal Üretimi (Örnek Mantık)
  df["sinyal_tarihsel"] = 0
  # RSI ve Fiyat Kesişimlerine Göre Sinyal (1: Al/Yükseliş, -1: Sat/Düşüş)
  df.loc[df["rsi"] < 30, "sinyal_tarihsel"] = 1
  df.loc[df["rsi"] > 70, "sinyal_tarihsel"] = -1

  # Sahte Sinyal Kontrolü (Örn: RSI uç noktada tükenmişse veya hemen tersine dönüyorsa)
  df["sahte_sinyal"] = False
  # Eğer RSI aşırı şişmişken AL verdiyse veya aşırı düşmüşken SAT verdiyse sahte sinyal kabul et
  df.loc[(df["sinyal_tarihsel"] == 1) & (df["rsi"] > 65), "sahte_sinyal"] = True
  df.loc[(df["sinyal_tarihsel"] == -1) & (df["rsi"] < 35), "sahte_sinyal"] = True

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
  return "Analiz tamamlandı."
