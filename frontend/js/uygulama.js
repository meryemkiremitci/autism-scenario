// =====================================================================
// uygulama.js — Akış ve arayüz
// ---------------------------------------------------------------------
// Ekrandaki her şeyi birbirine bağlar:
//   ürün seçimi → mağazaya giriş → görevliye yaklaşma → konuşma → bitiş
//
// Konuşmanın gidişatına bu dosya karar VERMEZ. Kullanıcının girdisini
// sunucuya gönderir, gelen cevabı (görevlinin cümleleri, jestleri, yeni
// adımın hazır cümleleri, rehber metni...) ekrana uygular.
// =====================================================================

import * as api from "./api.js";
import * as sahne from "./sahne.js";
import * as ses from "./ses.js";

const $ = (id) => document.getElementById(id);
const bekle = sahne.bekle;

// --- Arayüz elemanları ------------------------------------------------
const el = {
  altyazi: $("altyazi"), altyaziAc: $("altyaziAc"),
  secimEkrani: $("secimEkrani"), secimPanel: $("secimPanel"), urunKartlari: $("urunKartlari"),
  gorevPanel: $("gorevPanel"), gorevMetni: $("gorevMetni"), girBtn: $("girBtn"), degistirBtn: $("degistirBtn"),
  bitisEkrani: $("bitisEkrani"), ozet: $("ozet"), tekrarBtn: $("tekrarBtn"), yeniUrunBtn: $("yeniUrunBtn"),
  adim: $("adim"), ipucu: $("ipucu"), bekleme: $("bekleme"), mesgulNotu: $("mesgulNotu"), hareketBtn: $("hareketBtn"),
  panel: $("panel"), duzeltme: $("duzeltme"), duzeltmeMetni: $("duzeltmeMetni"),
  duzeltmeEvet: $("duzeltmeEvet"), duzeltmeHayir: $("duzeltmeHayir"),
  oneriler: $("oneriler"), onarimlar: $("onarimlar"),
  mikrofon: $("mikrofon"), girdi: $("girdi"), gonder: $("gonder"),
  gorevliMod: $("gorevliMod"), stokMod: $("stokMod"), boyutMod: $("boyutMod"), dilMod: $("dilMod"), beklemeMod: $("beklemeMod"),
  kalabalikAc: $("kalabalikAc"), sesAc: $("sesAc"), arkaPlanAc: $("arkaPlanAc"), ayakAc: $("ayakAc"),
};

// Ürün kartlarındaki küçük çizimler
const IKONLAR = {
  sut: '<rect x="18" y="16" width="22" height="34" rx="2" fill="#f4f2ec" stroke="#5b7fa6" stroke-width="2"/><path d="M18 16 L24 6 L34 6 L40 16 Z" fill="#5b7fa6"/><rect x="18" y="30" width="22" height="9" fill="#5b7fa6"/>',
  semsiye: '<path d="M8 30 Q30 2 52 30 Z" fill="#c4575a"/><path d="M30 30 L30 48 Q30 54 24 52" fill="none" stroke="#4b4f4a" stroke-width="3" stroke-linecap="round"/>',
  pil: '<rect x="20" y="12" width="18" height="38" rx="3" fill="#3a3f4b"/><rect x="25" y="8" width="8" height="5" rx="1" fill="#c9b26a"/><rect x="20" y="34" width="18" height="16" rx="3" fill="#c9b26a"/>',
  deterjan: '<path d="M16 54 L16 22 Q16 16 22 16 L26 16 L26 8 L36 8 L36 16 L40 16 Q46 16 46 22 L46 54 Z" fill="#6f9e6a"/><rect x="20" y="28" width="22" height="14" rx="2" fill="#f4f2ec"/>',
  firca: '<rect x="27" y="14" width="6" height="40" rx="3" fill="#5b7fa6"/><rect x="25" y="6" width="10" height="12" rx="2" fill="#f4f2ec" stroke="#cfc9bc"/>',
};

// Onarım kartları her adımda aynıdır; LLM'e gitmez, adımı değiştirmez
const ONARIM_KARTLARI = [
  { metin: "Tekrar söyler misiniz?", niyet: "tekrar" },
  { metin: "Biraz yavaş söyler misiniz?", niyet: "yavas" },
  { metin: "Bir saniye, düşünüyorum.", niyet: "sure" },
];

