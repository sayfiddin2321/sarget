# Moliya, tarif va Telegram yangilanishi

## Komissiya hisoboti

O'quvchilar soni va komissiya summasi alohida agregatlar bilan hisoblanadi.
Bir xil summali komissiyalar ham har biri bir martadan hisobga olinadi.
Bekor qilingan to'lov komissiyasi va tushumi faol hisobotga kirmaydi.

## Tarifning amal qilish qoidasi

- Har o'quvchining oylik summasi va guruh nomi `StudentTariff`da saqlanadi.
- Guruh narxi, chegirma, guruhni almashtirish va faol/haq to'lash to'xtatilgan
  holatiga o'tish **keyingi kalendar oydan** amal qiladi. Shu oy va oldingi
  oylar o'zgarmaydi. Summalar ikki kasrga yaxlitlanadi.
- Birinchi guruhga qabul kechroq bo'lsa, hisoblash biriktirilgan joriy oydan
  boshlanadi; undan oldingi kutish oylariga qarz yozilmaydi.
- Guruh o'chirilsa, eski qarz saqlanadi, keyingi oydan yangi haq hisoblanmaydi.
- Bir oy ichida bir necha o'zgarish bo'lsa keyingi oyning rejalashtirilgan
  tarifi yangilanadi. O'tgan tarif qatorlari o'zgarmaydi.
- Har to'lov o'zida belgilangan oy uchun hisoblanadi; ortiqcha to'lov boshqa
  oyga avtomatik o'tkazilmaydi. Kunlik bo'lib hisoblash, dars paketi va
  qaytarilgan pulni hisobga olish bu yangilanishning doirasiga kirmaydi.

Migratsiyadan oldingi narxlar bazada yo'q. Shuning uchun mavjud guruh narxi
va chegirmasi boshlang'ich taxmin sifatida olinadi va `is_estimated=True`
bilan belgilanadi. Bu tarixiy shartnoma narxi tasdiqlanganini anglatmaydi.
Migratsiya oldidan baza nusxasida qarzlar va to'lovlar saqlanishi tekshirildi.

O'quvchi profilidagi **Tarif tarixi va hisoblash qoidasi** bo'limida
boshlang'ich taxmin, amaldagi va rejalashtirilgan tariflarni ko'rish mumkin.

## Telegram hisobini ulash

1. CRMga kiring va **Telegram ulash** bo'limini oching.
2. Tegishli hisobni tanlab **10 daqiqalik kod yaratish**ni bosing.
3. Kodni hisob egasiga shaxsan bering. U botning shaxsiy chatiga `/link KOD`
   yuboradi. Ichki polling va webhook boti bu buyruqni qo'llaydi.
4. Ulanishni o'chirish uchun hisobni tanlab **Ulanishni uzish**ni bosing.

Kod faqat bir marta ishlaydi; bazaga uning SHA-256 xeshi yoziladi.
Yangi kod eski ishlatilmagan kodni bekor qiladi. Kod yaratish faqat POST va
CSRF himoyasi bilan ishlaydi; sahifa keshga saqlanmaydi. Admin barcha faol
hisoblarni, o'qituvchi o'zini, retsepshen o'zini va o'z o'quvchilarini ulaydi.
Bitta Telegram chatiga bitta profil ulanadi. Kodni faqat hisobning haqiqiy
egasiga berish mas'uliyati CRM xodimiga tegishli.

**Avval telefon orqali ulangan hisoblar qayta kod bilan tasdiqlanishi kerak.**
Eski `telegram_chat_id`ning o'zi shaxsiy ma'lumot olish uchun yetarli emas.

Tashqi bot serveri REST API ishlatsa:

- `.env`dagi `CRM_API_KEY`ni kuchli, tasodifiy qiymatga sozlang. Bo'sh yoki
  eski standart kalit bilan REST API 503 qaytaradi. Ichki botga bu kalit kerak emas.
- Kalit faqat serverda saqlansin; brauzer/mijoz ilovasiga berilmasin.
- `X-CRM-API-Key` yoki `Authorization: Bearer ...` sarlavhasini yuboring.
  URLdagi `api_key` qabul qilinmaydi.
- `POST /api/bot/auth/` endi `{"code":"KOD","chat_id":123456}` oladi.
  Telefon raqamining o'zi bilan ulash olib tashlangan.
- O'quvchi ma'lumoti faqat tasdiqlangan `chat_id` orqali olinadi. Xodim
  xulosasi faqat o'z doirasi bilan cheklanadi; o'qituvchiga qarz summalari berilmaydi.
- API kurslarni faol `Course` katalogidan oladi; guruh nomlarini kurs deb bermaydi.

## Moliyaviy tarix va to'lovni bekor qilish

**Moliyaviy tarix** bo'limi faqat adminga ochiq. To'lov, komissiya,
xarajat, maosh va tarif uchun vaqt, xodim, oldingi va yangi qiymatlar saqlanadi.
Import va Django admindagi oddiy saqlash/o'chirish ham qayd etiladi.
Migratsiya mavjud moliyaviy yozuvlarni **Boshlang'ich yozuv** deb qayd qiladi;
oldingi amallar va ularni bajargan odamlar taxmin bilan to'ldirilmaydi.

