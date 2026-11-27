Joriy hisobotlar, XLSX/DOCX, import va Telegram: [foydalanish yo'riqnomasi](REPORTING_GUIDE_2026-10-30.md).

Joriy qoidalar va o'zgarishlar: [moliya, tarif, Telegram va backup yo'riqnomasi](IMPROVEMENTS_2026-10-29.md).

Soddalashtirilgan SargetCRM

Loyiha Django va mavjud SQLite bazasida ishlaydi. Redis, Docker, AI agent,
Click/Payme va boshqa onlayn to'lov provayderlari talab qilinmaydi.
CRMdagi qo'lda naqd/karta/bank to'lovi yozuvlari saqlangan.

Kundalik ishlash uchun qo'shilgan imkoniyatlar:

- Arizalar, o'quvchilar, to'lovlar va baholar 50 tadan sahifalanadi. Keyingi
  sahifaga o'tganda qidiruv va filtrlar saqlanadi; jami hisoblar barcha
  filtrlangan yozuvlar bo'yicha chiqariladi.
- Retsepshen bosh sahifasidagi **Bugungi ishlar** uch navbatni ko'rsatadi:
  muddati kelgan qo'ng'iroqlar, yangi arizalar va bugunga rejalashtirilgan
  keyingi qo'ng'iroqlar. Navbatda o'ziga biriktirilgan va mas'ulsiz arizalar bor.
  Boshqa xodimga biriktirilgan ariza shu navbatga kirmaydi.
- **O'zimga olish** tugmasi mas'ulsiz arizani retsepshenga biriktiradi va
  tarixga yozadi. Boshqa xodimga biriktirilgan arizani bu tugma tortib olmaydi.
  Adminning oddiy tahriri mas'ulsiz arizani uning o'ziga biriktirmaydi.
- Qabul ro'yxatida **Mening arizalarim**, **Biriktirilmagan**, **Mening
  navbatim**, qayta aloqa muddati filtrlari mavjud; CSV eksport ham ayni
  filtrlarni qo'llaydi. Avvalgi umumiy qabul ro'yxati saqlangan: bu filtrlar
  ish navbatini ajratadi, alohida yangi maxfiylik chegarasi emas.
- Yangi Telegram va callback bildirishnomasi tegishli arizaga bog'lanadi.
  Qo'ng'iroq panelidan ochilganda xabar o'qilgan deb belgilanib, ariza ochiladi.
  **Barcha bildirishnomalar** sahifasida eski xabarlar va o'qilmaganlar filtri bor.
  Faqat xabar egasi uni ochishi yoki o'qilgan deb belgilashi mumkin.
- Migratsiyadan oldingi xabarlarning ariza bog'lanishi taxmin bilan
  to'ldirilmagan; ular tarixda o'qiladi. Ariza keyinchalik o'chirilsa ham
  bildirishnoma tarixi saqlanadi.

PowerShell, loyiha papkasida:

```powershell
Copy-Item .env.example .env
# .env ichida o'z qiymatlaringizni kiriting.
.\venv\Scripts\python.exe manage.py migrate
.\venv\Scripts\python.exe manage.py runserver
```

Mavjud `.env` bo'lsa ustiga nusxa olmang. `.env` avtomatik o'qiladi;
server environment qiymatlari undan ustun. Lokal ish uchun DEBUG=True,
production uchun DEBUG=False, haqiqiy hostlar va kuchli secret kiriting.
Productionning HTTPS va WSGI sozlamalari hosting tomonidan ta'minlanadi.

Telegram bot uchun .env dagi TELEGRAM_BOT_TOKEN ni sozlang.
TELEGRAM_WEBHOOK_SECRET faqat webhook ishlatganda kerak; ixtiyoriy
TELEGRAM_STAFF_CHAT_ID faqat xodimlar guruhiga tegishli bo'lsin.

Botda kurs tanlovini chiqarish uchun CRM menyusidagi **Kurslar** bo'limiga
kiring, **Kurs qo'shish** orqali kurs nomini saqlang va **Telegram botda faol
ko'rsatilsin** belgisini yoqing. Bot kurslar ro'yxatini har yangi ariza
boshlanganda CRM bazasidan oladi. Kursni o'chirmasdan botdan yashirish uchun
uni tahrirlab faol belgisini olib tashlang.

Haqiqiy HTTPS manzil tayyor bo'lganda webhook ishlatish:

```powershell
.\venv\Scripts\python.exe manage.py setup_telegram_webhook https://CRM-DOMAIN
```

Lokal kompyuterda public HTTPS domen bo'lmasa, `runserver` polling botni ham
avtomatik boshlaydi (`TELEGRAM_BOT_MODE=auto`, `DJANGO_DEBUG=True`). Alohida
terminal kerak emas:

```powershell
.\venv\Scripts\python.exe manage.py runserver
```

