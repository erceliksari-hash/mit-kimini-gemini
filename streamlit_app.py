import datetime
import json
import os
import threading
import time
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
import streamlit as st

# Proje Modülleri Entegrasyonu
from config import TELEGRAM_CHAT_ID, TELEGRAM_TOKEN
from data_sources import veri_cek
from indicators import (
    hesapla_teknikler,
    piyasa_analizi_yap,
    sinyal_kontrol,
)
from utils import donusum_noktalari_hesapla

st.set_page_config(page_title="Pro Finans Paneli & Algoritmik Bot", layout="wide")
st.markdown(
    """<style>.stApp { background-color: #0e1117; }</style>""",
    unsafe_allow_html=True,
)

# --- AYAR VE VERİ DOSYALARI ---
AYAR_DOSYASI = "ayarlar.json"
PORTFOY_DOSYASI = "portfoy_arsiv.json"
SANAL_PORTFOY_DOSYASI = "sanal_portfoy.json"

VARSAYILAN_AYARLAR = {
    "varliklar": ["AAPL", "BTC-USD", "ETH-USD", "SPY", "THYAO.IS"],
    "zaman_dilimi": "1h",
    "bot_sikligi_dk": 60,
    "oto_trade_aktif": True,
}

VARSAYILAN_SANAL_PORTFOY = {
    "bakiye": 10000.0,
    "baslangic_bakiye": 10000.0,
    "pozisyonlar": {},  # {"BTC-USD": {"maliyet": 60000, "adet": 0.1, "tarih": "...", "sl": 58000, "tp": 65000}}
    "islem_gecmisi": [],
}


# --- DOSYA YÖNETİMİ FONKSİYONLARI ---
def ayarlari_yukle():
    if not os.path.exists(AYAR_DOSYASI):
        with open(AYAR_DOSYASI, "w") as f:
            json.dump(VARSAYILAN_AYARLAR, f)
        return VARSAYILAN_AYARLAR
    try:
        with open(AYAR_DOSYASI, "r") as f:
            return json.load(f)
    except:
        return VARSAYILAN_AYARLAR


def ayarlari_kaydet(ayarlar):
    with open(AYAR_DOSYASI, "w") as f:
        json.dump(ayarlar, f)


def portfoy_yukle():
    if not os.path.exists(PORTFOY_DOSYASI):
        return {}
    try:
        with open(PORTFOY_DOSYASI, "r") as f:
            return json.load(f)
    except:
        return {}


def portfoy_kaydet(portfoy_verisi):
    with open(PORTFOY_DOSYASI, "w") as f:
        json.dump(portfoy_verisi, f)


def sanal_portfoy_yukle():
    if not os.path.exists(SANAL_PORTFOY_DOSYASI):
        with open(SANAL_PORTFOY_DOSYASI, "w") as f:
            json.dump(VARSAYILAN_SANAL_PORTFOY, f)
        return VARSAYILAN_SANAL_PORTFOY
    try:
        with open(SANAL_PORTFOY_DOSYASI, "r") as f:
            return json.load(f)
    except:
        return VARSAYILAN_SANAL_PORTFOY


def sanal_portfoy_kaydet(sanal_verisi):
    with open(SANAL_PORTFOY_DOSYASI, "w") as f:
        json.dump(sanal_verisi, f)


# --- TELEGRAM MESAJ GÖNDERİCİ ---
def telegram_bildirim_gonder(mesaj):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": mesaj,
        "parse_mode": "Markdown",
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except:
        pass


# --- İNTERNETTEN VARLIK ARAMA ---
def internette_varlik_ara(sorgu):
    try:
        url = f"https://query2.finance.yahoo.com/v1/finance/search?q={sorgu}"
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=5)
        data = response.json()
        quotes = data.get("quotes", [])
        sonuclar = []
        for q in quotes:
            symbol = q.get("symbol")
            shortname = q.get("shortname", q.get("longname", symbol))
            exchange = q.get("exchDisp", q.get("exchange", ""))
            if symbol:
                sonuclar.append({
                    "symbol": symbol,
                    "name": shortname,
                    "exchange": exchange,
                })
        return sonuclar
    except:
        return []


