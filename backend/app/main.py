"""
Sunucu (FastAPI)
================

Uç noktalar:
    GET  /api/senaryo  -> ürün listesi ve zorluk seviyeleri (seçim ekranı için)
    GET  /api/yetenekler -> sunucuda hangi servisler hazır (LLM, STT, TTS)
    POST /api/oturum   -> yeni oyun: varyasyonlar seçilir, başlangıç durumu döner
    POST /api/konus    -> kullanıcının bir girdisi; görevlinin cevabı ve yeni durum döner
    POST /api/stt      -> ses kaydı -> metin   (servis yoksa 501, tarayıcı kendi özelliğini kullanır)
    POST /api/tts      -> metin -> ses         (servis yoksa 501, tarayıcı kendi sesini kullanır)

Ayrıca frontend klasörünü "/" adresinden sunar; böylece tek komutla her şey çalışır.

Çalıştırma (backend klasöründe):
    uvicorn app.main:app --reload
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import akis, veri
from .dil.saglayici import baglanti_var_mi, saglayici_olustur
from .modeller import KonusCevabi, KonusIstegi, OturumIstegi
from .ses import stt, tts

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("magaza")

@asynccontextmanager
async def yasam_dongusu(_app: FastAPI):
    # Hangi LLM ile çalıştığımızı başlangıçta bir kez yazalım
    log.info("LLM sağlayıcısı: %s", saglayici_olustur().ad)
    yield


app = FastAPI(title="Mağaza senaryosu", version="0.1", lifespan=yasam_dongusu)


# ---------------------------------------------------------------------------
# Senaryo uç noktaları
# ---------------------------------------------------------------------------

@app.get("/api/senaryo")
async def senaryo() -> dict:
    """Seçim ekranı için ürünler ve zorluk seviyeleri. Gizli bir bilgi içermez."""
    d = veri.veri()
    return {
        "urunler": [{"id": u["id"], "ad": u["ad"], "istenen": u["istenen"], "yalin": u["yalin"], "ikon": u["ikon"]} for u in d["urunler"]],
        "zorluklar": list(d["zorluklar"].keys()),
    }


@app.get("/api/yetenekler")
async def yetenekler() -> dict:
    """
    Tarayıcı hangi servislerin sunucuda hazır olduğunu buradan öğrenir.
    llm_hazir: LLM'e küçük bir deneme çağrısı yapılır (15 sn önbellekli); zorluk modları buna bakar.
    Ses servisleri yoksa tarayıcının kendi özelliklerine düşülür.
    """
    from .ayarlar import AYARLAR
    return {
        "llm": saglayici_olustur().ad,
        "llm_hazir": await baglanti_var_mi(),   # gerçekten cevap veriyor mu (anahtar/ağ dahil)
        "stt": AYARLAR.stt_saglayici != "yok",
        "tts": AYARLAR.tts_saglayici != "yok",
    }


@app.post("/api/oturum", response_model=KonusCevabi)
async def oturum(istek: OturumIstegi) -> KonusCevabi:
    try:
        return await akis.oturum_baslat(istek)
    except KeyError:
        raise HTTPException(status_code=404, detail="Böyle bir ürün yok.")


@app.post("/api/konus", response_model=KonusCevabi)
async def konus(istek: KonusIstegi) -> KonusCevabi:
    try:
        return await akis.konus(istek)
    except KeyError:
        raise HTTPException(status_code=400, detail="Oturum durumu geçersiz.")


# ---------------------------------------------------------------------------
# Ses uç noktaları
# ---------------------------------------------------------------------------

@app.post("/api/stt")
async def sesi_yaziya(ses: UploadFile = File(...)) -> dict:
    veri_baytlari = await ses.read()
    metin = await stt.yaziya_cevir(veri_baytlari, ses.content_type or "audio/webm")
    del veri_baytlari  # ses kaydı saklanmaz
    if metin is None:
        raise HTTPException(status_code=501, detail="STT servisi yapılandırılmadı.")
    return {"metin": metin}


class TTSIstegi(BaseModel):
    metin: str = Field(min_length=1, max_length=300)
    hiz: float = Field(default=1.0, ge=0.5, le=1.5)
    cinsiyet: Literal["kadin", "erkek"] = "kadin"


@app.post("/api/tts")
async def yaziyi_sese(istek: TTSIstegi) -> Response:
    sonuc = await tts.sese_cevir(istek.metin, istek.hiz, istek.cinsiyet)
    if sonuc is None:
        raise HTTPException(status_code=501, detail="TTS servisi yapılandırılmadı.")
    ses, mime = sonuc
    return Response(content=ses, media_type=mime)


# ---------------------------------------------------------------------------
# Arayüz dosyaları (en sonda: /api/... adreslerini gölgelemesin)
# ---------------------------------------------------------------------------

class DogrulamaliStatik(StaticFiles):
    """
    Arayüz dosyalarını her seferinde yeniden doğrulatır (Cache-Control: no-cache).
    Değişmediyse tarayıcı 304 alır, değiştiyse yenisini indirir. Böylece JS modüllerinin
    (sahne.js gibi) eski kopyası tarayıcıda kalıp çizim ile ses uyumsuz çalışmaz.
    """

    async def get_response(self, path: str, scope):
        yanit = await super().get_response(path, scope)
        yanit.headers["Cache-Control"] = "no-cache"
        return yanit


ARAYUZ = Path(__file__).resolve().parents[2] / "frontend"
if ARAYUZ.exists():
    app.mount("/", DogrulamaliStatik(directory=ARAYUZ, html=True), name="arayuz")