// Zorluğun sadece tarayıcıda uygulanan kısmı (sunucunun ilgilenmediği duyusal ayarlar)
const ISTEMCI_ZORLUK = {
  kolay: { kalabalik: false, market: false, arkaPlan: false },
  orta:  { kalabalik: false, market: false, arkaPlan: false },
  zor:   { kalabalik: true,  market: true,  arkaPlan: true },
};

// --- Oyunun anlık hâli --------------------------------------------------
const oyun = {
  urun: null,           // seçilen ürün kaydı
  cevap: null,          // sunucudan gelen son paket
  durum: null,          // oturum durumu (her istekte sunucuya geri gönderilir)
  mesgul: false,        // bir istek ya da animasyon sürüyor mu
  sesliGirdi: false,    // yazı kutusundaki metin mikrofondan mı geldi
  sohbetSuruyor: false, // görevli başka müşteriyle konuşuyor mu (arka plan sesi için)
  sessizlikZaman: null,
  hareketFn: null,
};

const ayakSesi = ses.ayakSesiOlustur(() => el.ayakAc.checked);

// =====================================================================
// 1. AYARLAR
// =====================================================================

const seciliZorluk = () => document.querySelector('input[name="zorluk"]:checked').value;

/** Sunucuya giden ayarlar. Boş bırakılanlar zorluk paketinden (rastgele) seçilir. */
function sunucuAyarlari() {
  const bosIse = (v) => (v === "" ? null : v);
  return {
    zorluk: seciliZorluk(),
    gorevli: bosIse(el.gorevliMod.value),
    stok: bosIse(el.stokMod.value),
    boyut_acik: el.boyutMod.value === "" ? null : el.boyutMod.value === "acik",
    dil_duzeyi: bosIse(el.dilMod.value),
    bekleme_saniye: el.beklemeMod.value === "" ? null : Number(el.beklemeMod.value),
  };
}

/** Zorluk değişince tarayıcı tarafındaki duyusal ayarlar hazır paketten gelir (sonra tek tek değişebilir). */
function istemciZorlukUygula(z) {
  const p = ISTEMCI_ZORLUK[z];
  el.kalabalikAc.checked = p.kalabalik;
  el.sesAc.checked = p.market;
  el.arkaPlanAc.checked = p.arkaPlan;
  ortamGuncelle();
}

/** Diğer müşteriler ve ortam sesleri, kutucuklara göre açılır/kapanır. */
function ortamGuncelle() {
  sahne.kalabalik(el.kalabalikAc.checked);
  if (!oyun.cevap) return;   // ses ancak oyun başladıktan sonra
  el.sesAc.checked ? ses.ortam.market.baslat() : ses.ortam.market.durdur();
  el.arkaPlanAc.checked && oyun.sohbetSuruyor ? ses.ortam.arkaPlan.baslat() : ses.ortam.arkaPlan.durdur();
}

function altyaziGuncelle() {
  el.altyazi.classList.toggle("gorunur", el.altyaziAc.checked);
}

// =====================================================================
// 2. ÜRÜN SEÇİMİ VE GÖREV KARTI
// =====================================================================

async function urunleriYukle() {
  const { urunler } = await api.senaryoGetir();
  el.urunKartlari.innerHTML = "";
  for (const u of urunler) {
    const b = document.createElement("button");
    b.className = "urun-karti";
    b.innerHTML = `<svg viewBox="0 0 60 60" aria-hidden="true">${IKONLAR[u.ikon] || ""}</svg><b></b>`;
    b.querySelector("b").textContent = u.ad.charAt(0).toLocaleUpperCase("tr") + u.ad.slice(1);
    b.addEventListener("click", () => urunSec(u));
    el.urunKartlari.appendChild(b);
  }
}

/** Ürün seçilince sunucuda oturum açılır; görev kartının metni (boyut dahil) oradan gelir. */
async function urunSec(u) {
  oyun.urun = u;
  el.secimPanel.hidden = true;
  el.gorevPanel.hidden = false;
  el.gorevMetni.textContent = "Hazırlanıyor…";
  el.girBtn.disabled = true;
  try {
    const cevap = await api.oturumBaslat(u.id, sunucuAyarlari());
    oyun.cevap = cevap;
    oyun.durum = cevap.durum;
    el.gorevMetni.textContent = cevap.gorev;
    el.girBtn.disabled = false;
    el.girBtn.focus();
  } catch {
    el.gorevMetni.textContent = "Sunucuya ulaşılamadı. Sunucunun çalıştığını kontrol edip ürünü yeniden seç.";
  }
}

