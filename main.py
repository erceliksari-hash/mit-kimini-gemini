import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd

st.set_page_config(page_title="Finans Veri Ajanı", page_icon="📊", layout="wide")

# ============================================
# MODÜLLERİ İMPORT ET
# ============================================
from utils.indicators import (
    sma, ema, rsi, macd, bollinger, adx, stochastic, atr,
    ichimoku, vwap, supertrend, parabolic_sar, williams_r,
    fibonacci_retracement, obv, mfi, cci
)
from utils.data_sources import (
    YahooFinanceKaynagi, AlphaVantageKaynagi, TwelveDataKaynagi,
    InvestingComKaynagi, InvestingComAnlik, MockVeriKaynagi,
    AkilliVeriKoordinatoru, anlik_fiyat_cek
)
from utils.investing_assets import kategorik_varlik_listesi, sembol_isim_map
from utils.signals import SinyalTespit, donusum_noktalari_bul
from utils.telegram_notifier import TelegramNotifier, telegram_setup_yardimcisi

# ============================================
# SESSION STATE BAŞLATMA
# ============================================
def init_session_state():
    # Varsayılan takip listesi
    if "takip_listesi" not in st.session_state:
        st.session_state.takip_listesi = [
            {"sembol": "AAPL", "isim": "Apple", "tur": "Hisse (ABD)", "aktif": True},
            {"sembol": "MSFT", "isim": "Microsoft", "tur": "Hisse (ABD)", "aktif": True},
            {"sembol": "TSLA", "isim": "Tesla", "tur": "Hisse (ABD)", "aktif": True},
            {"sembol": "NVDA", "isim": "NVIDIA", "tur": "Hisse (ABD)", "aktif": True},
            {"sembol": "THYAO.IS", "isim": "Turk Hava Yollari", "tur": "BIST 100", "aktif": True},
            {"sembol": "GARAN.IS", "isim": "Garanti BBVA", "tur": "BIST 100", "aktif": True},
            {"sembol": "ASELS.IS", "isim": "Aselsan", "tur": "BIST 100", "aktif": True},
            {"sembol": "BTC-USD", "isim": "Bitcoin", "tur": "Kripto", "aktif": True},
            {"sembol": "ETH-USD", "isim": "Ethereum", "tur": "Kripto", "aktif": True},
            {"sembol": "GC=F", "isim": "Altin", "tur": "Emtia", "aktif": True},
            {"sembol": "EURUSD=X", "isim": "EUR/USD", "tur": "Forex", "aktif": True},
            {"sembol": "USDTRY=X", "isim": "USD/TRY", "tur": "Forex", "aktif": True},
            {"sembol": "XU100.IS", "isim": "BIST 100 Endeks", "tur": "Endeks", "aktif": True},
            {"sembol": "^GSPC", "isim": "S&P 500", "tur": "Endeks", "aktif": True},
        ]

    # Temel indikatörler
    if "indikatorler" not in st.session_state:
        st.session_state.indikatorler = {
            "sma_20": {"aktif": True, "period": 20, "color": "#FFA500", "panel": "ana"},
            "sma_50": {"aktif": False, "period": 50, "color": "#00CED1", "panel": "ana"},
            "sma_200": {"aktif": False, "period": 200, "color": "#4169E1", "panel": "ana"},
            "ema_12": {"aktif": False, "period": 12, "color": "#FF69B4", "panel": "ana"},
            "ema_26": {"aktif": False, "period": 26, "color": "#DC143C", "panel": "ana"},
            "rsi": {"aktif": False, "period": 14, "color": "#9370DB", "panel": "alt"},
            "macd": {"aktif": False, "fast": 12, "slow": 26, "signal": 9, "panel": "alt"},
            "bollinger": {"aktif": False, "period": 20, "std": 2, "color": "#20B2AA", "panel": "ana"},
            "adx": {"aktif": False, "period": 14, "color": "#FF4500", "panel": "alt"},
            "stochastic": {"aktif": False, "k_period": 14, "d_period": 3, "panel": "alt"},
            "atr": {"aktif": False, "period": 14, "color": "#FF8C00", "panel": "alt"},
            "ichimoku": {"aktif": False, "panel": "ana"},
            "vwap": {"aktif": False, "color": "#8A2BE2", "panel": "ana"},
            "supertrend": {"aktif": False, "period": 10, "multiplier": 3.0, "panel": "ana"},
            "parabolic_sar": {"aktif": False, "af": 0.02, "max_af": 0.2, "panel": "ana"},
            "williams_r": {"aktif": False, "period": 14, "panel": "alt"},
            "obv": {"aktif": False, "panel": "alt"},
            "mfi": {"aktif": False, "period": 14, "panel": "alt"},
            "cci": {"aktif": False, "period": 20, "panel": "alt"},
            "fibonacci": {"aktif": False, "panel": "ana"},
        }

    # Özel indikatörler
    if "custom_indikatorler" not in st.session_state:
        st.session_state.custom_indikatorler = {}

    # Sinyal tespit sistemi
    if "sinyal_tespit" not in st.session_state:
        st.session_state.sinyal_tespit = SinyalTespit()

    # Telegram notifier
    if "telegram" not in st.session_state:
        st.session_state.telegram = TelegramNotifier()

    # Son sinyal bildirim zamanları (tekrar önlemek için)
    if "son_sinyal_zamani" not in st.session_state:
        st.session_state.son_sinyal_zamani = {}

    # Sinyal geçmişi
    if "sinyal_gecmisi" not in st.session_state:
        st.session_state.sinyal_gecmisi = []


init_session_state()

# Varlık kütüphanesi
VARLIK_KUTUPHANESI = kategorik_varlik_listesi()