# --- DETAYLI TEKNİK ANALİZ VE YORUM OLUŞTURUCU ---
def detayli_analiz_ve_yorum_olustur(varlik, df_t_analiz, p_analiz, p_sinyal):
    fiyat = p_analiz["fiyat"]
    d1 = p_analiz["destek"]
    r1 = p_analiz["direnc"]

    s1 = d1
    s2 = s1 * 0.985
    s3 = s1 * 0.970

    r1_val = r1
    r2 = r1_val * 1.015
    r3 = r1_val * 1.030

    stop_loss = s1 if s1 < fiyat else fiyat * 0.97
    take_profit = r1_val if r1_val > fiyat else fiyat * 1.05

    is_fake = df_t_analiz.iloc[-1].get("sahte_sinyal", False)
    gecis_tarihi = df_t_analiz.iloc[-1].get("tarih", "-")

    sinyal_ust = str(p_sinyal).upper()
    if "AL" in sinyal_ust or "YÜKSELİŞ" in sinyal_ust:
        trend_yorum = "📈 *Yükseliş Trendi Hâkim.* Fiyat yukarı yönlü direnç bölgelerini test ediyor."
        gecis_yorum = f"Yükseliş Teyit Eşiği: `{r1_val:.2f}` üzeri tutunma."
    elif "SAT" in sinyal_ust or "DÜŞÜŞ" in sinyal_ust:
        trend_yorum = "📉 *Düşüş Baskısı Hâkim.* Satış baskısı devam ediyor, destekler takip edilmeli."
        gecis_yorum = f"Düşüş Derinleşme Eşiği: `{s1:.2f}` altı kırılım."
    else:
        trend_yorum = "⚖️ *Yatay / Belirsiz Seyir.* Konsolidasyon alanı içerisinde hareket ediyor."
        gecis_yorum = f"Kırılım Seviyeleri: `{r1_val:.2f}` Üstü Yükseliş | `{s1:.2f}` Altı Düşüş"

    if is_fake:
        sahte_yorum = "⚠️ *SİNYAL UYARISI:* Sahte/Tuzak sinyal tespit edildi! Hacim veya yardımcı indikatör doğrulaması zayıf."
    else:
        sahte_yorum = "✅ *GÜVENİLİR SİNYAL:* İndikatör ve hacim teyidi mevcut."

    rapor_metni = (
        f"🔹 *{varlik}*\n"
        f"   • *Fiyat:* `{fiyat:.2f}` | *Durum:* `{p_sinyal}`\n"
        f"   • *Geçiş Zamanı:* `{gecis_tarihi}`\n"
        f"   • *Destekler:* S1: `{s1:.2f}` | S2: `{s2:.2f}` | S3: `{s3:.2f}`\n"
        f"   • *Dirençler:* R1: `{r1_val:.2f}` | R2: `{r2:.2f}` | R3: `{r3:.2f}`\n"
        f"   • *Stop-Loss (SL):* `{stop_loss:.2f}` | *Take-Profit (TP):* `{take_profit:.2f}`\n"
        f"   • *Geçiş Seviyesi Yorumu:* {gecis_yorum}\n"
        f"   • *Teknik Değerlendirme:* {trend_yorum}\n"
        f"   • *Sinyal Kalitesi:* {sahte_yorum}\n\n"
    )
    return rapor_metni