function secimeDon() {
  el.bitisEkrani.classList.remove("acik");
  el.secimPanel.hidden = false;
  el.gorevPanel.hidden = true;
  el.secimEkrani.classList.add("acik");
}

// =====================================================================
// 3. MAĞAZAYA GİRİŞ VE YAKLAŞMA
// =====================================================================

async function magazayaGir() {
  ses.sesiAc();                       // tarayıcılar sesi ancak bir tıklamadan sonra açar
  el.secimEkrani.classList.remove("acik");
  await sahneyiSifirla();

  // Görevlinin başlangıç hâli sunucunun seçtiği varyasyondan gelir
  const mod = oyun.durum.varyasyon.gorevli;
  sahne.gorevliHazirla(mod);
  oyun.sohbetSuruyor = mod === "sohbet";
  ortamGuncelle();

  await bekle(200);
  await sahne.perdeAc();
  await sahne.yuru(sahne.CEKIMLER.giris.musteri, 1800, ayakSesi);

  el.adim.textContent = {
    bos: "Görevliyi gördün.",
    raf: "Görevliyi gördün, raf düzenliyor.",
    sohbet: "Görevliyi gördün, başka bir müşteriyle konuşuyor.",
  }[mod];
  el.ipucu.textContent = "Yaklaşmak için butona dokun ya da ↑ tuşuna bas.";
  hareketGoster("Görevliye yaklaş", gorevliyeYaklas);
}

async function gorevliyeYaklas() {
  oyun.mesgul = true;
  await sahne.yuru(sahne.CEKIMLER.yaninda.musteri, 2600, ayakSesi);   // uygun mesafede kendiliğinden durur
  await sahne.cekimeGec(sahne.CEKIMLER.yakin, true);                    // omuz arkası yakın çekim
  await cevabiUygula(oyun.cevap);                                        // ilk adımın cümleleri ve rehberi
  oyun.mesgul = false;
}

async function sahneyiSifirla() {
  oyunuTemizle();
  await sahne.perdeKapat();
  sahne.dunyaAyarla(sahne.CEKIMLER.disari.dunya);
  sahne.musteriAyarla(sahne.CEKIMLER.disari.musteri);
  document.getElementById("sahne").classList.remove("yakin");
}

function oyunuTemizle() {
  sessizlikIptal();
  hareketGizle();
  el.panel.classList.remove("acik");
  el.bekleme.classList.remove("acik");
  el.mesgulNotu.hidden = true;
  el.duzeltme.hidden = true;
  el.adim.textContent = el.ipucu.textContent = el.altyazi.textContent = "";
  if (ses.tarayiciSesiVar) speechSynthesis.cancel();
  ses.ortam.arkaPlan.durdur();
}

// Tek tuşla hareket: buton ya da ↑ / W tuşu
function hareketGoster(yazi, fn) {
  el.hareketBtn.textContent = yazi + " ↑";
  el.hareketBtn.hidden = false;
  oyun.hareketFn = fn;
}
function hareketGizle() { el.hareketBtn.hidden = true; oyun.hareketFn = null; }
async function hareketEt() {
  const fn = oyun.hareketFn;
  if (!fn) return;
  hareketGizle();
  el.ipucu.textContent = "";
  await fn();
}

// =====================================================================
// 4. KONUŞMA DÖNGÜSÜ
// =====================================================================

/** Kullanıcının bir girdisini gönderir. Aynı anda ikinci bir istek gönderilemez. */
async function gonder(girdi) {
  if (oyun.mesgul || !oyun.durum) return;
  oyun.mesgul = true;
  await isle(girdi);
  oyun.mesgul = false;
}

