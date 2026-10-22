"""
Kural tabanlı anlama (yedek)
============================

LLM yoksa ya da cevap veremezse kullanıcının cümlesi burada anahtar kelimelerle
yorumlanır. LLM kadar esnek değildir ama senaryonun LLM olmadan da ilerleyebilmesini
sağlar. Sonuç, LLM'den gelen sonuçla AYNI şekildedir (AnlamaSonucu).
"""

from __future__ import annotations

import re

from .. import veri
from ..modeller import AnlamaSonucu, OturumDurumu

# Her niyet için cümlede aranacak kelime parçaları (küçük harf, Türkçe)
ANAHTARLAR: dict[str, list[str]] = {
    "selam": ["merhaba", "selam", "pardon", "bakar mısınız", "bakar misiniz", "bakabilir", "kolay gelsin", "affedersiniz"],
    "tesekkur": ["teşekkür", "tesekkur", "sağ ol", "sağol", "sag ol", "eyvallah", "mersi"],
    "ayril": ["tamam", "peki", "gerek yok", "iyi günler", "hoşça kal", "neyse"],
    "gelis_sor": ["ne zaman", "gelir mi", "gelecek", "gelir"],
    "alternatif_sor": ["yarım", "başka boyut", "başka bir boyut", "küçük", "büyük", "orta", "katlanır", "2'li", "1,5", "farklı"],
    "evet": ["evet", "aynen", "doğru", "olur", "he ", "tabii"],
    "hayir": ["hayır", "hayir", "değil", "yok yok"],
    "bekle": ["bekle", "beklerim", "acelem yok"],
}
ISTEK_KELIMELERI = ["arıyorum", "ariyorum", "nerede", "nerde", "var mı", "lazım", "istiyorum", "bulabilir", "almak"]


def _iceriyor(metin: str, parcalar: list[str]) -> bool:
    return any(p in metin for p in parcalar)


def _urun_kokleri(urun_kaydi: dict) -> list[str]:
    """
    Ürün adından aranacak kökler: 'şemsiye' -> 'şems', 'diş fırçası' -> 'fırç', 'süt' -> 'süt'.
    Böylece 'şemsiyeler', 'sütü' gibi ekli hâller de yakalanır.
    """
    kokler = set()
    for kelime in (urun_kaydi["ad"] + " " + urun_kaydi["yalin"]).split():
        kelime = veri.tr_kucuk(kelime)
        if len(kelime) >= 3:
            kokler.add(kelime[:4] if len(kelime) > 4 else kelime)
    return sorted(kokler)


def kural_tabanli_anla(metin: str, durum: OturumDurumu) -> AnlamaSonucu:
    """Cümleyi anahtar kelimelerle yorumlar. Geçerli niyetlere uymayanı 'anlasilmadi' sayar."""
    m = " " + veri.tr_kucuk(metin).strip() + " "
    m = re.sub(r"\s+", " ", m)
    urun_kaydi = veri.urun(durum.urun_id)
    dugum = durum.dugum
    niyetler: list[str] = []
    varliklar: dict[str, str] = {}

    gorev_urunu_var = _iceriyor(m, _urun_kokleri(urun_kaydi))

    # Görev dışı bir ürün mü? (küçük mağaza haritasında geçen bir kelime)
    baska_urun = None
    for anahtar in veri.veri()["kategoriler"]:
        if f" {anahtar}" in m and not gorev_urunu_var:
            baska_urun = anahtar
            break

    # --- Onay adımı: önce evet/hayır ---
    if dugum == "onay":
        if _iceriyor(m, ANAHTARLAR["hayir"]):
            return AnlamaSonucu(niyetler=["hayir"], guven="yuksek")
        if _iceriyor(m, ANAHTARLAR["evet"]) or gorev_urunu_var:
            return AnlamaSonucu(niyetler=["evet"], guven="yuksek")
        return AnlamaSonucu(niyetler=["anlasilmadi"], guven="dusuk")

    # --- Selam (başka niyetlerle birlikte de olabilir) ---
    if _iceriyor(m, ANAHTARLAR["selam"]):
        niyetler.append("selam")

    if dugum == "seslen" and _iceriyor(m, ANAHTARLAR["bekle"]):
        niyetler.append("bekle")

    # --- Adıma göre asıl niyet ---
    if dugum in ("seslen", "urun", "tesekkur") and (gorev_urunu_var or (dugum != "tesekkur" and _iceriyor(m, ISTEK_KELIMELERI) and not baska_urun)):
        niyetler.append("urun_sor")
        varliklar["urun"] = urun_kaydi["ad"]
    elif dugum == "boyut" and (_iceriyor(m, ANAHTARLAR["alternatif_sor"]) or "var mı" in m) and not _iceriyor(m, ANAHTARLAR["tesekkur"]):
        niyetler.append("alternatif_sor")
    elif dugum == "gelis" and _iceriyor(m, ANAHTARLAR["gelis_sor"]):
        niyetler.append("gelis_sor")
    elif dugum == "tesekkur" and _iceriyor(m, ANAHTARLAR["tesekkur"]):
        niyetler.append("tesekkur")
    elif dugum in ("boyut", "gelis") and (_iceriyor(m, ANAHTARLAR["tesekkur"]) or _iceriyor(m, ANAHTARLAR["ayril"])):
        niyetler.append("ayril")   # bu adımlarda "teşekkürler" = ürünsüz ayrılmak
    elif dugum == "tesekkur" and _iceriyor(m, ANAHTARLAR["ayril"]):
        niyetler.append("ayril")
    elif baska_urun:
        niyetler.append("baska_urun")
        varliklar["urun"] = baska_urun

    if not niyetler:
        return AnlamaSonucu(niyetler=["anlasilmadi"], guven="dusuk")
    return AnlamaSonucu(niyetler=niyetler[:3], guven="yuksek", varliklar=varliklar)
