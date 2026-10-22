"""
Senaryo verisi
==============

data/magaza.json dosyasını okur ve şablon cümleleri oyun bilgileriyle doldurmaya
yarayan küçük yardımcıları içerir. Senaryonun içeriği (ürünler, yerler, cümleler)
tamamen o dosyadadır; burada sadece okuma ve doldurma işi yapılır.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

VERI_YOLU = Path(__file__).resolve().parent.parent / "data" / "magaza.json"


@lru_cache(maxsize=1)
def veri() -> dict[str, Any]:
    """JSON dosyasını bir kez okur, sonra bellekten verir."""
    with open(VERI_YOLU, encoding="utf-8") as f:
        return json.load(f)


def urun(urun_id: str) -> dict[str, Any]:
    """Ürün kaydını id'sinden bulur. Yoksa KeyError fırlatır (main.py bunu 404'e çevirir)."""
    for u in veri()["urunler"]:
        if u["id"] == urun_id:
            return u
    raise KeyError(urun_id)


def yer(yer_id: str) -> dict[str, str]:
    return veri()["yerler"][yer_id]


# ---------------------------------------------------------------------------
# Türkçe büyük/küçük harf
# ---------------------------------------------------------------------------
# Python'un str.upper() fonksiyonu "i" harfini "I" yapar; Türkçede "İ" olmalı.

def tr_buyuk_bas(metin: str) -> str:
    """Cümlenin ilk harfini Türkçe kurallarına göre büyütür: 'i' -> 'İ', 'ı' -> 'I'."""
    if not metin:
        return metin
    ilk = {"i": "İ", "ı": "I"}.get(metin[0], metin[0].upper())
    return ilk + metin[1:]


def tr_kucuk(metin: str) -> str:
    """Türkçe küçük harfe çevirir: 'İ' -> 'i', 'I' -> 'ı'."""
    return metin.replace("İ", "i").replace("I", "ı").lower()


# ---------------------------------------------------------------------------
# Şablon doldurma
# ---------------------------------------------------------------------------

_YER_TUTUCU = re.compile(r"\{([A-Za-zÇĞİÖŞÜçğıöşü_]+)\}")


def doldur(sablon: str, bilgiler: dict[str, str]) -> str:
    """
    '{esya}' gibi yer tutucuları bilgilerle değiştirir.

    Yer tutucu büyük harfle yazılmışsa ('{Esya}') değer de büyük harfle başlar.
    Örnek:
        doldur("{Esya} {yer}.", {"esya": "süt", "yer": "arkada"})  ->  "Süt arkada."
    """

    def degistir(eslesme: re.Match) -> str:
        anahtar = eslesme.group(1)
        kucuk = anahtar[0].lower() + anahtar[1:]
        deger = bilgiler.get(kucuk, "")
        return tr_buyuk_bas(deger) if anahtar[0].isupper() else deger

    return _YER_TUTUCU.sub(degistir, sablon)


def oyun_bilgileri(urun_kaydi: dict[str, Any], boyut_acik: bool) -> dict[str, str]:
    """
    Şablonlarda ve LLM paketinde kullanılan 'oyunun gerçekleri'.

    Boyut özelliği kapalıysa kullanıcı '1 litrelik süt' yerine sadece 'süt' ister.
    """
    return {
        "ad": urun_kaydi["ad"],
        "istenen": urun_kaydi["istenen"] if boyut_acik else urun_kaydi["yalin"],
        "alternatif": urun_kaydi["alternatif"],
        "gelis": urun_kaydi["gelis"],
        "yer": yer(urun_kaydi["yer"])["cumle"],
    }


def kategori_yeri(soz: str) -> str | None:
    """
    Görev dışı bir ürün sorulduğunda ('ekmek nerede') küçük mağaza haritasında arar.
    Bulursa yer id'si döner ('r2'), bulamazsa None. Görevli listede olmayan yeri uydurmaz.
    """
    soz = tr_kucuk(soz)
    for anahtar, yer_id in veri()["kategoriler"].items():
        if anahtar in soz:
            return yer_id
    return None
