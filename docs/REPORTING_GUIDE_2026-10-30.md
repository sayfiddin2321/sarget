# Hisobotlar, ruxsatlar va Telegram: foydalanish yo'riqnomasi

Ushbu yangilanish tasdiqlangan doira: rollar jadvalidagi tuzatishlar,
REP-01–REP-06 va bitta o'quvchining oylik hisoboti. Biriktirilgan katta
texnik topshiriqdagi barcha STU/FIN/GRP/BOT bo'limlari to'liq yangi platforma
sifatida joriy qilinmagan. Mavjud maosh/xarajat modullari olib tashlanmagan.

## Ishga tushirish

Loyiha papkasida:

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe manage.py migrate
.\venv\Scripts\python.exe manage.py runserver
```

**Alohida terminalda fon jarayoni:**

```powershell
.\venv\Scripts\python.exe manage.py process_crm_jobs --loop
```

U katta hisobotlarni yaratadi, oylik obunalarni tekshiradi va Telegram
navbatini yuboradi. `--loop` har 2 soniyada tekshiradi. Bir marta bajarish
uchun `--loop`ni olib tashlang; Windows Task Scheduler/cron bilan har daqiqada
ishga tushirish ham mumkin. Bir xil vazifaning bir necha nusxasini
ishga tushirmang. Server yoqilgan bo'lishi kerak.

**Eslatmalarni yaratish** avvalgidek alohida har daqiqalik vazifa:

```powershell
.\venv\Scripts\python.exe manage.py send_reminders
```

`send_reminders` tashqi xabarni to'g'ridan-to'g'ri yubormaydi: CRM xabarini
va barqaror Telegram navbatini yaratadi. `process_crm_jobs` ularni yetkazadi.
`Tizim holati` sahifasi jarayonlarning oxirgi ishlashi, kutayotgan hisobotlar
va xabarlar, yuborilmagan xabarlarni ko'rsatadi. Fon jarayoni o'chsa
tayyorlash/yuborish kutadi. Ushbu kod yangilanishi kompyuterning global
Scheduler sozlamalarini avtomatik almashtirmaydi.

## Rollar va xodim huquqlari

- To'liq admin faqat `is_superuser=True`. `is_staff=True`ning o'zi CRM
  boshqaruv huquqi bermaydi.
- **Xodim huquqlari** sahifasida super admin har bir xodimning ko'rish,
  tahrirlash, arxivlash, eksport, import, davomat, baho va Telegram amallarini
  yoqadi/o'chiradi. O'chirilgan huquq serverda ham tekshiriladi.
- O'qituvchi va retsepshenning **o'z oyligini ko'rish** ruxsati alohida
  boshqariladi va sukut bo'yicha o'chirilgan. Yoqilganda xodim faqat o'zining
  oylik yozuvlarini hamda o'qituvchi uchun bosh sahifadagi oylik kartasini
  ko'radi; hisoblash va to'langan holatini o'zgartirish super admin vakolatida.
- O'qituvchi o'z shaxsiy va guruhlari doirasida ishlaydi. Unga to'lov qabul
  qilish yoki boshqa guruhni boshqarish huquqi ushbu rol orqali berilmaydi.
- Resepshin barcha o'quvchilarni ko'radi, tahrirlaydi, guruhga biriktiradi,
  to'lov oladi va to'lov reyestrini ko'radi. To'lovni tahrirlash/bekor qilish
  va pul qaytarish super admin uchun qoladi.
- Resepshinga baholarni ko'rish/qo'yish va davomat belgilash sukut bo'yicha
  o'chirilgan; davomatni ko'rishi mumkin. Kerak bo'lsa super admin alohida
  ko'rish va yozish huquqlarini yoqadi. Yozish uchun tegishli ko'rish huquqi
  ham kerak.
- O'quvchini arxivlash tarixi va pullarini o'chirmaydi. Tiklash tugmasi
  o'quvchi kartasida. Murojaatni faqat super admin arxivlaydi/tiklaydi;
  arxivdagilar qabul ro'yxatidagi havola orqali ochiladi.
- **Mening profilim** sahifasi ism, telefon, rasm va izohni tahrirlaydi;
  maosh foizi, faol holat, login va boshqa xodim huquqlari bu shaklda yo'q.

## Filial, kurs va yozilishlar

Super admin **Filial va kampaniyalar** bo'limida filial va kampaniya
yaratadi. Guruhni tahrirlashda kurs va filial belgilanadi. Eski guruhlar uchun
filial/kurs nomlari taxminan yaratilmaydi: ular bir marta aniq biriktiriladi.

Shaxsning yagona UUIDsi va `STU-000001` shaklidagi ko'rinadigan raqami bor.
O'quvchi kartasida asosiy guruh, kelishilgan to'lov kuni va kursga
yozilishlar ko'rinadi. **Boshqa kursga yozish** orqali qo'shimcha yozilish
yaratiladi; uning guruhi, boshlanishi, holati, oylik narxi va to'lov kuni
alohida. To'lov formasida tegishli yozilishni tanlang; bo'sh qoldirilsa
asosiy kurs uchun hisoblanadi.

Eski kartalardan boshlang'ich yozilish ro'yxat sanasi va mavjud guruh asosida
migratsiya qilindi. Bunda oldingi noma'lum filial, kurs, shartnoma yoki
narxlar tarixi o'ylab topilmadi. Avvalgi taxminiy tarif belgilari saqlandi.
Davomati/yozilishi mavjud guruhni o'chirish o'rniga arxivlash ishlaydi.

## REP-01: filtrlar va sonlar

**Hisobotlar markazi**: davr, filial, kurs, guruh, o'qituvchi, bitta o'quvchi
va qo'shimcha filtrlar. O'qituvchi begona filtr/obyekt orqali boshqa
ma'lumotni ola olmaydi. O'quvchilar ro'yxatidagi eksport havolasi qidiruv,
status, manba va ro'yxat sanasi filtrlarini hisobotga olib o'tadi.

- Faol o'quvchilar: kamida bitta faol yozilishi bor takrorlanmas shaxslar.
- Faol yozilishlar: faol yozilishlar soni; bitta shaxs ikki kursda ikki yozilish.
- Yangi shaxslar: markaz bo'yicha ilk yozilish sanasi davrga tushganlar.
  Boshqa filial/kursdagi keyingi yozilish yangi shaxs deb sanalmaydi.

Faollik yozilishning saqlangan joriy holati va boshlanish/tugash sanalari
bilan aniqlanadi. Migratsiyadan oldingi yo'q holat almashish tarixi
qayta tiklangan deb hisoblanmaydi. Pul/qarz tarixini tanlangan sana bo'yicha
hisoblash faollik sonidan alohida.

## REP-02–03: marketing

Arizalar **yaratilgan sana kohortasi** bilan olinadi. Haqiqiy arizalar,
noto'g'ri murojaatlar va test yozuvlari alohida ko'rsatiladi.

To'lovli konversiya:

`kohortadagi kamida bir musbat, bekor qilinmagan to'lovga ega haqiqiy ariza / haqiqiy arizalar × 100`.

