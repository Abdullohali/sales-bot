# Fayldan yuklash: fayl tuzilishi qoidalari

Mahsulotlar, mijozlar va kuryerlarni bittalab qoʻlda kiritish shart emas: ularni bitta fayl bilan birdaniga yuklash mumkin. Fayldagi barcha yangi yozuvlar bitta yuklashda qoʻshiladi.

## Qayerdan yuklanadi

| Joy | Qanday |
|---|---|
| **Admin panel** | Kerakli boʻlimni oching (**Mijozlar**, **Mahsulotlar** yoki **Kuryerlar**) → roʻyxat tepasidagi **📥 Fayldan yuklash** tugmasi → faylni tanlang → **Yuklash**. Natija shu oynada chiqadi, oyna yopilganda roʻyxat yangilanadi |
| **Telegram bot** (faqat administrator) | Faylni botga oddiy hujjat sifatida yuboring. Fayl turi ustun nomlaridan avtomatik aniqlanadi |

Namuna fayllar:
- **Panelda:** «Fayldan yuklash» oynasidagi **Namunani** havolasi orqali. Har bir boʻlim oʻz namunasini beradi.
- **Botda:** `/template` buyrugʻi orqali. Bot uchala namunani ham yuboradi.

**Eng oson yoʻl:** namunani yuklab oling, maʼlumotlarni toʻldiring va shu faylning oʻzini yuklang.

## Umumiy qoidalar (barcha turlar uchun)

1. **Format:** `.xlsx` (Excel 2007 va yangi) yoki `.csv`.
   - Eski `.xls` formati qabul qilinmaydi. Excel'da: *Fayl → Boshqacha saqlash → Excel kitobi (.xlsx)*.
   - Google Sheets: *Fayl → Yuklab olish → Microsoft Excel (.xlsx)* yoki *CSV*.
2. **Birinchi qator — sarlavha** (ustun nomlari), maʼlumotlar 2-qatordan boshlanadi.
3. **Faqat birinchi varaq (list) oʻqiladi.** Qolgan varaqlar eʼtiborga olinmaydi.
4. **Ustunlar tartibi muhim emas.** Ustunlar nomi boʻyicha topiladi, va nomlar **oʻzbek, rus yoki ingliz tilida** boʻlishi mumkin (pastdagi jadvallarga qarang). Katta-kichik harf farq qilmaydi.
5. **Ortiqcha ustunlar** (masalan, «Izoh», «Telefon») eʼtiborga olinmaydi, ularni oʻchirish shart emas.
6. **Sarlavha umuman tanilmasa,** ustunlar namunadagi tartibda deb hisoblanadi. Bu holatda ham birinchi qator sarlavha sifatida oʻtkazib yuboriladi.
7. **Boʻsh qatorlar** jimgina oʻtkazib yuboriladi.
8. **Boʻshliqlar:** katakchalar boshidagi va oxiridagi boʻshliqlar olib tashlanadi, ichidagi bir nechta boʻshliq bittaga qisqartiriladi.
9. **Cheklovlar:** bitta faylda **5000 qatorgacha**, hajmi **10 MB gacha**. Kattaroq faylni qismlarga boʻling.
10. **Namuna qatori:** namunadagi misol qatorini (masalan, «Pomidor» yoki «Namuna restorani») **oʻchirib tashlang**, aks holda u ham yuklanadi.
11. **Xato qatorlar** oʻtkazib yuboriladi va natijada qator raqami bilan koʻrsatiladi, qolgan toʻgʻri qatorlar saqlanadi. Bunga quyidagilar kiradi:
    - majburiy ustun boʻsh;
    - Telegram ID notoʻgʻri;
    - bitta fayl ichida takrorlangan yozuv (faqat birinchisi olinadi).
12. **Faylni qayta yuklash xavfsiz:** mavjud yozuvlar takrorlanmaydi (har bir tur qanday solishtirilishi pastda yozilgan).
13. **Yuklash bilan hech narsa oʻchirilmaydi.** Faylda yoʻq yozuvlar bazada oʻz holicha qoladi.

### CSV fayllar uchun qoʻshimcha

- **Kodirovka:** UTF-8 (tavsiya etiladi) yoki Windows-1251. Rus Excel'idan saqlangan CSV ham oʻqiladi.
- **Ajratuvchi:** vergul `,`, nuqtali vergul `;` yoki tab. Ajratuvchi avtomatik aniqlanadi.
- **Matn ichida vergul yoki nuqtali vergul boʻlsa,** matnni qoʻshtirnoqqa oling: `"Kafe ""Bahor"", Chilonzor"`.

