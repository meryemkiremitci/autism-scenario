# Mağazada yardım isteme provası

Yüksek işlevli otizmli bireylerin günlük sosyal durumları güvenli bir ortamda prova etmesi için
bir web uygulaması. Bu senaryoda kullanıcı bir markete girer, bir görevliye yaklaşır ve aradığı
ürünü sorar. Görevli sesli konuşur; kullanıcı hazır cümlelerle, yazarak ya da konuşarak cevap verir.

Temel ilke: **senaryonun gidişatına kod karar verir, LLM yalnızca kullanıcıyı anlar ve görevlinin
cümlesini kurar.** Bu yüzden uygulama LLM olmadan da (hazır cümleler ve şablon cevaplarla) baştan
sona çalışır.

## Hızlı başlangıç

Python 3.10 veya üstü gerekir.

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Tarayıcıda **http://localhost:8000** adresini açın. Sayfa JavaScript modülleri kullandığı için
`index.html` dosyasına çift tıklayarak değil, sunucu üzerinden açılmalıdır.

Varsayılan ayarlarla LLM kapalıdır ("sahte" sağlayıcı): serbest yazılar anahtar kelime kurallarıyla
anlaşılır, görevlinin cümleleri şablonlardan gelir. Gerçek bir LLM bağlamak için:

```bash
cp .env.example .env
# .env içinde:  LLM_SAGLAYICI=anthropic  ve  ANTHROPIC_API_KEY=...
```

Azure OpenAI için:

```bash
# .env içinde:
LLM_SAGLAYICI=azure_openai
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_ENDPOINT=https://<kaynak-adi>.openai.azure.com
ANLAMA_MODELI=<deployment-adi>
CEVAP_MODELI=<deployment-adi>
```

Model adları `.env` dosyasından değiştirilebilir. Claude API belgeleri: https://docs.claude.com/en/api/overview

## Testler

```bash
cd backend
python -m pytest -q
```

Testler gerçek bir LLM'e bağlanmaz. Senaryo motorunun bütün dallarını, uç noktaları ve LLM
çıktılarının doğrulanmasını (taklit bir LLM ile) dener.

## Klasör yapısı

```
magaza-senaryosu/
├── backend/
│   ├── app/
│   │   ├── main.py          Sunucu ve uç noktalar (FastAPI). Arayüzü de "/" adresinden sunar.
│   │   ├── akis.py          Bir turun yolculuğu: girdi → anlama → motor → cevap → paket
│   │   ├── motor.py         Senaryo motoru (durum makinesi). Bütün kararlar burada. LLM yok.
│   │   ├── modeller.py      Sözleşmeler: tarayıcı↔sunucu ve sunucu↔LLM veri şekilleri
│   │   ├── veri.py          Senaryo verisini okuma, şablon doldurma, Türkçe büyük harf
│   │   ├── ayarlar.py       Ortam değişkenlerinden ayarlar (.env)
│   │   ├── dil/
│   │   │   ├── anlama.py    Anlama çağrısı: kullanıcı ne demek istedi? (listeden niyet seçer)
│   │   │   ├── cevap.py     Cevap çağrısı: görevli bunu nasıl söyler? (yoksa şablon)
│   │   │   ├── dogrulama.py LLM çıktılarının kontrolü (uydurma yer/sayı, fazla cümle...)
│   │   │   ├── kurallar.py  LLM yokken anahtar kelimelerle anlama (yedek)
│   │   │   └── saglayici.py LLM sağlayıcıları: Claude API ve anahtarsız "sahte" sağlayıcı
│   │   └── ses/
│   │       ├── stt.py       Konuşmayı yazıya çevirme (servis eklenecek yer)
│   │       └── tts.py       Yazıyı konuşmaya çevirme (servis eklenecek yer)
│   ├── data/
│   │   └── magaza.json      Senaryonun bütün içeriği: ürünler, yerler, cümleler, zorluklar
│   ├── tests/               Motor, akış ve doğrulama testleri
│   ├── requirements.txt
│   └── .env.example
└── frontend/
    ├── index.html           Sahne (SVG çizimi), stiller ve arayüz
    └── js/
        ├── uygulama.js      Akış ve arayüz: ürün seçimi, giriş, konuşma döngüsü, bitiş
        ├── sahne.js         Görsel katman: kamera, yürüme, görevlinin durumu ve jestleri, ağız
        ├── ses.js           Görevlinin sesi, bas-konuş mikrofon, ortam sesleri
        └── api.js           Sunucuyla konuşan küçük katman
```

