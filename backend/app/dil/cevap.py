"""
Cevap çağrısı
=============

Görevi: "Görevli bu bilgiyi nasıl söyler?"

NE söyleneceğine senaryo motoru karar verir ve bunu bir 'eylem' olarak iletir.
Bu dosya yalnızca cümleyi kurar:
  * Hazır cümle yolunda, onarımda ve LLM'in kapalı olduğu durumlarda: şablon (sabit).
  * Serbest yazı ve seste: LLM'den doğal bir cümle istenir; doğrulamadan geçemezse şablon.

Jest burada seçilmez; motorun belirlediği jest olduğu gibi aktarılır.
"""

from __future__ import annotations

import json

from .. import motor, veri
from ..ayarlar import AYARLAR
from ..modeller import GorevliAdimi, OturumDurumu
from .dogrulama import cevap_dogrula
from .saglayici import saglayici_olustur

# LLM'e cümlesi kurdurulabilecek eylemler. Diğerleri (kısa selam, "bir saniye",
# onarım, diğer müşterinin cümlesi) her zaman şablondan gelir.
LLM_ILE_KURULABILIR = {
    "karsila", "kendiliginden_sor", "ozur_buyurun", "bekleyen_hatirla", "tekrar_sor",
    "yer_tarif_et", "boyut_yok_bildir", "hic_yok_bildir", "alternatif_onayla", "gelis_zamani_soyle",
    "baska_urun_yeri", "baska_urun_bilinmiyor", "konu_disi", "netlestir", "anlayamadim",
    "vedalas", "vedalas_urunsuz",
}

# Her eylem için LLM'e "ne anlatılacağı" açıklaması
EYLEM_ACIKLAMALARI = {
    "karsila": "Müşteriyi karşıla ve yardım teklif et.",
    "kendiliginden_sor": "Müşterinin bir şey aradığını fark ettin; ona yardım teklif et.",
    "ozur_buyurun": "Beklettiğin için kısaca özür dile ve yardım teklif et.",
    "bekleyen_hatirla": "Beklettiğin için özür dile ve müşterinin daha önce söylediği ürünü arayıp aramadığını sorarak onaylat.",
    "tekrar_sor": "Müşterinin ne aradığını sor.",
    "yer_tarif_et": "Aranan eşyanın yerini söyle.",
    "boyut_yok_bildir": "İstenen boyutun kalmadığını söyle.",
    "hic_yok_bildir": "Ürünün şu an hiç kalmadığını söyle.",
    "alternatif_onayla": "Diğer boyutun olduğunu onayla ve yerini söyle.",
    "gelis_zamani_soyle": "Ürünün ne zaman geleceğini söyle.",
    "baska_urun_yeri": "Sorulan eşyanın yerini söyle.",
    "baska_urun_bilinmiyor": "Sorulan şeyin yerini bilmediğini kibarca söyle ve kasadaki çalışana sorulabileceğini belirt.",
    "konu_disi": (
        "Müşterinin söylediğine doğal ve uygun bir cevap ver (ör. hal hatır sorarsa iyi olduğunu söyle), "
        "sonra konuyu alışverişe getirip nasıl yardımcı olabileceğini sor. Toplam en fazla iki cümle."
    ),
    "netlestir": "Müşterinin tahmin edilen şeyi arayıp aramadığını kısa bir soruyla netleştir.",
    "anlayamadim": "Müşteriyi tam anlayamadığını kibarca söyle.",
    "vedalas": "Teşekküre karşılık ver ve iyi alışverişler dile.",
    "vedalas_urunsuz": "Teşekküre karşılık ver ve iyi günler dile.",
}

# Bu eylemlerde ürün, yer ve alternatif söylenmez: kullanıcı kendisi sormalı.
# LLM'e bu bilgiler hiç verilmez, cümlede geçerse de doğrulama cümleyi reddeder.
BILGI_VERILMEYEN = {
    "karsila", "kendiliginden_sor", "ozur_buyurun", "tekrar_sor", "konu_disi", "anlayamadim",
    "vedalas", "vedalas_urunsuz",
}

DIL_KURALLARI = {
    "sade": "Deyim, mecaz ve ima kullanma. Kısa, açık ve doğrudan cümleler kur. Her şeyi kelimenin tam anlamıyla söyle.",
    "gundelik": "Bir mahalle marketindeki görevli gibi doğal, gündelik konuş. Yaygın günlük ifadeler kullanabilirsin ama anlam açık kalsın.",
}