### Uzun raqamli kodlar (MXIK, Telegram ID)

Excel uzun raqamlarni buzishi mumkin. Masalan, 17 xonali `00702001001000001` qiymati `7,02E+14` boʻlib qoladi yoki boshidagi nollar yoʻqoladi.

- **Tavsiya:** namunadan foydalaning, unda bu ustunlar oldindan **«Matn» formatida**.
- **Oʻzingiz fayl tuzsangiz:** bu ustunlarni belgilang → *Format ячеек / Hujayra formati → Matn* qiling, keyin maʼlumotni kiriting.
- **MXIK son sifatida yozilgan boʻlsa,** tizim ogohlantirish beradi.

---

## 1. Mahsulotlar

| Ustun | Majburiy | Tanilgan sarlavhalar | Izoh |
|---|---|---|---|
| Nomi | **ha** | `Nomi`, `Nom`, `Mahsulot` · `Название`, `Наименование`, `Товар` · `Name`, `Product` | Mahsulot nomi |
| Oʻlchov birligi | yoʻq | `Oʻlchov birligi`, `Birlik` · `Ед. изм.`, `Ед.`, `Единица` · `Unit` | Boʻsh boʻlsa: `кг` |
| MXIK | yoʻq | `MXIK`, `IKPU` · `ИКПУ` · `IKPU` | 17 ta raqam. Boshqacha boʻlsa ham saqlanadi, lekin ogohlantirish bilan |
| Birlik kodi | yoʻq | `Birlik kodi`, `Kod` · `Код ед. изм.`, `Код ед.` · `Unit code`, `Code` | Soliq tizimidagi oʻlchov birligi kodi |

**Qanday solishtiriladi:**
- **Nomi boʻyicha** (katta-kichik harf farqsiz).
- **Mavjud mahsulot:** yangilanadi. Boʻsh **MXIK**, **kod** va **birlik** katakchalari saqlangan qiymatlarni oʻchirmaydi.
- **Yashirilgan (oʻchirilgan) mahsulot:** yana faol boʻladi.

Misol:

| Nomi | Oʻlchov birligi | MXIK | Birlik kodi |
|---|---|---|---|
| Pomidor | kg | 00702001001000001 | 796 |
| Bodring | kg | | |
| Olma Golden | yashik | 00805001002000003 | |

## 2. Mijozlar

| Ustun | Majburiy | Tanilgan sarlavhalar | Izoh |
|---|---|---|---|
| Mijoz | **ha** | `Mijoz`, `Mijoz nomi`, `Xaridor` · `Клиент`, `Название клиента`, `Покупатель` · `Client`, `Client name`, `Customer` | Mijoz nomi, botdagi roʻyxatda shunday koʻrinadi |
| STIR | yoʻq | `STIR`, `JShShIR` · `ИНН`, `ПИНФЛ` · `INN`, `TIN`, `PINFL` | 9 ta raqam (tashkilot) yoki 14 ta raqam (jismoniy shaxs JShShIRi). Boʻsh joy va chiziqchalar olib tashlanadi. Notoʻgʻri boʻlsa qator oʻtkazib yuboriladi. Nakladnoyda xaridor yonida chiqadi |

**Qanday solishtiriladi:**
- **Nomi boʻyicha** (katta-kichik harf farqsiz): «Kafe Bahor» va «kafe bahor» bitta mijoz hisoblanadi.
- **Mavjud mijoz:** takrorlanmaydi. Faylda STIR toʻldirilgan va bazadagidan farq qilsa — STIR yangilanadi («yangilangan»), aks holda «oʻzgarishsiz».
- **Boʻsh STIR** bazadagi STIRni oʻchirmaydi.
- Bir xil STIR bir nechta mijozda boʻlishi mumkin (masalan, bitta tashkilotning filiallari).
- **Yashirilgan mijoz:** yana faol boʻladi.

Misol:

| Mijoz | STIR |
|---|---|
| Bahor kafesi | 123456789 |
| «Navroʻz» restorani | |
| Makro Chilonzor | 30512345678901 |

## 3. Kuryerlar

