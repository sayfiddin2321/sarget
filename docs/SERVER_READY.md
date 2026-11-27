# CRM va bot: alohida serverlarga chiqarish

## crm.milliycrm.uz domenidagi tekshiruv (2026-11-11)

Botning mahalliy `.env` fayli `https://crm.milliycrm.uz` manziliga moslandi.
HTTPS ulanishi muvaffaqiyatli, ammo serverning hozirgi javoblari:

- `/api/bot/health/`: HTTP 404 (serverda yangi health endpoint mavjud emas).
- `/api/bot/courses/`: HTTP 503, `Bot API o'chirilgan: CRM_API_KEY sozlanmagan`.

Serverdagi CRM kodini yangilang, kutubxonalar va migratsiyalarni o'rnating.
CRM serverining `.env` faylida botdagi bilan aynan bir xil CRM_API_KEY
o'rnating (kalitni log yoki chatga chiqarmang). `TELEGRAM_BOT_MODE=disabled`
va `DJANGO_ALLOWED_HOSTS=crm.milliycrm.uz` sozlamalarini tekshiring.
CRM xizmatini qayta ishga tushiring; EnvironmentFile ishlatilsa, kalit
qiymati ham yangi muhitdan yuklanishi kerak.
Keyin bot serverida `venv/bin/python bot.py --check` ikkala manzil uchun
ham OK qaytarishi kerak; shundan so'ng bot xizmatini qayta ishga tushiring.

CRM bazasi faqat CRM serverida. Bot o'zining suhbat holati uchun SQLite ishlatadi,
CRM ma'lumotlari esa HTTPS API orqali keladi. Botga CRM bazasining paroli kerak emas.

## CRM serveri (/opt/sargetcrm, crmuser)

Kodni yangilashdan oldin mavjud baza va media/private fayllarni zaxiralang.
Windows venv, mahalliy .env va mahalliy bazani serverga kod bilan ko'chirmang.

```sh
cd /opt/sargetcrm
python3 -m venv venv
venv/bin/python -m pip install -r requirements.txt
# Faqat yangi o'rnatishda; mavjud .env ni almashtirmang:
cp .env.example .env
chmod 600 .env
```

`.env` dagi production qiymatlari:

```dotenv
DJANGO_DEBUG=False
DJANGO_SECRET_KEY=GENERATE_A_RANDOM_SECRET
DJANGO_ALLOWED_HOSTS=crm.milliycrm.uz
DJANGO_SECURE_SSL_REDIRECT=True
TELEGRAM_BOT_MODE=disabled
TELEGRAM_BOT_TOKEN=YOUR_TELEGRAM_TOKEN
CRM_API_KEY=GENERATE_A_RANDOM_API_KEY
CRM_BACKGROUND_JOBS=False
DB_ENGINE=postgres
DB_HOST=127.0.0.1
DB_PORT=5432
DB_NAME=sargetcrm
DB_USER=sargetuser
DB_PASSWORD=YOUR_DATABASE_PASSWORD
```

Har bir maxfiy kalitni alohida yarating:
`python3 -c "import secrets; print(secrets.token_urlsafe(48))"`.
CRM va botdagi **CRM_API_KEY bir xil** bo'lsin. Telegram tokeni ham bir xil:
CRM xabar yuboradi, faqat alohida bot xabarlarni qabul qiladi.

```sh
venv/bin/python manage.py migrate --noinput
venv/bin/python manage.py check
venv/bin/python manage.py check --deploy
venv/bin/python manage.py collectstatic --noinput
```

`0021_student_deleted_at` migratsiyasi superadmin o'chirish amali uchun shart.
O'chirish ro'yxatlardan olib tashlaydi, moliyaviy tarix va cheklarni saqlaydi.
Bu bazadan qaytarib bo'lmaydigan jismoniy o'chirish emas.

`0022_backfill_teacher_payroll` migratsiyasi mavjud to'lovlardan yetishmayotgan
o'qituvchi oyliklarini yaratadi va to'lanmagan oyliklarni yangilaydi. To'langan
oyliklar saqlanadi. O'qituvchi biriktirilmagan to'lovlar va tarixiy ko'chirish
yozuvlari bu hisobga kirmaydi. Yangi qisman to'lovlar ham to'liq tushgan summasi
bo'yicha oylikka avtomatik kiradi; masalan, 490 000 so'mlik tarifdan 480 000
so'm to'lansa, 40% ulush 192 000 so'm, qolgan qarz 10 000 so'm bo'ladi.
Dashboard, grafik va yillik hisobot xarajatlariga hisoblangan o'qituvchi hamda
retsepshen oyliklari ham kiradi. Oylikni to'langan deb belgilash xarajatni
takror qo'shmaydi. Shu oyliklarni qo'lda yana xarajat sifatida kiritmang.
Sana oralig'i hisobotida "Sof tushum" qaytarimlardan keyingi tushumdir;
"Markazda qolgan qism" esa undan o'qituvchi ulushi ayrilgandan keyingi summa.
Bu qismdan retsepshen maoshi va boshqa xarajatlar hali ayrilmagan.
"To'lovlar" ro'yxatidagi jami barcha tanlangan to'lovlar summasi bo'lib,
uni oraliq hisobot bilan solishtirishda bir xil sana va dars oyini tanlang.

