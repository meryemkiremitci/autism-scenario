// =====================================================================
// ses.js — Ses katmanı (tarayıcı tarafı)
// ---------------------------------------------------------------------
//  1. Görevlinin sesi (TTS): sunucuda servis varsa onun ses dosyası,
//     yoksa tarayıcının kendi sesi (speechSynthesis).
//  2. Kullanıcının sesi (STT), bas-konuş: sunucuda servis varsa kayıt
//     oraya gönderilir; yoksa tarayıcının konuşma tanıması kullanılır.
//     NOT: Chrome'un konuşma tanıması sesi Google'a gönderir. Gizlilik
//     açısından asıl hedef sunucudaki bir STT servisidir.
//  3. Ortam sesleri: market uğultusu, kasa bip'i, ayak sesi, arka plan
//     konuşmaları. Hepsi ses dosyası olmadan Web Audio ile üretilir.
// =====================================================================

import { sttGonder, ttsIste } from "./api.js";

const bekle = (ms) => new Promise((r) => setTimeout(r, ms));
const yetenek = { stt: false, tts: false };

/** Sunucunun yeteneklerini bildirir (uygulama.js başlangıçta çağırır). */
export function yetenekleriAyarla(y) {
  yetenek.stt = !!y.stt;
  yetenek.tts = !!y.tts;
}

// =====================================================================
// 1. GÖREVLİNİN SESİ
// =====================================================================

export const tarayiciSesiVar = "speechSynthesis" in window;
export const sesCikabilir = () => yetenek.tts || tarayiciSesiVar;

/**
 * Bir cümleyi seslendirir ve ağız animasyonunu sesle aynı anda başlatıp bitirir.
 *   agizFn(harfSuresi) : ağzı oynatan fonksiyon; bir Promise döndürür (sahne.agziOynat)
 *   kim                : "gorevli" ya da "diger" (diğer müşteri daha ince bir sesle konuşur)
 */
export async function seslendir(metin, { hiz = 1, kim = "gorevli", agizFn = null, cinsiyet = "kadin" } = {}) {
  ortam.kis(true);                    // görevli konuşurken ortam sesi kısılır
  try {
    // a) Sunucudaki TTS: ses dosyasının süresi belli olduğu için ağız tam eşleşir
    if (yetenek.tts && kim === "gorevli") {
      const kayit = await ttsIste(metin, hiz, cinsiyet);
      if (kayit) {
        const ses = new Audio(URL.createObjectURL(kayit));
        await new Promise((r) => { ses.onloadedmetadata = r; ses.onerror = r; });
        const harfSuresi = ((ses.duration || metin.length * 0.07) * 1000) / metin.length;
        const bitis = new Promise((r) => { ses.onended = r; ses.onerror = r; });
        ses.play().catch(() => {});
        await Promise.all([bitis, agizFn ? agizFn(harfSuresi) : null]);
        return;
      }
    }
    // b) Tarayıcının sesi: süre önceden bilinmediği için harf süresi tahmin edilir
    const harfSuresi = 72 / hiz;
    await Promise.all([tarayicidaOku(metin, hiz, kim === "diger" ? 1.35 : 1), agizFn ? agizFn(harfSuresi) : null]);
  } finally {
    ortam.kis(false);
  }
}

function tarayicidaOku(metin, hiz, perde) {
  return new Promise((bitti) => {
    if (!tarayiciSesiVar) return bitti();
    const s = new SpeechSynthesisUtterance(metin);
    s.lang = "tr-TR";
    s.rate = hiz;
    s.pitch = perde;
    const turkce = speechSynthesis.getVoices().filter((v) => v.lang.startsWith("tr"));
    if (turkce.length) s.voice = perde !== 1 && turkce[1] ? turkce[1] : turkce[0];
    // Bazı tarayıcılarda "bitti" olayı hiç gelmeyebiliyor; senaryo takılmasın diye yedek süre
    const yedek = setTimeout(bitti, (metin.length * 95) / hiz + 1500);
    s.onend = s.onerror = () => { clearTimeout(yedek); bitti(); };
    speechSynthesis.cancel();
    speechSynthesis.speak(s);
  });
}

// =====================================================================
// 2. KULLANICININ SESİ (bas-konuş)
// =====================================================================

const TanimaSinifi = window.SpeechRecognition || window.webkitSpeechRecognition;

/** Bu tarayıcıda sesli girdi mümkün mü? */
export const dinlemeMumkun = () => yetenek.stt ? !!window.MediaRecorder : !!TanimaSinifi;