# --- SANAL OTO-TRADE MOTORU ---
def sanal_oto_trade_isle(varlik, df_t_analiz, p_analiz, p_sinyal):
    ayarlar = ayarlari_yukle()
    if not ayarlar.get("oto_trade_aktif", True):
        return

    sanal = sanal_portfoy_yukle()
    fiyat = p_analiz["fiyat"]
    stop_loss = p_analiz["destek"] if p_analiz["destek"] < fiyat else fiyat * 0.97
    take_profit = p_analiz["direnc"] if p_analiz["direnc"] > fiyat else fiyat * 1.05
    is_fake = df_t_analiz.iloc[-1].get("sahte_sinyal", False)

    pozisyonlar = sanal.get("pozisyonlar", {})
    bakiye = sanal.get("bakiye", 10000.0)
    simdi_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    # 1. MEVCUT POZİSYON KONTROLÜ (Satış / SL / TP Durumları)
    if varlik in pozisyonlar:
        poz = pozisyonlar[varlik]
        maliyet = poz["maliyet"]
        adet = poz["adet"]
        sl = poz.get("sl", maliyet * 0.97)
        tp = poz.get("tp", maliyet * 1.05)

        satis_nedeni = None
        if fiyat <= sl:
            satis_nedeni = "🛑 Stop-Loss Tetiklendi"
        elif fiyat >= tp:
            satis_nedeni = "🎯 Take-Profit (Kâr Al) Tetiklendi"
        elif "SAT" in str(p_sinyal).upper() or "DÜŞÜŞ" in str(p_sinyal).upper():
            satis_nedeni = "📉 Sat Sinyali Geldi"

        if satis_nedeni:
            gelir = adet * fiyat
            harcanan = adet * maliyet
            pnl = gelir - harcanan
            pnl_yuzde = (pnl / harcanan) * 100

            sanal["bakiye"] += gelir
            del sanal["pozisyonlar"][varlik]

            islem_log = {
                "tarih": simdi_str,
                "varlik": varlik,
                "tip": "SATİŞ",
                "neden": satis_nedeni,
                "fiyat": fiyat,
                "adet": adet,
                "pnl": round(pnl, 2),
                "pnl_yuzde": round(pnl_yuzde, 2),
            }
            sanal["islem_gecmisi"].append(islem_log)
            sanal_portfoy_kaydet(sanal)

            # Telegram Bildirimi
            tg_msg = (
                f"🤖 *SANAL OTO-TRADE: POZİSYON KAPATILDI*\n\n"
                f"📌 *Varlık:* `{varlik}`\n"
                f"📋 *Neden:* {satis_nedeni}\n"
                f"💵 *Çıkış Fiyatı:* `{fiyat:.4f}` | *Maliyet:* `{maliyet:.4f}`\n"
                f"📊 *Kâr / Zarar:* `{pnl:+.2f} $` (%{pnl_yuzde:+.2f})\n"
                f"💰 *Yeni Sanal Bakiye:* `{sanal['bakiye']:.2f} $`"
            )
            telegram_bildirim_gonder(tg_msg)

    # 2. YENİ POZİSYON AÇMA (Alım Durumu)
    else:
        sinyal_ust = str(p_sinyal).upper()
        if ("AL" in sinyal_ust or "YÜKSELİŞ" in sinyal_ust) and not is_fake:
            # Kasadaki paranın maksimum %25'i ile veya min 500$ ile alım yap
            ayrilan_butce = min(bakiye * 0.25, bakiye)
            if ayrilan_butce >= 50.0:  # Minimum alım bütçesi
                adet = ayrilan_butce / fiyat
                sanal["bakiye"] -= ayrilan_butce
                sanal["pozisyonlar"][varlik] = {
                    "maliyet": fiyat,
                    "adet": adet,
                    "tarih": simdi_str,
                    "sl": stop_loss,
                    "tp": take_profit,
                }

                islem_log = {
                    "tarih": simdi_str,
                    "varlik": varlik,
                    "tip": "ALIM",
                    "neden": "📈 Güvenilir Al Sinyali",
                    "fiyat": fiyat,
                    "adet": adet,
                    "pnl": 0.0,
                    "pnl_yuzde": 0.0,
                }
                sanal["islem_gecmisi"].append(islem_log)
                sanal_portfoy_kaydet(sanal)

                # Telegram Bildirimi
                tg_msg = (
                    f"🤖 *SANAL OTO-TRADE: YENİ ALIM YAPILDI*\n\n"
                    f"📌 *Varlık:* `{varlik}`\n"
                    f"💵 *Alış Fiyatı:* `{fiyat:.4f}`\n"
                    f"🔢 *Alınan Lot:* `{adet:.4f}` | *Harcama:* `{ayrilan_butce:.2f} $`\n"
                    f"🛡️ *Stop-Loss:* `{stop_loss:.4f}` | 🎯 *Take-Profit:* `{take_profit:.4f}`\n"
                    f"💰 *Kalan Sanal Bakiye:* `{sanal['bakiye']:.2f} $`"
                )
                telegram_bildirim_gonder(tg_msg)


# --- OTOMATİK TARAMA BOTU THREAD ---
def otomatik_tarama_botu():
    time.sleep(10)
    while True:
        try:
            ayarlar = ayarlari_yukle()
            varliklar = sorted(ayarlar.get("varliklar", []))
            zaman_dilimi = ayarlar.get("zaman_dilimi", "1h")
            bekleme_suresi = ayarlar.get("bot_sikligi_dk", 60) * 60

            if varliklar:
                telegram_toplu_mesaj = f"📊 *Otomatik Teknik Analiz ve Sinyal Raporu* (Periyot: {zaman_dilimi})\n\n"
                for varlik in varliklar:
                    df_t = veri_cek(varlik, aralik=zaman_dilimi)
                    if df_t is not None and not df_t.empty:
                        df_t_analiz = hesapla_teknikler(df_t)
                        p_analiz = donusum_noktalari_hesapla(df_t_analiz)
                        p_sinyal = sinyal_kontrol(df_t_analiz)

                        # Sanal Trade Motorunu Çalıştır
                        sanal_oto_trade_isle(varlik, df_t_analiz, p_analiz, p_sinyal)

                        # Rapor Metni Ekle
                        telegram_toplu_mesaj += detayli_analiz_ve_yorum_olustur(
                            varlik, df_t_analiz, p_analiz, p_sinyal
                        )

                telegram_bildirim_gonder(telegram_toplu_mesaj)
        except Exception as e:
            pass
        time.sleep(bekleme_suresi)


