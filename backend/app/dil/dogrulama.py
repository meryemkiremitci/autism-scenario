"""
LLM çıktılarının doğrulanması
=============================

LLM'den gelen hiçbir şey kontrol edilmeden kullanılmaz. Bir kontrol bile geçmezse
çağıran taraf şablon cümleye (ya da kural tabanlı anlamaya) düşer; kullanıcı farkı
hissetmez. Burada karar verilmez, sadece "kullanılabilir mi?" sorusu cevaplanır.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from pydantic import ValidationError

from .. import veri
from ..modeller import AnlamaSonucu, CevapSonucu

# Görevlinin cümlesinde geçebilecek reyon sıra sözcükleri
SIRA_SOZCUKLERI = ["birinci", "ikinci", "üçüncü", "dördüncü", "beşinci", "altıncı", "yedinci"]


def anlama_dogrula(ham: Optional[dict[str, Any]], izinli: set[str]) -> Optional[AnlamaSonucu]:
    """
    Anlama çağrısının cevabını kontrol eder.
      * Beklenen şekilde mi? (Pydantic)
      * Niyetler gerçekten bu adımda geçerli mi? Geçersiz olanlar atılır.
    Geriye geçerli niyet kalmazsa None döner.
    """
    if not ham:
        return None
    try:
        sonuc = AnlamaSonucu.model_validate(ham)
    except ValidationError:
        return None
    gecerli = [n for n in sonuc.niyetler if n in izinli]
    if not gecerli:
        return None
    sonuc.niyetler = gecerli
    return sonuc


def cevap_dogrula(ham: Optional[dict[str, Any]], izinli_metin: str, yasaklilar: list[str]) -> Optional[str]:
    """
    Cevap çağrısının cümlesini kontrol eder. Geçerse cümleyi, geçmezse None döndürür.

    izinli_metin : görevlinin söyleyebileceği bütün gerçeklerin birleşimi (şablon + bilgiler).
                   Cümledeki sayılar ve reyon sözcükleri burada geçmek zorunda.
    yasaklilar   : cümlede geçmemesi gereken ifadeler (ör. sorulmamış alternatif boyut).
    """
    if not ham:
        return None
    try:
        cevap = CevapSonucu.model_validate(ham).cevap.strip()
    except ValidationError:
        return None

    kucuk = veri.tr_kucuk(cevap)
    izinli = veri.tr_kucuk(izinli_metin)

    # 1. En fazla iki cümle
    cumleler = [c for c in re.split(r"[.!?]+", cevap) if c.strip()]
    if len(cumleler) > 2:
        return None

    # 2. Uydurma sayı yok: cümledeki her sayı, verilen bilgilerde de geçmeli
    for sayi in re.findall(r"\d+(?:[.,]\d+)?", cevap):
        if sayi not in izinli_metin:
            return None

    # 3. Uydurma yer yok: "üçüncü reyon" gibi bir sıra sözcüğü bilgilerde geçmeli
    for soz in SIRA_SOZCUKLERI:
        if soz in kucuk and soz not in izinli:
            return None

    # 4. Söylenmemesi gerekenler geçmemeli
    for yasak in yasaklilar:
        if yasak and veri.tr_kucuk(yasak) in kucuk:
            return None

    # 5. Görevli rolünden çıkmamalı (yapay zekâ olduğunu söylemek gibi)
    if any(k in kucuk for k in ["yapay zeka", "yapay zekâ", "dil modeli", "asistan olarak"]):
        return None

    return cevap
