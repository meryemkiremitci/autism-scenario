// =====================================================================
// sahne.js — Görsel katman
// ---------------------------------------------------------------------
// Sahne ve karakterler index.html içindeki SVG'de çizili. Bu dosya sadece
// onları HAREKET ETTİRİR: kamera çekimleri, yürüme, görevlinin durumu ve
// jesti, dönme, sohbet animasyonu, ağız ve göz kırpma.
//
// Görsel katman karar vermez: ne olacağını sunucudaki senaryo motoru söyler,
// burası sadece gösterir. Bütün hareketler CSS ile yapılır; buradaki kod
// SVG elemanlarının sınıflarını ve özniteliklerini değiştirir.
// =====================================================================

const $ = (id) => document.getElementById(id);
export const bekle = (ms) => new Promise((r) => setTimeout(r, ms));
export const hareketAzalt = matchMedia("(prefers-reduced-motion: reduce)").matches;

// --- Elemanlar ---------------------------------------------------------
const sahneSvg = $("sahne");
const dunya = $("dunya");            // marketin tamamı: kamera aslında bunu kaydırıp büyütür
const perde = $("perde");            // çekim değişirken kararan katman
const mKonum = $("musteriKonum");    // kullanıcının avatarının ekrandaki yeri
const musteri = $("musteri");        // avatarın kendisi (yürürken "yuruyor" sınıfı alır)
const gorevli = $("gorevli");        // görevlinin önden çizimi
const gorevliAr = $("gorevliArka");  // görevlinin arkadan çizimi
const gorevliKp = $("gorevliKap");   // ikisini taşıyan grup (dönme bunun üzerinde)
const sohbetKp = $("sohbetKap");     // görevliyle konuşan diğer müşteri
const sohbetci = $("sohbetci");
const agiz = gorevli.querySelector(".agiz");

// =====================================================================
// 1. KAMERA ÇEKİMLERİ
// dunya: [ölçek, x, y]      müşteri: [ayakların x'i, y'si, ölçek]
// Kamera kaymaz: çekim değişirken perde kararır ve sahne yeni açıyla açılır.
// =====================================================================
export const CEKIMLER = {
  disari:  { dunya: [1, 0, 0],          musteri: [1320, 760, 1.15] },  // avatar kapının dışında
  giris:   { dunya: [1, 0, 0],          musteri: [930, 760, 1.15] },   // kapıdan girmiş, kameranın önünde
  yaninda: { dunya: [1, 0, 0],          musteri: [850, 532, 0.47] },   // görevlinin yanına yürümüş
  yakin:   { dunya: [2.4, -1344, -653], musteri: [870, 900, 1.65] },   // omuz arkası yakın çekim
};

export function dunyaAyarla([s, x, y]) {
  dunya.style.transform = `translate(${x}px, ${y}px) scale(${s})`;
}

/** Avatarı yerleştirir. sure > 0 ise oraya yürüyerek (CSS geçişiyle) gider. */
export function musteriAyarla([x, y, s], sure = 0) {
  mKonum.classList.toggle("yuru", sure > 0 && !hareketAzalt);
  mKonum.style.setProperty("--yurume-suresi", sure + "ms");
  mKonum.style.transform = `translate(${x}px, ${y}px) scale(${s})`;
}

export async function perdeKapat() { perde.classList.remove("acik"); await bekle(650); }
export async function perdeAc()    { perde.classList.add("acik");    await bekle(650); }

/** Perde arkasında çekimi değiştirir; kullanıcı kaymayı değil, açının değiştiğini görür. */
export async function cekimeGec(cekim, yakin = false) {
  await perdeKapat();
  dunyaAyarla(cekim.dunya);
  musteriAyarla(cekim.musteri);
  sahneSvg.classList.toggle("yakin", yakin);
  await bekle(150);
  await perdeAc();
}

/** Avatar yürür; adım sesleri ve bacak animasyonu yürüme süresince çalışır. */
export async function yuru(hedef, sure, ayakSesi) {
  musteri.classList.add("yuruyor");
  ayakSesi?.baslat();
  musteriAyarla(hedef, sure);
  await bekle(hareketAzalt ? 300 : sure);
  ayakSesi?.durdur();
  musteri.classList.remove("yuruyor");
}

// =====================================================================
// 2. GÖREVLİNİN BAŞLANGIÇ DURUMU
// Sunucunun seçtiği varyasyona göre: boşta, raf düzenliyor, başka müşteriyle konuşuyor.
// =====================================================================
export function gorevliHazirla(mod, cinsiyet = "erkek") {
  // Aynı çizimde kadın/erkek parçaları var (saç, kirpik, küpe); sınıf hangisinin görüneceğini seçer
  for (const svg of [gorevli, gorevliAr]) {
    svg.classList.toggle("kadin", cinsiyet === "kadin");
    svg.classList.toggle("erkek", cinsiyet !== "kadin");
  }
  sohbetDurdur();
  sahneSvg.classList.toggle("mod-konusma", mod === "sohbet");   // diğer müşteri görünür
  sohbetKp.classList.remove("gitti");
  gorevliKp.classList.remove("sohbette", "don");
  gorevliKp.classList.toggle("arkasi-donuk", mod === "raf");
  gorevliAr.classList.toggle("duzenliyor", mod === "raf");
  durum("bekliyor");
  if (mod === "sohbet") sohbetBaslat();
}