CRM va bot to'xtashi uchun `Ctrl+C` bosing. BotFather bergan botni
Telegramda ochib `/start` yuboring. Polling va webhook bir vaqtda ishlamaydi;
`run_telegram_bot` webhook sozlangan bo'lsa ishga tushishni rad etadi. Kompyuter
qayta yoqilgandan keyin shu buyruqni yana boshlash kerak. Productiondagi
`serve`, avtomatik qayta boshlash va birga ishlaydigan fon vazifalari uchun
[joriy ishga tushirish yo'riqnomasiga](RUNNING_CRM_AND_BOT.md) qarang.

`runserver` yoki `serve` standart sozlamada eslatma va navbatni ham bajaradi.
Faqat `CRM_BACKGROUND_JOBS=False` tanlanganda eslatmalar uchun Windows Task
Schedulerda alohida task yarating:

- Program: loyihadagi `venv\Scripts\python.exe` ning to'liq manzili.
- Arguments: `manage.py send_reminders`.
- Start in: loyihaning to'liq papkasi.
- Har 1 daqiqada takrorlash; bir nusxasi ishlayotgan bo'lsa yangi nusxa ochmaslik.
- Kompyuter/server va scheduler doim ishlashi kerak.

Linux serverda shu buyruqni cron bilan har daqiqada bajarish mumkin.
Django serverini ochish scheduler ishga tushganini anglatmaydi.

Amalga oshirilgan tuzatishlar:

- Faol biznes roli yo'q hisoblar uchun CRM yopilgan; API va kartada obyekt doirasi.
- Xavfsiz login redirect; GET orqali baho o'chirish yopilgan.
- To'lov formasida foydalanuvchi matni xavfsiz DOM bilan ko'rsatiladi.
- Student, teacher va resepshnning CRMdagi o'chirish amali arxivlashga o'tkazilgan.
  Xodimni arxivlash uning loginini ham bloklaydi.
- To'lov mavjud bo'lsa o'quvchini bazadan hard-delete qilish PROTECT bilan to'xtaydi.
- Qarzdorlikda har bir oyning qisman to'lovi va eski to'lanmagan oylar hisoblanadi.
- Yangi to'lovda o'qituvchi va uning foizi saqlanadi; komissiya eski resepshn/foizni saqlaydi.
- To'langan o'qituvchi/resepshn oyligi qayta hisoblashda o'tkazib yuboriladi.
- Lead o'quvchiga aylanganda resepshn va ko'rish huquqi saqlanadi.
- Davomat holatlari tekshiriladi va qayta ochilganda tiklanadi; baho dublikati bazada cheklangan.
- Bir kundagi boshqa callback vaqti alohida eslatma oladi.
- Grafiklar JSON bilan chiqariladi; oylar kalendar bo'yicha yaratiladi.
- Noto'g'ri filtr/oy 500 o'rniga boshqariladigan javob beradi.
- CSV eksport filtrga mos, formula ko'rinishidagi qiymatlar oddiy matnga aylantiriladi.
- To'lov eslatmasi barcha muddati kelgan qarz qoldig'ini hisoblaydi;
  ichki moliyaviy bildirishnomalar super adminga yuboriladi.
  Telegramda yuborish xatosi keyingi tekshiruvda qayta uriniladi.

Muhim hisoblash qoidalari:

- Har o'quvchining tarifi tarix bilan saqlanadi. Narx, chegirma va holat
  o'zgarishi keyingi oydan amal qiladi; o'tgan oylar o'zgarmaydi.
- Eski yozuvlarning boshlang'ich narxi taxminiy deb belgilanadi.
- To'lov o'chirilmaydi: sabab bilan bekor qilinadi, asl yozuv va tarix saqlanadi.
- Telegram hisobini ulash uchun CRMdan bir martalik kod olish kerak.
- `backup_database` endi baza va rasmlarni tekshirilgan ZIP arxivga oladi.
- Eslatmalar faqat scheduler orqali yaratiladi; GET polling faqat o'qiydi.
- SQLite uchun parallel scheduler nusxalarini ishlatmang. To'liq outbox va
  ko'p worker arxitekturasi bu yangilanishda qo'shilmagan.

Auditning 2026-10-29 kungi hisoboti oldingi holatni qayd etadi. Undagi 35
bandning hammasi yopilgan deb hisoblanmaydi: to'liq billing, delivery outbox,
kengaytirilgan audit/monitoring va boshqa yangi funksiyalar
alohida rivojlantirish ishlari bo'lib qoladi. AI, Docker, Redis va onlayn
to'lov integratsiyalari foydalanuvchi talabiga ko'ra bu rejaning doirasiga kirmaydi.

Tekshirish:

```powershell
.\venv\Scripts\python.exe manage.py test core
.\venv\Scripts\python.exe manage.py check
.\venv\Scripts\python.exe manage.py backup_database
```

`backup_database` baza va media fayllarni `backups/` ichidagi ZIP arxivga oladi. Bu papka
ichida shaxsiy ma'lumot bor; uni ommaviy saytga chiqarmang. Media fayllari arxiv ichida tekshiriladi. Bitta kompyuterdagi nusxa tashqi zaxira o'rnini bosmaydi.