To'lov ariza yaratilganidan keyin, tanlangan kuzatish oxirigacha tushgan
bo'lishi kerak. Arizani shunchaki o'quvchiga aylantirish pul tushganini
bildirmaydi. Kurs filtri hali o'quvchiga aylanmagan shu kursga qiziqqan
arizalarni ham saqlaydi. Murojaatning kurs matni katalog nomiga mos bo'lishi
kerak; noma'lum erkin kurs nomlari mos katalog filtriga taxmin bilan kiritilmaydi.

Kanal va reklama manbasi alohida. Masalan, kanal `telegram`, reklama manbasi
`Instagram reklama`. Kampaniyaning `start` kodi serverdagi yozuvga bog'lanadi.
Noma'lum/yo'q kodda reklama manbasi bo'sh qoladi; Telegram avtomatik reklama
manbasi deb yozilmaydi. Eski `source` ham moslik uchun alohida saqlanadi.

XLSXda arizalar bilan birga kohorta yakuni va manba/bosqichlar varaqlari bor.
Kuzatishning oxirgi sanasi fayl va sahifada chiqadi. Bosqichlar arizaning
saqlangan holati; mavjud bo'lmagan tarixiy holatlar taxminan yaratilmaydi.

## REP-04: hisoblar

Quyidagi hisobotlar mavjud:

