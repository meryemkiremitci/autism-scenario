"""
Metni konuşmaya çevirme (TTS)
=============================

Görevlinin cümlesi buraya gelir ve ses dosyasına çevrilir. Varsayılan sağlayıcı
"yok"tur ve uç nokta 501 döndürür; o durumda tarayıcı kendi konuşma sentezini
(speechSynthesis) kullanır. Azure için TTS_SAGLAYICI=azure ve AZURE_SPEECH_* ayarları gerekir.

Not: Sık tekrar eden cümlelerin ("Rica ederim, iyi alışverişler!") sesi bir kez
üretilip saklanabilir; aşağıdaki küçük önbellek bunun içindir.
"""

from __future__ import annotations

import logging
from typing import Optional
from xml.sax.saxutils import escape

import httpx

from ..ayarlar import AYARLAR

log = logging.getLogger(__name__)

# (metin, hız) -> (ses verisi, mime türü). Sadece görevlinin cümleleri; kişisel veri içermez.
_onbellek: dict[tuple[str, float, str], tuple[bytes, str]] = {}


async def sese_cevir(metin: str, hiz: float = 1.0, cinsiyet: str = "kadin") -> Optional[tuple[bytes, str]]:
    """Metni sese çevirir. Servis yapılandırılmamışsa ya da hata olursa None döner."""
    if AYARLAR.tts_saglayici == "yok":
        return None
    anahtar = (metin, hiz, cinsiyet)
    if anahtar in _onbellek:
        return _onbellek[anahtar]

    if AYARLAR.tts_saglayici == "azure" and AYARLAR.azure_speech_key and AYARLAR.azure_speech_region:
        sonuc = await _azure(metin, hiz, cinsiyet)
        if sonuc:
            _onbellek[anahtar] = sonuc
        return sonuc
    return None


async def _azure(metin: str, hiz: float, cinsiyet: str) -> Optional[tuple[bytes, str]]:
    ses = AYARLAR.azure_speech_ses_erkek if cinsiyet == "erkek" else AYARLAR.azure_speech_ses_kadin
    oran = f"{round((hiz - 1) * 100):+d}%"          # 0.7 -> "-30%", 1.0 -> "+0%"
    ssml = (
        f'<speak version="1.0" xml:lang="tr-TR"><voice name="{ses}">'
        f'<prosody rate="{oran}">{escape(metin)}</prosody></voice></speak>'
    )
    try:
        async with httpx.AsyncClient(timeout=AYARLAR.llm_zaman_asimi) as istemci:
            yanit = await istemci.post(
                f"https://{AYARLAR.azure_speech_region}.tts.speech.microsoft.com/cognitiveservices/v1",
                headers={
                    "Ocp-Apim-Subscription-Key": AYARLAR.azure_speech_key,   # anahtar sadece sunucuda
                    "Content-Type": "application/ssml+xml",
                    "X-Microsoft-OutputFormat": "audio-24khz-48kbitrate-mono-mp3",
                    "User-Agent": "magaza-senaryosu",
                },
                content=ssml.encode("utf-8"),
            )
        yanit.raise_for_status()
        return yanit.content, "audio/mpeg"
    except Exception as hata:  # zaman aşımı, ağ, HTTP hatası
        log.warning("Azure TTS başarısız: %s", hata)
        return None