## Bir tur nasıl işler?

1. Kullanıcı bir şey söyler (hazır cümle, yazı ya da ses).
2. **Hazır cümle** ise niyeti zaten bellidir; LLM'e gidilmez.
   **Yazı ya da ses** ise `dil/anlama.py` LLM'den niyeti ister. LLM yalnızca o adımda geçerli
   niyetlerden seçebilir. Cevap gelmezse ya da kontrolden geçmezse `dil/kurallar.py` devreye girer.
3. `motor.py` niyete ve oyunun koşullarına (stok, görevlinin durumu) bakarak görevlinin ne yapacağına
   (eylem) ve jestine karar verir, bir sonraki adıma geçer.
4. `dil/cevap.py` eylemi cümleye çevirir: hazır cümle yolunda hep aynı şablon, serbest girdide LLM'in
   kurduğu doğal bir cümle. LLM'in cümlesi kontrolden geçmezse yine şablon kullanılır.
5. Tarayıcı cümleyi seslendirir, ağzı sesle birlikte oynatır, jesti yapar ve yeni adımın hazır
   cümlelerini gösterir.

Oturum durumu tarayıcıda tutulur ve her istekte sunucuya gönderilir. Sunucu hiçbir şey hatırlamaz,
veritabanı gerekmez.

## Sık yapılacak değişiklikler

| Ne | Nerede |
| --- | --- |
| Yeni ürün, yer ya da görevli cümlesi | `backend/data/magaza.json` (kod değişmez) |
| Zorluk seviyelerinin içeriği | `magaza.json` → `zorluklar`; duyusal ayarlar `uygulama.js` → `ISTEMCI_ZORLUK` |
| Yeni bir adım ya da dal | `motor.py` (`DUGUM_NIYETLERI` ve `_tek_niyet`), sonra `magaza.json` → `hazir_cumleler` |
| Başka bir LLM servisi | `dil/saglayici.py` içine yeni bir sınıf |
| Bulut STT / TTS servisi | `ses/stt.py`, `ses/tts.py` ve `.env` |
| Bir özelliği kapatmak | Çoğu ayar arayüzdeki "Ayrıntılı ayarlar"dan ya da `magaza.json` → `zorluklar`'dan |

## Bilinen sınırlamalar ve açık konular

- **Sesli girdi:** Sunucuda STT servisi yoksa tarayıcının konuşma tanıması kullanılır. Chrome'da bu,
  sesi Google'a gönderir. Gizlilik (KVKK) açısından asıl hedef sunucudaki bir STT servisidir;
  ses kayıtları hiçbir yerde saklanmamalıdır.
- **Görevlinin sesi:** Tarayıcının sesi bilgisayardan bilgisayara farklıdır. Daha tutarlı bir ses için
  bir TTS servisi bağlanabilir; o zaman ağız hareketleri de ses süresine tam oturur.
- **Yazı tipi:** Nunito yazı tipi Google Fonts'tan yüklenir; internet yoksa sistem yazı tipine düşülür.
- Hocalara danışılacak konular (dil düzeyinin zorluğa bağlanması, boyut değişikliği dalı, bekleme
  süreleri, beklerken araya girme) ayrıntılı tasarım belgesindeki "Açık sorular" bölümündedir.
  Bunların hepsi ya bir ayar değeri ya da açılıp kapanan bir dal olarak sisteme yansır.