# ============================================
# OZEL İNDİKATÖR FONKSİYONLARI
# ============================================
def custom_indikator_ekle(isim: str, kod: str) -> tuple[bool, str]:
    try:
        local_ns = {}
        import_dict = {
            "pd": pd, "np": __import__("numpy"),
            "sma": sma, "ema": ema, "rsi": rsi, "macd": macd, "bollinger": bollinger,
            "adx": adx, "stochastic": stochastic, "atr": atr, "ichimoku": ichimoku,
            "vwap": vwap, "supertrend": supertrend, "parabolic_sar": parabolic_sar,
            "williams_r": williams_r, "obv": obv, "mfi": mfi, "cci": cci
        }
        exec(kod, import_dict, local_ns)

        func = None
        for key, val in local_ns.items():
            if callable(val) and not key.startswith('_'):
                func = val
                break

        if func is None:
            return False, "Fonksiyon bulunamadi. 'def indikator_adi(df, ...)' seklinde tanimlayin."

        st.session_state.custom_indikatorler[isim] = {
            "fonksiyon": func, "kod": kod, "aktif": True,
            "color": "#FFD700", "tip": "cizgi", "panel": "ana"
        }
        return True, f"✅ '{isim}' indikatoru eklendi!"
    except Exception as e:
        return False, f"❌ Hata: {e}"


def custom_indikator_sil(isim: str) -> bool:
    if isim in st.session_state.custom_indikatorler:
        del st.session_state.custom_indikatorler[isim]
        return True
    return False