let aktif = null;   // o an süren dinleme

/** Mikrofon butonuna basılınca çağrılır. */
export async function dinlemeBaslat() {
  if (aktif) return;
  if (yetenek.stt) {
    // Sunucudaki STT: sesi kaydet, bırakınca gönder
    const akis = await navigator.mediaDevices.getUserMedia({ audio: true });
    const kaydedici = new MediaRecorder(akis);
    const parcalar = [];
    kaydedici.ondataavailable = (e) => parcalar.push(e.data);
    kaydedici.start();
    aktif = { tur: "kayit", kaydedici, akis, parcalar };
  } else if (TanimaSinifi) {
    // Tarayıcının konuşma tanıması
    const tanima = new TanimaSinifi();
    tanima.lang = "tr-TR";
    tanima.interimResults = false;
    tanima.maxAlternatives = 1;
    const sonuc = new Promise((r) => {
      let metin = "";
      tanima.onresult = (e) => { metin = Array.from(e.results).map((x) => x[0].transcript).join(" "); };
      tanima.onend = () => r(metin);
      tanima.onerror = () => r(metin);
    });
    tanima.start();
    aktif = { tur: "tanima", tanima, sonuc };
  }
}

/**
 * MediaRecorder kaydını (Chrome'da webm/opus) 16 kHz, tek kanal, 16 bit WAV'a çevirir.
 * Sunucudaki konuşma tanıma servisleri en güvenilir bu biçimi okur. Çevrilemezse null döner.
 */
async function wavaCevir(blob) {
  try {
    const hedef = 16000;
    const kaynakSes = await baglam().decodeAudioData(await blob.arrayBuffer());
    const cevrimdisi = new OfflineAudioContext(1, Math.max(1, Math.ceil(kaynakSes.duration * hedef)), hedef);
    const kaynak = cevrimdisi.createBufferSource();
    kaynak.buffer = kaynakSes;
    kaynak.connect(cevrimdisi.destination);
    kaynak.start();
    const ornekler = (await cevrimdisi.startRendering()).getChannelData(0);

    const wav = new DataView(new ArrayBuffer(44 + ornekler.length * 2));
    const yaz = (konum, metin) => [...metin].forEach((c, i) => wav.setUint8(konum + i, c.charCodeAt(0)));
    yaz(0, "RIFF"); wav.setUint32(4, 36 + ornekler.length * 2, true); yaz(8, "WAVE");
    yaz(12, "fmt "); wav.setUint32(16, 16, true); wav.setUint16(20, 1, true); wav.setUint16(22, 1, true);
    wav.setUint32(24, hedef, true); wav.setUint32(28, hedef * 2, true); wav.setUint16(32, 2, true); wav.setUint16(34, 16, true);
    yaz(36, "data"); wav.setUint32(40, ornekler.length * 2, true);
    ornekler.forEach((x, i) => wav.setInt16(44 + i * 2, Math.max(-1, Math.min(1, x)) * 0x7fff, true));
    return new Blob([wav], { type: "audio/wav" });
  } catch {
    return null;
  }
}

/** Mikrofon butonu bırakılınca çağrılır; yazıya çevrilmiş metni döndürür (yoksa ""). */
export async function dinlemeBitir() {
  const a = aktif;
  aktif = null;
  if (!a) return "";
  if (a.tur === "tanima") {
    a.tanima.stop();
    return (await a.sonuc).trim();
  }
  const bitti = new Promise((r) => (a.kaydedici.onstop = r));
  a.kaydedici.stop();
  await bitti;
  a.akis.getTracks().forEach((t) => t.stop());      // mikrofonu hemen kapat
  const kayit = new Blob(a.parcalar, { type: a.kaydedici.mimeType || "audio/webm" });
  const wav = await wavaCevir(kayit);
  return ((await sttGonder(wav || kayit)) || "").trim();   // kayıt gönderildikten sonra tarayıcıda da tutulmaz
}

// =====================================================================
// 3. ORTAM SESLERİ (Web Audio, ses dosyası yok)
// =====================================================================

let ctx = null;
const baglam = () => (ctx ||= new (window.AudioContext || window.webkitAudioContext)());

/** Tarayıcılar sesi ancak bir kullanıcı hareketinden sonra açar; "Markete gir" butonunda çağrılır. */
export const sesiAc = () => baglam().resume();

