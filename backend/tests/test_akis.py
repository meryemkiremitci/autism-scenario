"""
Uçtan uca akış testleri (sahte LLM ile)
=======================================

Gerçek bir LLM'e bağlanmadan, sunucunun uç noktalarını baştan sona dener.
Sahte sağlayıcı anlama için kural tabanlı yedeği kullanır, cevaplar şablondan gelir.
"""

from fastapi.testclient import TestClient

from app.main import app

istemci = TestClient(app)


def oturum(**ayar):
    yanit = istemci.post("/api/oturum", json={"urun_id": "sut", "ayarlar": {"zorluk": "zor", **ayar}})
    assert yanit.status_code == 200
    return yanit.json()


def konus(cevap, **girdi):
    yanit = istemci.post("/api/konus", json={"durum": cevap["durum"], "girdi": girdi})
    assert yanit.status_code == 200, yanit.text
    return yanit.json()


def test_senaryo_listesi():
    veri = istemci.get("/api/senaryo").json()
    assert len(veri["urunler"]) == 5 and "zor" in veri["zorluklar"]


def test_hazir_cumlelerle_bastan_sona():
    c = oturum(gorevli="raf", stok="var")
    assert "1 litrelik süt" in c["gorev"]
    c = konus(c, tur="hazir", metin="Pardon, bakar mısınız?", niyet="selam")
    assert "gorevli_doner" in c["olaylar"] and c["onarim_acik"]
    c = konus(c, tur="hazir", metin="1 litrelik süt arıyorum.", niyet="urun_sor")
    assert c["adimlar"][0]["jest"] == "isaret" and c["adimlar"][0]["kaynak"] == "sablon"
    c = konus(c, tur="hazir", metin="Teşekkür ederim.", niyet="tesekkur")
    assert c["bitis"]["urunlu"] is True


def test_serbest_yazi_kural_tabanli_anlama():
    c = oturum(gorevli="bos", stok="boyut")
    c = konus(c, tur="yazi", metin="merhaba, süt arıyorum")
    # İki niyet: kısa selam + boyut yok
    assert [a["eylem"] for a in c["adimlar"]] == ["karsila_kisa", "boyut_yok_bildir"]
    c = konus(c, tur="yazi", metin="yarım litrelik var mı acaba")
    assert c["adimlar"][0]["eylem"] == "alternatif_onayla"


def test_onarim_son_cumleyi_tekrarlar():
    c = oturum(gorevli="bos")
    c = konus(c, tur="hazir", metin="Merhaba", niyet="selam")
    c = konus(c, tur="onarim", metin="Biraz yavaş söyler misiniz?", niyet="yavas")
    assert c["adimlar"][0]["metin"].startswith("Tabii.") and c["adimlar"][0]["hiz"] == 0.7


def test_bekleme_akisi():
    c = oturum(gorevli="sohbet", hafiza="unut")
    c = konus(c, tur="hazir", metin="Merhaba", niyet="selam")
    assert c["bekleme"]["saniye"] > 0 and c["oneriler"] == []
    c = konus(c, tur="bekleme_bitti")
    assert [a["kim"] for a in c["adimlar"]] == ["diger", "gorevli"]
