def donusum_noktalari_hesapla(df_analiz):
  """Basit destek ve direnç noktalarını hesaplar."""
  if df_analiz.empty:
    return {"fiyat": 0, "destek": 0, "direnc": 0}

  son_fiyat = df_analiz["close"].iloc[-1]
  destek = df_analiz["low"].rolling(window=20).min().iloc[-1]
  direnc = df_analiz["high"].rolling(window=20).max().iloc[-1]

  return {"fiyat": son_fiyat, "destek": destek, "direnc": direnc}