if "arkaplan_bot_aktif" not in globals():
    globals()["arkaplan_bot_aktif"] = True
    threading.Thread(target=otomatik_tarama_botu, daemon=True).start()


# --- BACKTEST MOTORU ---
def calistir_backtest(df):
    sermaye = 10000
    bakiye = sermaye
    pozisyon = 0
    giris_fiyati = 0
    islemler = []

    for index, row in df.iterrows():
        sinyal = row.get("sinyal_tarihsel", 0)
        if sinyal == 1 and pozisyon == 0:
            pozisyon = 1
            giris_fiyati = row["close"]
            giris_tarihi = row.get("tarih", index)
        elif sinyal == -1 and pozisyon == 1:
            pozisyon = 0
            cikis_fiyati = row["close"]
            cikis_tarihi = row.get("tarih", index)

            oran = (cikis_fiyati - giris_fiyati) / giris_fiyati
            kar_zarar_tutari = bakiye * oran
            bakiye += kar_zarar_tutari

            durum = "Başarılı ✅" if kar_zarar_tutari > 0 else "Başarısız ❌"
            islemler.append({
                "Giriş Tarihi": giris_tarihi,
                "Çıkış Tarihi": cikis_tarihi,
                "Giriş Fiyatı": round(giris_fiyati, 4),
                "Çıkış Fiyatı": round(cikis_fiyati, 4),
                "İşlem PnL ($)": round(kar_zarar_tutari, 2),
                "Durum": durum,
            })

    toplam_islem = len(islemler)
    basarili_islem = sum(1 for i in islemler if i["İşlem PnL ($)"] > 0)
    win_rate = (basarili_islem / toplam_islem * 100) if toplam_islem > 0 else 0
    net_kar_yuzde = ((bakiye - sermaye) / sermaye) * 100

    return {
        "son_bakiye": bakiye,
        "toplam_islem": toplam_islem,
        "win_rate": win_rate,
        "net_kar_yuzde": net_kar_yuzde,
        "islemler": islemler,
    }


# --- PLOTLY GRAFİK OLUŞTURUCU ---
def grafik_olustur(df, varlik_kodu, drag_mode="zoom"):
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.7, 0.3],
        subplot_titles=(f"{varlik_kodu} Fiyat Grafiği ve İndikatörler", "RSI (14)"),
    )

    x_axis = df["tarih"] if "tarih" in df.columns else df.index

    # Candlestick
    fig.add_trace(
        go.Candlestick(
            x=x_axis,
            open=df["open"],
            high=df["high"],
            low=df["low"],
            close=df["close"],
            name="Fiyat",
        ),
        row=1,
        col=1,
    )

    # Hareketli Ortalamalar
    if "sma_20" in df.columns:
        fig.add_trace(
            go.Scatter(
                x=x_axis, y=df["sma_20"], mode="lines", name="SMA 20", line=dict(color="orange", width=1)
            ),
            row=1,
            col=1,
        )
    if "ema_50" in df.columns:
        fig.add_trace(
            go.Scatter(
                x=x_axis, y=df["ema_50"], mode="lines", name="EMA 50", line=dict(color="cyan", width=1)
            ),
            row=1,
            col=1,
        )

    # RSI
    if "rsi" in df.columns:
        fig.add_trace(
            go.Scatter(
                x=x_axis, y=df["rsi"], mode="lines", name="RSI", line=dict(color="magenta", width=1.5)
            ),
            row=2,
            col=1,
        )
        fig.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1)
        fig.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1)

    fig.update_layout(
        template="plotly_dark",
        dragmode=drag_mode,
        xaxis_rangeslider_visible=False,
        height=600,
        margin=dict(l=20, r=20, t=40, b=20),
    )
    return fig


# --- STREAMLIT ARAYÜZ (UI) ---
aktif_ayarlar = ayarlari_yukle()
aktif_portfoy = portfoy_yukle()
sanal_portfoy = sanal_portfoy_yukle()

