# 2026-11-11: mahalliy yakuniy tekshiruv

## Bot tezligi va takroriy so'rovlar bo'yicha keyingi tekshiruv

- CRM to'liq testlari: 270 ta, OK.
- Bot testlari: 17 ta, OK.
- Ayni chatdagi takroriy ulash so'rovi muvaffaqiyatni qaytaradi; boshqa chat,
  eskirgan kod va bekor qilingan binding qayta ulana olmaydi.
- Telegram update deduplikatsiyasi, diskdagi pending navbatning qayta ochilishi,
  boshqa ishchidagi sekin chatdan mustaqil javob va chat xabarlari tartibi tekshirildi.
- Bir state bazasi uchun ikkinchi polling jarayoni bloklanishi tekshirildi.
- /help endi bitta account so'rovi yuboradi; /summary javobiga role qo'shildi.
- Mahalliy CRMning amaldagi TELEGRAM_BOT_MODE qiymati disabled ekani tekshirildi.
- Bu real Telegram tarmog'idagi tezlik o'lchovi emas; serverga deploy qilinmadi.

## Oldingi umumiy tekshiruv

- CRM: `manage.py test core --noinput` - 266 test, OK.
- Alohida bot: `python -m unittest discover -v` - 11 test, OK.
- API: kurslar, ariza, takroriy ariza, ulash kodi, o'quvchi ma'lumoti,
  xodim xulosasi, account, lead-message, health va autentifikatsiya testlari.
- Real lokal HTTP: alohida botning requests klienti Django test serveriga
  health/courses/leads/account so'rovlarini yubordi; to'g'ri va noto'g'ri kalit
  tekshirildi. Telegramga xabar yuborilmadi.
- 37 asosiy sahifa uchun superadmin GET smoke tekshiruvi o'tdi.
- O'quvchini o'chirish: superadmin ruxsati, GET o'zgartirmasligi, oddiy xodimga
  rad javobi, ro'yxatdan yashirilishi, to'lov va chek saqlanishi tekshirildi.
- To'lovlar, qaytarimlar, oyliklar, sana filtrlari, QR PNG va ommaviy tekshiruv
  testlari to'liq CRM test to'plamiga kiradi.
- `makemigrations --check --dry-run`: No changes detected.
- CRM va bot `pip check`: No broken requirements found.
- `collectstatic` vaqtinchalik katalogga bajarildi; kerakli JS fayllar mavjud.
- Mahalliy SQLite zaxirasi yaratildi, 0021 migratsiyasi qo'llandi.
- SQLite `PRAGMA integrity_check`: ok.
- Production rejimdagi `check --deploy`: W004 (HSTS) ogohlantirishi;
  boshqa xato yo'q. HTTPS tayyor bo'lgach yoqish uchun SERVER_READY.md ga qarang.

Test bazalari alohida yaratilib o'chirildi. Haqiqiy o'quvchilar o'chirilmadi.

## Bu tekshiruvga kirmagan tashqi muhit

Production serverlar, DNS/TLS, Nginx va systemd bajarilishi, haqiqiy Telegram
tokeni, PostgreSQL migratsiya/backup/tiklash va telefonda QR skanerlash shu
kompyuterdagi avtomatik testlardan tasdiqlanmaydi. Serverlarga deploy qilinmadi.
Ularning yakuniy tekshiruvi uchun docs/SERVER_READY.md buyruqlari tayyor.
