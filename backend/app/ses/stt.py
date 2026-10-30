"""
Konuşmayı yazıya çevirme (STT)
==============================

Kullanıcının sesi buraya gelir ve metne çevrilir. Servis henüz seçilmedi; bu yüzden
varsayılan sağlayıcı "yok"tur ve uç nokta 501 döndürür. O durumda tarayıcı kendi
konuşma tanıma özelliğini kullanır (bkz. frontend/js/ses.js).

Gizlilik kuralları (KVKK):
  * Ses kaydı SAKLANMAZ: çevrildikten hemen sonra bellekten atılır.
  * Diske yazılmaz, günlüğe (log) içeriği basılmaz.

Yeni bir servis eklemek için: aşağıya bir sınıf yazıp `yaziya_cevir` içinde seçin.
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

from ..ayarlar import AYARLAR

log = logging.getLogger(__name__)


async def yaziya_cevir(ses: bytes, mime: str) -> Optional[str]:
    """
    Sesi metne çevirir. Servis yapılandırılmamışsa ya da hata olursa None döner.
    Konuşma bulunamadıysa "" döner (arayüz "bir şey duyamadım" der).
    """
    if AYARLAR.stt_saglayici == "azure" and AYARLAR.azure_speech_key and AYARLAR.azure_speech_region:
        return await _azure(ses, mime)
    return None


async def _azure(ses: bytes, mime: str) -> Optional[str]:
    """
    Azure Speech kısa ses REST API'si (en fazla ~60 sn). Arayüz 16 kHz WAV gönderir;
    başka bir biçim gelirse olduğu gibi iletilir (webm/opus Azure'da güvenilir değil).
    """
    if mime.startswith("audio/wav") or mime.startswith("audio/x-wav"):
        mime = "audio/wav; codecs=audio/pcm; samplerate=16000"
    try:
        async with httpx.AsyncClient(timeout=AYARLAR.llm_zaman_asimi + 4) as istemci:
            yanit = await istemci.post(
                f"https://{AYARLAR.azure_speech_region}.stt.speech.microsoft.com/speech/recognition/conversation/cognitiveservices/v1",
                params={"language": "tr-TR", "format": "simple"},
                headers={
                    "Ocp-Apim-Subscription-Key": AYARLAR.azure_speech_key,   # anahtar sadece sunucuda
                    "Content-Type": mime,
                    "Accept": "application/json",
                },
                content=ses,
            )
        yanit.raise_for_status()
        sonuc = yanit.json()
    except Exception as hata:  # zaman aşımı, ağ, HTTP hatası, bozuk cevap (ses içeriği günlüğe yazılmaz)
        log.warning("Azure STT başarısız: %s", hata)
        return None
    if sonuc.get("RecognitionStatus") != "Success":
        return ""   # NoMatch / InitialSilenceTimeout: konuşma anlaşılmadı
    return (sonuc.get("DisplayText") or "").strip()