st.sidebar.title("🤖 Pro Asistan & Oto-Trade")
sayfa = st.sidebar.radio(
    "Menü Seçimi",
    [
        "📚 Varlık Havuzu",
        "📈 Canlı Analiz & Sinyaller",
        "🤖 Sanal Oto-Trade & Cüzdan",
        "💼 Portföy Yönetimi",
        "⏳ Geriye Dönük Test",
        "⚙️ Bot Ayarları",
    ],
)
st.sidebar.divider()

HAZIR_VARLIKLAR = {
    "BIST 100 Kapsamlı Liste": {
        "AKBNK (Akbank)": "AKBNK.IS",
        "ALARK (Alarko Holding)": "ALARK.IS",
        "ARCLK (Arçelik)": "ARCLK.IS",
        "ASELS (Aselsan)": "ASELS.IS",
        "BIMAS (BİM Mağazalar)": "BIMAS.IS",
        "EREGL (Ereğli Demir Çelik)": "EREGL.IS",
        "FROTO (Ford Otosan)": "FROTO.IS",
        "GARAN (Garanti BBVA)": "GARAN.IS",
        "KCHOL (Koç Holding)": "KCHOL.IS",
        "THYAO (Türk Hava Yolları)": "THYAO.IS",
        "TUPRS (Tüpraş)": "TUPRS.IS",
    },
    "Kripto (İlk 50 / Popüler)": {
        "Bitcoin (BTC)": "BTC-USD",
        "Ethereum (ETH)": "ETH-USD",
        "Solana (SOL)": "SOL-USD",
        "Ripple (XRP)": "XRP-USD",
        "Cardano (ADA)": "ADA-USD",
        "Avalanche (AVAX)": "AVAX-USD",
        "Chainlink (LINK)": "LINK-USD",
        "Dogecoin (DOGE)": "DOGE-USD",
    },
    "Küresel Emtialar ve Fonlar": {
        "Altın (Gold Ons)": "GC=F",
        "Brent Petrol": "BZ=F",
        "Gümüş (Silver Ons)": "SI=F",
        "Invesco QQQ (Nasdaq ETF)": "QQQ",
        "Vanguard S&P 500 (SPY)": "SPY",
    },
}

# === SAYFA 1: VARLIK HAVUZU ===
if sayfa == "📚 Varlık Havuzu":
    st.title("📚 Varlık Havuzu ve Piyasalar")
    secilenler = set(aktif_ayarlar["varliklar"])

    st.subheader("📋 Aktif Varlık Listesi ve Yönetimi")
    st.markdown("Takip edilen sabit varlıklarınız aşağıdadır. İstemediğinizi çıkarabilirsiniz.")

    if not secilenler:
        st.info("Aktif listenizde hiç varlık bulunmuyor.")
    else:
        aktif_liste_sirali = sorted(list(secilenler))
        silinecekler_listesi = []
        cols = st.columns(4)
        for i, v_kod in enumerate(aktif_liste_sirali):
            with cols[i % 4]:
                if st.button(f"❌ Çıkar: {v_kod}", key=f"sil_aktif_{v_kod}", use_container_width=True):
                    silinecekler_listesi.append(v_kod)

        if silinecekler_listesi:
            for s_kod in silinecekler_listesi:
                secilenler.discard(s_kod)
            aktif_ayarlar["varliklar"] = sorted(list(secilenler))
            ayarlari_kaydet(aktif_ayarlar)
            st.success("Seçilen varlık çıkarıldı!")
            time.sleep(0.5)
            st.rerun()

    st.divider()

    tab_bist, tab_kripto, tab_emtia = st.tabs(["🇹🇷 BIST 100", "🪙 Kripto", "🛢️ Emtia & Fonlar"])
    kategori_anahtarlari = list(HAZIR_VARLIKLAR.keys())

    with tab_bist:
        for isim, kod in HAZIR_VARLIKLAR[kategori_anahtarlari[0]].items():
            if st.checkbox(isim, value=(kod in secilenler), key=f"hb_{kod}"):
                secilenler.add(kod)
            else:
                secilenler.discard(kod)

    with tab_kripto:
        for isim, kod in HAZIR_VARLIKLAR[kategori_anahtarlari[1]].items():
            if st.checkbox(isim, value=(kod in secilenler), key=f"hk_{kod}"):
                secilenler.add(kod)
            else:
                secilenler.discard(kod)

    with tab_emtia:
        for isim, kod in HAZIR_VARLIKLAR[kategori_anahtarlari[2]].items():
            if st.checkbox(isim, value=(kod in secilenler), key=f"hef_{kod}"):
                secilenler.add(kod)
            else:
                secilenler.discard(kod)

    st.divider()
    if st.button("💾 SEÇİMLERİ SABİTLE VE KAYDET", use_container_width=True, type="primary"):
        aktif_ayarlar["varliklar"] = sorted(list(secilenler))
        ayarlari_kaydet(aktif_ayarlar)
        st.success("Varlık listeniz kaydedildi!")
        time.sleep(0.5)
        st.rerun()