async function isle(girdi) {
  sessizlikIptal();
  panelKilit(true);
  el.duzeltme.hidden = true;

  // Kullanıcının söylediği ekranda görünsün ("(Bekle)" gibi eylem çipleri hariç)
  if (girdi.metin && !girdi.metin.startsWith("(")) el.ipucu.textContent = `Sen: “${girdi.metin}”`;

  // Serbest girdide cevap birkaç saniye sürebilir; görevli o sırada "düşünüyor"
  const yuzuBize = !sahne.arkasiDonuk() && !oyun.sohbetSuruyor;
  if ((girdi.tur === "yazi" || girdi.tur === "ses") && yuzuBize) sahne.durum("dusunuyor");

  let cevap;
  try {
    cevap = await api.konus(oyun.durum, girdi);
  } catch {
    sahne.durum("bekliyor");
    el.ipucu.textContent = "Cevap alınamadı. Bağlantıyı kontrol edip yeniden dene.";
    panelKilit(false);
    return;
  }
  await cevabiUygula(cevap, girdi.tur);
}

/**
 * Sunucudan gelen paketi ekrana uygular:
 *   görsel olaylar → görevlinin (ve diğer müşterinin) cümleleri → bekleme ya da bitiş → yeni adımın arayüzü
 */
async function cevabiUygula(c, girdiTuru = null) {
  oyun.cevap = c;
  oyun.durum = c.durum;

  // --- Görsel olaylar ---
  if (c.olaylar.includes("gorevli_doner")) await sahne.gorevliDonsun();
  if (c.olaylar.includes("gorevli_bakar")) sahne.kullaniciyaBak();

  // --- Cümleler, sırayla ---
  for (const adim of c.adimlar) {
    if (adim.kim === "diger") {
      // Görevliyle konuşan müşteri teşekkür eder ve uzaklaşır
      sahne.sohbetDurdur();
      el.altyazi.textContent = `Diğer müşteri: ${adim.metin}`;
      await ses.seslendir(adim.metin, { kim: "diger" });
      oyun.sohbetSuruyor = false;
      ortamGuncelle();
      await sahne.sohbetciAyrilsin();
      continue;
    }
    await gorevliSoylesin(adim);
  }

  // --- Görevli meşgul: bekleme ---
  if (c.bekleme) return beklemeyiYonet(c);

  // --- Bitiş ---
  if (c.bitis) return bitir(c.bitis);

  arayuzuGuncelle(c);
  panelKilit(false);

  // Sessizlik: tepki vermeyen kullanıcı için zamanlayıcı. Sessizliğe karşılık
  // hiçbir şey olmadıysa (ör. arkası dönük görevli fark etmedi) tekrar kurulmaz.
  const bosSessizlik = girdiTuru === "sessiz" && c.adimlar.length === 0;
  if (!bosSessizlik) sessizlikKur(c.sessizlik_saniye);
}

async function gorevliSoylesin(adim) {
  sahne.durum("konusuyor", adim.jest);
  await ses.seslendir(adim.metin, {
    hiz: adim.hiz,
    agizFn: (harfSuresi) => sahne.agziOynat(adim.metin, harfSuresi, el.altyazi),
  });
  await bekle(500);                    // jest konuşma bitince hemen kaybolmasın
  sahne.durum("bekliyor");
}

/** Görevli diğer müşteriyle işini bitirene kadar girdi kilitli; süre dolunca sunucuya haber verilir. */
async function beklemeyiYonet(c) {
  arayuzuGuncelle(c);
  panelKilit(true);
  el.mesgulNotu.hidden = false;

  // Görevli tekrar sohbetine döner
  if (!c.durum.sohbet_bitti && c.durum.varyasyon.gorevli === "sohbet") {
    sahne.sohbetBaslat();
    oyun.sohbetSuruyor = true;
    ortamGuncelle();
  }

  // Bekleme çubuğu (Zor seviyede istenirse gizlenebilir)
  el.bekleme.classList.remove("acik");
  void el.bekleme.offsetWidth;          // animasyonu baştan başlatmak için
  el.bekleme.style.setProperty("--bekleme", `${c.bekleme.saniye}s`);
  el.bekleme.classList.toggle("acik", c.bekleme.cubuk_gorunur);

  await bekle(c.bekleme.saniye * 1000);
  el.bekleme.classList.remove("acik");
  el.mesgulNotu.hidden = true;
  await isle({ tur: "bekleme_bitti" });
}

