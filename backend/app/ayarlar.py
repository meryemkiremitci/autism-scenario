"""
Sunucu ayarları
===============

Bütün ayarlar ortam değişkenlerinden okunur (bkz. .env.example). Gizli anahtarlar
yalnızca sunucuda durur; tarayıcıya hiçbir zaman gönderilmez.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env_dosyasini_oku() -> None:
    """
    backend/.env dosyası varsa içindeki ANAHTAR=değer satırlarını ortam değişkeni yapar.
    (Ek bir kütüphane gerektirmesin diye basit bir okuyucu.)
    Ortamda zaten tanımlı olan değişkenlerin üzerine yazmaz.
    """
    yol = Path(__file__).resolve().parent.parent / ".env"
    if not yol.exists():
        return
    for satir in yol.read_text(encoding="utf-8").splitlines():
        satir = satir.strip()
        if not satir or satir.startswith("#") or "=" not in satir:
            continue
        anahtar, deger = satir.split("=", 1)
        os.environ.setdefault(anahtar.strip(), deger.strip().strip('"').strip("'"))


_env_dosyasini_oku()


@dataclass(frozen=True)
class SunucuAyarlari:
    # Hangi LLM kullanılacak: "anthropic", "azure_openai" ya da "sahte".
    # "sahte" = API anahtarı olmadan çalışan, anahtar kelimeye bakan basit kural sistemi.
    llm_saglayici: str = os.getenv("LLM_SAGLAYICI", "sahte")
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")

    # Azure OpenAI. Endpoint: https://<kaynak-adi>.openai.azure.com
    azure_openai_api_key: str = os.getenv("AZURE_OPENAI_API_KEY", "")
    azure_openai_endpoint: str = os.getenv("AZURE_OPENAI_ENDPOINT", "")
    azure_openai_api_version: str = os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21")

    # Anlama tek bir sınıflandırma yaptığı için küçük ve hızlı bir model yeterli.
    # Azure OpenAI kullanılırken buraya modelin değil "deployment"ın adı yazılır.
    anlama_modeli: str = os.getenv("ANLAMA_MODELI", "claude-haiku-5-5")
    cevap_modeli: str = os.getenv("CEVAP_MODELI", "claude-haiku-5-5")

    # LLM bu süreden uzun sürerse beklenmez, şablona düşülür (saniye).
    llm_zaman_asimi: float = float(os.getenv("LLM_ZAMAN_ASIMI", "6"))

    # Serbest yazı/seste görevlinin cümlesini LLM kursun mu? Kapalıysa hep şablon kullanılır.
    llm_cevap_acik: bool = os.getenv("LLM_CEVAP_ACIK", "1") == "1"

    # LLM'e gönderilecek konuşma geçmişi (son kaç satır)
    gecmis_uzunlugu: int = int(os.getenv("GECMIS_UZUNLUGU", "8"))

    # Ses servisleri: "yok" = tarayıcının kendi özellikleri kullanılır.
    stt_saglayici: str = os.getenv("STT_SAGLAYICI", "yok")
    tts_saglayici: str = os.getenv("TTS_SAGLAYICI", "yok")

    # Azure Speech (TTS_SAGLAYICI=azure). Bölge örn. "westeurope"; ses adı Türkçe bir Neural ses olmalı.
    azure_speech_key: str = os.getenv("AZURE_SPEECH_KEY", "")
    azure_speech_region: str = os.getenv("AZURE_SPEECH_REGION", "")
    azure_speech_ses: str = os.getenv("AZURE_SPEECH_SES", "tr-TR-EmelNeural")


AYARLAR = SunucuAyarlari()
