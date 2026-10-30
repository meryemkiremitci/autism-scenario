"""
Akış
====

Bir turun baştan sona yolculuğu bu dosyada birleşir:

    girdi ──▶ (gerekirse) anlama ──▶ senaryo motoru ──▶ cevap ──▶ tarayıcıya giden paket

  * Hazır cümle  : niyet zaten belli, anlama atlanır, cevap şablondan gelir.
  * Yazı / ses   : önce anlama (LLM ya da kural), sonra motor, sonra cevap (LLM ya da şablon).
  * Onarım       : motor son cümleyi tekrarlatır, LLM çağrılmaz.
  * Sessizlik    : motor görevlinin durumuna göre karar verir.
  * Bekleme sonu : diğer müşteri ayrılır, görevli kullanıcıya döner.
"""

from __future__ import annotations

from . import motor, veri
from .dil.anlama import anla
from .dil.cevap import cumle_kur
from .dil.saglayici import saglayici_olustur, son_cagri_basarili
from .modeller import (
    Bitis,
    HazirCumle,
    KonusCevabi,
    KonusIstegi,
    OturumDurumu,
    OturumIstegi,
    Tur,
)

GECMIS_UST_SINIR = 30          # tarayıcıyla taşınan geçmiş bu kadar satırı geçmesin
KONUSMA_SESSIZLIK_SANIYE = 30  # konuşma ortasında rehber ipucu için bekleme


async def oturum_baslat(istek: OturumIstegi) -> KonusCevabi:
    """Yeni oyun: varyasyonlar seçilir, kullanıcı görevliye seslenme adımında başlar."""
    durum = motor.baslangic(istek.urun_id, istek.ayarlar)
    cevap = _paketle(motor.MotorSonucu(durum=durum), adimlar=[])
    istenen = motor.bilgiler(durum)["istenen"]
    cevap.gorev = f"Bugün {istenen} almak istiyorsun. Markette nerede olduğunu bilmiyorsun; bir görevliden yardım iste."
    return cevap


async def konus(istek: KonusIstegi) -> KonusCevabi:
    """Kullanıcının bir girdisini işler ve görevlinin cevabını döndürür."""
    durum, girdi = istek.durum, istek.girdi

    # --- 1. Girdiyi motora uygun hâle getir ---
    if girdi.tur == "hazir":
        _musteri_satiri(durum, girdi.metin or "", "hazir")
        niyet = girdi.niyet or "anlasilmadi"
        sonuc = motor.isle(durum, [niyet], girdi_turu="hazir")

    elif girdi.tur in ("yazi", "ses"):
        metin = (girdi.metin or "").strip()
        if not metin:
            return _paketle(motor.MotorSonucu(durum=durum), adimlar=[])
        anlama, _kaynak = await anla(durum, girdi)
        _musteri_satiri(durum, metin, girdi.tur)
        sonuc = motor.isle(
            durum,
            anlama.niyetler,
            varliklar=anlama.varliklar,
            guven=anlama.guven,
            tahmin=anlama.tahmin,
            duzeltilmis_metin=anlama.duzeltilmis_metin,
            girdi_turu=girdi.tur,
        )
        if sonuc.duzeltme:
            # Yanlış duyulmuş olabilecek cümle onaylanmadıkça geçmişe girmez
            sonuc.durum.gecmis.pop()

    elif girdi.tur == "onarim":
        _musteri_satiri(durum, girdi.metin or "", "onarim")
        sonuc = motor.onarim(durum, girdi.niyet or "tekrar")
        if sonuc.eylemler and "Görevliden tekrar etmesini istedin" not in sonuc.durum.kayit and girdi.niyet != "sure":
            sonuc.durum.kayit.append("Görevliden tekrar etmesini istedin")

    elif girdi.tur == "sessiz":
        sonuc = motor.sessiz(durum)

    else:  # bekleme_bitti
        sonuc = motor.bekleme_bitti(durum)

    # --- 2. Eylemleri cümleye çevir ---
    son_musteri = next((t.metin for t in reversed(sonuc.durum.gecmis) if t.kim == "musteri"), None)
    adimlar = []
    for eylem in sonuc.eylemler:
        adim = await cumle_kur(eylem, sonuc.durum, girdi.tur, son_musteri)
        adimlar.append(adim)
        sonuc.durum.gecmis.append(Tur(kim=adim.kim, metin=adim.metin, jest=adim.jest))
        if adim.kim == "gorevli":
            sonuc.durum.gorevli_konustu = True

    cevap = _paketle(sonuc, adimlar)
    if girdi.tur in ("yazi", "ses"):
        # Gerçek bir LLM ayarlıysa ve son çağrısı başarısızsa arayüz uyarı gösterir / hazır cümlelere döner
        cevap.llm_kesik = saglayici_olustur().ad != "sahte" and son_cagri_basarili() is False
    return cevap


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------