/** Yeni adımın rehber metni, hazır cümleleri, onarım kartları ve (varsa) düzeltme önerisi. */
function arayuzuGuncelle(c) {
  el.adim.textContent = c.rehber;

  // "Şunu mu demek istedin?": ses yanlış duyulduysa. Kullanıcının hatası değil, arayüz önerir.
  if (c.duzeltme) {
    el.duzeltmeMetni.textContent = `Şunu mu demek istedin? “${c.duzeltme}”`;
    el.duzeltme.hidden = false;
  }

  el.oneriler.innerHTML = "";
  for (const h of c.oneriler) {
    el.oneriler.appendChild(cip(h.metin, "cip", () => gonder({ tur: "hazir", metin: h.metin, niyet: h.niyet })));
  }

  // Onarım kartları ancak görevli bir şey söyledikten sonra anlamlıdır
  el.onarimlar.innerHTML = "";
  if (c.onarim_acik) {
    for (const k of ONARIM_KARTLARI) {
      el.onarimlar.appendChild(cip(k.metin, "cip onarim", () => gonder({ tur: "onarim", metin: k.metin, niyet: k.niyet })));
    }
  }

  el.panel.classList.toggle("acik", !["bitti"].includes(c.durum.dugum));
}

function cip(metin, sinif, tikla) {
  const b = document.createElement("button");
  b.className = sinif;
  b.textContent = metin;
  b.addEventListener("click", tikla);
  return b;
}

function panelKilit(kilitli) {
  el.panel.querySelectorAll("button, input").forEach((e) => (e.disabled = kilitli));
}

function bitir(b) {
  el.panel.classList.remove("acik");
  el.adim.textContent = el.ipucu.textContent = "";
  el.ozet.innerHTML = "";
  for (const satir of b.ozet) {
    const li = document.createElement("li");
    li.textContent = satir;
    el.ozet.appendChild(li);
  }
  el.bitisEkrani.classList.add("acik");
  el.tekrarBtn.focus();
}

// =====================================================================
// 5. SESSİZLİK ZAMANLAYICISI
// =====================================================================

function sessizlikKur(saniye) {
  sessizlikIptal();
  if (!saniye) return;
  oyun.sessizlikZaman = setTimeout(() => gonder({ tur: "sessiz" }), saniye * 1000);
}
function sessizlikIptal() {
  clearTimeout(oyun.sessizlikZaman);
  oyun.sessizlikZaman = null;
}
/** Kullanıcı yazıyor ya da konuşuyorsa sessiz sayılmaz: zamanlayıcı baştan başlar. */
function etkinlikVar() {
  if (oyun.sessizlikZaman) sessizlikKur(oyun.cevap?.sessizlik_saniye);
}

// =====================================================================
// 6. YAZI VE SES GİRDİSİ
// =====================================================================

function yaziyiGonder() {
  const metin = el.girdi.value.trim();
  if (!metin) return;
  const tur = oyun.sesliGirdi ? "ses" : "yazi";
  el.girdi.value = "";
  oyun.sesliGirdi = false;
  gonder({ tur, metin });
}

// Bas-konuş: basılı tutarken dinler, bırakınca yazıya çevrilen metin kutuya gelir.
// Göndermeden önce kullanıcı ne anlaşıldığını görür ve düzeltebilir.
async function dinlemeyeBasla() {
  if (el.mikrofon.disabled || el.mikrofon.classList.contains("dinliyor")) return;
  sessizlikIptal();
  el.mikrofon.classList.add("dinliyor");
  el.ipucu.textContent = "Dinliyorum… Bitince butonu bırak.";
  try {
    await ses.dinlemeBaslat();
  } catch {
    el.mikrofon.classList.remove("dinliyor");
    el.ipucu.textContent = "Mikrofona erişilemedi. Tarayıcı izinlerini kontrol et ya da yazarak devam et.";
  }
}
async function dinlemeyiBitir() {
  if (!el.mikrofon.classList.contains("dinliyor")) return;
  el.mikrofon.classList.remove("dinliyor");
  const metin = await ses.dinlemeBitir();
  if (metin) {
    el.girdi.value = metin;
    oyun.sesliGirdi = true;
    el.ipucu.textContent = "Söylediğin yazıya çevrildi. Doğruysa “Söyle”ye bas, değilse düzelt.";
    el.girdi.focus();
  } else {
    el.ipucu.textContent = "Bir şey duyamadım. Tekrar deneyebilir ya da yazabilirsin.";
  }
  etkinlikVar();
}