# ============================================
# STREAMLIT UI
# ============================================
def main():
    st.title("📊 Çok Kaynaklı Finans Veri Ajanı v6.0")
    st.markdown("**Investing.com → Twelve Data → Alpha Vantage → Yahoo Finance → Mock** sırasıyla en güvenilir veriyi bulur.")

    # ==================== SIDEBAR ====================
    with st.sidebar:
        st.header("⚙️ Ayarlar")

        # API Anahtarları
        with st.expander("🔑 API Anahtarları", expanded=False):
            alpha_key = st.text_input("Alpha Vantage API Key", type="password", key="alpha_key")
            twelve_key = st.text_input("Twelve Data API Key", type="password", key="twelve_key")

        # Telegram Ayarları
        with st.expander("📱 Telegram Bildirimleri", expanded=False):
            st.markdown("<small>" + telegram_setup_yardimcisi() + "</small>", unsafe_allow_html=True)

            tg_token = st.text_input("Bot Token", type="password", key="tg_token")
            tg_chat_id = st.text_input("Chat ID", key="tg_chat_id")

            if tg_token and tg_chat_id:
                st.session_state.telegram.ayarla(tg_token, tg_chat_id)

            if st.button("🔗 Bağlantıyı Test Et", key="tg_test"):
                if st.session_state.telegram.aktif_mi():
                    with st.spinner("Test ediliyor..."):
                        ok, msg = st.session_state.telegram.test_baglantisi()
                        if ok:
                            st.success(msg)
                        else:
                            st.error(msg)
                else:
                    st.error("Bot token ve Chat ID girin!")

            if st.session_state.telegram.aktif_mi():
                st.success("✅ Telegram aktif")

        # Zaman Dilimi
        periyot = st.selectbox(
            "Zaman Dilimi",
            ["1d", "1h", "15m", "5m", "1m"],
            format_func=lambda x: {"1d": "📅 Günlük", "1h": "🕐 Saatlik",
                                   "15m": "⏱️ 15 Dakika", "5m": "⏱️ 5 Dakika", "1m": "⏱️ 1 Dakika"}[x]
        )

        st.divider()

        # ==================== İNDİKATÖRLER ====================
        st.subheader("📈 Teknik İndikatörler")

        # Ana Panel İndikatörleri
        with st.expander("📊 Ana Grafik İndikatörleri", expanded=True):
            col1, col2 = st.columns(2)
            with col1:
                st.session_state.indikatorler["sma_20"]["aktif"] = st.checkbox(
                    "SMA 20", value=st.session_state.indikatorler["sma_20"]["aktif"], key="chk_sma20")
                st.session_state.indikatorler["sma_50"]["aktif"] = st.checkbox(
                    "SMA 50", value=st.session_state.indikatorler["sma_50"]["aktif"], key="chk_sma50")
                st.session_state.indikatorler["sma_200"]["aktif"] = st.checkbox(
                    "SMA 200", value=st.session_state.indikatorler["sma_200"]["aktif"], key="chk_sma200")
                st.session_state.indikatorler["ema_12"]["aktif"] = st.checkbox(
                    "EMA 12", value=st.session_state.indikatorler["ema_12"]["aktif"], key="chk_ema12")
                st.session_state.indikatorler["ema_26"]["aktif"] = st.checkbox(
                    "EMA 26", value=st.session_state.indikatorler["ema_26"]["aktif"], key="chk_ema26")
            with col2:
                st.session_state.indikatorler["bollinger"]["aktif"] = st.checkbox(
                    "Bollinger Bantları", value=st.session_state.indikatorler["bollinger"]["aktif"], key="chk_bb")
                st.session_state.indikatorler["ichimoku"]["aktif"] = st.checkbox(
                    "Ichimoku Bulutu", value=st.session_state.indikatorler["ichimoku"]["aktif"], key="chk_ichi")
                st.session_state.indikatorler["vwap"]["aktif"] = st.checkbox(
                    "VWAP", value=st.session_state.indikatorler["vwap"]["aktif"], key="chk_vwap")
                st.session_state.indikatorler["supertrend"]["aktif"] = st.checkbox(
                    "SuperTrend", value=st.session_state.indikatorler["supertrend"]["aktif"], key="chk_st")
                st.session_state.indikatorler["parabolic_sar"]["aktif"] = st.checkbox(
                    "Parabolic SAR", value=st.session_state.indikatorler["parabolic_sar"]["aktif"], key="chk_psar")
                st.session_state.indikatorler["fibonacci"]["aktif"] = st.checkbox(
                    "Fibonacci Düzeltme", value=st.session_state.indikatorler["fibonacci"]["aktif"], key="chk_fib")

        # Alt Panel İndikatörleri
        with st.expander("📉 Osilatör İndikatörleri", expanded=False):
            col1, col2 = st.columns(2)
            with col1:
                st.session_state.indikatorler["rsi"]["aktif"] = st.checkbox(
                    "RSI (14)", value=st.session_state.indikatorler["rsi"]["aktif"], key="chk_rsi")
                st.session_state.indikatorler["macd"]["aktif"] = st.checkbox(
                    "MACD", value=st.session_state.indikatorler["macd"]["aktif"], key="chk_macd")
                st.session_state.indikatorler["stochastic"]["aktif"] = st.checkbox(
                    "Stochastic (14,3)", value=st.session_state.indikatorler["stochastic"]["aktif"], key="chk_stoch")
            with col2:
                st.session_state.indikatorler["adx"]["aktif"] = st.checkbox(
                    "ADX (14)", value=st.session_state.indikatorler["adx"]["aktif"], key="chk_adx")
                st.session_state.indikatorler["williams_r"]["aktif"] = st.checkbox(
                    "Williams %R (14)", value=st.session_state.indikatorler["williams_r"]["aktif"], key="chk_wr")
                st.session_state.indikatorler["cci"]["aktif"] = st.checkbox(
                    "CCI (20)", value=st.session_state.indikatorler["cci"]["aktif"], key="chk_cci")
                st.session_state.indikatorler["mfi"]["aktif"] = st.checkbox(
                    "MFI (14)", value=st.session_state.indikatorler["mfi"]["aktif"], key="chk_mfi")

        # Hacim İndikatörleri
        with st.expander("📊 Hacim İndikatörleri", expanded=False):
            st.session_state.indikatorler["obv"]["aktif"] = st.checkbox(
                "OBV", value=st.session_state.indikatorler["obv"]["aktif"], key="chk_obv")
            st.session_state.indikatorler["atr"]["aktif"] = st.checkbox(
                "ATR (14)", value=st.session_state.indikatorler["atr"]["aktif"], key="chk_atr")

        st.divider()

        # ==================== ÖZEL İNDİKATÖR ====================
        st.subheader("➕ Özel İndikatör Ekle")
        with st.expander("Yeni İndikatör", expanded=False):
            yeni_isim = st.text_input("İndikatör Adı", placeholder="ornek_indikator", key="custom_name")

            ornek_kodu = '''def my_indicator(df, period=14):
    """
    Kendi indikatörünüzü buraya yazın.
    df parametresi veri çerçevesini içerir.
    pd.Series döndürmelidir.
    """
    close = df['Close']
    return close.rolling(window=period).mean()
'''
            yeni_kod = st.text_area("Python Kodu", height=250, value=ornek_kodu, key="custom_code")

            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("💾 Kaydet", use_container_width=True, key="btn_save_custom"):
                    if yeni_isim and yeni_kod:
                        ok, msg = custom_indikator_ekle(yeni_isim, yeni_kod)
                        if ok:
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)
                    else:
                        st.warning("İsim ve kod gerekli!")
            with col_b:
                if st.button("🧪 Test Et", use_container_width=True, key="btn_test_custom"):
                    if yeni_isim and yeni_kod:
                        ok, msg = custom_indikator_ekle(f"_test_{yeni_isim}", yeni_kod)
                        if ok:
                            st.success("Kod derleme başarılı!")
                            custom_indikator_sil(f"_test_{yeni_isim}")
                        else:
                            st.error(msg)
                    else:
                        st.warning("İsim ve kod gerekli!")

        # Kayıtlı özel indikatörler
        if st.session_state.custom_indikatorler:
            st.markdown("---")
            st.caption("📌 Kayıtlı Özel İndikatörlerim:")
            for isim, ind in list(st.session_state.custom_indikatorler.items()):
                col_x, col_y = st.columns([3, 1])
                with col_x:
                    ind["aktif"] = st.checkbox(
                        f"🔧 {isim}", value=ind.get("aktif", True), key=f"custom_{isim}")
                with col_y:
                    if st.button("🗑️", key=f"del_custom_{isim}"):
                        custom_indikator_sil(isim)
                        st.rerun()

        st.divider()

        # ==================== TAKİP LİSTESİ YÖNETİMİ ====================
        st.subheader("📋 Takip Listem")

        # Yeni varlık ekleme - kategorili
        with st.expander("➕ Varlık Ekle (Kategorili)", expanded=False):
            kategori_sec = st.selectbox("Kategori Seç", list(VARLIK_KUTUPHANESI.keys()), key="add_cat")
            varliklar = VARLIK_KUTUPHANESI.get(kategori_sec, [])
            if varliklar:
                varlik_sec = st.selectbox(
                    "Varlık Seç", varliklar, format_func=lambda x: f"{x[0]} - {x[1]}", key="add_var")
                if st.button("Listeye Ekle", use_container_width=True, key="btn_add"):
                    mevcut_semboller = [v["sembol"] for v in st.session_state.takip_listesi]
                    if varlik_sec[0] not in mevcut_semboller:
                        st.session_state.takip_listesi.append({
                            "sembol": varlik_sec[0], "isim": varlik_sec[1],
                            "tur": kategori_sec, "aktif": True
                        })
                        st.success(f"✅ {varlik_sec[1]} eklendi!")
                        st.rerun()
                    else:
                        st.warning("⚠️ Zaten listede!")
            else:
                st.info("Bu kategoride varlık bulunamadı.")

        # Serbest ekleme
        with st.expander("➕ Sembol ile Ekle", expanded=False):
            serbest_sembol = st.text_input("Sembol (örn: AAPL, BTC-USD)", key="free_symbol")
            serbest_isim = st.text_input("İsim (isteğe bağlı)", key="free_name")
            serbest_kategori = st.text_input("Kategori (isteğe bağlı)", value="Diğer", key="free_cat")
            if st.button("Ekle", use_container_width=True, key="btn_free_add"):
                if serbest_sembol:
                    mevcut = [v["sembol"] for v in st.session_state.takip_listesi]
                    if serbest_sembol.upper() not in [m.upper() for m in mevcut]:
                        st.session_state.takip_listesi.append({
                            "sembol": serbest_sembol.upper(),
                            "isim": serbest_isim or serbest_sembol.upper(),
                            "tur": serbest_kategori, "aktif": True
                        })
                        st.success(f"✅ {serbest_sembol.upper()} eklendi!")
                        st.rerun()
                    else:
                        st.warning("⚠️ Zaten listede!")

        # Mevcut liste
        st.markdown("---")
        for i, varlik in enumerate(st.session_state.takip_listesi):
            col_a, col_b, col_c = st.columns([4, 1, 1])
            with col_a:
                aktif = st.checkbox(
                    f"**{varlik['sembol']}**",
                    value=varlik.get("aktif", True),
                    key=f"aktif_{i}",
                    label_visibility="visible"
                )
                st.session_state.takip_listesi[i]["aktif"] = aktif
                st.caption(f"{varlik['isim']} | {varlik['tur']}")
            with col_b:
                if st.button("🗑️", key=f"sil_{i}", help=f"{varlik['isim']} sil"):
                    st.session_state.takip_listesi.pop(i)
                    st.rerun()

        st.divider()

        # Sinyal ayarları
        st.subheader("🔔 Sinyal Ayarları")
        sinyal_aktif = st.checkbox("Sinyal Tespiti Aktif", value=True, key="sinyal_aktif")
        telegram_bildirim = st.checkbox("Telegram Bildirimleri", value=False, key="tg_bildirim")
        if st.button("🔄 Sinyalleri Sıfırla", key="reset_signals"):
            st.session_state.sinyal_tespit = SinyalTespit()
            st.session_state.son_sinyal_zamani = {}
            st.session_state.sinyal_gecmisi = []
            st.success("Sinyal geçmişi sıfırlandı!")

        st.divider()
        use_mock = st.checkbox("🧪 Mock Veri Kullan (Test)", value=False)

    # ==================== ANA İÇERİK ====================

    # Sekme yapısı
    tab1, tab2, tab3 = st.tabs(["💰 Piyasa Özeti", "📊 Grafik Analizi", "🔔 Sinyaller"])

    # ========== TAB 1: PİYASA ÖZETİ ==========
    with tab1:
        st.subheader("💰 Anlık Piyasa Verileri")
        aktif_varliklar = [v for v in st.session_state.takip_listesi if v.get("aktif", True)]

        if aktif_varliklar:
            cols_per_row = 4
            rows = [aktif_varliklar[i:i+cols_per_row] for i in range(0, len(aktif_varliklar), cols_per_row)]

            for row in rows:
                cols = st.columns(len(row))
                for col, varlik in zip(cols, row):
                    with col:
                        with st.spinner(f"⏳ {varlik['sembol']}..."):
                            veri = anlik_fiyat_cek(varlik["sembol"], alpha_key, twelve_key)

                        if veri.get("hata"):
                            st.error(f"❌ {varlik['sembol']}: Veri alınamadı")
                        else:
                            fiyat = veri["fiyat"]
                            degisim = veri["degisim"]
                            degisim_yuzde = veri["degisim_yuzde"]
                            kaynak = veri.get("kaynak", "Bilinmiyor")
                            renk = "🟢" if degisim >= 0 else "🔴"
                            isaret = "+" if degisim >= 0 else ""

                            st.metric(
                                label=f"{renk} {varlik['isim']} ({varlik['sembol']})",
                                value=f"{fiyat:,.4f}" if fiyat < 1 else f"{fiyat:,.2f}",
                                delta=f"{isaret}{degisim_yuzde:.2f}% ({isaret}{degisim:,.4f})" if fiyat < 1 else f"{isaret}{degisim_yuzde:.2f}% ({isaret}{degisim:,.2f})",
                                delta_color="normal"
                            )
                            st.caption(f"📡 {kaynak} | Hacim: {veri['hacim']:,} | Yüksek: {veri['yuksek']:.2f} | Düşük: {veri['dusuk']:.2f}")

                            # Sinyal kontrolü
                            if sinyal_aktif:
                                try:
                                    koordinator = AkilliVeriKoordinatoru()
                                    koordinator.kaynak_ekle(YahooFinanceKaynagi(), 4)
                                    if use_mock:
                                        koordinator.kaynak_ekle(MockVeriKaynagi(), 99)
                                    paket = koordinator.veri_cek(varlik["sembol"], "1d")
                                    df_mini = paket.veri

                                    if len(df_mini) > 50:
                                        sinyal = st.session_state.sinyal_tespit.sinyal_kontrol(
                                            varlik["sembol"], varlik["isim"], df_mini)

                                        if sinyal and telegram_bildirim and st.session_state.telegram.aktif_mi():
                                            # Son 5 dakika içinde bildirim gönderildiyse tekrar gönderme
                                            son_zaman = st.session_state.son_sinyal_zamani.get(varlik["sembol"])
                                            simdi = pd.Timestamp.now()
                                            if son_zaman is None or (simdi - son_zaman).total_seconds() > 300:
                                                st.session_state.telegram.sinyal_bildirimi(
                                                    sinyal.sembol, sinyal.isim, sinyal.tipi,
                                                    sinyal.fiyat, sinyal.detay)
                                                st.session_state.son_sinyal_zamani[varlik["sembol"]] = simdi
                                                st.session_state.sinyal_gecmisi.append({
                                                    "sembol": sinyal.sembol,
                                                    "isim": sinyal.isim,
                                                    "tipi": sinyal.tipi,
                                                    "fiyat": sinyal.fiyat,
                                                    "tarih": simdi,
                                                    "detay": sinyal.detay
                                                })
                                except:
                                    pass
        else:
            st.info("📭 Takip listeniz boş. Sidebar'dan varlık ekleyin.")

    # ========== TAB 2: GRAFİK ANALİZİ ==========
    with tab2:
        st.subheader("📊 Detaylı Grafik")

        secenekler = [(v["sembol"], f"{v['isim']} ({v['sembol']})") for v in st.session_state.takip_listesi]
        if secenekler:
            secili = st.selectbox("Grafik için sembol seç", secenekler, format_func=lambda x: x[1], key="grafik_secim")
            secili_sembol = secili[0]
        else:
            secili_sembol = st.text_input("Sembol girin (örn: AAPL)", value="AAPL", key="grafik_manual")

        if st.button("🚀 Grafiği Çiz", type="primary", use_container_width=True):
            with st.spinner("Tüm kaynaklar deneniyor..."):
                koordinator = AkilliVeriKoordinatoru()
                koordinator.kaynak_ekle(InvestingComKaynagi(), 1)
                if twelve_key:
                    koordinator.kaynak_ekle(TwelveDataKaynagi(twelve_key), 2)
                if alpha_key:
                    koordinator.kaynak_ekle(AlphaVantageKaynagi(alpha_key), 3)
                koordinator.kaynak_ekle(YahooFinanceKaynagi(), 4)
                if use_mock:
                    koordinator.kaynak_ekle(MockVeriKaynagi(), 99)

                try:
                    paket = koordinator.veri_cek(secili_sembol, periyot)
                    df = paket.veri

                    # Bilgi kartları
                    col1, col2, col3, col4 = st.columns(4)
                    col1.metric("📡 Kaynak", paket.kaynak)
                    col2.metric("⏱️ Gecikme", paket.gecikme)
                    col3.metric("📊 Veri Sayısı", f"{len(df)} satır")
                    col4.metric("💵 Son Kapanış", f"{df['Close'].iloc[-1]:.4f}" if df['Close'].iloc[-1] < 1 else f"{df['Close'].iloc[-1]:.2f}")

                    st.success(f"✅ {paket.kaynak} üzerinden veri alındı!")

                    # Dönüşüm noktaları analizi
                    with st.spinner("Dönüşüm noktaları analiz ediliyor..."):
                        donusumler = donusum_noktalari_bul(df)

                    # Seviye kartları
                    seviye_col1, seviye_col2, seviye_col3, seviye_col4 = st.columns(4)
                    simdiki = donusumler["simdiki_fiyat"]
                    destek = donusumler["aktif_destek"]
                    direnc = donusumler["aktif_direnc"]

                    seviye_col1.metric("📍 Şimdiki Fiyat", f"{simdiki:.2f}")
                    seviye_col2.metric("🟢 Destek", f"{destek:.2f}", delta=f"-{donusumler['destek_mesafe']:.1f}%", delta_color="inverse")
                    seviye_col3.metric("🔴 Direnç", f"{direnc:.2f}", delta=f"+{donusumler['direnc_mesafe']:.1f}%", delta_color="inverse")

                    if donusumler.get("sinyal"):
                        sinyal_renk = {"AL": "🟢", "SAT": "🔴"}
                        seviye_col4.markdown(f"### {sinyal_renk.get(donusumler['sinyal'], '⚪')} {donusumler['sinyal']}")
                    else:
                        seviye_col4.metric("⚖️ Durum", "Nötr")

                    trend_emoji = {"yukselis": "📈", "dusus": "📉", "notr": "⚖️"}
                    st.info(f"{trend_emoji.get(donusumler['trend'], '⚪')} Mevcut Trend: {donusumler['trend'].upper()}")

                    # İndikatör analizi
                    if len(df) > 50 and sinyal_aktif:
                        with st.spinner("İndikatör analizi yapılıyor..."):
                            analiz = st.session_state.sinyal_tespit.tum_indikator_analiz(df)
                            if "indikatorler" in analiz:
                                with st.expander("📊 İndikatör Değerleri", expanded=False):
                                    ind_cols = st.columns(4)
                                    idx = 0
                                    for key, val in analiz["indikatorler"].items():
                                        with ind_cols[idx % 4]:
                                            st.metric(key, f"{val}")
                                        idx += 1

                                if analiz.get("sinyaller"):
                                    sinyal_emojiler = {"YUKSELIS": "🟢", "DUSUS": "🔴"}
                                    st.markdown("**🔔 Tespit Edilen Sinyaller:**")
                                    for s in analiz["sinyaller"][:5]:
                                        st.markdown(f"{sinyal_emojiler.get(s['tip'], '⚪')} **{s['kaynak']}**: {s['mesaj']}")

                    # Grafik çizimi
                    aktif_indikatorler = {k: v for k, v in st.session_state.indikatorler.items() if v["aktif"]}
                    alt_panel_sayisi = sum(1 for v in aktif_indikatorler.values() if v.get("panel") == "alt")
                    alt_panel_isimleri = [k for k, v in aktif_indikatorler.items() if v.get("panel") == "alt"]

                    rows = 1 + alt_panel_sayisi
                    row_heights = [0.55] + [0.15] * alt_panel_sayisi

                    fig = make_subplots(
                        rows=rows, cols=1,
                        shared_xaxes=True,
                        vertical_spacing=0.03,
                        row_heights=row_heights,
                        subplot_titles=[f"{secili_sembol} - {periyot}"] + alt_panel_isimleri
                    )

                    # Candlestick
                    fig.add_trace(go.Candlestick(
                        x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'],
                        name=secili_sembol, increasing_line_color='#26a69a', decreasing_line_color='#ef5350'
                    ), row=1, col=1)

                    close = df['Close']

                    # SMA 20
                    if st.session_state.indikatorler["sma_20"]["aktif"]:
                        sma20 = sma(close, 20)
                        fig.add_trace(go.Scatter(x=df.index, y=sma20, mode='lines', name="SMA 20",
                                                  line=dict(color="#FFA500", width=1.5)), row=1, col=1)

                    # SMA 50
                    if st.session_state.indikatorler["sma_50"]["aktif"]:
                        sma50 = sma(close, 50)
                        fig.add_trace(go.Scatter(x=df.index, y=sma50, mode='lines', name="SMA 50",
                                                  line=dict(color="#00CED1", width=1.5)), row=1, col=1)

                    # SMA 200
                    if st.session_state.indikatorler["sma_200"]["aktif"]:
                        sma200 = sma(close, 200)
                        fig.add_trace(go.Scatter(x=df.index, y=sma200, mode='lines', name="SMA 200",
                                                  line=dict(color="#4169E1", width=1.5)), row=1, col=1)

                    # EMA 12
                    if st.session_state.indikatorler["ema_12"]["aktif"]:
                        ema12 = ema(close, 12)
                        fig.add_trace(go.Scatter(x=df.index, y=ema12, mode='lines', name="EMA 12",
                                                  line=dict(color="#FF69B4", width=1.5)), row=1, col=1)

                    # EMA 26
                    if st.session_state.indikatorler["ema_26"]["aktif"]:
                        ema26 = ema(close, 26)
                        fig.add_trace(go.Scatter(x=df.index, y=ema26, mode='lines', name="EMA 26",
                                                  line=dict(color="#DC143C", width=1.5)), row=1, col=1)

                    # Bollinger Bantları
                    if st.session_state.indikatorler["bollinger"]["aktif"]:
                        ust, orta, alt = bollinger(close, 20, 2)
                        fig.add_trace(go.Scatter(x=df.index, y=ust, mode='lines', name="BB Üst",
                                                  line=dict(color="#20B2AA", width=1, dash='dash')), row=1, col=1)
                        fig.add_trace(go.Scatter(x=df.index, y=alt, mode='lines', name="BB Alt",
                                                  line=dict(color="#20B2AA", width=1, dash='dash'),
                                                  fill='tonexty', fillcolor="rgba(32, 178, 170, 0.1)"), row=1, col=1)
                        fig.add_trace(go.Scatter(x=df.index, y=orta, mode='lines', name="BB Orta",
                                                  line=dict(color="#20B2AA", width=1.5)), row=1, col=1)

                    # Ichimoku Bulutu
                    if st.session_state.indikatorler["ichimoku"]["aktif"]:
                        tenkan, kijun, senkou_a, senkou_b, chikou = ichimoku(df)
                        # Senkou Span A ve B arasını doldur
                        fig.add_trace(go.Scatter(x=df.index, y=senkou_a, mode='lines', name="Senkou A",
                                                  line=dict(color="#1E90FF", width=1)), row=1, col=1)
                        fig.add_trace(go.Scatter(x=df.index, y=senkou_b, mode='lines', name="Senkou B",
                                                  line=dict(color="#FF6347", width=1),
                                                  fill='tonexty', fillcolor="rgba(30, 144, 255, 0.1)"), row=1, col=1)
                        fig.add_trace(go.Scatter(x=df.index, y=tenkan, mode='lines', name="Tenkan",
                                                  line=dict(color="#FFD700", width=1)), row=1, col=1)
                        fig.add_trace(go.Scatter(x=df.index, y=kijun, mode='lines', name="Kijun",
                                                  line=dict(color="#FF69B4", width=1.5)), row=1, col=1)

                    # VWAP
                    if st.session_state.indikatorler["vwap"]["aktif"]:
                        vwap_val = vwap(df)
                        fig.add_trace(go.Scatter(x=df.index, y=vwap_val, mode='lines', name="VWAP",
                                                  line=dict(color="#8A2BE2", width=1.5)), row=1, col=1)

                    # SuperTrend
                    if st.session_state.indikatorler["supertrend"]["aktif"]:
                        st_val, st_trend = supertrend(df, 10, 3.0)
                        fig.add_trace(go.Scatter(x=df.index, y=st_val, mode='lines', name="SuperTrend",
                                                  line=dict(color="#FF4500", width=1.5)), row=1, col=1)

                    # Parabolic SAR
                    if st.session_state.indikatorler["parabolic_sar"]["aktif"]:
                        psar = parabolic_sar(df, 0.02, 0.2)
                        fig.add_trace(go.Scatter(x=df.index, y=psar, mode='markers', name="Parabolic SAR",
                                                  marker=dict(color="#9932CC", size=4, symbol='diamond')), row=1, col=1)

                    # Fibonacci Düzeltme Seviyeleri
                    if st.session_state.indikatorler["fibonacci"]["aktif"]:
                        fib_levels = fibonacci_retracement(df['High'], df['Low'], 100)
                        renkler = {"0%": "red", "23.6%": "orange", "38.2%": "yellow",
                                   "50%": "blue", "61.8%": "green", "78.6%": "purple", "100%": "red"}
                        for level, value in fib_levels.items():
                            fig.add_hline(y=value, line_dash="dot", line_color=renkler.get(level, "gray"),
                                          annotation_text=f"Fib {level}: {value:.2f}", row=1, col=1)

                    # Destek ve Direnç çizgileri
                    fig.add_hline(y=destek, line_dash="dash", line_color="green",
                                  annotation_text=f"Destek: {destek:.2f}", row=1, col=1)
                    fig.add_hline(y=direnc, line_dash="dash", line_color="red",
                                  annotation_text=f"Direnç: {direnc:.2f}", row=1, col=1)

                    # Dönüşüm noktaları
                    for nokta in donusumler["yukselis_noktalari"][-5:]:
                        fig.add_trace(go.Scatter(
                            x=[nokta["tarih"]], y=[nokta["fiyat"]], mode='markers',
                            marker=dict(symbol='arrow-up', size=15, color='green'),
                            name=f"📈 Yükseliş {nokta['tarih'].strftime('%m-%d')}", showlegend=False
                        ), row=1, col=1)

                    for nokta in donusumler["dusus_noktalari"][-5:]:
                        fig.add_trace(go.Scatter(
                            x=[nokta["tarih"]], y=[nokta["fiyat"]], mode='markers',
                            marker=dict(symbol='arrow-down', size=15, color='red'),
                            name=f"📉 Düşüş {nokta['tarih'].strftime('%m-%d')}", showlegend=False
                        ), row=1, col=1)

                    # Özel indikatörler
                    for isim, ind in st.session_state.custom_indikatorler.items():
                        if ind.get("aktif") and ind.get("panel", "ana") == "ana":
                            try:
                                sonuc = ind["fonksiyon"](df)
                                if isinstance(sonuc, pd.Series):
                                    fig.add_trace(go.Scatter(
                                        x=df.index, y=sonuc, mode='lines', name=f"🔧 {isim}",
                                        line=dict(color=ind.get("color", "#FFD700"), width=1.5)
                                    ), row=1, col=1)
                            except Exception as e:
                                st.warning(f"🔧 {isim} indikatörü çalıştırılamadı: {e}")

                    # Hacim
                    if 'Volume' in df.columns:
                        fig.add_trace(go.Bar(x=df.index, y=df['Volume'], name="Hacim",
                                              marker_color='rgba(100, 100, 100, 0.3)'), row=1, col=1)

                    # ========== ALT PANEL İNDİKATÖRLERİ ==========
                    current_row = 2

                    # RSI
                    if st.session_state.indikatorler["rsi"]["aktif"]:
                        rsi_val = rsi(close, 14)
                        fig.add_trace(go.Scatter(x=df.index, y=rsi_val, mode='lines', name="RSI",
                                                  line=dict(color="#9370DB", width=1.5)), row=current_row, col=1)
                        fig.add_hline(y=70, line_dash="dash", line_color="red", row=current_row, col=1)
                        fig.add_hline(y=30, line_dash="dash", line_color="green", row=current_row, col=1)
                        fig.add_hline(y=50, line_dash="dot", line_color="gray", row=current_row, col=1)
                        fig.update_yaxes(range=[0, 100], row=current_row, col=1)
                        current_row += 1

                    # MACD
                    if st.session_state.indikatorler["macd"]["aktif"]:
                        macd_line, signal_line, histogram = macd(close, 12, 26, 9)
                        fig.add_trace(go.Scatter(x=df.index, y=macd_line, mode='lines', name="MACD",
                                                  line=dict(color='#2196F3', width=1.5)), row=current_row, col=1)
                        fig.add_trace(go.Scatter(x=df.index, y=signal_line, mode='lines', name="Signal",
                                                  line=dict(color='#FF9800', width=1.5)), row=current_row, col=1)
                        fig.add_trace(go.Bar(
                            x=df.index, y=histogram, name="Histogram",
                            marker_color=['#26a69a' if h >= 0 else '#ef5350' for h in histogram.fillna(0)]
                        ), row=current_row, col=1)
                        current_row += 1

                    # ADX
                    if st.session_state.indikatorler["adx"]["aktif"]:
                        adx_val, plus_di, minus_di = adx(df, 14)
                        fig.add_trace(go.Scatter(x=df.index, y=adx_val, mode='lines', name="ADX",
                                                  line=dict(color="#FF4500", width=1.5)), row=current_row, col=1)
                        fig.add_trace(go.Scatter(x=df.index, y=plus_di, mode='lines', name="+DI",
                                                  line=dict(color="green", width=1)), row=current_row, col=1)
                        fig.add_trace(go.Scatter(x=df.index, y=minus_di, mode='lines', name="-DI",
                                                  line=dict(color="red", width=1)), row=current_row, col=1)
                        fig.add_hline(y=25, line_dash="dash", line_color="orange", row=current_row, col=1)
                        current_row += 1

                    # Stochastic
                    if st.session_state.indikatorler["stochastic"]["aktif"]:
                        k, d = stochastic(df, 14, 3)
                        fig.add_trace(go.Scatter(x=df.index, y=k, mode='lines', name="%K",
                                                  line=dict(color="#2196F3", width=1.5)), row=current_row, col=1)
                        fig.add_trace(go.Scatter(x=df.index, y=d, mode='lines', name="%D",
                                                  line=dict(color="#FF9800", width=1.5)), row=current_row, col=1)
                        fig.add_hline(y=80, line_dash="dash", line_color="red", row=current_row, col=1)
                        fig.add_hline(y=20, line_dash="dash", line_color="green", row=current_row, col=1)
                        fig.update_yaxes(range=[0, 100], row=current_row, col=1)
                        current_row += 1

                    # Williams %R
                    if st.session_state.indikatorler["williams_r"]["aktif"]:
                        wr = williams_r(df, 14)
                        fig.add_trace(go.Scatter(x=df.index, y=wr, mode='lines', name="Williams %R",
                                                  line=dict(color="#9932CC", width=1.5)), row=current_row, col=1)
                        fig.add_hline(y=-20, line_dash="dash", line_color="red", row=current_row, col=1)
                        fig.add_hline(y=-80, line_dash="dash", line_color="green", row=current_row, col=1)
                        current_row += 1

                    # CCI
                    if st.session_state.indikatorler["cci"]["aktif"]:
                        cci_val = cci(df, 20)
                        fig.add_trace(go.Scatter(x=df.index, y=cci_val, mode='lines', name="CCI",
                                                  line=dict(color="#FF69B4", width=1.5)), row=current_row, col=1)
                        fig.add_hline(y=100, line_dash="dash", line_color="red", row=current_row, col=1)
                        fig.add_hline(y=-100, line_dash="dash", line_color="green", row=current_row, col=1)
                        current_row += 1

                    # MFI
                    if st.session_state.indikatorler["mfi"]["aktif"]:
                        mfi_val = mfi(df, 14)
                        fig.add_trace(go.Scatter(x=df.index, y=mfi_val, mode='lines', name="MFI",
                                                  line=dict(color="#20B2AA", width=1.5)), row=current_row, col=1)
                        fig.add_hline(y=80, line_dash="dash", line_color="red", row=current_row, col=1)
                        fig.add_hline(y=20, line_dash="dash", line_color="green", row=current_row, col=1)
                        fig.update_yaxes(range=[0, 100], row=current_row, col=1)
                        current_row += 1

                    # ATR
                    if st.session_state.indikatorler["atr"]["aktif"]:
                        atr_val = atr(df, 14)
                        fig.add_trace(go.Scatter(x=df.index, y=atr_val, mode='lines', name="ATR",
                                                  line=dict(color="#FF8C00", width=1.5)), row=current_row, col=1)
                        current_row += 1

                    # OBV
                    if st.session_state.indikatorler["obv"]["aktif"]:
                        obv_val = obv(df)
                        fig.add_trace(go.Scatter(x=df.index, y=obv_val, mode='lines', name="OBV",
                                                  line=dict(color="#4169E1", width=1.5)), row=current_row, col=1)
                        current_row += 1

                    # Özel indikatörler (alt panel)
                    for isim, ind in st.session_state.custom_indikatorler.items():
                        if ind.get("aktif") and ind.get("panel", "ana") == "alt":
                            try:
                                sonuc = ind["fonksiyon"](df)
                                if isinstance(sonuc, pd.Series):
                                    fig.add_trace(go.Scatter(
                                        x=df.index, y=sonuc, mode='lines', name=f"🔧 {isim}",
                                        line=dict(color=ind.get("color", "#FFD700"), width=1.5)
                                    ), row=current_row, col=1)
                                    current_row += 1
                            except Exception as e:
                                st.warning(f"🔧 {isim} indikatörü çalıştırılamadı: {e}")

                    # Layout
                    fig.update_layout(
                        template="plotly_dark",
                        height=600 + (150 * alt_panel_sayisi),
                        showlegend=True,
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                        xaxis_rangeslider_visible=False,
                        dragmode='zoom',
                        hovermode='x unified',
                        margin=dict(l=50, r=50, t=80, b=50),
                    )

                    fig.update_xaxes(rangeslider=dict(visible=False))
                    fig.update_yaxes(title_text="Fiyat", row=1, col=1)

                    # Zaman aralığı butonları
                    fig.update_layout(
                        updatemenus=[
                            dict(
                                type="buttons", direction="left",
                                buttons=[
                                    dict(method="relayout", label="1G", args=[{"xaxis.range": [df.index[-1] - pd.Timedelta(days=1), df.index[-1]]}]),
                                    dict(method="relayout", label="1H", args=[{"xaxis.range": [df.index[-1] - pd.Timedelta(days=7), df.index[-1]]}]),
                                    dict(method="relayout", label="1A", args=[{"xaxis.range": [df.index[-1] - pd.Timedelta(days=30), df.index[-1]]}]),
                                    dict(method="relayout", label="3A", args=[{"xaxis.range": [df.index[-1] - pd.Timedelta(days=90), df.index[-1]]}]),
                                    dict(method="relayout", label="6A", args=[{"xaxis.range": [df.index[-1] - pd.Timedelta(days=180), df.index[-1]]}]),
                                    dict(method="relayout", label="Tümü", args=[{"xaxis.autorange": True}]),
                                ],
                                pad={"r": 10, "t": 10}, showactive=True,
                                x=0.11, xanchor="left", y=1.12, yanchor="top"
                            ),
                            dict(
                                type="buttons", direction="left",
                                buttons=[
                                    dict(method="relayout", args=[{"xaxis.autorange": True, "yaxis.autorange": True}], label="↔️ Sıfırla"),
                                ],
                                pad={"r": 10, "t": 10},
                                x=0.55, xanchor="left", y=1.12, yanchor="top"
                            )
                        ]
                    )

                    st.plotly_chart(fig, use_container_width=True, config={
                        'scrollZoom': True, 'displayModeBar': True,
                        'modeBarButtonsToAdd': ['drawline', 'drawopenpath', 'eraseshape'],
                    })

                    # Ek bilgiler
                    with st.expander("📋 Ham Veriyi Gör", expanded=False):
                        st.dataframe(df.tail(50), use_container_width=True)

                    with st.expander("📈 İstatistikler", expanded=False):
                        st.write(df.describe())

                    with st.expander("🎯 Dönüşüm Noktaları Detayı", expanded=False):
                        col_y, col_d = st.columns(2)
                        with col_y:
                            st.markdown("**📈 Yükseliş Noktaları (Son 5)**")
                            for nokta in donusumler["yukselis_noktalari"][-5:]:
                                st.write(f"  {nokta['tarih'].strftime('%Y-%m-%d')}: {nokta['fiyat']:.2f}")
                        with col_d:
                            st.markdown("**📉 Düşüş Noktaları (Son 5)**")
                            for nokta in donusumler["dusus_noktalari"][-5:]:
                                st.write(f"  {nokta['tarih'].strftime('%Y-%m-%d')}: {nokta['fiyat']:.2f}")

                        st.markdown("---")
                        st.write(f"**Son 20 bar Destek:** {destek:.4f}")
                        st.write(f"**Son 20 bar Direnç:** {direnc:.4f}")

                    st.caption(f"Son güncelleme: {paket.son_guncelleme.strftime('%Y-%m-%d %H:%M:%S')}")

                except Exception as e:
                    st.error(f"❌ Hata: {e}")
                    import traceback
                    st.code(traceback.format_exc())

    # ========== TAB 3: SİNYALLER ==========
    with tab3:
        st.subheader("🔔 Sinyal Geçmişi ve Durumu")

        col1, col2, col3 = st.columns(3)
        sayac = st.session_state.sinyal_tespit.sinyal_sayaci()
        col1.metric("📊 Toplam Sinyal", sayac["toplam"])
        col2.metric("🟢 Yükseliş", sayac["yukselis"])
        col3.metric("🔴 Düşüş", sayac["dusus"])

        st.divider()

        # Son sinyaller tablosu
        if st.session_state.sinyal_gecmisi:
            st.markdown("**📋 Son Bildirilen Sinyaller:**")
            sinyal_data = []
            for s in sorted(st.session_state.sinyal_gecmisi, key=lambda x: x["tarih"], reverse=True)[:20]:
                sinyal_data.append({
                    "Tarih": s["tarih"].strftime("%Y-%m-%d %H:%M"),
                    "Sembol": s["sembol"],
                    "İsim": s["isim"],
                    "Sinyal": s["tipi"],
                    "Fiyat": f"{s['fiyat']:.4f}",
                })
            st.dataframe(pd.DataFrame(sinyal_data), use_container_width=True)
        else:
            st.info("Henüz sinyal kaydedilmedi. Sinyal tespiti aktifse, varlıkların fiyat değişimleri inceleniyor...")

        # Manuel sinyal testi
        with st.expander("🧪 Manuel Telegram Test", expanded=False):
            test_sembol = st.text_input("Test Sembol", value="BTC-USD", key="test_sym")
            test_isim = st.text_input("Test İsim", value="Bitcoin", key="test_name")
            test_tipi = st.selectbox("Sinyal Tipi", ["YUKSELIS", "DUSUS"], key="test_tip")
            test_fiyat = st.number_input("Test Fiyat", value=50000.0, key="test_fiyat")
            if st.button("📨 Test Mesajı Gönder", key="test_tg"):
                if st.session_state.telegram.aktif_mi():
                    ok, msg = st.session_state.telegram.sinyal_bildirimi(
                        test_sembol, test_isim, test_tipi, test_fiyat, "Manuel test mesajı")
                    if ok:
                        st.success("✅ Test mesajı gönderildi!")
                    else:
                        st.error(f"❌ {msg}")
                else:
                    st.error("Telegram ayarları yapılmamış!")

    st.divider()
    st.caption("🔧 Çok Kaynaklı Finans Veri Ajanı v6.0 | Investing.com + 20+ İndikatör + Telegram + Sinyal Sistemi")


if __name__ == "__main__":
    main()
