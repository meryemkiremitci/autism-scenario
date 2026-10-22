"""
Sözleşmeler (veri modelleri)
============================

Bu dosya, sistemin parçaları arasında gidip gelen bütün verilerin şeklini tanımlar:

  * Tarayıcı  <-> Sunucu   : OturumIstegi, KonusIstegi, KonusCevabi
  * Sunucu    <-> LLM      : AnlamaSonucu, CevapSonucu

Pydantic kullanıyoruz; bir veri bu şekillere uymuyorsa FastAPI isteği otomatik
olarak reddeder, LLM'den gelen bozuk cevaplar da burada yakalanır.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Sabit değer kümeleri
# ---------------------------------------------------------------------------

# Görevlinin oyun başındaki durumu
GorevliDurumu = Literal["bos", "raf", "sohbet"]

# Ürünün stok durumu
StokDurumu = Literal["var", "boyut", "yok"]

# Görevli meşgulken söylenen ürünü bekleme sonunda hatırlıyor mu?
Hafiza = Literal["hatirla", "unut"]

# Görevlinin konuşma dili
DilDuzeyi = Literal["sade", "gundelik"]

# Konuşmanın adımları (düğümler). Ayrıntısı motor.py içinde.
Dugum = Literal["seslen", "bekleme", "urun", "boyut", "gelis", "tesekkur", "onay", "bitti"]

# Kullanıcı girdisinin türü
GirdiTuru = Literal[
    "hazir",          # hazır cümle seçildi (niyet zaten belli)
    "yazi",           # serbest yazı
    "ses",            # sesli konuşma (yazıya çevrilmiş hali gelir)
    "onarim",         # "Tekrar söyler misiniz?" gibi onarım kartı
    "sessiz",         # kullanıcı bir süre hiçbir şey yapmadı
    "bekleme_bitti",  # görevli diğer müşteriyle işini bitirdi (tarayıcı süreyi saydı)
]

# Anlama çağrısının güven düzeyi. Sayı yerine kategori kullanıyoruz,
# çünkü LLM'lerin "%73 eminim" gibi sayıları güvenilir değildir.
Guven = Literal["yuksek", "orta", "dusuk"]


# ---------------------------------------------------------------------------
# Oturum ayarları ve oyunun gerçekleri
# ---------------------------------------------------------------------------

class Ayarlar(BaseModel):
    """Oturum başlarken zorluk paketinden (ve kullanıcının değişikliklerinden) çıkan ayarlar."""

    zorluk: Literal["kolay", "orta", "zor"] = "orta"
    # None = zorluk paketinden rastgele seç. Bir değer verilirse o sabitlenir.
    gorevli: Optional[GorevliDurumu] = None
    stok: Optional[StokDurumu] = None
    hafiza: Optional[Hafiza] = None
    boyut_acik: Optional[bool] = None
    dil_duzeyi: Optional[DilDuzeyi] = None
    bekleme_saniye: Optional[int] = Field(default=None, ge=1, le=60)
    sessizlik_saniye: Optional[int] = Field(default=None, ge=3, le=120)


class Varyasyon(BaseModel):
    """Oturum başında KODUN seçtiği koşullar. Oyun boyunca değişmez."""

    gorevli: GorevliDurumu
    stok: StokDurumu
    hafiza: Hafiza
    boyut_acik: bool
    dil_duzeyi: DilDuzeyi
    bekleme_saniye: int
    sessizlik_saniye: int


class Tur(BaseModel):
    """Konuşma geçmişindeki tek bir satır."""

    kim: Literal["musteri", "gorevli", "diger"]
    metin: str
    tur: Optional[str] = None      # müşteri satırları için girdi türü (hazir, yazi, ses...)
    jest: Optional[str] = None     # görevli satırları için (onarımda tekrar kullanılır)


class BekleyenNiyet(BaseModel):
    """Söylenmiş ama henüz cevaplanmamış niyet (ör. görevli meşgulken 'süt arıyorum')."""

    niyet: str
    donus_dugumu: Dugum                  # onay alınınca hangi adıma dönülecek
    varliklar: dict[str, str] = {}


class OturumDurumu(BaseModel):
    """
    Senaryo motorunun her an bildiği şeylerin tamamı.

    Sunucu bunu HATIRLAMAZ: her istekte tarayıcı gönderir, sunucu yeni hâlini döndürür.
    Böylece veritabanına gerek kalmaz ve sunucu hafif kalır.
    """

    surum: int = 1                       # sözleşme değişirse eski/yeni durumu ayırt etmek için
    urun_id: str
    varyasyon: Varyasyon
    dugum: Dugum = "seslen"
    bekleyen: Optional[BekleyenNiyet] = None

    # Görsel ve akış bayrakları
    gorevli_dondu: bool = False          # raf modunda görevli bize döndü mü
    sohbet_bitti: bool = False           # sohbet modunda diğer müşteri ayrıldı mı
    seslendi: bool = False               # sohbet sırasında kullanıcı seslendi mi
    gorevli_konustu: bool = False        # onarım kartları ancak bundan sonra görünür
    yonlendirilen: Optional[str] = None  # görevlinin yerini tarif ettiği eşya

    gecmis: list[Tur] = []
    kayit: list[str] = []                # bitiş ekranındaki "yaptıkların" listesi
    bitti: bool = False
    urunlu: Optional[bool] = None


# ---------------------------------------------------------------------------
# Tarayıcı <-> Sunucu
# ---------------------------------------------------------------------------

class OturumIstegi(BaseModel):
    urun_id: str
    ayarlar: Ayarlar = Ayarlar()


class Girdi(BaseModel):
    tur: GirdiTuru
    metin: Optional[str] = Field(default=None, max_length=300)
    niyet: Optional[str] = None          # hazır cümle ve onarım kartları niyetiyle gelir


class KonusIstegi(BaseModel):
    durum: OturumDurumu
    girdi: Girdi


class HazirCumle(BaseModel):
    metin: str
    niyet: str


class GorevliAdimi(BaseModel):
    """Görevlinin bir cevabı: ne söyleyecek, hangi jesti yapacak."""

    eylem: str
    metin: str
    jest: str
    hiz: float = 1.0                     # "Biraz yavaş söyler misiniz?" için 0.7
    kaynak: Literal["sablon", "llm"] = "sablon"
    kim: Literal["gorevli", "diger"] = "gorevli"   # "diger" = görevliyle konuşan müşteri


class Bekleme(BaseModel):
    """Tarayıcı bu süre boyunca girdiyi kilitler, sonra 'bekleme_bitti' gönderir."""

    saniye: int
    cubuk_gorunur: bool = True


class Bitis(BaseModel):
    urunlu: bool
    ozet: list[str]


class KonusCevabi(BaseModel):
    durum: OturumDurumu
    adimlar: list[GorevliAdimi] = []
    olaylar: list[str] = []              # görsel olaylar: gorevli_doner, sohbet_baslar, sohbet_biter...
    oneriler: list[HazirCumle] = []      # yeni adımın hazır cümleleri
    onarim_acik: bool = False            # onarım kartları gösterilsin mi
    rehber: str = ""                     # ekranın altındaki kısa açıklama
    duzeltme: Optional[str] = None       # "Şunu mu demek istedin?" (sadece sesli girdide)
    bekleme: Optional[Bekleme] = None
    sessizlik_saniye: Optional[int] = None  # bu adımda kaç saniye sessizlikten sonra 'sessiz' gönderilsin
    bitis: Optional[Bitis] = None
    gorev: Optional[str] = None             # sadece oturum başında: görev kartının metni


# ---------------------------------------------------------------------------
# Sunucu <-> LLM
# ---------------------------------------------------------------------------

class AnlamaSonucu(BaseModel):
    """Anlama çağrısının cevabı. LLM yalnızca verilen listeden seçer."""

    niyetler: list[str] = Field(min_length=1, max_length=3)
    guven: Guven
    duzeltilmis_metin: Optional[str] = None   # ses yanlış duyulduysa tahmini doğru cümle
    tahmin: Optional[str] = None              # belirsizse kastedilen şey (ör. "süt")
    varliklar: dict[str, str] = {}            # cümleden çıkan ürün, boyut gibi bilgiler


class CevapSonucu(BaseModel):
    """Cevap çağrısının cevabı. Tek alan: görevlinin cümlesi."""

    cevap: str = Field(min_length=1, max_length=220)
