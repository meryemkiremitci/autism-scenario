"""
Senaryo motoru (durum makinesi)
===============================

Konuşmanın hangi adımda olduğunu bilen ve bir sonraki adıma karar veren parça.

Temel ilke: KARARLARI BU DOSYA VERİR. LLM'den yalnızca "kullanıcı ne demek istedi"
(niyet) bilgisini alır; stok durumu, ürünün yeri, bir sonraki adım ve görevlinin
jesti burada belirlenir. Bu dosyada hiçbir LLM ya da ağ çağrısı yoktur, bu yüzden
tamamen test edilebilir (bkz. tests/test_motor.py).

Dört kavram:
    düğüm    : kullanıcının sırası olan an           (ör. "urun")
    niyet    : kullanıcının o anda ne demek istediği  (ör. "urun_sor")
    eylem    : görevlinin cevap olarak ne yapacağı    (ör. "yer_tarif_et")
    varyasyon: oyun başında seçilen koşullar           (stok, görevli durumu...)
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Optional

from . import veri
from .modeller import (
    Ayarlar,
    Bekleme,
    BekleyenNiyet,
    OturumDurumu,
    Varyasyon,
)

# ---------------------------------------------------------------------------
# 1. Düğümler ve niyetler
# ---------------------------------------------------------------------------
# Her düğümde geçerli olan niyetler ve açıklamaları. Açıklamalar anlama
# çağrısında LLM'e de gönderilir; LLM sadece bu listeden seçebilir.

DUGUM_NIYETLERI: dict[str, dict[str, str]] = {
    "seslen": {
        "selam": "Müşteri selam veriyor ya da görevlinin dikkatini çekmeye çalışıyor",
        "urun_sor": "Müşteri selam vermeden doğrudan aradığı ürünü söylüyor",
    },
    "urun": {
        "urun_sor": "Müşteri aradığı ürünü söylüyor, soruyor ya da tarif ediyor",
        "selam": "Müşteri sadece selam veriyor",
        "ayril": "Müşteri teşekkür edip ya da vedalaşıp (ör. 'tamam teşekkürler', 'iyi günler') başka bir şey sormadan ayrılmak istiyor",
    },
    "boyut": {
        "alternatif_sor": "Müşteri ürünün başka bir boyutunu soruyor",
        "ayril": "Müşteri teşekkür edip ya da sadece vedalaşıp (ör. 'tamam', 'iyi günler', 'hoşça kal') ürünü almadan ayrılmak istiyor",
    },
    "gelis": {
        "gelis_sor": "Müşteri ürünün ne zaman geleceğini soruyor",
        "ayril": "Müşteri teşekkür edip ya da sadece vedalaşıp (ör. 'tamam', 'iyi günler', 'hoşça kal') ürünü almadan ayrılmak istiyor",
    },
    "tesekkur": {
        "tesekkur": "Müşteri yardım için teşekkür ediyor",
        "ayril": "Müşteri teşekkür etmeden kısaca konuşmayı bitiriyor (ör. 'tamam', 'iyi günler')",
        "urun_sor": "Müşteri ürünün yerini tekrar soruyor",
    },
    "onay": {
        "evet": "Müşteri görevlinin sorusunu onaylıyor",
        "hayir": "Müşteri görevlinin sorusuna hayır diyor",
    },
}

# Her düğümde geçerli olan genel niyetler. Bunlar adımı değiştirmez.
GENEL_NIYETLER: dict[str, str] = {
    "konu_disi": "Müşteri alışverişle ilgisi olmayan bir şey söylüyor",
    "baska_urun": "Müşteri görevindeki üründen farklı bir ürünün yerini soruyor",
    "anlasilmadi": "Söylenen şey anlaşılmıyor ya da hiçbir niyete uymuyor",
}

# "Ne zaman gelir?" bir kez sorulunca kayda bu satır girer; hazır cümle bir daha önerilmez
GELIS_KAYDI = "Ürünün ne zaman geleceğini sordun"

# Görevli başka müşteriyle konuşurken "beklemeyi seçmek" de bir niyettir
BEKLE_NIYETI = {"bekle": "Müşteri görevlinin işini bitirmesini beklemeyi seçiyor"}


def izinli_niyetler(durum: OturumDurumu) -> dict[str, str]:
    """Bu düğümde kabul edilen bütün niyetler (düğüme özel + genel)."""
    niyetler = dict(DUGUM_NIYETLERI.get(durum.dugum, {}))
    if durum.dugum == "seslen" and durum.varyasyon.gorevli == "sohbet" and not durum.sohbet_bitti:
        niyetler.update(BEKLE_NIYETI)
    niyetler.update(GENEL_NIYETLER)
    return niyetler


# ---------------------------------------------------------------------------
# 2. Eylemler ve jestler
# ---------------------------------------------------------------------------
# Jest seçimi LLM'e bırakılmaz: aynı durumda görevli hep aynı jesti yapar
# (öngörülebilirlik). Yer tarif eden eylemlerin jesti yerin kendisinden gelir.

SABIT_JESTLER: dict[str, str] = {
    "boyut_yok_bildir": "omuz",
    "hic_yok_bildir": "omuz",
    "baska_urun_bilinmiyor": "omuz",
    "bir_saniye_de": "bekle",
    "diger_musteri_tesekkur": "",
}
VARSAYILAN_JEST = "anlat"


@dataclass
class Eylem:
    """Görevlinin yapacağı tek bir şey. Cümlesi cevap katmanında (dil/cevap.py) kurulur."""

    ad: str
    jest: str = VARSAYILAN_JEST
    bilgiler: dict[str, str] = field(default_factory=dict)   # şablon için ek bilgiler
    kim: str = "gorevli"
    hiz: float = 1.0
    sabit_metin: Optional[str] = None                         # onarımda son cümle aynen tekrarlanır


def _eylem(ad: str, **bilgiler: str) -> Eylem:
    """Eylemi oluşturur ve jestini belirler."""
    return Eylem(ad=ad, jest=SABIT_JESTLER.get(ad, VARSAYILAN_JEST), bilgiler=bilgiler)


def _yer_eylemi(ad: str, yer_id: str, **bilgiler: str) -> Eylem:
    """Bir yeri tarif eden eylem: cümlesi ve jesti o yerin kaydından gelir."""
    yer_kaydi = veri.yer(yer_id)
    return Eylem(ad=ad, jest=yer_kaydi["jest"], bilgiler={"yer": yer_kaydi["cumle"], **bilgiler})


# ---------------------------------------------------------------------------
# 3. Motorun çıktısı
# ---------------------------------------------------------------------------

@dataclass
class MotorSonucu:
    durum: OturumDurumu
    eylemler: list[Eylem] = field(default_factory=list)
    olaylar: list[str] = field(default_factory=list)   # görsel olaylar (gorevli_doner, sohbet_biter...)
    bekleme: Optional[Bekleme] = None
    duzeltme: Optional[str] = None                      # "Şunu mu demek istedin?" metni
    rehber_ek: Optional[str] = None                     # rehbere eklenecek ipucu


# ---------------------------------------------------------------------------
# 4. Oturum başlangıcı
# ---------------------------------------------------------------------------

def varyasyon_sec(ayarlar: Ayarlar, rng: random.Random | None = None) -> Varyasyon:
    """
    Zorluk paketinden ve kullanıcının değişikliklerinden oyunun koşullarını seçer.
    Bir ayar verilmişse o kullanılır; verilmemişse paketteki seçeneklerden rastgele biri.
    """
    rng = rng or random.Random()
    paket = veri.veri()["zorluklar"][ayarlar.zorluk]
    return Varyasyon(
        gorevli=ayarlar.gorevli or rng.choice(paket["gorevli"]),
        gorevli_cinsiyet=ayarlar.gorevli_cinsiyet or rng.choice(["kadin", "erkek"]),
        stok=ayarlar.stok or rng.choice(paket["stok"]),
        hafiza=ayarlar.hafiza or rng.choice(paket["hafiza"]),
        boyut_acik=paket["boyut_acik"] if ayarlar.boyut_acik is None else ayarlar.boyut_acik,
        dil_duzeyi=ayarlar.dil_duzeyi or paket["dil_duzeyi"],
        bekleme_saniye=ayarlar.bekleme_saniye or paket["bekleme_saniye"],
        sessizlik_saniye=ayarlar.sessizlik_saniye or paket["sessizlik_saniye"],
    )


def baslangic(urun_id: str, ayarlar: Ayarlar, rng: random.Random | None = None) -> OturumDurumu:
    """Yeni bir oturumun ilk durumu: kullanıcı mağazaya girmiş, görevliye seslenecek."""
    veri.urun(urun_id)  # ürün yoksa burada hata verir
    return OturumDurumu(urun_id=urun_id, varyasyon=varyasyon_sec(ayarlar, rng), dugum="seslen")


def bilgiler(durum: OturumDurumu) -> dict[str, str]:
    """Bu oturumun 'oyun gerçekleri' (ürün adı, istenen boyut, yer cümlesi...)."""
    return veri.oyun_bilgileri(veri.urun(durum.urun_id), durum.varyasyon.boyut_acik)


def etkin_stok(durum: OturumDurumu) -> str:
    """Boyut özelliği kapalıysa 'boyut yok' durumu 'var' gibi davranır."""
    v = durum.varyasyon
    return "var" if (v.stok == "boyut" and not v.boyut_acik) else v.stok


# ---------------------------------------------------------------------------
# 5. Ana giriş: niyetleri işle
# ---------------------------------------------------------------------------

def isle(
    durum: OturumDurumu,
    niyetler: list[str],
    *,
    varliklar: dict[str, str] | None = None,
    guven: str = "yuksek",
    tahmin: str | None = None,
    duzeltilmis_metin: str | None = None,
    girdi_turu: str = "hazir",
) -> MotorSonucu:
    """
    Kullanıcının niyetlerini sırayla işler ve yeni durumu, görevlinin eylemlerini döndürür.

    Gelen durum değiştirilmez; kopyası üzerinde çalışılır.
    """
    d = durum.model_copy(deep=True)
    s = MotorSonucu(durum=d)
    varliklar = varliklar or {}
    if d.bitti:
        return s

    # İlk adımda (seslen) görevlinin dikkatini çekmek yeterli; belirsizlik önemli değil.
    if d.dugum == "seslen" and guven == "orta":
        guven = "yuksek"

    # --- Düşük güven -------------------------------------------------------
    if guven == "dusuk":
        if girdi_turu == "ses" and duzeltilmis_metin:
            # Makine yanlış duymuş olabilir: kullanıcının hatası değil, düzeltmeyi ARAYÜZ önerir.
            s.duzeltme = duzeltilmis_metin
        elif d.dugum != "seslen":
            s.eylemler.append(_eylem("anlayamadim"))
        return s

    # --- Orta güven: görevli rol içinde netleştirir -----------------------
    # Sadece ürün sorularında anlamlı ("Süt mü arıyorsunuz?"). "İyi günler" gibi
    # veda ya da teşekkür cümlelerinde sorulursa saçma olur; onlar normal işlenir.
    asil = next((n for n in niyetler if n not in GENEL_NIYETLER), "urun_sor")
    if guven == "orta" and tahmin and asil == "urun_sor":
        donus = d.dugum if d.dugum != "onay" else (d.bekleyen.donus_dugumu if d.bekleyen else "urun")
        d.bekleyen = BekleyenNiyet(niyet=asil, donus_dugumu=donus, varliklar=varliklar)
        d.dugum = "onay"
        s.eylemler.append(_eylem("netlestir", tahmin=tahmin))
        return s

    # --- İlk adımda selamsız başlayan cümleler -----------------------------
    # "süt arıyorum" da görevlinin dikkatini çeker: önce selam, sonra asıl niyet.
    if d.dugum == "seslen" and niyetler and niyetler[0] not in ("selam", "bekle"):
        niyetler = ["selam"] + [n for n in niyetler if n not in GENEL_NIYETLER]

    # --- Niyetleri sırayla işle ---------------------------------------------
    # "Merhaba, süt arıyorum" iki niyet taşır: motor ikisini de işler ve adım atlar.
    for i, niyet in enumerate(niyetler):
        devam = _tek_niyet(s, niyet, varliklar, niyetler[i + 1:])
        if not devam or d.bitti:
            break
    return s


def _tek_niyet(s: MotorSonucu, niyet: str, varliklar: dict[str, str], kalan: list[str]) -> bool:
    """Tek bir niyeti işler. False dönerse geri kalan niyetler işlenmez."""
    d = s.durum

    if niyet not in izinli_niyetler(d):
        s.eylemler.append(_eylem("anlayamadim"))
        return False

    # ---- Genel niyetler (adımı değiştirmez) ----
    if niyet == "konu_disi":
        s.eylemler.append(_eylem("konu_disi"))
        return True
    if niyet == "anlasilmadi":
        s.eylemler.append(_eylem("anlayamadim"))
        return False
    if niyet == "baska_urun":
        return _baska_urun(s, varliklar)

    # ---- Düğüme özel niyetler ----
    if d.dugum == "seslen":
        if niyet == "selam":
            return _selam(s, varliklar, kalan)
        if niyet == "bekle":
            d.seslendi = False
            d.kayit.append("Görevlinin işini bitirmesini beklemeyi seçtin")
            _beklemeye_al(s)
            return False

    if d.dugum == "urun":
        if niyet == "urun_sor":
            return _urun_sor(s)
        if niyet == "selam":
            s.eylemler.append(_eylem("karsila_kisa"))
            return True
        if niyet == "ayril":
            # Başka bir ürünün yerini öğrenip teşekkür etmek de buraya düşer: ürün alınmadan bitiş
            return _bitir(s, urunlu=False, eylem_adi="vedalas_urunsuz")

    if d.dugum == "boyut":
        if niyet == "alternatif_sor":
            b = bilgiler(d)
            d.kayit.append("Başka bir boyut sordun")
            return _yonlendir(s, b["alternatif"], eylem_adi="alternatif_onayla")
        if niyet == "ayril":
            return _bitir(s, urunlu=False, eylem_adi="vedalas_urunsuz")

    if d.dugum == "gelis":
        if niyet == "gelis_sor":
            d.kayit.append(GELIS_KAYDI)
            s.eylemler.append(_eylem("gelis_zamani_soyle"))
            return True
        if niyet == "ayril":
            return _bitir(s, urunlu=False, eylem_adi="vedalas_urunsuz")

    if d.dugum == "tesekkur":
        if niyet == "tesekkur":
            d.kayit.append("Teşekkür ettin")
            return _bitir(s, urunlu=True, eylem_adi="vedalas")
        if niyet == "ayril":
            return _bitir(s, urunlu=True, eylem_adi="vedalas_kisa")
        if niyet == "urun_sor" and d.yonlendirilen:
            # Kullanıcı yeri tekrar sordu: aynı tarif tekrarlanır
            yer_id = veri.urun(d.urun_id)["yer"]
            s.eylemler.append(_yer_eylemi("yer_tarif_et", yer_id, esya=d.yonlendirilen))
            return True

    if d.dugum == "onay":
        return _onay(s, niyet, varliklar)

    # Buraya düşülmemeli; düşülürse güvenli taraf: anlaşılmadı.
    s.eylemler.append(_eylem("anlayamadim"))
    return False


# ---------------------------------------------------------------------------
# 6. Niyet işleyicileri
# ---------------------------------------------------------------------------

def _selam(s: MotorSonucu, varliklar: dict[str, str], kalan: list[str]) -> bool:
    d, v = s.durum, s.durum.varyasyon
    d.kayit.append("Görevliye seslendin")

    # Görevli başka müşteriyle konuşuyor: "bir saniye" der ve sohbetine döner.
    if v.gorevli == "sohbet" and not d.sohbet_bitti:
        d.seslendi = True
        s.olaylar.append("gorevli_bakar")
        s.eylemler.append(_eylem("bir_saniye_de"))
        # Selamla birlikte ürün de söylendiyse ("Merhaba, süt arıyorum") sakla:
        # bekleme bitince görevli hatırlayabilir ya da tekrar sorabilir (varyasyon).
        asil = next((n for n in kalan if n not in GENEL_NIYETLER and n != "selam"), None)
        if asil:
            d.bekleyen = BekleyenNiyet(niyet=asil, donus_dugumu="urun", varliklar=varliklar)
        _beklemeye_al(s)
        return False

    # Görevli raf düzenliyor: önce kullanıcıya döner.
    if v.gorevli == "raf" and not d.gorevli_dondu:
        d.gorevli_dondu = True
        s.olaylar.append("gorevli_doner")

    d.dugum = "urun"
    # Arkasından başka niyet geliyorsa kısa selam yeter ("Merhaba! Süt arkadaki...").
    s.eylemler.append(_eylem("karsila_kisa" if kalan else "karsila"))
    return True


def _urun_sor(s: MotorSonucu) -> bool:
    d = s.durum
    b = bilgiler(d)
    d.urun_soruldu = True
    d.kayit.append(f"{veri.tr_buyuk_bas(b['istenen'])} sordun")
    stok = etkin_stok(d)

    if stok == "var":
        return _yonlendir(s, b["istenen"], eylem_adi="yer_tarif_et")
    if stok == "boyut":
        d.dugum = "boyut"
        s.eylemler.append(_eylem("boyut_yok_bildir"))
        return True
    # stok == "yok": benzer ürün önerilmez (karar), sadece "yok" denir
    d.dugum = "gelis"
    s.eylemler.append(_eylem("hic_yok_bildir"))
    return True


def _yonlendir(s: MotorSonucu, esya: str, eylem_adi: str) -> bool:
    """Görevli eşyanın yerini söyler ve işaret eder; sıradaki adım teşekkür."""
    d = s.durum
    yer_id = veri.urun(d.urun_id)["yer"]
    s.eylemler.append(_yer_eylemi(eylem_adi, yer_id, esya=esya))
    d.yonlendirilen = esya
    d.dugum = "tesekkur"
    d.kayit.append(f"Görevli sana {esya} için yol tarif etti")
    return True


def _baska_urun(s: MotorSonucu, varliklar: dict[str, str]) -> bool:
    """
    Görev dışı bir ürün soruldu ("ekmek nerede"). Görevli yalnızca küçük mağaza
    haritasından yer söyler; listede yoksa bilmediğini söyler. Görevi hatırlatmak
    görevlinin değil rehberin işidir.
    """
    d = s.durum
    soz = varliklar.get("urun", "").strip()
    gorev_urunu = veri.urun(d.urun_id)["ad"]

    # Aslında görev ürününü soruyorsa ("süt nerede") normal akışa yönlendir
    if soz and veri.tr_kucuk(gorev_urunu) in veri.tr_kucuk(soz) and d.dugum == "urun":
        return _urun_sor(s)

    if soz and soz not in d.baska_sorulan:
        d.baska_sorulan.append(soz)
    d.kayit.append(f"Başka bir ürünü sordun: {soz}" if soz else "Başka bir ürünü sordun")

    yer_id = veri.kategori_yeri(soz) if soz else None
    if yer_id:
        s.eylemler.append(_yer_eylemi("baska_urun_yeri", yer_id, esya=soz))
    else:
        s.eylemler.append(_eylem("baska_urun_bilinmiyor"))
    b = bilgiler(d)
    s.rehber_ek = f"Unutma, bugün {b['istenen']} almak istiyorsun."
    return True


def _onay(s: MotorSonucu, niyet: str, varliklar: dict[str, str]) -> bool:
    """Görevlinin 'Süt mü arıyorsunuz?' gibi sorusuna verilen cevap."""
    d = s.durum
    bekleyen = d.bekleyen
    d.bekleyen = None
    donus = bekleyen.donus_dugumu if bekleyen else "urun"
    d.dugum = donus

    if niyet == "hayir":
        s.eylemler.append(_eylem("tekrar_sor"))
        return True
    if niyet == "evet" and bekleyen:
        return _tek_niyet(s, bekleyen.niyet, bekleyen.varliklar, [])
    # "Evet, süt" gibi doğrudan asıl niyeti söylediyse onu işle
    return _tek_niyet(s, niyet, varliklar, [])


def _beklemeye_al(s: MotorSonucu) -> None:
    d = s.durum
    d.dugum = "bekleme"
    s.bekleme = Bekleme(saniye=d.varyasyon.bekleme_saniye)


def _bitir(s: MotorSonucu, urunlu: bool, eylem_adi: str) -> bool:
    d = s.durum
    if not urunlu:
        d.kayit.append(
            "Teşekkür edip ürünü almadan ayrılmaya karar verdin" if d.urun_soruldu
            else "Aradığın ürünü sormadan ayrılmaya karar verdin"
        )
    s.eylemler.append(_eylem(eylem_adi))
    d.bitti, d.urunlu, d.dugum = True, urunlu, "bitti"
    return False


# ---------------------------------------------------------------------------
# 7. Niyet taşımayan girdiler: sessizlik, bekleme sonu, onarım
# ---------------------------------------------------------------------------

def sessiz(durum: OturumDurumu) -> MotorSonucu:
    """Kullanıcı bir süre hiçbir şey yapmadı. Görevlinin durumuna göre farklı davranılır."""
    d = durum.model_copy(deep=True)
    s = MotorSonucu(durum=d)
    if d.bitti:
        return s

    if d.dugum == "seslen":
        mod = d.varyasyon.gorevli
        if mod == "bos":
            # Görevli kullanıcıyı görüyor ve kendisi sorar
            d.dugum = "urun"
            d.kayit.append("Görevli seni fark edip kendisi sordu")
            s.eylemler.append(_eylem("kendiliginden_sor"))
        elif mod == "raf":
            # Arkası dönük görevli fark etmez; sadece rehber ipucu verir
            # Temel rehber zaten "arkası dönük, seslen" diyor; aynı şeyi tekrarlamayız
            s.rehber_ek = "Seni henüz fark etmedi."
        elif not d.sohbet_bitti:
            # Sohbet sırasında sessiz kalmak = beklemek
            d.seslendi = False
            d.kayit.append("Görevlinin işini bitirmesini bekledin")
            _beklemeye_al(s)
    elif d.dugum not in ("bekleme", "bitti"):
        s.rehber_ek = "Acele etme. Hazır olduğunda devam edebilirsin."
    return s


def bekleme_bitti(durum: OturumDurumu) -> MotorSonucu:
    """Görevli diğer müşteriyle işini bitirdi; diğer müşteri ayrılır, görevli kullanıcıya döner."""
    d = durum.model_copy(deep=True)
    s = MotorSonucu(durum=d)
    if d.dugum != "bekleme":
        return s

    d.sohbet_bitti = True
    if d.seslendi:
        d.kayit.append("Görevli işini bitirene kadar bekledin")
    s.olaylar.append("sohbet_biter")
    s.eylemler.append(Eylem(ad="diger_musteri_tesekkur", jest="", kim="diger"))

    if d.bekleyen and d.varyasyon.hafiza == "hatirla":
        # Görevli kullanıcının söylediği ürünü hatırlıyor ve onaylatıyor
        d.dugum = "onay"
        s.eylemler.append(_eylem("bekleyen_hatirla"))
    elif d.seslendi:
        # Görevli hatırlamıyor (ya da ürün söylenmemişti): özür dileyip tekrar sorar
        d.bekleyen = None
        d.dugum = "urun"
        s.eylemler.append(_eylem("ozur_buyurun"))
    else:
        d.dugum = "urun"
        s.eylemler.append(_eylem("karsila"))
    return s


def onarim(durum: OturumDurumu, tur: str) -> MotorSonucu:
    """
    Onarım kartları: 'tekrar', 'yavas', 'sure'. LLM çağrılmaz, adım değişmez.
    Görevli henüz hiçbir şey söylemediyse anlamsız oldukları için yok sayılır.
    """
    d = durum.model_copy(deep=True)
    s = MotorSonucu(durum=d)
    if not d.gorevli_konustu or d.bitti or d.dugum == "bekleme":
        return s

    if tur == "sure":
        s.eylemler.append(_eylem("acele_etmeyin"))
        return s

    son = next((t for t in reversed(d.gecmis) if t.kim == "gorevli"), None)
    if son:
        s.eylemler.append(Eylem(
            ad="tekrar",
            jest=son.jest or VARSAYILAN_JEST,
            sabit_metin=f"Tabii. {son.metin}",
            hiz=0.7 if tur == "yavas" else 1.0,
        ))
    return s


# ---------------------------------------------------------------------------
# 8. Rehber metinleri
# ---------------------------------------------------------------------------

def rehber(durum: OturumDurumu) -> str:
    """Ekranın altındaki kısa açıklama. Rehber hiçbir zaman 'yanlış' demez."""
    d = durum
    if d.dugum == "seslen":
        return {
            "bos": "Görevli seni görüyor. Ona seslen.",
            "raf": "Görevli sana arkası dönük, raf düzenliyor. Dikkatini çekmek için ona seslen.",
            "sohbet": "Görevli başka bir müşteriyle konuşuyor. Ona seslenebilir ya da konuşmasının bitmesini bekleyebilirsin.",
        }[d.varyasyon.gorevli]
    return {
        "bekleme": "Görevli diğer müşteriyle konuşmasını bitiriyor. Biraz bekle.",
        "urun": "Aradığın ürünü söyle.",
        "boyut": "İstediğin boyut yokmuş. Başka bir şey sorabilir ya da teşekkür edebilirsin.",
        "gelis": "Ürün şu an yokmuş. Ne zaman geleceğini sorabilir ya da teşekkür edip ayrılabilirsin.",
        "tesekkur": "Görevli yolu tarif etti. Teşekkür edebilirsin.",
        "onay": "Görevlinin sorusuna cevap ver.",
        "bitti": "",
    }[d.dugum]