- To'lov reyestri — pul tushgan sana, xizmat oyi, usul, xodim va ma'lum bo'lsa
  tarixiy guruh/kurs/filial bilan.
- To'lagan/qisman/to'lamagan — tanlangan xizmat oylari va guruh bo'yicha.
- Muddati o'tgan qarz — holat sanasidan oldingi muddatdagi musbat qoldiq;
  aynan holat sanasida to'lanadigan summa alohida.
- Avans — tegishli oy haqidan ortiqcha yoki kelgusi oy uchun oldindan
  qabul qilingan pul. Boshqa kurs/oyga avtomatik ko'chirish yo'q.
- Pul qaytarish reyestri. Super admin chekdan **Pul qaytarishni qayd etish**
  orqali haqiqiy qaytarimni yozadi. Summa mavjud qoldiqdan oshmaydi. Qaytarim
  qarzni qayta ochadi; u chegirma yoki to'lovni bekor qilish bilan bir xil emas.
- Guruh to'lishi, davomat, baholar va muddati kelgan bajarilmagan callbacklar.

Davr yalpi tushumi, shu davrdagi qaytarim, bekor qilish va **sof pul tushumi**
alohida. Sof pul tushumi foyda deb nomlanmaydi. Xizmat oyi va pul tushgan
sanani aralashtirmang. Davr oxiridagi qarz pul tushumidan alohida hisoblanadi.
Eski to'lovda tarixiy filial/kurs/guruh yozilmagan bo'lsa ushbu filtrga taxmin
bilan kiritilmaydi; umumiy reyestrda ko'rinadi.

Bu to'liq FIN-01–FIN-10 hisob-faktura/taqsimot daftari emas. Mavjud oylik
tarif va aniq tanlangan yozilish asosida hisoblanadi; kunlik prorata, kredit
tuzatishi yoki avansni boshqa kursga taqsimlash yangi yashirin amal sifatida
qo'shilmagan.

## REP-05: Excel va Word

Har hisobot XLSXga chiqadi. DOCXning oldindan belgilangan shablonlari:
o'quvchilar, davomat, baholar, to'lovlar reyestri va foydalanuvchi so'ragan
bitta o'quvchi uchun birlashtirilgan hisobot. Erkin konstruktor yo'q.

500 satrdan katta fayl fonda tayyorlanadi va **Mening fayllarim**da chiqadi.
Fayllar `private/reports/`da, ommaviy `media/`dan tashqarida saqlanadi.
Faylni faqat uni yaratgan foydalanuvchi oladi; yuklash va yuborish paytida
joriy huquq hamda o'quvchi/guruh doirasi yana tekshiriladi. Huquq/doira
o'zgarsa eski fayl bloklanadi va yangisini yaratish kerak.

`=`, `+`, `-`, `@` bilan formula sifatida ishlashi mumkin bo'lgan foydalanuvchi
matnlari XLSXda matn sifatida chiqariladi. Summalar hisoblashda DECIMAL.

## Bitta o'quvchining oylik hisoboti

1. O'quvchilar ro'yxatida hisobot belgisini yoki kartadagi **Oylik hisobot /
   Excel / Word / Telegram** tugmasini bosing.
2. Oyni yoki sana oralig'ini tanlang. Shu shaxsning ma'lumotlari, davomat
   sanalari/holatlari, baholari va ruxsat bo'lsa to'lovlari bir faylga yig'iladi.