`0023_reconcile_refunded_payroll` migratsiyasi qaytarimlarni va har bir to'lov
ulushining ikki xonali yaxlitlanishini hisobga olib, to'lanmagan oylik va
komissiyalarni yangilaydi. To'langan oyliklar saqlanadi. Oylik allaqachon
to'langan bo'lsa, qaytarim kiritishdan oldin uni to'lanmagan holatga qaytaring.
Yangi to'lovda qo'shimcha kurs tanlansa, ulush shu kurs o'qituvchisiga yoziladi.
Dashboard va yillik hisobot tushumi pul tushgan sana, qaytarim va bekor qilish
sanasi bo'yicha hisoblanadi. Eski oy to'lovi keyingi oyda bekor qilinsa,
kamayish keyingi oyda aks etadi; eski oy tushumi yashirincha o'chirilmaydi.

2026-11-20 tekshiruv natijalari: [moliya va bot tekshiruvi](FINANCIAL_AUDIT_2026-11-20.md).
Bildirishnomalarning sana bo'yicha saqlanadigan tarixi: [foydalanish tartibi](NOTIFICATIONS.md).

`deploy/sarget-crm.service` va `deploy/sarget-crm-jobs.service` ni systemd ga
o'rnating. Papka `crmuser` ga tegishli bo'lsin. Jobs xizmati hisobotlar va
Telegram navbatini bajaradi. `/srv` uchun `deploy/sargetcrm.service` muqobil
variant; ikki CRM xizmatini bir vaqtda ishga tushirmang.

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now sarget-crm sarget-crm-jobs
```

`deploy/nginx.conf` dagi domen, TLS sertifikati va papka yo'llarini moslang.
`limit_req_zone` direktivalari `http` kontekstida, `server` tashqarisida turadi.
Django faqat `127.0.0.1:8000` da ishlaydi; 8000 portni internetga ochmang.
Nginx HTTPS sarlavhasini o'zi o'rnatadi, Waitress faqat lokal proksiga ishonadi.

```sh
sudo nginx -t
sudo systemctl reload nginx
sudo systemctl status sarget-crm sarget-crm-jobs
```

`check --deploy` lokal testda bitta HSTS ogohlantirishi berdi (W004).
HTTPS sertifikati va redirect to'g'ri ishlashi tekshirilgach,
`.env` da `DJANGO_SECURE_HSTS_SECONDS=31536000` qo'yish mumkin.
HSTS brauzerni uzoq muddat HTTPS ishlatishga majbur qiladi; uni HTTPS tayyor
bo'lmasdan yoqmang. Nginx namunasida ham HSTS sarlavhasi bor.

## Bot serveri (/opt/sarget_bot, botuser)

Bot serverida CRM papkasi kerak emas. Faqat sarget_BOT fayllarini joylang:

```sh
cd /opt/sarget_bot
python3 -m venv venv
venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
chmod 600 .env
```

`.env`:

```dotenv
TELEGRAM_BOT_TOKEN=YOUR_TELEGRAM_TOKEN
CRM_API_URL=https://crm.milliycrm.uz
BOT_ENV=production
CRM_API_KEY=SAME_RANDOM_API_KEY_AS_CRM
BOT_STATE_DB=/opt/sarget_bot/bot_state.sqlite3
```

`CRM_API_URL` saytning asosiy manzili; `/api/bot` qismini qo'shmang.
Avval tekshiring (polling va webhookni o'zgartirmaydi):

```sh
venv/bin/python bot.py --check
```

Ikkala tekshiruv OK bo'lsin: health (CRM va baza), courses (API kaliti).
401 - noto'g'ri kalit; 301/302 - manzil; 503 - CRM/baza/API sozlamasi;
ulanish xatosi - DNS/TLS/tarmoq. API boshqa manzilga redirect qilinmaydi.
Bot uchun tashqi port yoki Nginx shart emas; CRM va Telegramga chiquvchi HTTPS kerak.
Botning Nginx namunasidagi statik javob jarayon sog'lomligini isbotlamaydi.

`sarget-bot.service` ni systemd ga o'rnating; papka `botuser` ga tegishli bo'lsin:

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now sarget-bot
sudo systemctl status sarget-bot
sudo journalctl -u sarget-bot -n 50 --no-pager
```

Bitta token uchun bitta polling jarayoni. Lokal botni shu token bilan parallel
ishga tushirmang (409 Conflict). Botning state bazasini ham zaxiralang.

## Yakuniy server tekshiruvi

- Login, o'quvchi yaratish/tahrirlash, guruhga biriktirish va superadmin o'chirishi.
- Telegram /start arizasi CRM Qabul sahifasida paydo bo'lishi.
- CRM kodi bilan /link, /my_info, /my_debt; xodimda /summary.
- To'lov, chek PNG saqlash va telefondan QR havolasini ochish.
- Sana oralig'i va dars oyi filtrlari, oylik hisoblari.
- Jobs ishlashi, hisobotlar, Telegram navbati, backup va tiklash.

## Avtomatik testlar

```sh
# CRM virtual muhitida; bot papkasi yonma-yon bo'lsin:
python -m pip install -r requirements-dev.txt
python manage.py test core --noinput
python manage.py makemigrations --check --dry-run
python -m pip check
# Bot virtual muhitida, bot papkasida:
python -m unittest discover -v
python -m pip check
```

HTTP contract testi botning haqiqiy HTTP klientini lokal Django test serveriga
ulaydi; Telegramga xabar yubormaydi. Mahalliy testlar production DNS, TLS,
Nginx/systemd, haqiqiy Telegram tokeni va PostgreSQL sozlamalarini tekshirmaydi.
Ular serverda yuqoridagi buyruqlar bilan alohida tekshiriladi.
