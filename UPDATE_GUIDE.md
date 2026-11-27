Joriy hisobotlar, XLSX/DOCX, import va Telegram: [foydalanish yo'riqnomasi](docs/REPORTING_GUIDE_2026-10-30.md).

# Sarget CRM — 1-bosqich yangilanish

Bu oldingi bosqichning arxiv yo'riqnomasi. Joriy tarif, Telegram ulash,
moliyaviy tarix va zaxiralash qoidalari uchun
[yangi yo'riqnomani](docs/IMPROVEMENTS_2026-10-29.md) o'qing.

## O'rnatish

1. Loyihani va `db.sqlite3` faylini zaxiralang. Eski bazani yangi ZIPdagi namuna bazasi bilan almashtirmang.
2. Python muhitiga `pip install -r requirements.txt`.
3. `python manage.py migrate`
4. `python manage.py runserver`
5. CRM menyusidagi **Qabul arizalari** bo'limini oching.
6. Bot uchun server muhitida `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`, `TELEGRAM_STAFF_CHAT_ID` qiymatlarini kiriting. Webhookni `https://api.telegram.org/bot<TOKEN>/setWebhook` orqali HTTPS manzil `https://DOMAIN/integrations/telegram/webhook/` ga sozlang; secret_token maydoni env qiymatiga teng bo'lsin.
7. Botga `Ism | +998901234567 | SMM PRO` ko'rinishida xabar yuborilganda yangi qabul arizasi yaratiladi. Hozircha bu faqat minimal webhook prototipidir, tugmali bot emas.
8. Qayta aloqa bildirishnomalari CRM ochiq turganda avtomatik tekshiriladi. Yangi ariza va to'lov eslatmalari hamda Telegram xabarlari uchun `python manage.py send_reminders` buyrug'ini har daqiqada cron/Windows Task Scheduler bilan ishga tushiring. Server ishga tushishi avtomatik scheduler ishga tushganini anglatmaydi.

## Qo'shildi

- Alohida arizalar reyestri; ism, telefon, kurs, manba va holat.
- Qo'ng'iroq vaqtini belgilash; qayta aloqa tarixi.
- Telegramdan shartli formatdagi arizani webhook orqali qabul qilish.
- Yangi arizani mavjud o'quvchilar ro'yxatiga o'tkazish (dastlab `pending`).
- Arizalarni Excel mos CSV formatida eksport qilish.
- Admin va retsepshen uchun qabul sahifasi, faqat admin o'chirishi mumkin.
- Muddati kelgan qayta aloqa, 24 soatdan oshgan yangi ariza va muddatli to'lovlar uchun CRM bildirishnomalari.
- CRM ichida qo'ng'iroq belgisi ostidagi o'qilmagan bildirishnomalar ro'yxati va yangi xabarlar uchun ekrandagi qalqib chiquvchi ogohlantirish.
- Telegram xodimlar chatiga yuborish (token/chat ID bo'lsa).
- Ruxsat tizimidagi `teacher_profile` va `receptionist_profile` bog'lanishini tuzatish.

## Keyingi bosqichda bajarilishi kerak

- To'liq tugmali Telegram bot, telefon kontaktini yuborish, kurs tanlash, `/start` kampaniya UTM/deep-link attributsiyasi.
- Har bir retsepshenga alohida Telegram bildirishnomasi; murojaat egasiga bot orqali javob va 2 tomonlama chat.
- To'lov kuni individual va shartnoma asosida sozlanishi, muddatni hisoblash, qisman to'lov qoldig'i, chek PDF/PNG, qaytarish tranzaksiyalari, audit.
- RBAC: admin tomonidan har bir xodimga alohida CRUD ruxsatlar, o'qituvchi profilini tahrirlash, xavfsiz obyekt darajasidagi tekshiruvlar.
- O'quvchi baholari, ota-onaga davomat yuborish, haqiqiy XLSX/DOCX eksport/import.
- Diagrammalar, manbalar bo'yicha konversiya va marketing xarajatlarini kiritish.
- Production DB PostgreSQL, HTTPS, monitoring, zaxira nusxa, API testlar.

## Muhim

Loyihani Django serverida avtomatik sinovdan o'tkazish ushbu muhitda imkonsiz bo'ldi (Django paketi mavjud emas, internetdan o'rnatib bo'lmadi). Python sintaksisi tekshirildi, ammo migratsiya va to'liq integratsion testlar serverda bajarilishi shart.

## Yangilanish — dars jadvali, guruh formasi va mobil ro'yxat

- **To'qnashuvlar ishonchli hisoblanadi.** Oldin `1-2-3-4-5` va `1-3-5` kabi kun kombinatsiyalari solishtirilmasdi, xona nomidagi katta/kichik harf farqi hisobga olinmasdi va har bir juft guruh tekshirilardi. Endi umumiy `core/utils.find_group_conflicts` ishlaydi: kunlar kodlari bo'yicha kesishma, vaqt oralig'i, xona nomi (bo'sh joy va registrga befarq) va o'qituvchi tekshiriladi. Solishtirish xona/o'qituvchi bo'yicha guruhlangan, shuning uchun guruhlar ko'payganda ham tez ishlaydi.
- **Filtrlangan jadval ham to'qnashuvni ko'rsatadi.** Kun/xona/o'qituvchi filtri qo'llanganda ko'rsatilgan kartochka filtrdan tashqaridagi guruh bilan to'qnashsa ham qizil hosiya va izoh chiqadi. "Jami to'qnashuv" endi ekranda ko'ringan guruhlar soni.
- **Guruh formasi ogohlantiradi.** Saqlashdan oldin xona/o'qituvchi to'qnashuvi tekshiriladi. To'qnashuv saqlashga to'sqinlik qilmaydi (jadvalni keyin tuzatish mumkin), lekin forma sahifasida sariq ogohlantirish va ro'yxatga qaytgach xabar chiqadi; jadvalda guruh qizil belgilanadi.
- **Ma'lumot izchilligi.** Guruhlar ro'yxatida kunlar avval xom kod (`1-3-5`) emas, o'qiladigan ko'rinishda (`Du / Chor / Ju`) chiqadi. `max_students` 500 dan oshsa forma xato beradi (HTML chegarasi ham moslashtirildi).
- **Mobil ro'yxat.** 1100 px dan tor ekranda O'quvchilar jadvali ustun-ustun kartochkalarga aylanadi (`data-label` sarlavhalar bilan), sahifa gorizontal siljimaydi. Bu A25 audit kamchiligining bir qismini yopadi.
- **Avtomatik testlar.** `python manage.py test core` — 89 test (jadval to'qnashuvi, forma ogohlantirishi, mobil qatorlar, baholash havolasi, bot API fixture'i). Eski `test_bot_api.py` fixture'i joriy model bilan moslashtirildi.
