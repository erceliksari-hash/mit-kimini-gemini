
data_sources_py = '''import pandas as pd
import yfinance as yf


def veri_cek(sembol, aralik="1d", periyot=None):
    """
    Belirtilen sembol için yfinance üzerinden veri çeker.
    
    Parametreler:
        sembol: Varlık kodu (örn: BTC-USD, THYAO.IS)
        aralik: Zaman dilimi (1m, 5m, 15m, 30m, 1h, 4h, 1d)
        periyot: Veri periyodu (örn: 60d, 1y). None ise otomatik hesaplanır.
    """
    try:
        # BIST hisseleri (.IS) için saatlik veri YF'da yoktur
        if ".IS" in sembol.upper() and aralik in ["1m", "5m", "15m", "30m", "1h", "4h"]:
            aralik = "1d"
        
        # Periyot otomatik belirleme
        if periyot is None:
            if aralik in ["1m", "5m"]:
                periyot = "5d"
            elif aralik in ["15m", "30m", "1h"]:
                periyot = "60d"
            elif aralik == "4h":
                periyot = "120d"
            else:
                periyot = "2y"
        
        df = yf.download(sembol, period=periyot, interval=aralik, progress=False)
        
        if df is None or df.empty:
            return None
        
        # MultiIndex düzeltme
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [col[0] for col in df.columns]
        
        # Index'i sütuna çevir
        df.reset_index(inplace=True)
        
        # Sütun adlarını standartlaştır
        kolon_eslestirme = {
            "Datetime": "tarih",
            "Date": "tarih",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
            "Adj Close": "adj_close"
        }
        df.rename(columns=kolon_eslestirme, inplace=True)
        
        # Gerekli sütunları kontrol et
        gerekliler = ["tarih", "open", "high", "low", "close"]
        for g in gerekliler:
            if g not in df.columns:
                return None
        
        # Sayısal sütunları float'a çevir
        for kol in ["open", "high", "low", "close", "volume"]:
            if kol in df.columns:
                df[kol] = pd.to_numeric(df[kol], errors="coerce")
        
        df = df.dropna(subset=["close"]).reset_index(drop=True)
        
        return df
        
    except Exception as e:
        print(f"[VERI HATASI] {sembol} ({aralik}): {e}")
        return None
'''

with open("/mnt/agents/output/data_sources.py", "w", encoding="utf-8") as f:
    f.write(data_sources_py)

print("✅ data_sources.py oluşturuldu")
