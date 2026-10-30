"""
Senaryo motoru testleri
=======================

Motor LLM'den bağımsız olduğu için bütün dalları burada doğrudan deneyebiliyoruz.
Çalıştırma (backend klasöründe):   python -m pytest -q
"""

from app import motor
from app.modeller import Ayarlar


def yeni(**ayar) -> "motor.OturumDurumu":
    """Varsayılanları sabit, istenen ayarları verilmiş yeni bir oturum."""
    temel = dict(zorluk="zor", gorevli="bos", stok="var", hafiza="hatirla", boyut_acik=True)
    temel.update(ayar)
    return motor.baslangic("sut", Ayarlar(**temel))


def adlar(sonuc) -> list[str]:
    return [e.ad for e in sonuc.eylemler]


# --- Görevliye seslenme -----------------------------------------------------

def test_bosta_selam_karsilar():
    s = motor.isle(yeni(), ["selam"])
    assert adlar(s) == ["karsila"]
    assert s.durum.dugum == "urun"


def test_raf_modunda_gorevli_doner():
    s = motor.isle(yeni(gorevli="raf"), ["selam"])
    assert "gorevli_doner" in s.olaylar
    assert s.durum.gorevli_dondu


def test_iki_niyet_adim_atlar():
    # "Merhaba, süt arıyorum": kısa selam + doğrudan yer tarifi
    s = motor.isle(yeni(), ["selam", "urun_sor"])
    assert adlar(s) == ["karsila_kisa", "yer_tarif_et"]
    assert s.durum.dugum == "tesekkur"


def test_selamsiz_urun_sorusu_de_dikkat_ceker():
    s = motor.isle(yeni(gorevli="raf"), ["urun_sor"])
    assert "gorevli_doner" in s.olaylar
    assert adlar(s) == ["karsila_kisa", "yer_tarif_et"]


# --- Stok dalları ------------------------------------------------------------

def test_stok_var():
    d = motor.isle(yeni(), ["selam"]).durum
    s = motor.isle(d, ["urun_sor"])
    assert adlar(s) == ["yer_tarif_et"]
    assert s.eylemler[0].jest == "isaret"          # buzdolapları solda
    assert s.durum.dugum == "tesekkur"


def test_boyut_yok_sonra_alternatif():
    d = motor.isle(yeni(stok="boyut"), ["selam"]).durum
    s = motor.isle(d, ["urun_sor"])
    assert adlar(s) == ["boyut_yok_bildir"] and s.eylemler[0].jest == "omuz"
    s = motor.isle(s.durum, ["alternatif_sor"])
    assert adlar(s) == ["alternatif_onayla"]
    assert s.durum.yonlendirilen == "yarım litrelik süt"


def test_boyut_kapaliysa_boyut_yok_var_gibi_davranir():
    d = motor.isle(yeni(stok="boyut", boyut_acik=False), ["selam"]).durum
    assert adlar(motor.isle(d, ["urun_sor"])) == ["yer_tarif_et"]


def test_hic_yok_gelis_ve_urunsuz_bitis():
    d = motor.isle(yeni(stok="yok"), ["selam"]).durum
    s = motor.isle(d, ["urun_sor"])
    assert s.durum.dugum == "gelis"
    s = motor.isle(s.durum, ["gelis_sor"])
    assert adlar(s) == ["gelis_zamani_soyle"] and s.durum.dugum == "gelis"
    s = motor.isle(s.durum, ["ayril"])
    assert s.durum.bitti and s.durum.urunlu is False


def test_tesekkur_urunlu_bitis():
    d = motor.isle(yeni(), ["selam", "urun_sor"]).durum
    s = motor.isle(d, ["tesekkur"])
    assert adlar(s) == ["vedalas"] and s.durum.urunlu is True


def test_tamam_deyip_ayrilmak_da_gecerli():
    d = motor.isle(yeni(), ["selam", "urun_sor"]).durum
    s = motor.isle(d, ["ayril"])
    assert adlar(s) == ["vedalas_kisa"] and s.durum.bitti


# --- Görevli başka müşteriyle konuşuyor ----------------------------------------

def test_sohbette_bir_saniye_ve_hatirlama():
    s = motor.isle(yeni(gorevli="sohbet", hafiza="hatirla"), ["selam", "urun_sor"])
    assert adlar(s) == ["bir_saniye_de"] and s.bekleme is not None
    assert s.durum.bekleyen and s.durum.bekleyen.niyet == "urun_sor"
    s = motor.bekleme_bitti(s.durum)
    assert adlar(s) == ["diger_musteri_tesekkur", "bekleyen_hatirla"]
    assert s.durum.dugum == "onay"
    s = motor.isle(s.durum, ["evet"])
    assert adlar(s) == ["yer_tarif_et"]


def test_sohbette_unutursa_tekrar_sorar():
    s = motor.isle(yeni(gorevli="sohbet", hafiza="unut"), ["selam", "urun_sor"])
    s = motor.bekleme_bitti(s.durum)
    assert adlar(s) == ["diger_musteri_tesekkur", "ozur_buyurun"]
    assert s.durum.dugum == "urun"


