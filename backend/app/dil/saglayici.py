"""
LLM sağlayıcıları
=================

Sistemin geri kalanı hangi LLM'in kullanıldığını bilmez; sadece bu dosyadaki
`LLMSaglayici` arayüzünü kullanır. Başka bir servise geçmek için yeni bir sınıf
yazıp `saglayici_olustur()` içine eklemek yeterlidir.

Üç sağlayıcı var:
  * AnthropicSaglayici   : Claude API'yi (Messages API) çağırır.
  * AzureOpenAISaglayici : Azure OpenAI chat completions uç noktasını çağırır.
  * SahteSaglayici     : API anahtarı olmadan çalışır. Anlama için anahtar kelime
                         kurallarını kullanır, cevap üretmez (her zaman şablon).
                         Geliştirme, test ve sunum için kullanışlıdır.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional, Protocol

import httpx

from ..ayarlar import AYARLAR

log = logging.getLogger(__name__)


class LLMSaglayici(Protocol):
    """Bütün sağlayıcıların uyması gereken arayüz."""

    ad: str

    async def json_iste(self, sistem: str, kullanici: str, model: str, max_tokens: int = 300) -> Optional[dict[str, Any]]:
        """
        LLM'e bir istek gönderir ve cevabı JSON nesnesi olarak döndürür.
        Herhangi bir sorunda (zaman aşımı, ağ hatası, bozuk JSON) None döner;
        çağıran taraf bu durumda şablona düşer. Bu fonksiyon asla hata fırlatmaz.
        """
        ...


# ---------------------------------------------------------------------------
# Claude API
# ---------------------------------------------------------------------------

class AnthropicSaglayici:
    ad = "anthropic"
    URL = "https://api.anthropic.com/v1/messages"

    def __init__(self, api_key: str, zaman_asimi: float) -> None:
        self._api_key = api_key
        self._istemci = httpx.AsyncClient(timeout=zaman_asimi)

    async def json_iste(self, sistem: str, kullanici: str, model: str, max_tokens: int = 300) -> Optional[dict[str, Any]]:
        try:
            yanit = await self._istemci.post(
                self.URL,
                headers={
                    "x-api-key": self._api_key,               # anahtar sadece sunucuda
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": max_tokens,
                    "system": sistem,
                    "messages": [{"role": "user", "content": kullanici}],
                },
            )
            yanit.raise_for_status()
            # Cevap metin blokları halinde gelir; hepsini birleştiriyoruz
            metin = "".join(b.get("text", "") for b in yanit.json().get("content", []) if b.get("type") == "text")
            return _json_ayikla(metin)
        except Exception as hata:  # zaman aşımı, ağ, HTTP hatası, bozuk JSON...
            log.warning("LLM çağrısı başarısız (%s): %s", model, hata)
            return None


# ---------------------------------------------------------------------------
# Azure OpenAI
# ---------------------------------------------------------------------------

class AzureOpenAISaglayici:
    ad = "azure_openai"

    def __init__(self, api_key: str, endpoint: str, api_version: str, zaman_asimi: float) -> None:
        self._api_key = api_key
        self._endpoint = endpoint.rstrip("/")
        self._api_version = api_version
        self._istemci = httpx.AsyncClient(timeout=zaman_asimi)

    async def json_iste(self, sistem: str, kullanici: str, model: str, max_tokens: int = 300) -> Optional[dict[str, Any]]:
        # Azure'da `model` yerine URL'deki deployment adı kullanılır.
        url = f"{self._endpoint}/openai/deployments/{model}/chat/completions"
        try:
            yanit = await self._istemci.post(
                url,
                params={"api-version": self._api_version},
                headers={"api-key": self._api_key},              # anahtar sadece sunucuda
                json={
                    "messages": [
                        {"role": "system", "content": sistem},
                        {"role": "user", "content": kullanici},
                    ],
                    "max_completion_tokens": max_tokens,
                    "response_format": {"type": "json_object"},
                },
            )
            yanit.raise_for_status()
            metin = yanit.json()["choices"][0]["message"].get("content") or ""
            return _json_ayikla(metin)
        except Exception as hata:  # zaman aşımı, ağ, HTTP hatası, bozuk JSON...
            log.warning("LLM çağrısı başarısız (%s): %s", model, hata)
            return None


def _json_ayikla(metin: str) -> Optional[dict[str, Any]]:
    """
    Model bazen JSON'u ```json ... ``` içine koyar ya da başına bir cümle ekler.
    İlk '{' ile son '}' arasını alıp çözmeyi deneriz.
    """
    metin = re.sub(r"```(?:json)?", "", metin).strip()
    bas, son = metin.find("{"), metin.rfind("}")
    if bas == -1 or son == -1:
        return None
    try:
        sonuc = json.loads(metin[bas:son + 1])
        return sonuc if isinstance(sonuc, dict) else None
    except json.JSONDecodeError:
        return None


# ---------------------------------------------------------------------------
# Sahte sağlayıcı (API anahtarsız çalışma)
# ---------------------------------------------------------------------------

class SahteSaglayici:
    """
    LLM yokmuş gibi davranır: her çağrıda None döndürür.
    Böylece anlama katmanı kural tabanlı yedeğe, cevap katmanı da şablonlara düşer.
    Senaryo LLM olmadan da baştan sona çalışır; bu, sistemin asgari sürümüdür.
    """

    ad = "sahte"

    async def json_iste(self, sistem: str, kullanici: str, model: str, max_tokens: int = 300) -> Optional[dict[str, Any]]:
        return None


# ---------------------------------------------------------------------------
# Seçim
# ---------------------------------------------------------------------------

_saglayici: Optional[LLMSaglayici] = None


def saglayici_olustur() -> LLMSaglayici:
    """Ayarlara göre sağlayıcıyı bir kez oluşturur ve sonra hep aynısını verir."""
    global _saglayici
    if _saglayici is None:
        if AYARLAR.llm_saglayici == "anthropic" and AYARLAR.anthropic_api_key:
            _saglayici = AnthropicSaglayici(AYARLAR.anthropic_api_key, AYARLAR.llm_zaman_asimi)
        elif AYARLAR.llm_saglayici == "azure_openai" and AYARLAR.azure_openai_api_key and AYARLAR.azure_openai_endpoint:
            _saglayici = AzureOpenAISaglayici(
                AYARLAR.azure_openai_api_key,
                AYARLAR.azure_openai_endpoint,
                AYARLAR.azure_openai_api_version,
                AYARLAR.llm_zaman_asimi,
            )
        else:
            if AYARLAR.llm_saglayici == "anthropic":
                log.warning("ANTHROPIC_API_KEY tanımlı değil; sahte sağlayıcıya geçiliyor.")
            elif AYARLAR.llm_saglayici == "azure_openai":
                log.warning("AZURE_OPENAI_API_KEY veya AZURE_OPENAI_ENDPOINT tanımlı değil; sahte sağlayıcıya geçiliyor.")
            _saglayici = SahteSaglayici()
    return _saglayici
