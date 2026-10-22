"""
LLM çıktılarının doğrulanması
=============================

Gerçek LLM yerine istediğimiz cevabı döndüren bir taklit sağlayıcı kullanıyoruz.
Amaç: LLM yanlış bir şey söylediğinde sistemin şablona düştüğünü göstermek.
"""

import asyncio

from app import motor
from app.dil import anlama, cevap
from app.dil.dogrulama import anlama_dogrula, cevap_dogrula
from app.modeller import Ayarlar, Girdi


class TaklitLLM:
    """Her çağrıda önceden verilen cevabı döndürür."""
    ad = "taklit"

    def __init__(self, cevap):
        self.cevap = cevap

    async def json_iste(self, *args, **kwargs):
        return self.cevap


def durum():
    d = motor.baslangic("sut", Ayarlar(zorluk="zor", gorevli="bos", stok="boyut", boyut_acik=True))
    return motor.isle(d, ["selam"]).durum


def test_anlama_gecersiz_niyeti_atar():
    sonuc = anlama_dogrula({"niyetler": ["uydurma", "urun_sor"], "guven": "yuksek"}, {"urun_sor"})
    assert sonuc.niyetler == ["urun_sor"]
    assert anlama_dogrula({"niyetler": ["uydurma"], "guven": "yuksek"}, {"urun_sor"}) is None
    assert anlama_dogrula({"bozuk": True}, {"urun_sor"}) is None


def test_cevap_uydurma_reyonu_reddeder():
    izinli = "Süt arkadaki buzdolaplarında, en solda."
    assert cevap_dogrula({"cevap": "Süt beşinci reyonda."}, izinli, []) is None
    assert cevap_dogrula({"cevap": "Sütler arkadaki buzdolaplarında, en solda."}, izinli, [])


def test_cevap_soylenmeyecek_alternatifi_reddeder():
    cumle = {"cevap": "1 litrelik kalmadı ama yarım litrelik süt var."}
    assert cevap_dogrula(cumle, "1 litrelik süt yarım litrelik süt", ["yarım litrelik süt"]) is None


def test_llm_bozuk_cevap_verirse_sablona_duser(monkeypatch):
    monkeypatch.setattr(cevap, "saglayici_olustur", lambda: TaklitLLM({"cevap": "Süt 7. reyonda, 5 lira."}))
    eylem = motor.Eylem(ad="boyut_yok_bildir", jest="omuz")
    adim = asyncio.run(cevap.cumle_kur(eylem, durum(), "yazi", "süt arıyorum"))
    assert adim.kaynak == "sablon" and adim.metin.startswith("Maalesef")


def test_llm_iyi_cevap_verirse_kullanilir(monkeypatch):
    monkeypatch.setattr(cevap, "saglayici_olustur", lambda: TaklitLLM({"cevap": "Maalesef 1 litrelik süt bugün bitti."}))
    eylem = motor.Eylem(ad="boyut_yok_bildir", jest="omuz")
    adim = asyncio.run(cevap.cumle_kur(eylem, durum(), "yazi", "süt arıyorum"))
    assert adim.kaynak == "llm"


def test_anlama_llm_yoksa_kurala_duser(monkeypatch):
    monkeypatch.setattr(anlama, "saglayici_olustur", lambda: TaklitLLM(None))
    sonuc, kaynak = asyncio.run(anlama.anla(durum(), Girdi(tur="yazi", metin="süt nerede")))
    assert kaynak == "kural" and sonuc.niyetler == ["urun_sor"]