SISTEM = """Sen bir mahalle marketinde çalışan, kibar ve sabırlı bir görevlisin. Bir müşteriyle konuşuyorsun.

Kurallar:
- En fazla iki kısa cümle kur.
- SADECE "soylenecekler" içindeki bilgileri kullan. Ürün, yer, fiyat, sayı ya da zaman UYDURMA.
- "soylenmeyecekler" listesindeki şeyleri asla söyleme, ima da etme.
- Rolünden çıkma; yapay zekâ olduğundan söz etme.
- {dil}

Sadece şu biçimde, başka hiçbir şey eklemeden JSON döndür:
{{"cevap": "..."}}"""


def _soylenmeyecekler(eylem_adi: str, bilgiler: dict[str, str]) -> list[str]:
    """
    LLM'ler yardımsever olmak için kullanıcıdan önce davranabilir:
    "1 litrelik yok ama yarım litrelik var" demek, kullanıcının "Yarım litrelik var mı?"
    diye sorma provasını elinden alır. Bunu açıkça yasaklıyoruz.
    """
    if eylem_adi in ("boyut_yok_bildir", "hic_yok_bildir"):
        # Alternatif, geliş zamanı ve yer ancak kullanıcı sorarsa söylenir. "Hiç yok" derken
        # alternatif ya da yer vermek ayrıca çelişkili olur; LLM'e bu bilgiler hiç verilmez.
        return [bilgiler["alternatif"], bilgiler["gelis"], bilgiler["yer"]]
    return []


def sablon_cumlesi(eylem: motor.Eylem, durum: OturumDurumu) -> str:
    """Eylemin ilk şablonunu oyun bilgileriyle doldurur (öğrenme için hep aynı cümle)."""
    bilgi = {**motor.bilgiler(durum), **eylem.bilgiler}
    sablonlar = veri.veri()["sablonlar"].get(eylem.ad) or ["..."]
    return veri.doldur(sablonlar[0], bilgi)


async def cumle_kur(eylem: motor.Eylem, durum: OturumDurumu, girdi_turu: str, son_musteri_cumlesi: str | None) -> GorevliAdimi:
    """Bir eylemi, görevlinin (ya da diğer müşterinin) söyleyeceği cümleye çevirir."""
    kim = "diger" if eylem.kim == "diger" else "gorevli"

    # Onarım: son cümle aynen tekrarlanır
    if eylem.sabit_metin:
        return GorevliAdimi(eylem=eylem.ad, metin=eylem.sabit_metin, jest=eylem.jest, hiz=eylem.hiz, kim=kim)

    sablon = sablon_cumlesi(eylem, durum)
    adim = GorevliAdimi(eylem=eylem.ad, metin=sablon, jest=eylem.jest, hiz=eylem.hiz, kim=kim)

    # LLM yalnızca serbest girdide ve izin verilen eylemlerde devreye girer
    if not (AYARLAR.llm_cevap_acik and girdi_turu in ("yazi", "ses") and eylem.ad in LLM_ILE_KURULABILIR):
        return adim

    bilgi = {**motor.bilgiler(durum), **eylem.bilgiler}
    yasaklilar = _soylenmeyecekler(eylem.ad, bilgi)
    # Söylenebilecekler: eylemin kendi bilgileri + şablon (örnek). Yasaklananlar çıkarılır.
    soylenecekler = {k: v for k, v in bilgi.items() if v not in yasaklilar}
    if eylem.ad in BILGI_VERILMEYEN:
        soylenecekler = dict(eylem.bilgiler)
        yasaklilar = [bilgi["ad"], bilgi["istenen"], bilgi["alternatif"]]
    paket = {
        "eylem": eylem.ad,
        "ne_anlatilacak": EYLEM_ACIKLAMALARI.get(eylem.ad, ""),
        "soylenecekler": soylenecekler,
        "soylenmeyecekler": yasaklilar,
        "ornek_cumle": sablon,
        "musterinin_son_cumlesi": son_musteri_cumlesi,
        "gecmis": [{"kim": t.kim, "metin": t.metin} for t in durum.gecmis[-AYARLAR.gecmis_uzunlugu:]],
    }
    sistem = SISTEM.format(dil=DIL_KURALLARI[durum.varyasyon.dil_duzeyi])
    ham = await saglayici_olustur().json_iste(sistem, json.dumps(paket, ensure_ascii=False), AYARLAR.cevap_modeli, max_tokens=150)

    # Doğrulama: cümledeki sayılar ve yerler, verilen bilgilerde geçmek zorunda
    izinli_metin = sablon + " " + " ".join(soylenecekler.values())
    cumle = cevap_dogrula(ham, izinli_metin, yasaklilar)
    if cumle:
        adim.metin, adim.kaynak = cumle, "llm"
    return adim