# === SAYFA 2: CANLI ANALİZ & SİNYALLER ===
elif sayfa == "📈 Canlı Analiz & Sinyaller":
    st.title("📈 Canlı Analiz, Çoklu Destek/Direnç ve İndikatör Sinyalleri")
    mevcut_varliklar = sorted(aktif_ayarlar.get("varliklar", []))

    if not mevcut_varliklar:
        st.warning("Lütfen Varlık Havuzundan varlık seçin.")
    else:
        if "secilen_aktif_grafik" not in st.session_state or st.session_state["secilen_aktif_grafik"] not in mevcut_varliklar:
            st.session_state["secilen_aktif_grafik"] = mevcut_varliklar[0]

        telegram_toplu_mesaj = f"📊 *Canlı Sinyal Raporu* (Periyot: {aktif_ayarlar['zaman_dilimi']})\n\n"

        for varlik in mevcut_varliklar:
            df_temp = veri_cek(varlik, aralik=aktif_ayarlar["zaman_dilimi"])
            if df_temp is not None and not df_temp.empty:
                df_t_analiz = hesapla_teknikler(df_temp)
                p_analiz = donusum_noktalari_hesapla(df_t_analiz)
                p_sinyal = sinyal_kontrol(df_t_analiz)

                detay_metni = detayli_analiz_ve_yorum_olustur(varlik, df_t_analiz, p_analiz, p_sinyal)
                telegram_toplu_mesaj += detay_metni

                col_info, col_btn = st.columns([4, 1])
                with col_info:
                    st.markdown(detay_metni)
                with col_btn:
                    st.markdown("<br>", unsafe_allow_html=True)
                    if st.button(f"📊 Grafiği İncele", key=f"btn_list_{varlik}", use_container_width=True):
                        st.session_state["secilen_aktif_grafik"] = varlik
                        st.rerun()
                st.divider()

        if st.button("📤 Tüm Listenin Analizini Telegram'a Gönder", type="primary", use_container_width=True):
            telegram_bildirim_gonder(telegram_toplu_mesaj)
            st.success("Rapor Telegram'a gönderildi!")

        st.divider()
        st.header(f"📊 Gelişmiş Grafik İncelemesi: `{st.session_state['secilen_aktif_grafik']}`")

        grafik_modu = st.selectbox(
            "Grafik Fare Modu:",
            ["🔍 Zoom (Yakınlaştır/Uzaklaştır)", "✋ Kaydırma / Pan (Sürükle)"]
        )
        drag_mode_val = "pan" if "Kaydırma" in grafik_modu else "zoom"

        df_grafik = veri_cek(st.session_state["secilen_aktif_grafik"], aralik=aktif_ayarlar["zaman_dilimi"])
        if df_grafik is not None and not df_grafik.empty:
            df_grafik_analiz = hesapla_teknikler(df_grafik)
            fig = grafik_olustur(df_grafik_analiz, st.session_state["secilen_aktif_grafik"], drag_mode=drag_mode_val)
            st.plotly_chart(fig, use_container_width=True)