export const arkasiDonuk = () => gorevliKp.classList.contains("arkasi-donuk");

// =====================================================================
// 3. GÖREVLİNİN DURUMU VE JESTİ
// CSS, data-durum ve data-jest özniteliklerine bakarak kolları ve yüzü hareket ettirir.
// Jestler: anlat, isaret, isaret-sag, omuz, bekle (el kalkık)
// =====================================================================
export function durum(yeni, jest = "") {
  gorevli.setAttribute("data-durum", yeni);
  gorevli.setAttribute("data-jest", jest || "");
}

/** Arkası dönük görevli önce kolunu indirir, sonra kısa bir daralmayla döner. */
export async function gorevliDonsun() {
  if (!arkasiDonuk()) return;
  gorevliAr.classList.remove("duzenliyor");
  await bekle(hareketAzalt ? 0 : 500);
  if (!hareketAzalt) { gorevliKp.classList.add("don"); await bekle(230); }
  gorevliKp.classList.remove("arkasi-donuk", "don");
  await bekle(hareketAzalt ? 100 : 350);
}

// =====================================================================
// 4. BAŞKA MÜŞTERİYLE SOHBET
// Görevlinin ağzı sessizce oynar, bakışı diğer müşteridedir.
// =====================================================================
let sohbetZaman = null;

export function sohbetBaslat() {
  sohbetDurdur();
  gorevliKp.classList.add("sohbette");      // bakış sola, diğer müşteriye
  durum("konusuyor", "anlat");
  const sekiller = ["a", "e", "o", "", ""];
  sohbetZaman = setInterval(() => {
    agiz.setAttribute("class", "agiz " + sekiller[Math.floor(Math.random() * sekiller.length)]);
  }, 110);
}

export function sohbetDurdur() {
  clearInterval(sohbetZaman);
  sohbetZaman = null;
  agiz.setAttribute("class", "agiz");
}

/** Görevli kısa bir an kullanıcıya bakar ("bir saniye" demeden önce). */
export function kullaniciyaBak() {
  sohbetDurdur();
  gorevliKp.classList.remove("sohbette");
  durum("bekliyor");
}

/** Diğer müşteri yürüyerek uzaklaşır, görevli kullanıcıya döner. */
export async function sohbetciAyrilsin() {
  sohbetDurdur();
  durum("bekliyor");
  sohbetci.classList.add("yuruyor");
  sohbetKp.classList.add("gitti");
  await bekle(hareketAzalt ? 200 : 2000);
  gorevliKp.classList.remove("sohbette");
  await bekle(hareketAzalt ? 100 : 500);
  sohbetci.classList.remove("yuruyor");
}

// =====================================================================
// 5. AĞIZ
// Harflere göre şekil: a/ı açık, o/ö/u/ü yuvarlak, e/i yayvan, m/b/p kapalı.
// Harf süresi sesin süresinden hesaplanır, böylece ağız ve ses birlikte biter.
// =====================================================================
function agizSekli(harf) {
  const h = harf.toLocaleLowerCase("tr");
  if ("aı".includes(h)) return "a";
  if ("oöuü".includes(h)) return "o";
  if ("ei".includes(h)) return "e";
  if ("mbp .,!?".includes(h)) return "";
  return "e";
}

/**
 * Metni harf harf ilerletir: her adımda ağız şekli değişir, altyazıya bir harf eklenir.
 * harfSuresi: milisaniye (ses süresi / harf sayısı)
 */
export function agziOynat(metin, harfSuresi, altyaziEl) {
  return new Promise((bitti) => {
    if (altyaziEl) altyaziEl.textContent = "";
    let i = 0;
    const z = setInterval(() => {
      if (i >= metin.length) {
        clearInterval(z);
        agiz.setAttribute("class", "agiz");
        return bitti();
      }
      if (altyaziEl) altyaziEl.textContent += metin[i];
      agiz.setAttribute("class", "agiz " + agizSekli(metin[i]));
      i++;
    }, Math.max(30, harfSuresi));
  });
}

// =====================================================================
// 6. ORTAM: diğer müşteriler, gerçekçilik seviyesi, göz kırpma
// =====================================================================
export const kalabalik = (acik) => sahneSvg.classList.toggle("kalabalik-acik", acik);
export const seviye = (n) => (sahneSvg.dataset.seviye = n);

/** Göz kırpma 2-6 saniye arası rastgele aralıklarla: sabit aralık makine gibi durur. */
function gozKirp(el) {
  el.setAttribute("data-kirp", "1");
  setTimeout(() => el.setAttribute("data-kirp", "0"), 130);
  setTimeout(() => gozKirp(el), 2000 + Math.random() * 4000);
}
export function gozKirpmayiBaslat() {
  if (hareketAzalt) return;
  setTimeout(() => gozKirp(gorevli), 1500);
  document.querySelectorAll(".npc").forEach((n, i) => setTimeout(() => gozKirp(n), 800 + i * 1300));
}
