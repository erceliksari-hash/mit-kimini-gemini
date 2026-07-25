import json
import os
import time
import requests
from config import TELEGRAM_CHAT_ID, TELEGRAM_TOKEN
from data_sources import veri_cek
from indicators import hesapla_teknikler, sinyal_kontrol
from utils import donusum_noktalari_hesapla

SANAL_CUZDAN_DOSYASI = "sanal_cuzdan.json"
ISLEM_BASINA_TUTAR = 1000.0  # Bot her sinyalde en fazla 1000$ lık alım yapar

def cuzdan_yukle():
    if not os.path.exists(SANAL_CUZDAN_DOSYASI):
        baslangic = {
            "bakiye": 10000.0, 
            "baslangic_bakiyesi": 10000.0,
            "pozisyonlar": {}, 
            "gecmis_islemler": []
        }
        with open(SANAL_CUZDAN_DOSYASI, "w") as f:
            json.dump(baslangic, f)
        return baslangic
    try:
        with open(SANAL_CUZDAN_DOSYASI, "r") as f:
            return json.load(f)
    except:
        return {"bakiye": 10000.0, "baslangic_bakiyesi": 10000.0, "pozisyonlar": {}, "gecmis_islemler": []}

def cuzdan_kaydet(cuzdan):
    with open(SANAL_CUZDAN_DOSYASI, "w") as f:
        json.dump(cuzdan, f)

def telegram_bildirim_gonder(mesaj):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": mesaj, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
    except:
        pass

def otonom_islem_karari(varlik, df_analiz, sinyal, fiyat):
    cuzdan = cuzdan_yukle()
    bakiye = cuzdan["bakiye"]
    pozisyonlar = cuzdan["pozisyonlar"]
    
    sinyal_ust = sinyal.upper()
    islem_yapildi = False
    mesaj = ""

    # ALIM KARARI (Sadece listede yoksa ve bakiye yeterliyse)
    if ("AL" in sinyal_ust or "YÜKSELİŞ" in sinyal_ust) and varlik not in pozisyonlar:
        if bakiye >= ISLEM_BASINA_TUTAR:
            alinacak_adet = ISLEM_BASINA_TUTAR / fiyat
            cuzdan["bakiye"] -= ISLEM_BASINA_TUTAR
            cuzdan["pozisyonlar"][varlik] = {
                "maliyet": fiyat,
                "adet": alinacak_adet,
                "tarih": time.strftime('%Y-%m-%d %H:%M')
            }
            islem_yapildi = True
            mesaj = (
                f"🤖 *OTONOM İŞLEM: ALIM YAPILDI* 🟢\n"
                f"🔹 *Varlık:* `{varlik}`\n"
                f"🔹 *Alış Fiyatı:* `{fiyat:.2f}$`\n"
                f"🔹 *Miktar:* `{alinacak_adet:.4f} Lot`\n"
                f"🔹 *Yorum:* Güçlü yükseliş trendi tespit edildi. Teknik indikatörler destekliyor. Portföye eklendi."
            )
            
    # SATIM KARARI (Listede varsa ve sat sinyali geldiyse)
    elif ("SAT" in sinyal_ust or "DÜŞÜŞ" in sinyal_ust) and varlik in pozisyonlar:
        pozisyon = pozisyonlar[varlik]
        satis_tutari = pozisyon["adet"] * fiyat
        kar_zarar = satis_tutari - (pozisyon["adet"] * pozisyon["maliyet"])
        kar_zarar_yuzde = (kar_zarar / (pozisyon["adet"] * pozisyon["maliyet"])) * 100
        
        cuzdan["bakiye"] += satis_tutari
        
        # Geçmişe kaydet
        cuzdan["gecmis_islemler"].append({
            "varlik": varlik,
            "alis_fiyati": pozisyon["maliyet"],
            "satis_fiyati": fiyat,
            "kar_zarar_usd": kar_zarar,
            "yuzde": kar_zarar_yuzde,
            "tarih": time.strftime('%Y-%m-%d %H:%M')
        })
        
        del cuzdan["pozisyonlar"][varlik]
        islem_yapildi = True
        
        durum_ikon = "✅ KÂR" if kar_zarar > 0 else "❌ ZARAR"
        mesaj = (
            f"🤖 *OTONOM İŞLEM: SATIŞ YAPILDI* 🔴\n"
            f"🔹 *Varlık:* `{varlik}`\n"
            f"🔹 *Satış Fiyatı:* `{fiyat:.2f}$`\n"
            f"🔹 *Kâr/Zarar:* `{kar_zarar:+.2f}$` (%{kar_zarar_yuzde:+.2f}) {durum_ikon}\n"
            f"🔹 *Yorum:* Trendin döndüğü veya düşüş sinyallerinin arttığı tespit edildi. Risk almamak için pozisyon kapatıldı."
        )

    if islem_yapildi:
        cuzdan_kaydet(cuzdan)
        telegram_bildirim_gonder(mesaj)


def ana_dongu():
    print("🤖 Otonom Sanal Trader 7/24 Devrede...")
    
    # Botun fırsat arayacağı ekstra geniş kripto listesi (Araştırma Havuzu)
    kesif_havuzu = ["BTC-USD", "ETH-USD", "SOL-USD", "AVAX-USD", "XRP-USD", "ADA-USD", "LINK-USD", "MATIC-USD"]

    while True:
        try:
            # Önce kullanıcının kendi ayarladığı sabit listeyi al
            if os.path.exists("ayarlar.json"):
                with open("ayarlar.json", "r") as f:
                    ayarlar = json.load(f)
            else:
                ayarlar = {"varliklar": ["BTC-USD"], "zaman_dilimi": "1h", "bot_sikligi_dk": 60}
            
            sabit_varliklar = ayarlar.get("varliklar", [])
            zaman_dilimi = ayarlar.get("zaman_dilimi", "1h")
            bekleme_suresi = ayarlar.get("bot_sikligi_dk", 60) * 60

            # Sabit liste ve Keşif havuzunu birleştirip tekrar edenleri temizle
            tarama_listesi = list(set(sabit_varliklar + kesif_havuzu))

            for varlik in tarama_listesi:
                df = veri_cek(varlik, aralik=zaman_dilimi)
                if df is not None and not df.empty:
                    df_analiz = hesapla_teknikler(df)
                    p_analiz = donusum_noktalari_hesapla(df_analiz)
                    p_sinyal = sinyal_kontrol(df_analiz)
                    guncel_fiyat = p_analiz["fiyat"]
                    
                    # Otonom al-sat karar motorunu çağır
                    otonom_islem_karari(varlik, df_analiz, p_sinyal, guncel_fiyat)
                    
            time.sleep(bekleme_suresi)
            
        except Exception as e:
            print(f"Hata: {e}")
            time.sleep(60)

if __name__ == "__main__":
    ana_dongu()
