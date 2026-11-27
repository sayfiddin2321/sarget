# CRM va Telegram botni birga ishga tushirish

## Lokal kompyuter: bitta buyruq

Mavjud `.env` faylini almashtirmang. Unda `TELEGRAM_BOT_TOKEN` berilgan bo‘lsa,
quyidagi sozlamalar bilan CRM va bot birga boshlanadi:

```dotenv
DJANGO_DEBUG=True
TELEGRAM_BOT_MODE=auto
CRM_BACKGROUND_JOBS=True
```

```powershell
.\venv\Scripts\python.exe manage.py runserver
```

Bot Telegramdan xabarlarni polling orqali oladi. Kod yangilanib Django qayta
yuklanganda workerlar faqat xizmat qilayotgan jarayonda boshlanadi. `--noreload`
ham ishlaydi. Bot uchun ikkinchi terminal ochish kerak emas.

Eslatmalar, Telegramga yuborish navbati, katta hisobotlar va oylik hisobot
obunalari ham shu buyruq bilan bajariladi. CRM eslatmalari har daqiqada,
hisobot/xabar navbati har 2 soniyada tekshiriladi.

Faqat CRM kerak bo‘lsa:

```powershell
.\venv\Scripts\python.exe manage.py runserver --without-bot --without-jobs
```

`--without-bot` faqat kiruvchi pollingni o‘chiradi; `--without-jobs` eslatma,
hisobot va chiquvchi Telegram navbatini o‘chiradi. `CRM_BACKGROUND_JOBS=False`
shu server buyruqlarida fon vazifalarini doimiy o‘chirish uchun ishlatiladi.
Token bo‘lmasa CRM va hisobot workeri ishlaydi, Telegram navbati yuborishga
urinilmaydi. `check`, `migrate`, `test` va WSGI importi worker boshlamaydi.

## Production: bitta xizmat, bitta buyruq

`runserver` internet serveri uchun ishlatilmaydi. `serve` Waitress WSGI serveri
bilan CRMni, bot rejimini va fon vazifalarini birga boshqaradi. Linux va
Windows qo‘llab-quvvatlanadi. Standart host `127.0.0.1`, port `8000`;
internetdan HTTPS reverse proxy orqali ochiladi.

### Tavsiya: webhook

Serverdagi `.env`ga o‘zingizning qiymatlaringizni kiriting:

```dotenv
DJANGO_DEBUG=False
DJANGO_SECRET_KEY=<kuchli-tasodifiy-maxfiy-qiymat>
DJANGO_ALLOWED_HOSTS=crm.example.com
DJANGO_SECURE_SSL_REDIRECT=True
TELEGRAM_BOT_TOKEN=<BotFather-tokeni>
TELEGRAM_BOT_MODE=auto
TELEGRAM_PUBLIC_URL=https://crm.example.com
TELEGRAM_WEBHOOK_SECRET=<tasodifiy-A-Z-a-z-0-9-pastki-chiziq-va-tire>
CRM_BACKGROUND_JOBS=True
```

`TELEGRAM_PUBLIC_URL` faqat domenni o‘z ichiga olsin, `/path`, login/parol,
query yoki fragment bo‘lmasin. Secret 1–256 ta `A-Z`, `a-z`, `0-9`, `_`, `-`
belgilaridan tuziladi. Token va secretni Gitga qo‘shmang.

Bir martalik tayyorlash (mavjud bazani saqlab):

```bash
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py check --deploy
```

Doimiy ishga tushirish:

```bash
python manage.py serve
```

`serve` boshida webhook Telegramga ulanadi. Bot xabarlari CRMning o‘zidagi
`/integrations/telegram/webhook/` manziliga keladi. Alohida polling jarayoni
kerak emas. Mavjud kutilayotgan Telegram xabarlari o‘chirib tashlanmaydi.
Noto‘g‘ri mahalliy webhook sozlamasi yoki tugallanmagan migratsiya bilan
xizmat boshlanmaydi; konsoldagi aniq xatoni tuzatib, qayta boshlang.
Telegram tarmog‘i vaqtincha ishlamasa, CRM ochiq qoladi; webhook ulanishi
fonda qayta uriniladi. Konsolda “Telegram webhook ulandi” chiqishini tekshiring.

