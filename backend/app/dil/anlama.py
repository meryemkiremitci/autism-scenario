"""
Anlama çağrısı
==============

Görevi: "Kullanıcı bu adımda ne demek istedi?"
Yalnızca serbest yazı ve ses girdilerinde çalışır; hazır cümleler buraya hiç gelmez.

LLM'in hafızası yoktur. Bu yüzden her çağrıda ona üç katmanlı bir paket gönderilir:
  1. Sabit rol (sistem talimatı)
  2. Oyunun gerçekleri (ürün, istenen boyut...)
  3. O anki durum (adım, geçerli niyetler, konuşma geçmişi, kullanıcının cümlesi)

LLM yalnızca verilen listeden niyet SEÇER; hiçbir karar vermez.
"""

from __future__ import annotations

import json
from typing import Literal

from .. import motor
from ..ayarlar import AYARLAR
from ..modeller import AnlamaSonucu, Girdi, OturumDurumu
from .dogrulama import anlama_dogrula
from .kurallar import kural_tabanli_anla
from .saglayici import saglayici_olustur

SISTEM = """Sen bir alışveriş provası uygulamasında, müşterinin mağaza görevlisine söylediği cümleyi sınıflandıran bir yardımcısın.
Görevin SADECE sınıflandırmak. Cevap yazma, karar verme.

Kurallar:
- Niyetleri YALNIZCA sana verilen "gecerli_niyetler" listesinden seç. Listede olmayan niyet uydurma.
- Cümle birden fazla şey söylüyorsa (ör. "Merhaba, süt arıyorum") niyetleri söylenme sırasıyla listele.
- Kısa ya da eksik cümleleri kabul et: "süt" tek başına da bir ürün sorusudur. Kusursuz cümle bekleme.
- Ne demek istendiği belli ama emin değilsen guven="orta" ver ve "tahmin" alanına kastedilen şeyi yaz (ör. "süt").
- Cümle anlamsızsa guven="dusuk" ver. Girdi sesten geldiyse ve yanlış duyulmuş olabileceğini düşünüyorsan
  "duzeltilmis_metin" alanına müşterinin büyük olasılıkla söylemek istediği cümleyi yaz.
- Görev dışı bir ürün soruluyorsa niyet "baska_urun" olsun ve varliklar.urun alanına o ürünü yaz.

Sadece şu biçimde, başka hiçbir şey eklemeden JSON döndür:
{"niyetler": ["..."], "guven": "yuksek|orta|dusuk", "duzeltilmis_metin": null, "tahmin": null, "varliklar": {}}"""


def _paket(durum: OturumDurumu, girdi: Girdi) -> str:
    """LLM'e gidecek bilgi paketini JSON metni olarak hazırlar."""
    izinli = motor.izinli_niyetler(durum)
    son_gorevli = next((t.metin for t in reversed(durum.gecmis) if t.kim == "gorevli"), None)
    paket = {
        "adim": durum.dugum,
        "gecerli_niyetler": [{"ad": ad, "aciklama": aciklama} for ad, aciklama in izinli.items()],
        "gercekler": motor.bilgiler(durum),
        "son_gorevli_cumlesi": son_gorevli,
        # Hafızasız LLM'in konuşmanın başını bilmesi için son birkaç satır
        "gecmis": [{"kim": t.kim, "metin": t.metin} for t in durum.gecmis[-AYARLAR.gecmis_uzunlugu:]],
        "girdi": {"tur": girdi.tur, "metin": girdi.metin},
    }
    return json.dumps(paket, ensure_ascii=False)


async def anla(durum: OturumDurumu, girdi: Girdi) -> tuple[AnlamaSonucu, Literal["llm", "kural"]]:
    """
    Kullanıcının cümlesini anlar. Önce LLM denenir; cevap gelmez ya da doğrulamadan
    geçemezse kural tabanlı yedek kullanılır. İkinci değer hangisinin kullanıldığını söyler.
    """
    izinli = set(motor.izinli_niyetler(durum))
    ham = await saglayici_olustur().json_iste(SISTEM, _paket(durum, girdi), AYARLAR.anlama_modeli, max_tokens=200)
    sonuc = anlama_dogrula(ham, izinli)
    if sonuc is not None:
        return sonuc, "llm"
    return kural_tabanli_anla(girdi.metin or "", durum), "kural"