To'lovni bekor qilishda sabab majburiy. Asl to'lov va komissiya bazada
saqlanadi; faol tushum, komissiya va qarzni hisoblashdan chiqariladi.
Eski chekni moliyaviy tarix orqali ochish mumkin; unda **BEKOR QILINGAN**
belgisi ko'rinadi. Bu pulni mijozga haqiqatan qaytarish operatsiyasi emas.
O'qituvchi yoki retsepshen maoshi to'langan oyga tegishli to'lov summasi/oyini
o'zgartirish va bekor qilish bloklanadi. To'lov egasini almashtirish o'rniga
xato to'lovni bekor qilib, yangi yozuv yaratiladi.

Tarix CRM va Django admin orqali tahrirlanmaydi yoki o'chirilmaydi.
Bu DB administratoridan himoyalangan kriptografik jurnal emas. Dasturchilar
moliyaviy o'zgarishlarda `save()` ishlatishi kerak; bevosita SQL bu jurnalni
chetlab o'tadi. To'lov uchun queryset `update`, `bulk_update`, `delete` yopilgan;
`bulk_create` oddiy `save()` yo'li orqali bajariladi.

## Eslatmalar va tizim holati

Bildirishnoma GET so'rovi endi faqat o'qiydi. Eslatmalarni yaratish uchun
`send_reminders` rejalashtirilgan holda ishlashi shart. Ochiq brauzer
15 soniyada tekshiradi, yashirin tabda tekshiruv to'xtaydi.

**Tizim holati** bo'limida vazifaning boshlanish/tugash vaqti, holati,
Telegramga yuborilgan va qayta urinishni kutayotgan xabarlar soni ko'rinadi.
3 daqiqa eslatma vazifasi boshlanmasa yoki 24 soat zaxira olinmasa ogohlantiradi.
Bu sahifa tashqi monitoring yoki telefon orqali favqulodda signal o'rnini bosmaydi.
Telegramning yuborish va tasdiq orasidagi uzilishida takroriy xabar ehtimoli
saqlanadi; to'liq outbox va parallel worker mexanizmi qo'shilmagan.

Windows Task Schedulerda quyidagi vazifalarni sozlang. Bu yangilanish
kompyuterning Scheduler sozlamalarini avtomatik o'zgartirmaydi:

| Vazifa | Program | Arguments | Takrorlash |
| --- | --- | --- | --- |
| Eslatmalar | `C:\Users\User\Desktop\sargetcrm\venv\Scripts\python.exe` | `manage.py send_reminders` | Har 1 daqiqada |
| Zaxiralash | shu Python yo'li | `manage.py backup_database` | Har kuni |

Ikkalasida ham **Start in**: `C:\Users\User\Desktop\sargetcrm`.
**If the task is already running: Do not start a new instance** tanlansin.
Server/kompyuter ishlab turishi kerak. Tashqi disk yoki tarmoq papkasi tayyor
bo'lsa, backup argumentiga `--output-dir "D:\CRM-Backups"` qo'shish mumkin.

## Baza va rasmlarni zaxiralash/tiklash

```powershell
.\venv\Scripts\python.exe manage.py backup_database
.\venv\Scripts\python.exe manage.py verify_backup backups\ARXIV-NOMI.zip
# Ishchi bazani almashtirmasdan yangi papkaga tiklash sinovi:
.\venv\Scripts\python.exe manage.py verify_backup backups\ARXIV-NOMI.zip --restore-to backups\restore-check
```

ZIP ichida SQLite bazaning yaxlit nusxasi, barcha `media/` fayllar va SHA-256
manifest bor. Yaratilganda baza yaxlitligi, foreign keylar va fayl xeshlari
tekshiriladi. Tiklash faqat hali mavjud bo'lmagan yangi papkaga bajariladi;
ishchi baza va rasmlar ustiga yozilmaydi. `.env`, bot tokeni va dastur kodi
arxivga kirmaydi; ularni alohida, maxfiy joyda saqlang.

Arxiv shifrlanmagan va shaxsiy ma'lumot saqlaydi. Uni ommaviy papkaga qo'ymang.
Mahalliy nusxani boshqa disk/qurilmaga olib chiqish alohida sozlanadi.
Media fayllar baza nusxasidan keyin o'qiladi: aniq bir vaqtdagi holat zarur
bo'lsa, zaxiralash davomida yangi rasm yuklashni to'xtating. Eski SQLite-only
zaxiralar saqlanadi; yangi `verify_backup` ZIP format uchun mo'ljallangan.

## Tekshirish

```powershell
.\venv\Scripts\python.exe manage.py test core --noinput
.\venv\Scripts\python.exe manage.py check
.\venv\Scripts\python.exe manage.py makemigrations --check --dry-run
```
