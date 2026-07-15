def donusum_noktalari_hesapla(df):
    # Sadece hesaplama yap, session_state'e burada dokunma
    close = df['Close']
    son_20 = close.tail(20)
    return {
        "destek": float(son_20.min()),
        "direnc": float(son_20.max()),
        "fiyat": float(close.iloc[-1])
    }