/** Kahverengi gürültü: beyaz gürültünün yumuşatılmışı. Uğultu ve havalandırma gibi duyulur. */
function gurultuKaynagi(saniye = 4) {
  const c = baglam();
  const uzunluk = c.sampleRate * saniye;
  const tampon = c.createBuffer(1, uzunluk, c.sampleRate);
  const v = tampon.getChannelData(0);
  let son = 0;
  for (let i = 0; i < uzunluk; i++) {
    son = (son + 0.02 * (Math.random() * 2 - 1)) / 1.02;
    v[i] = son * 3.5;
  }
  const kaynak = c.createBufferSource();
  kaynak.buffer = tampon;
  kaynak.loop = true;
  return kaynak;
}

/** Bir ortam sesi parçası: başlat / durdur / kıs. */
function ortamParcasi(kur) {
  let parca = null;
  return {
    baslat() { if (!parca) parca = kur(); },
    durdur() { if (parca) { parca.durdur(); parca = null; } },
    kis(k) { if (parca) parca.ana.gain.linearRampToValueAtTime(k ? parca.dusuk : parca.normal, baglam().currentTime + 0.3); },
  };
}

// Market uğultusu ve arada kasa "bip bip"i
const market = ortamParcasi(() => {
  const c = baglam();
  const ana = c.createGain(); ana.gain.value = 0.6; ana.connect(c.destination);
  const kaynak = gurultuKaynagi();
  const f = c.createBiquadFilter(); f.type = "lowpass"; f.frequency.value = 450;
  const g = c.createGain(); g.gain.value = 0.12;
  kaynak.connect(f).connect(g).connect(ana); kaynak.start();
  let zaman = null;
  const bip = () => {
    [0, 0.16].forEach((d) => {
      const o = c.createOscillator(), og = c.createGain(), t0 = c.currentTime + d;
      o.frequency.value = 1750;
      og.gain.setValueAtTime(0, t0);
      og.gain.linearRampToValueAtTime(0.025, t0 + 0.01);
      og.gain.linearRampToValueAtTime(0, t0 + 0.09);
      o.connect(og).connect(ana); o.start(t0); o.stop(t0 + 0.1);
    });
    zaman = setTimeout(bip, 4000 + Math.random() * 6000);
  };
  zaman = setTimeout(bip, 2500);
  return { ana, normal: 0.6, dusuk: 0.25, durdur() { clearTimeout(zaman); kaynak.stop(); ana.disconnect(); } };
});

// Arka plan konuşmaları: konuşma frekanslarında, hece ritmiyle dalgalanan anlamsız bir uğultu.
// Gerçek kelime yoktur; kullanıcı duyduklarını kendisine söylenmiş sanmasın diye.
const arkaPlan = ortamParcasi(() => {
  const c = baglam();
  const ana = c.createGain(); ana.gain.value = 0.5; ana.connect(c.destination);
  const kaynak = gurultuKaynagi();
  const f = c.createBiquadFilter(); f.type = "bandpass"; f.frequency.value = 520; f.Q.value = 0.9;
  const ritim = c.createGain(); ritim.gain.value = 0.05;
  const lfo = c.createOscillator(); lfo.frequency.value = 3.6;          // saniyede ~3-4 hece
  const lfoGuc = c.createGain(); lfoGuc.gain.value = 0.04;
  lfo.connect(lfoGuc).connect(ritim.gain);
  kaynak.connect(f).connect(ritim).connect(ana);
  kaynak.start(); lfo.start();
  return { ana, normal: 0.5, dusuk: 0.15, durdur() { kaynak.stop(); lfo.stop(); ana.disconnect(); } };
});

export const ortam = {
  market,
  arkaPlan,
  kis(k) { market.kis(k); arkaPlan.kis(k); },
};

// Ayak sesi: her adımda kısa, boğuk bir gürültü patlaması (sol ve sağ adım biraz farklı)
export function ayakSesiOlustur(acikMi) {
  let zaman = null, sol = true;
  const adim = () => {
    const c = baglam();
    const uz = Math.floor(c.sampleRate * 0.07);
    const t = c.createBuffer(1, uz, c.sampleRate), v = t.getChannelData(0);
    for (let i = 0; i < uz; i++) v[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / uz, 3);
    const k = c.createBufferSource(), f = c.createBiquadFilter(), g = c.createGain();
    k.buffer = t; f.type = "lowpass"; f.frequency.value = sol ? 900 : 780; g.gain.value = 0.35;
    k.connect(f).connect(g).connect(c.destination); k.start();
    sol = !sol;
  };
  return {
    baslat() { if (!acikMi()) return; adim(); zaman = setInterval(adim, 350); },
    durdur() { clearInterval(zaman); },
  };
}

export { bekle };
