# bot_servisi.py
import json
import os
import time
from config import TELEGRAM_CHAT_ID, TELEGRAM_TOKEN
from data_sources import veri_cek
from indicators import hesapla_teknikler, sinyal_kontrol
import requests
from utils import donusum_noktalari_hesapla


def ayarlari_yukle():
    if os.path.exists("ayarlar.json"):
        with open("ayarlar.json", "r") as f:
            return json.load(f)
    return {"varliklar": ["BTC-USD"], "zaman_dilimi": "1h", "bot_sikligi_dk": 60}


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


def detayli_analiz_ve_yorum_olustur(varlik, df_t_analiz, p_analiz, p_sinyal):
    fiyat = p_analiz["fiyat"]
    d1 = p_analiz["destek"]
    r1 = p_analiz["direnc"]

    s1, s2, s3 = d1, d1 * 0.985, d1 * 0.970
    r1_val, r2, r3 = r1, r1 * 1.015, r1 * 1.030

    stop_loss = s1 if s1 < fiyat else fiyat * 0.97
    take_profit = r1_val if r1_val > fiyat else fiyat * 1.05
    is_fake = df_t_analiz.iloc[-1].get("sahte_sinyal", False)

    sinyal_ust = p_sinyal.upper()
    if "AL" in sinyal_ust or "YÜKSELİŞ" in sinyal_ust:
        trend_yorum = "📈 *Yükseliş Trendi Hâkim.*"
        gecis_yorum = f"Yükseliş Teyit Eşiği: `{r1_val:.2f}`"
    elif "SAT" in sinyal_ust or "DÜŞÜŞ" in sinyal_ust:
        trend_yorum = "📉 *Düşüş Baskısı Hâkim.*"
        gecis_yorum = f"Düşüş Derinleşme Eşiği: `{s1:.2f}`"
    else:
        trend_yorum = "⚖️ *Yatay Seyir.*"
        gecis_yorum = f"Kırılım: `{r1_val:.2f}` Üstü / `{s1:.2f}` Altı"

    sahte_yorum = (
        "⚠️ *SİNYAL UYARISI:* Sahte/Tuzak sinyal riski!"
        if is_fake
        else "✅ *GÜVENİLİR SİNYAL*"
    )

    return (
        f"🔹 *{varlik}*\n"
        f"   • *Fiyat:* `{fiyat:.2f}` | *Sinyal:* `{p_sinyal}`\n"
        f"   • *Destekler:* `{s1:.2f}` | `{s2:.2f}` | `{s3:.2f}`\n"
        f"   • *Dirençler:* `{r1_val:.2f}` | `{r2:.2f}` | `{r3:.2f}`\n"
        f"   • *SL:* `{stop_loss:.2f}` | *TP:* `{take_profit:.2f}`\n"
        f"   • *Yorum:* {trend_yorum} ({gecis_yorum})\n"
        f"   • *Durum:* {sahte_yorum}\n\n"
    )


def ana_dongu():
    print("🤖 Telegram Bot Servisi 7/24 Modunda Çalışıyor...")
    while True:
        try:
            ayarlar = ayarlari_yukle()
            varliklar = sorted(ayarlar.get("varliklar", []))
            zaman_dilimi = ayarlar.get("zaman_dilimi", "1h")
            bekleme_suresi = ayarlar.get("bot_sikligi_dk", 60) * 60

            if varliklar:
                mesaj = f"📊 *7/24 Otomatik Analiz Raporu* ({zaman_dilimi})\n\n"
                for varlik in varliklar:
                    df = veri_cek(varlik, aralik=zaman_dilimi)
                    if df is not None and not df.empty:
                        df_analiz = hesapla_teknikler(df)
                        p_analiz = donusum_noktalari_hesapla(df_analiz)
                        p_sinyal = sinyal_kontrol(df_analiz)
                        mesaj += detayli_analiz_ve_yorum_olustur(
                            varlik, df_analiz, p_analiz, p_sinyal
                        )
                telegram_bildirim_gonder(mesaj)
                print(
                    f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Rapor Telegram'a"
                    " gönderildi."
                )
        except Exception as e:
            print(f"Hata oluştu: {e}")

        time.sleep(bekleme_suresi)


if __name__ == "__main__":
    ana_dongu()