def test_beklemeyi_secmek():
    s = motor.isle(yeni(gorevli="sohbet"), ["bekle"])
    assert s.durum.dugum == "bekleme"
    s = motor.bekleme_bitti(s.durum)
    assert adlar(s)[-1] == "karsila"


# --- Sessizlik -------------------------------------------------------------

def test_sessizlik_gorevli_durumuna_gore():
    assert adlar(motor.sessiz(yeni(gorevli="bos"))) == ["kendiliginden_sor"]
    raf = motor.sessiz(yeni(gorevli="raf"))
    assert adlar(raf) == [] and raf.rehber_ek                # arkası dönük, fark etmez
    assert motor.sessiz(yeni(gorevli="sohbet")).durum.dugum == "bekleme"


# --- Belirsizlik ve genel niyetler ---------------------------------------------

def test_orta_guven_netlestirir():
    d = motor.isle(yeni(), ["selam"]).durum
    s = motor.isle(d, ["urun_sor"], guven="orta", tahmin="süt")
    assert adlar(s) == ["netlestir"] and s.durum.dugum == "onay"
    s = motor.isle(s.durum, ["evet"])
    assert adlar(s) == ["yer_tarif_et"]


def test_dusuk_guven_seste_duzeltme_onerir():
    d = motor.isle(yeni(), ["selam"]).durum
    s = motor.isle(d, ["urun_sor"], guven="dusuk", duzeltilmis_metin="Süt arıyorum.", girdi_turu="ses")
    assert s.duzeltme == "Süt arıyorum." and not s.eylemler


def test_baska_urun_yeri_ve_bilinmeyen():
    d = motor.isle(yeni(), ["selam"]).durum
    s = motor.isle(d, ["baska_urun"], varliklar={"urun": "ekmek"})
    assert adlar(s) == ["baska_urun_yeri"] and s.durum.dugum == "urun"
    s = motor.isle(d, ["baska_urun"], varliklar={"urun": "çiçek"})
    assert adlar(s) == ["baska_urun_bilinmiyor"]


def test_gecersiz_niyet_anlasilmadi():
    d = motor.isle(yeni(), ["selam"]).durum
    assert adlar(motor.isle(d, ["gelis_sor"])) == ["anlayamadim"]


# --- Onarım --------------------------------------------------------------

def test_onarim_gorevli_konusmadan_yok_sayilir():
    assert adlar(motor.onarim(yeni(), "tekrar")) == []


# --- Ürün adımında veda ---------------------------------------------------------

def test_baska_urun_sorup_tesekkur_edince_biter():
    # Şemsiye görevi: "ekmek nerede" -> yer söylenir, adım değişmez; "tamam teşekkürler" -> veda
    d = motor.isle(yeni(), ["selam"]).durum
    s = motor.isle(d, ["baska_urun"], varliklar={"urun": "ekmek"})
    assert adlar(s) == ["baska_urun_yeri"] and s.durum.dugum == "urun"
    s = motor.isle(s.durum, ["ayril"])
    assert adlar(s) == ["vedalas_urunsuz"] and s.durum.bitti and s.durum.urunlu is False


def test_baska_urun_sorup_ayrilinca_ozet_baska_urun_der():
    from app import akis
    d = motor.isle(yeni(), ["selam"]).durum
    d = motor.isle(d, ["baska_urun"], varliklar={"urun": "ekmek"}).durum
    s = motor.isle(d, ["ayril"])
    assert s.durum.urun_soruldu is False and s.durum.baska_sorulan == ["ekmek"]
    ozet = akis._paketle(s, []).bitis.ozet
    assert any("başka bir ürünü (ekmek) sordun" in satir for satir in ozet)
    assert not any("Ürünü almadan ayrıldın" in satir for satir in ozet)


def test_baska_urun_sonra_kendi_urunu_basarili_sayilir():
    # Önce ekmek, sonra görev ürününü (süt) sorar, teşekkür eder: normal başarı
    d = motor.isle(yeni(), ["selam"]).durum
    d = motor.isle(d, ["baska_urun"], varliklar={"urun": "ekmek"}).durum
    d = motor.isle(d, ["urun_sor"]).durum
    assert d.dugum == "tesekkur" and d.urun_soruldu
    s = motor.isle(d, ["tesekkur"])
    assert s.durum.bitti and s.durum.urunlu is True


def test_hic_sormadan_ayrilinca_ozet_bunu_soyler():
    from app import akis
    d = motor.isle(yeni(), ["selam"]).durum
    s = motor.isle(d, ["ayril"])
    ozet = akis._paketle(s, []).bitis.ozet
    assert "Aradığın ürünü sormadan ayrıldın." in ozet


# --- Görevlinin cinsiyeti ---------------------------------------------------------

def test_gorevli_cinsiyeti_secilebilir_ve_rastgele_iki_degeri_de_alir():
    import random
    for c in ("kadin", "erkek"):
        assert motor.baslangic("sut", Ayarlar(gorevli_cinsiyet=c)).varyasyon.gorevli_cinsiyet == c
    gorulen = {motor.baslangic("sut", Ayarlar(), random.Random(i)).varyasyon.gorevli_cinsiyet for i in range(20)}
    assert gorulen == {"kadin", "erkek"}
