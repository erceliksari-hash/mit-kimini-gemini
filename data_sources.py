import pandas as pd
import yfinance as yf


def veri_cek(sembol, aralik="1h"):
  """Belirtilen sembol için yfinance üzerinden veri çeker."""
  try:
    periyot = "60d" if aralik in ["15m", "30m", "1h"] else "1y"
    df = yf.download(sembol, period=periyot, interval=aralik, progress=False)

    if df.empty:
      return None

    df.reset_index(inplace=True)
    df.rename(
        columns={
            "Datetime": "tarih",
            "Date": "tarih",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        },
        inplace=True,
    )

    if isinstance(df.columns, pd.MultiIndex):
      df.columns = [col[0] for col in df.columns]

    return df
  except Exception as e:
    return None