def _musteri_satiri(durum: OturumDurumu, metin: str, tur: str) -> None:
    """Müşterinin cümlesini geçmişe yazar. Hazır cümleler de yazılır; LLM sonraki turda bilsin diye."""
    if metin:
        durum.gecmis.append(Tur(kim="musteri", metin=metin, tur=tur))


def _oneriler(durum: OturumDurumu) -> list[HazirCumle]:
    """Yeni adımın hazır cümleleri. Yer tutucular oyun bilgileriyle doldurulur."""
    if durum.dugum in ("bekleme", "bitti"):
        return []
    bilgi = motor.bilgiler(durum)
    liste = []
    for h in veri.veri()["hazir_cumleler"].get(durum.dugum, []):
        if h["niyet"] == "gelis_sor" and motor.GELIS_KAYDI in durum.kayit:
            continue   # cevabı zaten aldı; aynı soruyu tekrar önermeyelim
        liste.append(HazirCumle(metin=veri.doldur(h["metin"], bilgi), niyet=h["niyet"]))
    if durum.dugum == "seslen" and durum.varyasyon.gorevli == "sohbet" and not durum.sohbet_bitti:
        liste.append(HazirCumle(metin="(Konuşmasının bitmesini bekle)", niyet="bekle"))
    return liste


def _paketle(sonuc: motor.MotorSonucu, adimlar: list) -> KonusCevabi:
    """Motorun sonucunu tarayıcının anlayacağı pakete çevirir."""
    d = sonuc.durum
    d.gecmis = d.gecmis[-GECMIS_UST_SINIR:]

    rehber = motor.rehber(d)
    if sonuc.rehber_ek:
        rehber = f"{rehber} {sonuc.rehber_ek}".strip()

    # Sessizlik zamanlayıcısı: ilk adımda varyasyona göre, konuşma ortasında daha uzun
    if d.dugum == "seslen":
        sessizlik = d.varyasyon.sessizlik_saniye
    elif d.dugum in ("bekleme", "bitti"):
        sessizlik = None
    else:
        sessizlik = KONUSMA_SESSIZLIK_SANIYE

    bitis = None
    if d.bitti:
        ozet = ["Markete girdin", "Görevliye yaklaştın", *d.kayit]
        if not d.urunlu:
            if d.urun_soruldu:
                ozet.append("Ürünü almadan ayrıldın. Bu da gerçek hayatta sık olan, geçerli bir sonuç.")
            elif d.baska_sorulan:
                ozet.append(f"Aradığın ürün yerine başka bir ürünü ({', '.join(d.baska_sorulan)}) sordun ve ayrıldın.")
            else:
                ozet.append("Aradığın ürünü sormadan ayrıldın.")
        bitis = Bitis(urunlu=bool(d.urunlu), ozet=ozet)

    return KonusCevabi(
        durum=d,
        adimlar=adimlar,
        olaylar=sonuc.olaylar,
        oneriler=_oneriler(d),
        # Onarım kartları ancak görevli bir şey söyledikten sonra anlamlıdır
        onarim_acik=d.gorevli_konustu and d.dugum not in ("bekleme", "bitti"),
        rehber=rehber,
        duzeltme=sonuc.duzeltme,
        bekleme=sonuc.bekleme,
        sessizlik_saniye=sessizlik,
        bitis=bitis,
    )
