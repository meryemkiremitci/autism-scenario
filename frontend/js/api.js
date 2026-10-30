// =====================================================================
// api.js — Sunucuyla konuşan küçük katman
// ---------------------------------------------------------------------
// Tarayıcı LLM'e ya da ses servislerine HİÇBİR ZAMAN doğrudan gitmez;
// her şey sunucu üzerinden geçer (anahtarlar sunucuda kalır).
// Oturum durumu tarayıcıda tutulur ve her istekte sunucuya gönderilir.
// =====================================================================

async function istek(yol, govde) {
  const yanit = await fetch(yol, {
    method: govde ? "POST" : "GET",
    headers: govde ? { "Content-Type": "application/json" } : undefined,
    body: govde ? JSON.stringify(govde) : undefined,
  });
  if (!yanit.ok) {
    const detay = await yanit.text().catch(() => "");
    throw new Error(`Sunucu ${yanit.status}: ${detay}`);
  }
  return yanit.json();
}

/** Seçim ekranı için ürün listesi ve zorluk seviyeleri. */
export const senaryoGetir = () => istek("/api/senaryo");

/** Yeni oyun. ayarlar: { zorluk, gorevli?, stok?, boyut_acik?, dil_duzeyi?, bekleme_saniye? } */
export const oturumBaslat = (urun_id, ayarlar) => istek("/api/oturum", { urun_id, ayarlar });

/**
 * Kullanıcının bir girdisini gönderir.
 * girdi: { tur: "hazir"|"yazi"|"ses"|"onarim"|"sessiz"|"bekleme_bitti", metin?, niyet? }
 */
export const konus = (durum, girdi) => istek("/api/konus", { durum, girdi });

/**
 * Görevlinin cümlesini sunucudaki TTS servisiyle sese çevirmeyi dener.
 * Servis yoksa (501) null döner; o zaman tarayıcının kendi sesi kullanılır.
 */
export async function ttsIste(metin, hiz = 1, cinsiyet = "kadin") {
  try {
    const yanit = await fetch("/api/tts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ metin, hiz, cinsiyet }),
    });
    return yanit.ok ? await yanit.blob() : null;
  } catch {
    return null;
  }
}

/** Ses kaydını sunucudaki STT servisine gönderir. Servis yoksa null döner. */
export async function sttGonder(kayit) {
  try {
    const form = new FormData();
    form.append("ses", kayit, kayit.type === "audio/wav" ? "ses.wav" : "ses.webm");
    const yanit = await fetch("/api/stt", { method: "POST", body: form });
    return yanit.ok ? (await yanit.json()).metin : null;
  } catch {
    return null;
  }
}

/** Sunucuda hangi servisler hazır: { llm, stt, tts } */
export const yetenekler = () => istek("/api/yetenekler");