3. Davomatning keldi+kechikdi foizi va baholarning o'rtacha bali ko'rsatiladi.
   Belgilanmagan darslar yo'q yozuv sifatida "kelmadi"ga aylantirilmaydi.
4. XLSX yoki DOCX yuklang. Telegram bo'limida ulangan o'quvchi yoki
   ota-onani tanlab, Excel hisobotni yuborish navbatiga qo'ying. Hisobot sahifasi
   endi faqat davr va hisobotni ko'rsatadi; XLSX import alohida menyuda.
5. Telegram ulanmagan bo'lsa, **Telegramni ulash** bo'limida o'quvchi yoki
   ota-onani tanlang. CRM bergan `/start link_KOD` buyrug'ini qabul qiluvchi
   botga yuboradi. Kod 10 daqiqalik va bir martalik; ulanganidan so'ng sahifani
   yangilab hisobotni yuboring.

Yuborish holati hisobot sahifasidagi jadvalda ko'rinadi. Navbatdagi hisobotni
tayyorlash va jo'natish uchun `process_crm_jobs --loop` worker ishlashi kerak;
worker to'xtagan bo'lsa, hisobot navbatda qoladi.

Hisobot tarkibi uni yaratgan xodim vakolatiga mos: masalan, o'qituvchi
fayliga moliyaviy reyestr kirmaydi. Resepshinga baholarni ko'rish ruxsati
o'chirilgan bo'lsa, u yaratgan faylda baholar ham bo'lmaydi.

## REP-06: import

Oddiy import turlari: shaxs ma'lumotlari, davomat, baholar. **XLSX import**
yoki o'quvchining hisobot sahifasidagi import havolasidan boshlang.

1. Tegishli XLSX shablonni yuklang. Bir fayl — tanlangan turdagi bitta varaq.
2. Dublikat strategiyasini tanlang: xato, o'tkazib yuborish, aniq raqam/kalit
   bilan yangilash yoki telefon o'xshash bo'lsa ham alohida yangi shaxs.
3. Preview satr, ustun, sabab, bajariladigan amal va ogohlantirishni ko'rsatadi.
   Hali biznes yozuvi o'zgarmaydi. Bir xato bo'lsa butun fayl bloklanadi.
4. Tasdiqlang. Huquqlar, guruh sig'imi, dublikatlar va eski yozuv versiyasi
   yana tekshiriladi; barchasi bitta tranzaksiyada bajariladi.

Fayl 5 MB/5000 satrgacha. Formula qabul qilinmaydi. Preview 24 soat amal
qiladi. Ikki marta tasdiqlash ikkinchi nusxa yaratmaydi. Telefon tengligi
shaxsni avtomatik birlashtirmaydi. O'qituvchi yangi shaxs yaratmaydi, faqat
o'zining aniq raqamli o'quvchisini va ruxsatli guruhdagi akademik yozuvni
yangilaydi. Tanlangan bitta o'quvchi importiga boshqa shaxsni qo'shib bo'lmaydi.

**Moliyaviy tarix alohida:** adminning to'lov importi endi alohida XLSX
migratsiya. Manba reyesrining jami summasi kiritiladi; preview summasi bilan
mos kelishi shart. Tasdiqda mavjud dublikatlar yana tekshiriladi va bazadagi
pul yozuvlari o'sishi fayl jami bilan solishtiriladi. Telefon bo'yicha taxminiy
bog'lash, tarixiy o'qituvchi/filial yoki komissiyani joriy qiymatdan to'ldirish
yo'q. Mavjud tarixiy fayllar tayyorlanishi va solishtirilishi administrator
tomonidan bajariladi. Eski to'g'ridan-to'g'ri CSV import yo'llari shu yangi
preview jarayoniga almashtirilgan.

## Telegram: bir martalik va avtomatik yuborish

`.env`da `TELEGRAM_BOT_TOKEN` sozlangan bo'lsin. Bot polling yoki webhook
orqali ishlashi, yuborish navbati uchun yuqoridagi fon jarayoni ham ishlashi
kerak. Shunchaki telefon/username yozish xabar yuborishga yetarli emas.

