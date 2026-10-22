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

from typing import Optional

from ..ayarlar import AYARLAR


async def yaziya_cevir(ses: bytes, mime: str) -> Optional[str]:
    """
    Sesi metne çevirir. Servis yapılandırılmamışsa None döner.

    Örnek bir bulut servisi eklendiğinde burası şöyle görünecek:
        if AYARLAR.stt_saglayici == "ornek_servis":
            return await OrnekServis().cevir(ses, mime, dil="tr-TR")
    """
    if AYARLAR.stt_saglayici == "yok":
        return None
    return None