// =====================================================================
// 7. OLAY BAĞLANTILARI VE BAŞLANGIÇ
// =====================================================================

el.girBtn.addEventListener("click", magazayaGir);
el.degistirBtn.addEventListener("click", secimeDon);
el.yeniUrunBtn.addEventListener("click", async () => { await sahneyiSifirla(); secimeDon(); });
el.tekrarBtn.addEventListener("click", async () => {
  el.bitisEkrani.classList.remove("acik");
  await urunSec(oyun.urun);
  el.secimEkrani.classList.add("acik");
});
el.hareketBtn.addEventListener("click", hareketEt);
document.addEventListener("keydown", (e) => {
  const yaziyor = document.activeElement === el.girdi;
  if ((e.key === "ArrowUp" || e.key.toLowerCase() === "w") && !yaziyor && oyun.hareketFn) {
    e.preventDefault();
    hareketEt();
  }
});

el.gonder.addEventListener("click", yaziyiGonder);
el.girdi.addEventListener("keydown", (e) => { if (e.key === "Enter") yaziyiGonder(); });
el.girdi.addEventListener("input", () => {
  if (!el.girdi.value) oyun.sesliGirdi = false;
  etkinlikVar();
});

// Mikrofon: fare/dokunmatik için basılı tutma, klavye için Boşluk tuşuna basılı tutma
el.mikrofon.addEventListener("pointerdown", (e) => { e.preventDefault(); dinlemeyeBasla(); });
el.mikrofon.addEventListener("pointerup", dinlemeyiBitir);
el.mikrofon.addEventListener("pointerleave", dinlemeyiBitir);
el.mikrofon.addEventListener("keydown", (e) => { if (e.key === " " && !e.repeat) { e.preventDefault(); dinlemeyeBasla(); } });
el.mikrofon.addEventListener("keyup", (e) => { if (e.key === " ") dinlemeyiBitir(); });

el.duzeltmeEvet.addEventListener("click", () => {
  const metin = oyun.cevap?.duzeltme;
  if (metin) gonder({ tur: "yazi", metin });   // kullanıcı onayladı: artık doğrulanmış yazı
});
el.duzeltmeHayir.addEventListener("click", () => {
  el.duzeltme.hidden = true;
  el.ipucu.textContent = "Tekrar söyleyebilir ya da yazabilirsin.";
});

document.querySelectorAll('input[name="zorluk"]').forEach((r) =>
  r.addEventListener("change", () => istemciZorlukUygula(r.value)));
[el.kalabalikAc, el.sesAc, el.arkaPlanAc].forEach((k) => k.addEventListener("change", ortamGuncelle));
el.altyaziAc.addEventListener("change", altyaziGuncelle);
document.querySelectorAll('input[name="seviye"]').forEach((r) =>
  r.addEventListener("change", () => sahne.seviye(r.value)));

async function baslat() {
  // Sahne seçim ekranının arkasında görünsün
  sahne.dunyaAyarla(sahne.CEKIMLER.disari.dunya);
  sahne.musteriAyarla(sahne.CEKIMLER.disari.musteri);
  document.getElementById("perde").classList.add("acik");
  sahne.gozKirpmayiBaslat();
  istemciZorlukUygula(seciliZorluk());

  // Sunucuda hangi servisler var? Yoksa tarayıcının kendi özellikleri kullanılır.
  try { ses.yetenekleriAyarla(await api.yetenekler()); } catch { /* sunucu yoksa aşağıda görünür */ }
  if (!ses.sesCikabilir()) el.altyaziAc.checked = true;   // ses çıkamıyorsa altyazı kendiliğinden açılır
  altyaziGuncelle();
  el.mikrofon.hidden = !ses.dinlemeMumkun();

  try {
    await urunleriYukle();
  } catch {
    el.urunKartlari.textContent = "Sunucuya ulaşılamadı. Backend klasöründe “uvicorn app.main:app” komutuyla sunucuyu başlatıp sayfayı yenile.";
  }
}

baslat();
