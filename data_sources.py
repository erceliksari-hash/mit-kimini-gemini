@st.cache_data(ttl=3600)
def veri_cek(sembol):
    try:
        # 'auto_adjust' parametresi ile veriyi temizleyin
        df = yf.download(sembol, period="1mo", auto_adjust=True, progress=False)
        if df is None or df.empty:
            return None
        # Sütunları düzelt (MultiIndex sorununu engellemek için)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df
    except Exception:
        return None