| Ustun | Majburiy | Tanilgan sarlavhalar | Izoh |
|---|---|---|---|
| Telegram ID | **ha** | `Telegram ID`, `Telegram`, `TG ID`, `ID` | Faqat raqamlar. Kuryer uni botda `/myid` buyrugʻi bilan biladi |
| Kuryer ismi | **ha** | `Kuryer ismi`, `Ism`, `Kuryer`, `F.I.Sh.` · `Имя доставщика`, `Имя`, `Доставщик`, `ФИО` · `Courier name`, `Name`, `Courier` | Hisobot va yuk xatlarida shunday koʻrinadi |

**Qanday solishtiriladi:**
- **Telegram ID boʻyicha.**
- **Mavjud kuryer:** ismi fayldagi bilan yangilanadi.
- **Oʻchirilgan kuryer:** yana yoqiladi.

**Muhim:** Telegram ID — bu `@username` **emas**, balki raqam (masalan, `552020132`). Uni har bir kuryer botga `/myid` yozib oladi. Bot unga «Ruxsat yoʻq» deb javob bergan taqdirda ham ID koʻrsatiladi.

Misol:

| Telegram ID | Kuryer ismi |
|---|---|
| 552020132 | Alisher Karimov |
| 610447215 | Sardor Toshmatov |

---

## Bot fayl turini qanday aniqlaydi

Bot ustun nomlariga qarab quyidagi tartibda tekshiradi:
1. **Telegram ID** va **ism** ustunlari bor → **kuryerlar**.
2. **Mijoz** ustuni bor → **mijozlar**.
3. Qolgan holatlarda → **mahsulotlar**.

Shu sababli mijozlar faylida ustun nomi «Nomi» emas, aynan **«Mijoz»** (`Клиент`, `Client`) boʻlishi kerak. Aks holda bot faylni mahsulotlar deb qabul qiladi.

Admin panelda tur qaysi boʻlimdan yuklayotganingizga qarab belgilanadi. Agar fayl boshqa boʻlimga tegishli boʻlib koʻrinsa (masalan, «Mahsulotlar» boʻlimidan yuklanmoqda, lekin faylda «Mijoz» ustuni bor), hech narsa yuklanmaydi va panel toʻgʻri boʻlimdan yuklashni soʻraydi.

## Natija

Yuklashdan keyin uchta son koʻrsatiladi:
- **yangi:** qoʻshilganlar, yoki yashirilgan/oʻchirilgan va yana faollashtirilganlar;
- **yangilangan:** mavjud yozuvlar, maʼlumoti oʻzgargan (mahsulotlarda: fayldagi barcha mavjud mahsulotlar);
- **oʻzgarishsiz:** mavjud yozuvlar, maʼlumoti bir xil.

Ularning ostida oʻtkazib yuborilgan qatorlar va ogohlantirishlar roʻyxati keladi, har biri qator raqami bilan. Xatoni faylda tuzatib, faylni qayta yuklash mumkin: allaqachon qoʻshilgan yozuvlar takrorlanmaydi.

## Tez-tez uchraydigan xatolar

| Xabar | Sabab va yechim |
|---|---|
| *Eski .xls formati qoʻllab-quvvatlanmaydi* | Faylni `.xlsx` yoki `.csv` qilib qayta saqlang |
| *Faylni oʻqib boʻlmadi* | Fayl buzilgan, parol bilan himoyalangan yoki Excel/CSV emas |
| *N-qator: «…» toʻldirilmagan* | Majburiy ustun boʻsh: toʻldiring yoki qatorni oʻchiring |
| *N-qator: Telegram ID «…» faqat raqamlardan iborat boʻlishi kerak* | `@username` yoki matn yozilgan: raqamli ID kerak (`/myid`) |
| *N-qator: «…» faylda yuqorida bor* | Bitta faylda bir xil nom yoki ID ikki marta: faqat birinchisi olinadi |
| *N-qator: MXIK matn emas, son sifatida yozilgan* | MXIK ustunini «Matn» formatiga oʻtkazib, kodlarni qayta kiriting |
| *Bu «…» boʻlimi uchun fayl koʻrinadi* | Fayl boshqa boʻlimdan yuklanmoqda: koʻrsatilgan boʻlimni ochib, oʻsha yerdan yuklang |
| *Qatorlar juda koʻp* | 5000 qatordan koʻp: faylni bir nechta qismga boʻling |