Umumiy **Telegram ulash** sahifasida o'quvchi yoki **ota-ona/vasiy** turini
tanlang. Hisobot sahifasidagi ulash bo'limi ham shu 10 daqiqalik, bir martalik
koddan foydalanadi: qabul qiluvchi botga `/start link_KOD` yuboradi. Kod telefon
egasi ekanini o'z-o'zidan isbotlamaydi: kodni haqiqiy o'quvchi/vasiyga berishni
xodim tekshiradi.

Avtomatik oylik hisobot:

- Telegrami ulangan faol o'quvchi va vasiylarga obuna formasini alohida
  yoqmasdan, har oyning 1-kunida o'tgan oyning hisoboti avtomatik yuboriladi.
  Hisobot Excel fayli bo'lib, davomat, baholar va to'lovlar ro'yxatini
  (chek raqami, summa, sana va to'lov usuli) o'z ichiga oladi; alohida chek
  fayllari yuborilmaydi.
- Yuborish tarixi navbatda, qayta urinish, yuborilgan yoki bekor qilingan
  holatni ko'rsatadi.
- O'quvchi va vasiy bot buyruqlari orqali hisobotlarni boshqara olmaydi; bu
  sozlamani CRM xodimi boshqaradi. Ulanish uzilsa yoki xodim ulanishni o'chirsa,
  navbatdagi yuborish bekor qilinadi.
- Avtomatik hisobot uchun faol superuser va doimiy ishlaydigan
  `process_crm_jobs --loop` jarayoni talab qilinadi. Telegram tokeni sozlanib,
  bot Telegramdan xabar qabul qilishi va CRM internetdan ochiq bo'lishi kerak.

Yangi ariza va callbacklar mas'ul resepshinning tasdiqlangan shaxsiy chatiga,
to'lov eslatmalari esa CRMda o'quvchiga mas'ul resepshin va super adminlarga
ko'rsatiladi. To'lov sanasidan 3 kun oldin, to'lov kuni hamda qarz qolgan har
kuni bildirishnoma yaratiladi. Uni ochish o'quvchi kartasiga olib boradi;
xodim u yerdan tasdiqlangan o'quvchi yoki ota-ona Telegramini tanlab xabar
matnini tahrirlaydi va jo'natishni tasdiqlaydi. Tizim mijozga o'z-o'zidan
to'lov xabari yubormaydi. Ixtiyoriy `TELEGRAM_STAFF_CHAT_ID` guruhiga ham ichki
xabar beriladi. O'quvchi kartasidagi Telegram bo'limi matn yuborish navbatini
ko'rsatadi; davomat/baholar Excel hisoboti esa **Oylik hisobot / Telegram**
sahifasidan yuboriladi. Murojaat kartasida **Telegram xabari** orqali mijozga
yozish va kelgan javoblarni ko'rish mumkin.

Takroriy vazifalar kalit bilan ajratiladi, xatolarda qayta urinish va
Telegram 429 kutish vaqti hisobga olinadi. Tarmoq uzilishi xabar yuborilgach,
tasdiq bazaga yozilishidan oldin yuz bersa kam uchraydigan takroriy yuborish
ehtimoli saqlanadi. Worker birinchi ishga tushganda mavjud haqiqiy navbatni
yuboradi; uni sinov uchun ishchi token bilan tasodifan ishga tushirmang.

## Tekshiruv

```powershell
.\venv\Scripts\python.exe manage.py test core --noinput
.\venv\Scripts\python.exe manage.py check
.\venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\venv\Scripts\python.exe manage.py backup_database
```

Testlar haqiqiy XLSX/DOCXni o'qib tekshiradi, import preview/tasdiq, rol va
obyekt doirasi, tarixiy pul qoldig'i, marketing kohortasi hamda Telegram
navbati holatlarini sun'iy bazada sinaydi. Telegram yetkazilishi testlarda
taqlid qilinadi; haqiqiy odamlarga xabar yuborilmaydi.