HTTPS va static/media uchun `deploy/nginx.conf.example` namunasi bor.
Domen, sertifikatlar va papka yo‘llarini serveringizga moslang. TLS sertifikati
oldindan tayyor bo‘lishi kerak. Nginx `X-Forwarded-Proto` qiymatini o‘zi
yozadi; Waitress faqat `127.0.0.1` proxydan kelgan sarlavhaga ishonadi.
Boshqa proxy IP ishlatilsa `serve --trusted-proxy ANIQ-IP` kiriting va
8000-portga tashqi kirishni yoping. `*` ishlatilmaydi.

Linuxda doim ishlashi va server qayta yoqilganda avtomatik boshlanishi uchun
`deploy/sargetcrm.service` namunasi berilgan. `User`, `Group`,
`WorkingDirectory`, `ExecStart` qiymatlarini haqiqiy serverga moslang;
xizmat foydalanuvchisiga baza, `media/` va `private/` uchun yozish huquqi
kerak. Static/media fayllarini Nginx o‘qiy olishi ham kerak.
Linuxda `.env` faqat xizmat foydalanuvchisiga o‘qiladigan bo‘lsin
(`chmod 600 .env`); `private/` va `backups/` kataloglarini ham faqat xizmat
foydalanuvchisiga oching. Bu kataloglar Nginx orqali tarqatilmaydi.

Moslangan fayl `/etc/systemd/system/sargetcrm.service`ga o‘rnatilgach:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now sargetcrm
sudo systemctl status sargetcrm
sudo journalctl -u sargetcrm -f
```

Nginx moslangach `sudo nginx -t` bilan tekshiring va uni qayta yuklang.
`Restart=on-failure` to‘xtab qolgan xizmatni qayta boshlaydi.
Yangilashda avval odatdagi zaxira nusxasini oling; kerakli migratsiya va
`collectstatic`dan keyin `sudo systemctl restart sargetcrm` ishlating.

### HTTPS webhook ishlatib bo‘lmasa

```dotenv
TELEGRAM_BOT_MODE=polling
```

`python manage.py serve` CRM, polling bot va navbatni bir jarayonda boshlaydi.
Bu rejimda bitta bot tokeniga faqat bitta polling nusxasi ishlashi kerak.
Loyiha ichidagi fayl locki ikkinchi polling va fon worker nusxasini
boshlatmaydi. Boshqa server/checkoutdagi xuddi shu token uchun lock umumiy
emas; ulardagi pollingni alohida to‘xtating. Shu sabab productionda webhook
afzal. CRM uchun tashqi HTTPS talabi bu rejimda ham saqlanadi.

Avval webhook ulangan bo‘lsa, polling uni avtomatik o‘chirmaydi: shu botning
production ulanishini tasodifan uzib qo‘ymaslik uchun xato beradi. Rejimni
ongli ravishda almashtirganda Telegram webhookini alohida o‘chiring;
`drop_pending_updates` bilan kutilayotgan xabarlarni yo‘qotmang. Lokal va
production uchun alohida bot tokenlaridan foydalanish qulay.

## Muhim ish tartibi

- `serve` bilan ishlaganda eski `run_telegram_bot`, `process_crm_jobs --loop`
  va `send_reminders` schedulerlarini parallel boshlamang. Fon vazifalari
  shu xizmatga ko‘chadi. Alohida tashqi worker kerak bo‘lsa
  `CRM_BACKGROUND_JOBS=False` ishlating.
- Vaqtinchalik tarmoq yoki worker xatosida avtomatik qayta urinish bor.
  Javobi yuborilmagan bot yangilanishi tasdiqlanmaydi; suhbat va arizalar
  bazadagi mavjud takrorlardan himoya bilan qayta ishlanadi.
- `private/runtime/*.lock` tokenlarni saqlamaydi. Jarayon tugashi bilan
  operatsion tizim lockni bo‘shatadi; lock faylini qo‘lda o‘chirmang.
- Backup avvalgidek alohida rejalashtiriladi. Bu buyruq ma’lumotlar bazasini
  almashtirmaydi va backup jadvalini o‘zgartirmaydi.
- Tashqi botning haqiqiy ishlashini server o‘rnatilgach `/start`, CRMdan
  Telegram xabar yuborish va **Tizim holati** orqali tekshiring. Domen,
  HTTPS, token va server tarmog‘i to‘g‘ri bo‘lishi zarur.

Manbalar: [Django deployment](https://docs.djangoproject.com/en/stable/howto/deployment/),
[Telegram Bot API](https://core.telegram.org/bots/api),
[Waitress reverse proxy](https://docs.pylonsproject.org/projects/waitress/en/stable/reverse-proxy.html).