# === SAYFA 3: SANAL OTO-TRADE & CÜZDAN ===
elif sayfa == "🤖 Sanal Oto-Trade & Cüzdan":
    st.title("🤖 Sanal Oto-Trade Botu ve Deneme Cüzdanı")
    st.markdown("Bot, **1 haftalık deneme süresi** boyunca ürettiği Al/Sat kararları ile otomatik işlem yapar. Gerçek para kullanılmaz.")

    # KPI Metrikleri
    toplam_sanal_portfoy_degeri = sanal_portfoy["bakiye"]
    acik_pozisyonlar = sanal_portfoy.get("pozisyonlar", {})

    # Açık pozisyonların güncel değerini hesapla
    for v_kod, v_poz in acik_pozisyonlar.items():
        df_c = veri_cek(v_kod, aralik="1h")
        if df_c is not None and not df_c.empty:
            anlik_f = df_c["close"].iloc[-1]
            toplam_sanal_portfoy_degeri += anlik_f * v_poz["adet"]
        else:
            toplam_sanal_portfoy_degeri += v_poz["maliyet"] * v_poz["adet"]

    toplam_pnl = toplam_sanal_portfoy_degeri - sanal_portfoy.get("baslangic_bakiye", 10000.0)
    toplam_pnl_yuzde = (toplam_pnl / sanal_portfoy.get("baslangic_bakiye", 10000.0)) * 100

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Kullanılabilir Sanal Bakiye", f"{sanal_portfoy['bakiye']:.2f} $")
    k2.metric("Toplam Portföy Değeri", f"{toplam_sanal_portfoy_degeri:.2f} $")
    k3.metric("Net Kâr / Zarar", f"{toplam_pnl:+.2f} $", delta=f"%{toplam_pnl_yuzde:+.2f}")
    k4.metric("Açık Pozisyon Sayısı", str(len(acik_pozisyonlar)))

    st.divider()

    # Bot Kontrol Butonları
    c_bot1, c_bot2 = st.columns(2)
    with c_bot1:
        oto_durum = aktif_ayarlar.get("oto_trade_aktif", True)
        yeni_durum = st.toggle("🤖 Algoritmik Oto-Trade Aktif", value=oto_durum)
        if yeni_durum != oto_durum:
            aktif_ayarlar["oto_trade_aktif"] = yeni_durum
            ayarlari_kaydet(aktif_ayarlar)
            st.success("Oto-trade durumu güncellendi!")
            st.rerun()

    with c_bot2:
        if st.button("🔄 Sanal Cüzdanı Sıfırla ($10,000 Başlangıç)", type="secondary"):
            sanal_portfoy_kaydet(VARSAYILAN_SANAL_PORTFOY)
            st.success("Sanal cüzdan sıfırlandı!")
            st.rerun()

    st.divider()
    st.subheader("📌 Açık Pozisyonlar (Bot Tarafından Tutulanlar)")

    if not acik_pozisyonlar:
        st.info("Şu an açık bir sanal pozisyon bulunmuyor. Bot sinyal bekliyor.")
    else:
        poz_listesi = []
        for v_kod, v_poz in acik_pozisyonlar.items():
            df_c = veri_cek(v_kod, aralik="1h")
            anlik_f = df_c["close"].iloc[-1] if df_c is not None and not df_c.empty else v_poz["maliyet"]
            k_z = (anlik_f - v_poz["maliyet"]) * v_poz["adet"]
            k_z_pct = ((anlik_f - v_poz["maliyet"]) / v_poz["maliyet"]) * 100

            poz_listesi.append({
                "Varlık": v_kod,
                "Giriş Tarihi": v_poz["tarih"],
                "Alış Fiyatı": round(v_poz["maliyet"], 4),
                "Anlık Fiyat": round(anlik_f, 4),
                "Lot Adedi": round(v_poz["adet"], 4),
                "Stop-Loss": round(v_poz.get("sl", 0), 4),
                "Take-Profit": round(v_poz.get("tp", 0), 4),
                "Kâr / Zarar ($)": round(k_z, 2),
                "Kâr / Zarar (%)": f"%{k_z_pct:+.2f}",
            })
        st.dataframe(pd.DataFrame(poz_listesi), use_container_width=True)

    st.divider()
    st.subheader("📜 Bot İşlem Geçmişi (Log)")
    islem_gecmisi = sanal_portfoy.get("islem_gecmisi", [])
    if islem_gecmisi:
        st.dataframe(pd.DataFrame(islem_gecmisi[::-1]), use_container_width=True)
    else:
        st.caption("Henüz yapılmış bir işlem kaydı yok.")

