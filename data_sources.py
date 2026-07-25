import pandas as pd
import yfinance as yf


def veri_cek(sembol, aralik="1h"):
    """Belirtilen sembol için yfinance üzerinden veri çeker."""
    try:
        periyot = "60d" if aralik in ["15m", "30m", "1h"] else "1y"
        df = yf.download(sembol, period=periyot, interval=aralik, progress=False)

        if df is None or df.empty:
            return None

        # 1. Önce MultiIndex (tüplü sütun yapısı) varsa düzeltilmeli
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [col[0] for col in df.columns]

        # 2. Index'i sütuna çevir (Datetime / Date)
        df.reset_index(inplace=True)

        # 3. Sütun adlarını standartlaştır
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

        # Gerekli temel sütunların varlığını kontrol et
        gerekliler = ["tarih", "open", "high", "low", "close"]
        for g in gerekliler:
            if g not in df.columns:
                return None

        df = df.dropna(subset=["close"])
        return df
    except Exception as e:
        return None
