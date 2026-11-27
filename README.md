Joriy hisobotlar, XLSX/DOCX, import va Telegram: [foydalanish yo'riqnomasi](docs/REPORTING_GUIDE_2026-10-30.md).

CRM va botni alohida serverga chiqarish: [yangilangan yo'riqnoma](docs/SERVER_READY.md).

# Sarget IT Academy — CRM Tizimi

Joriy moliya, tarixiy tarif, Telegram ulash va zaxiralash: [yangilanish yo'riqnomasi](docs/IMPROVEMENTS_2026-10-29.md).
Professional o'quv markaz boshqaruv tizimi.

Joriy soddalashtirilgan o'rnatish va cheklovlar: [Django + SQLite yo'riqnomasi](docs/SIMPLE_SETUP.md).
Redis, Docker, AI va Click/Payme integratsiyalari talab qilinmaydi.

## Rollar

| Rol | Imkoniyatlar |
|-----|-------------|
| **Boshliq (Admin)** | Barcha imkoniyatlar — to'liq nazorat |
| **O'qituvchi** | O'z guruhlari, o'quvchilar, davomat, o'z oyligi |
| **Retsepshen** | Yangi o'quvchi qabul qilish, to'lov qabul qilish |

## Ishga tushirish

CRM va Telegram botni bitta buyruqda ishga tushirish hamda production serverga
o‘rnatish: [joriy yo‘riqnoma](docs/RUNNING_CRM_AND_BOT.md).
Lokal: `python manage.py runserver`. Production: `python manage.py serve`
(HTTPS va `.env` sozlamalarini yo‘riqnomaga mos kiriting).

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

## Login ma'lumotlari (demo)
- **Admin:** admin / admin12345
- **O'qituvchi:** teacher1 / teacher123
- **Retsepshen:** reception1 / recept123

## Texnologiyalar
- Django 4.2+ (Python 3.10+)
- SQLite (ishlab chiqish), PostgreSQL (production uchun tavsiya)
- Bootstrap-free — sof CSS variables tizimi
- Chart.js, Select2, Font Awesome 6
"# sargetacademy-crm" 

## Telegram bot va qabul arizalari

Bot `/start` dan keyin ism, familiya, kurs va telefonni ketma-ket so'raydi.
Telefonni tugma orqali yoki matn bilan yuborish mumkin. `/cancel` arizani bekor
qiladi. Yakunlangan ariza CRMdagi **Qabul arizalari** bo'limiga tushadi; faol
retsepshenlar va super admin CRMda bildirishnoma oladi. Tugallanmagan suhbat
bazada saqlanadi, server qayta ishga tushsa davom ettirish mumkin.

Retsepshen arizani ochib holat va aloqa natijasini saqlaydi. Mas'ulsiz arizani
o'ziga olgan yoki birinchi saqlagan retsepshen mas'ul bo'ladi. Super admin holatlar bo'yicha umumiy sonlarni,
mas'ulni va harakatlar tarixidagi xodim, vaqt, natijani ko'radi.
Bog'lanilmagan (`Yangi`) ariza uchun Toshkent vaqti bo'yicha keyingi kundan
boshlab har kuni bir marta eslatma yaratiladi. Holat o'zgarsa bu eslatma
to'xtaydi. `Qayta qo'ng'iroq` holati uchun sana/vaqt majburiy; alohida eslatma
belgilangan vaqtdan 10 daqiqa oldin boshlanadi va holat o'zgarguncha har kuni
takrorlanadi. Bildirishnomani o'qish ariza holatini o'zgartirmaydi.

PowerShellda serverni ishga tushirishdan oldin muhit o'zgaruvchilarini sozlang
(qiymatlar namunaviy; haqiqiy tokenni kodga yozmang):

```powershell
$env:TELEGRAM_BOT_TOKEN = '<BotFather bergan token>'
$env:TELEGRAM_WEBHOOK_SECRET = '<tasodifiy-maxfiy-qiymat>'
# Ixtiyoriy: faqat xodimlar kiradigan Telegram guruhining chat IDsi.
$env:TELEGRAM_STAFF_CHAT_ID = '<xodimlar guruhi chat IDsi>'
python manage.py migrate
python manage.py setup_telegram_webhook https://crm.example.com
```

Webhook uchun internetdan ochiladigan HTTPS domen kerak. Secret faqat
`A-Z`, `a-z`, `0-9`, `_`, `-` belgilaridan tuzilsin (1–256 belgi).
Webhook sozlash buyrug'i Telegramda tashqi o'zgarish qiladi; uni haqiqiy
domen va token tayyor bo'lganda bajaring. Botga `/start` yuborib tekshiring.

`runserver` va `serve` standart holatda eslatma va xabar navbatini ham
bajaradi. Faqat `CRM_BACKGROUND_JOBS=False` tanlanganda serverdagi cron yoki
Windows Task Scheduler orqali quyidagi buyruqni har
daqiqada, shu loyiha papkasida va server bilan bir xil muhit o'zgaruvchilari
bilan ishga tushiring:

```powershell
python manage.py send_reminders
```

Fon vazifalari o'chirilgan bo'lsa `send_reminders` rejalashtirilgan buyruq
sifatida ishlashi shart. CRMdagi davriy tekshiruv faqat tayyor bildirishnomalarni o'qiydi. Ixtiyoriy
Telegram guruhi sozlangan bo'lsa kunlik eslatmalar o'sha guruhga ham yuboriladi;
mijozlarga xodimlarning ichki eslatmalari yuborilmaydi. Telegram yuborishi
muvaffaqiyatsiz bo'lsa keyingi ishga tushishda qayta uriniladi.

To'lov muddati yaqinlashganda (3 kun oldin), to'lov kuni va qarz qolgan har
kuni CRMda mas'ul xodimga bildirishnoma keladi. Bildirishnomani ochib o'quvchi
kartasidagi Telegram bo'limidan ulangan o'quvchi yoki ota-onani tanlab, matnni
tekshirib yuboring. Xabarlar rozilik bilan tasdiqlangan Telegram ulanishlariga
navbatlanadi; xodim tasdiqlamaguncha mijozga avtomatik to'lov xabari yuborilmaydi.
Davomat va baholar hisobotini ham o'quvchi kartasidan Telegramga yuborish mumkin.

Telegrami tasdiqlangan faol o'quvchi va vasiylarga o'tgan oyning davomat,
baho va to'lovlar ro'yxati (chek raqami, summa, sana, usul) Excel hisoboti
har oyning 1-kunida avtomatik yuboriladi. `runserver` va `serve` bu navbatni
ham bajaradi. Faqat `CRM_BACKGROUND_JOBS=False` bo'lsa alohida PowerShell
oynasida `python manage.py process_crm_jobs --loop` doimiy ishlasin; navbat
bazada saqlanadi va jarayon qayta ishga tushganda davom etadi. Batafsil:
[hisobot va Telegram yo'riqnomasi](docs/REPORTING_GUIDE_2026-10-30.md).

Reklama manbasini saqlash: `https://t.me/BOT_USERNAME?start=instagram`.
Telegram takror yuborgan bir xil update qayta ariza yoki bildirishnoma
yaratmaydi. Testlar: `python manage.py test core`.


### Sana oralig?i bo?yicha oylik va chek tekshiruvi

Oyliklar ? Sana oralig?i bo?yicha hisoblash (`/salaries/period/`) sahifasida
pul tushgan boshlanish va tugash sanalarini tanlang. Ikkala kun ham kiradi:
masalan, 2026-05-10 dan 2026-06-10 gacha. Qaysi dars oyi uchun to?langanini
alohida tanlash mumkin (aprel, iyul va hokazo); bo?sh qoldirilsa barcha oylar kiradi.
O?qituvchi filtri, takrorlanmagan o?quvchilar soni, to?lovlar soni, har bir to?lovning
sanasi va dars oyi hamda saqlangan foiz asosidagi o?qituvchi ulushi ko?rsatiladi.
Bu jonli hisob: mavjud kalendar oylik yozuvlarini o?zgartirmaydi va to?langan
oylik sifatida saqlamaydi. Bekor qilingan va tarixiy import to?lovlari chiqariladi;
qaytarimlar hisobot ochilgan paytdagi holat bo?yicha tushumdan ayriladi.
To?lovlar ro?yxatida ham pul tushgan sana oralig?i va dars oyi birgalikda filtrlanadi.

Yangi chiqarilgan chek QR kodi imzolangan ommaviy tekshirish havolasini saqlaydi.
Telefon orqali kirish talab qilinmasdan to?lov holati bazadan tekshiriladi:
tasdiqlangan, bekor qilingan, qisman yoki to?liq qaytarilgan. Telefon raqami va
o?quvchi ismi ochiq tekshirish sahifasida ko?rsatilmaydi. Chekni CRMning telefon
orqali ochiladigan haqiqiy domenidan yarating; localhost havolasi boshqa qurilmada
ochilmaydi. Avval saqlangan QR rasmlarini yangilash uchun chekni qayta chiqarish kerak.

QR havolalari uchun server muhitida `QR_VERIFY_BASE_URL` ga CRMning ommaviy
HTTPS manzilini berish mumkin (masalan, `https://crm.example.uz`). Bu manzil
Telegram manzilidan ustun turadi. QR ochilganda chek raqami, summa, sana va
joriy holat bazadan olinadi; noto'g'ri havolaga tasdiq belgisi chiqarilmaydi.
Chek sahifasida 80 mm yoki 58 mm qog'oz tanlanadi; sahifa balandligi tanlangan
chop etish kengligidagi mazmunga qarab hisoblanadi. Yangi CSS/JS fayllari serverga
chiqarilganda `collectstatic` bajarilishi kerak. Yakuniy qog'oz uzunligi printer
drayveri sozlamalariga ham bog'liq. Sozlamalar va testlar:
[termal chek yo'riqnomasi](docs/RECEIPT_PRINTING.md).
"# sarget" 
"# sarget" 