# === SAYFA 4: MANUEL PORTFÖY YÖNETİMİ ===
elif sayfa == "💼 Portföy Yönetimi":
    st.title("💼 Gerçek / Manuel Portföy Takibi")

    with st.expander("➕ Yeni İşlem / Varlık Ekle", expanded=True):
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            mevcut_havuz = sorted(aktif_ayarlar.get("varliklar", ["BTC-USD"]))
            p_varlik = st.selectbox("Varlık Seç", mevcut_havuz)
        with col2:
            p_tarih = st.date_input("Alım Tarihi", value=datetime.date.today())
        with col3:
            p_harcanan = st.number_input("Harcanan Tutar", min_value=0.0, value=1000.0)
        with col4:
            p_maliyet = st.number_input("Alış Fiyatı", min_value=0.0, format="%.4f")
        with col5:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("Kaydet", use_container_width=True, type="primary"):
                if p_maliyet > 0:
                    p_adet = p_harcanan / p_maliyet
                    aktif_portfoy[p_varlik] = {
                        "tarih": str(p_tarih),
                        "harcanan": p_harcanan,
                        "maliyet": p_maliyet,
                        "adet": p_adet,
                    }
                    portfoy_kaydet(aktif_portfoy)
                    st.success("Kayıt eklendi!")
                    time.sleep(0.5)
                    st.rerun()

    st.divider()
    st.subheader("📊 Canlı Portföy Durumu")
    if not aktif_portfoy:
        st.info("Henüz portföye varlık eklenmedi.")
    else:
        silinecekler = []
        for v_kod, v_veri in sorted(aktif_portfoy.items()):
            df_canli = veri_cek(v_kod, aralik="1h")
            if df_canli is not None and len(df_canli) >= 2:
                anlik_fiyat = df_canli["close"].iloc[-1]
                maliyet = v_veri["maliyet"]
                adet = v_veri["adet"]
                harcanan = v_veri.get("harcanan", maliyet * adet)
                guncel_deger = anlik_fiyat * adet
                toplam_kar = guncel_deger - harcanan

                c1, c2, c3, c4 = st.columns([2, 2, 2, 1])
                c1.markdown(f"### {v_kod}\n`Lot: {adet:.4f}`")
                c2.markdown(f"**Maliyet:** `{harcanan:.2f}`\n**Güncel:** `{guncel_deger:.2f}`")
                c3.markdown(f"**Net K/Z:** `{toplam_kar:+.2f} $`")
                with c4:
                    if st.button("🗑️ Sil", key=f"sil_man_{v_kod}"):
                        silinecekler.append(v_kod)
                st.divider()

        for s in silinecekler:
            del aktif_portfoy[s]
            portfoy_kaydet(aktif_portfoy)
            st.rerun()

# === SAYFA 5: GERİYE DÖNÜK TEST ===
elif sayfa == "⏳ Geriye Dönük Test":
    st.title("⏳ Strateji Testi (Backtest)")
    mevcut_varliklar = sorted(aktif_ayarlar.get("varliklar", ["BTC-USD"]))
    test_edilecek = st.selectbox("Test Edilecek Varlık", mevcut_varliklar)

    if st.button("🚀 Backtest'i Başlat", type="primary"):
        with st.spinner("Geçmiş veriler simüle ediliyor..."):
            df_test = veri_cek(test_edilecek, aralik=aktif_ayarlar["zaman_dilimi"])
            if df_test is not None and not df_test.empty:
                df_test_analiz = hesapla_teknikler(df_test)
                sonuclar = calistir_backtest(df_test_analiz)

                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Net Kâr Yüzdesi", f"%{sonuclar['net_kar_yuzde']:.2f}")
                c2.metric("Toplam İşlem", str(sonuclar["toplam_islem"]))
                c3.metric("Başarı Oranı", f"%{sonuclar['win_rate']:.1f}")
                c4.metric("Son Bakiye", f"{sonuclar['son_bakiye']:.2f} $")

                if sonuclar["islemler"]:
                    st.dataframe(pd.DataFrame(sonuclar["islemler"]), use_container_width=True)

# === SAYFA 6: BOT AYARLARI ===
elif sayfa == "⚙️ Bot Ayarları":
    st.title("⚙️ Bot ve Zaman Dilimi Ayarları")

    zaman_dilimleri = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]
    mevcut_zaman_dilimi = aktif_ayarlar.get("zaman_dilimi", "1h")

    secilen_zaman_dilimi = st.selectbox(
        "Veri Zaman Dilimi (Periyot)",
        zaman_dilimleri,
        index=zaman_dilimleri.index(mevcut_zaman_dilimi) if mevcut_zaman_dilimi in zaman_dilimleri else 4
    )

    mevcut_siklik = aktif_ayarlar.get("bot_sikligi_dk", 60)
    secilen_siklik = st.number_input(
        "Otomatik Bildirim ve Tarama Sıklığı (Dakika)",
        min_value=1,
        value=int(mevcut_siklik),
    )

    if st.button("💾 Ayarları Kaydet", type="primary", use_container_width=True):
        aktif_ayarlar["zaman_dilimi"] = secilen_zaman_dilimi
        aktif_ayarlar["bot_sikligi_dk"] = int(secilen_siklik)
        ayarlari_kaydet(aktif_ayarlar)
        st.success("Bot ayarları güncellendi!")
        time.sleep(0.5)
        st.rerun()
