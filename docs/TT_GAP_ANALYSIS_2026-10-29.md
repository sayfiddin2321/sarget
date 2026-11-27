# Texnik topshiriq va amaldagi CRM solishtiruvi

Tekshirish sanasi: 2026-10-29. Asos: foydalanuvchi yuborgan texnik topshiriq va
uning oxiridagi rollar jadvali. Bu hujjat tekshiruv natijasi; yangi funksiyalar
ishga tushirilgani haqidagi hisobot emas.

## Tekshiruv doirasi

Ruxsatlar, URLlar, viewlar, formalar, modellar, eksport/import, shablonlar,
Telegram bot va eslatma buyruqlari tekshirildi. Mavjud **114 ta test o'tdi**.
Qo'shimcha rol ssenariylari sun'iy ma'lumotli xotira bazasida bajarildi.
Ishchi bazaga biznes yozuvi qo'shilmadi, haqiqiy Telegram xabari yuborilmadi.
Server/schedulerning amalda ishlashi, haqiqiy Telegram yetkazilishi va
brauzerdagi PNG/chop etish ushbu tekshiruvda sinovdan o'tkazilmadi.

Statuslar: **Bor** — asosiy kod yo'li mavjud; **Qisman** — talabning bir qismi
bor, ammo imkoniyat yoki rol chegarasi yetishmaydi; **Yo'q** — tegishli oqim
topilmadi. Testlarning o'tishi barcha TT talablari bajarilganini anglatmaydi.

## Rollarning hozirgi holati

| Amal | Admin | Resepshin | O'qituvchi |
| --- | --- | --- | --- |
| Dashboard | Umumiy | Qabul/ish navbati | O'z guruhlari, kunlik davomat |
| Xodim qo'shish/tahrirlash/arxivlash | Bor | Yo'q | Yo'q |
| Har xodim uchun alohida huquqlarni yoqish/o'chirish | Maxsus panel yo'q | Yo'q | Yo'q |
| Murojaatlar | Boshqaradi | Boshqaradi | Kirish yopiq |
| O'quvchilar ro'yxati | Barcha | O'ziga biriktirilgan | O'ziga biriktirilgan |
| O'quvchi qo'shish | Bor | Faqat qabul/pending | Yo'q |
| O'quvchini tahrirlash | Bor | Yopiq | O'ziniki, ayrim maydonlar yopiq |
| O'quvchini arxivlash | Bor | Yo'q | Yo'q |
| Guruh yaratish/tahrirlash/o'chirish | Bor | Yo'q | Yo'q |
| O'quvchini guruhga biriktirish | Bor | Yo'q | Yo'q |
| Guruhlarni ko'rish | To'liq | Jadval orqali, biriktirishsiz | Dashboard/jadval orqali; groups/ ro'yxati yopiq |
| Davomat ko'rish/belgilash | Barcha | Barcha guruhlarda | O'z guruhlarida |
| Baho ko'rish/qo'yish/tahrirlash | Bor | Bor; o'chirish yopiq | O'z guruhlarida |
| To'lov qabul qilish | Bor | O'z o'quvchilaridan | Yo'q |
| To'lovlar umumiy ro'yxati | Bor | Yopiq | Yopiq |
| To'lovni tahrirlash/bekor qilish | Bor; to'langan maosh davri himoyalangan | Yo'q | Yo'q |
| Markaziy hisobot sahifasi | Bor | Yopiq | Yopiq |
| O'quvchilar CSV eksport/import | Bor | O'z doirasida; import ham bor | Yopiq |
| Murojaatlar CSV eksport | Bor | Bor | Yopiq |
| To'lovlar CSV eksport/import | Bor | Yopiq | Yopiq |
| XLSX/DOCX hisobotlar | Yo'q | Yo'q | Yo'q |
| O'z profilini va rasmini mustaqil tahrirlash | Maxsus oqim yo'q | Maxsus oqim yo'q | Maxsus oqim yo'q |

Dalillar: `core/permissions.py:get_role, visible_students`;
`core/views.py:student_create, student_edit, student_delete, group_list,
payment_list, payment_export, reports, take_attendance, take_grades`;
`core/urls.py`; `core/templates/core/base.html`.

TTda resepshin uchun "barcha o'quvchilar" deyiladi, oxirgi jadvalda esa
"ruxsat etilgan ma'lumotlar" deyiladi. Joriy ro'yxat faqat o'z o'quvchilarini
ko'rsatadi. Yakuniy siyosatda umumiy ko'rish va tahrirlash doirasi alohida
belgilanishi kerak. O'qituvchining "cheklangan murojaatlar" vakolatida aniq
qaysi murojaatlar va amallar nazarda tutilgani TTda belgilanmagan.

## Yetishmayotgan va qisman bajarilgan talablar

| № | Talab | Holat | Amaldagi farq / bajariladigan ish |
| --- | --- | --- | --- |
| 1 | Faqat super adminning to'liq nazorati | Qisman | Teacher/Receptionist profilsiz `is_staff=True` hisob ham admin hisoblanadi. Bu qat'iy super-admin qoidasiga mos emas. |
| 2 | Xodim vakolatlarini alohida yoqish/o'chirish | Yo'q | Asosiy viewlar maxsus rol tekshiruvlarini ishlatadi. Django adminning standart permissionlari bu tekshiruvlarni avtomatik almashtirmaydi. |
| 3 | Resepshin o'quvchini tahrirlaydi va guruhga biriktiradi | Yo'q | Oddiy qabul formasi guruhsiz pending yaratadi; student_edit resepshinga yopiq. Importda o'quvchi/guruh yozuvi kirishi mumkinligi oddiy qabul oqimi o'rnini bosmaydi. |
| 4 | Resepshin/o'qituvchi o'z doirasida o'quvchini o'chiradi | Yo'q | Arxivlash faqat adminga ochiq. To'lov/tarixni saqlash uchun butunlay o'chirish o'rniga arxivlash qoidasi ishlatilishi kerak. |
| 5 | O'qituvchi o'z profilini va rasmini tahrirlaydi | Yo'q | Rasm maydoni bor, lekin o'z profilini tahrirlash URL/formasi yo'q; xodim formasi admin uchun. |
| 6 | O'qituvchining haftalik/oylik/yillik hisoboti | Qisman | Bugungi davomat, baholar ro'yxati, o'quvchi detali va maosh tarixi bor; yagona davr tanlanadigan o'quv hisoboti yo'q. reports faqat admin uchun. |
| 7 | Resepshinning to'lovlar va ish natijalari hisoboti | Qisman | Operatsion dashboard va ayrim o'quvchi to'lovlari bor; to'lovlar reyestri, umumiy hisobot va to'lov eksporti yopiq. |
| 8 | O'qituvchining Excel/Word import/eksporti | Yo'q | O'qituvchi student_export va student_importdan ham foydalanolmaydi. |
| 9 | Haqiqiy Excel (.xlsx) fayllar | Yo'q | Mavjud import/eksportlar CSV. CSV Excelda ochiladi, lekin XLSX format emas. |
| 10 | Word (.docx) hisobotlar | Yo'q | Word yaratish/o'qish oqimi topilmadi. |
| 11 | Davomat va baholarni eksport qilish | Yo'q | Tegishli export URL/viewlar yo'q. Ota-onaga yuborish uchun tayyor fayl ham yo'q. |
| 12 | To'lov qilgan/qisman/qilmaganlar oy va guruh bo'yicha | Qisman | Qarzdorlik summasi va to'lovlar mavjud; belgilangan oy uchun uch holatli alohida to'liq ro'yxat/filtr yo'q. |
| 13 | Alohida kelishilgan to'lov muddati | Qisman | Muddat registration_date kuni bilan olinadi; o'quvchi uchun alohida payment_due_day/sana maydoni yo'q. |
| 14 | To'lov eslatmasi aynan resepshinga | Qisman | CRMda moliyaviy eslatma faqat faol superuserlarga yaratiladi. Telegram yuborish umumiy TELEGRAM_STAFF_CHAT_IDga boradi; mas'ul resepshinning tasdiqlangan shaxsiy chatiga yo'naltirilmaydi. |
| 15 | Yangi murojaat haqida botdan darhol resepshinga xabar | Qisman | CRM bildirishnomasi darhol yaratiladi. Telegram yangi-ariza yo'li esa yaratilgan sanadan keyingi kunlik eslatmada, umumiy guruhga ishlaydi. |
| 16 | Murojaat egasiga CRMdan Telegram xabari yuborish | Yo'q | Chat ID saqlanadi, lekin yozish formasi, yuborish amali va muloqot tarixi yo'q. |
| 17 | Ota-onaga davomat/baholarni yuborish | Qisman | Telefon va ota-ona telefoni bor. Tayyor XLSX/DOCX, yuborish jurnali va avtomatik shaxsiy yuborish oqimi yo'q. |
| 18 | Marketing samaradorligi | Qisman | Lead source/campaign va holatlar mavjud; asosiy hisobot aktiv o'quvchilar source sonini hisoblaydi. Manba→murojaat→kelish→birinchi to'lov konversiya hisoboti yo'q. |
| 19 | Bot/target/Instagram manbasining asosiy ro'yxatda saqlanishi | Qisman | Original Lead saqlanadi; lead_enrollda bu manbalar Student.source='social'ga birlashadi. referral ham bu kod yo'lida walk_in bo'lib qoladi. |
| 20 | Murojaatlarning kunlik/haftalik/oylik/yillik tahlili | Qisman | Sana saqlanadi, holat sonlari va CSV bor; filtered_leadsda davr/yil/hafta kesimi yo'q. |
| 21 | Barcha qarzdorlar bo'yicha aniq umumiy statistika | Qisman | reports context qarzdorlarni eng yuqori 25 taga kesadi; shablondagi "qarzdorlar soni" shu kesilgan ro'yxat uzunligi. 25 tadan ko'p qarzdorda jami son noto'g'ri ko'rinadi. |
| 22 | Telefon qilish | Bor, cheklangan | tel: havolasi bor. Bu qurilmaning telefon ilovasini ochadi; CRM ichidagi telefoniya integratsiyasi emas. |
| 23 | Chek ko'rish, chop etish, PNG yuklash | Bor | Kod va tugmalar mavjud; bevosita Telegram/telefon share amali yo'q. Yuklangan PNGni qo'lda yuborish mumkin. |
| 24 | Davomat sanalarining tarixi | Bor, cheklangan | Bazada saqlanadi, kun bo'yicha ko'riladi. Student detailda oxirgi 30 yozuv; haftalik/oylik/yillik tahlil va eksport alohida kerak. Davomat belgilash hozir joriy kun uchun. |

Dalillar: `core/models.py:Student, Lead, Payment`;
`core/views.py:student_list, student_edit, payment_list, payment_export,
attendance_list, take_attendance, grade_list, reports`;
`core/leads.py:lead_enroll, lead_export`;
`core/admissions.py:filtered_leads`;
`core/management/commands/send_reminders.py:send_telegram, dispatch_reminders`;
`core/telegram_bot.py:registration_reply`;
`core/templates/core/payment_receipt.html`; `requirements.txt`.

## Mavjud va TTga asosan mos qismlar

- Uchta rol, alohida dashboardlar va login; faol roli yo'q hisoblar yopiladi.
- Admin xodimlar, guruhlar, kurslar va o'quvchilarni boshqaradi.
- O'qituvchi o'z o'quvchilari, guruh jadvali, davomat va baholar bilan ishlaydi.
- Qabul holatlari: Yangi, Bog'landik, Qayta qo'ng'iroq, Keladi, Keldi,
  O'qishga yozildi, Qiziqmadi, Adashib tushgan. Aloqa izohi va tarixi saqlanadi.
- Telegram arizasi ism/familiya, kurs, telefon, vaqt va kampaniya bilan saqlanadi.
- Qabuldan pending o'quvchiga o'tkazish bor; guruhga biriktirish admin oqimida.
- Callback 10 daqiqa oldin boshlanadi, holat callback bo'lib tursa kuniga bir
  marta takrorlanadi. Bir kunda boshqa vaqtga ko'chirish alohida eslatma oladi.
- Bog'lanilmagan yangi murojaat keyingi kundan kuniga bir marta eslatiladi;
  holati newdan o'zgarsa yangi eslatma to'xtaydi.
- Qarzdorlikda qisman to'lov hisoblanadi. Qarz to'liq yopilsa yangi qarz
  eslatmasi yaratilmaydi. Eski bildirishnomani o'qilgan deb belgilash alohida amal.
- Naqd/karta/bank/o'tkazma to'lovlar, saqlanadigan chek, tezkor qidiruv,
  admin grafiklari, tarif tarixi, moliyaviy audit va ZIP zaxira mavjud.

Bu eslatmalar ishlab turishi uchun send_reminders har daqiqada scheduler
orqali bajarilishi shart. Kod mavjudligi haqiqiy serverdagi scheduler yoki
Telegram konfiguratsiyasi ishlayotganini tasdiqlamaydi.

## Alohida tasdiqlangan ruxsat nomuvofiqliklari

Sun'iy bazada quyidagilar qayta tasdiqlandi:

1. Resepshin ro'yxatda faqat o'z o'quvchisini ko'radi, ammo boshqa resepshinga
   tegishli/mas'ulsiz o'quvchi detailini ID orqali ochishi mumkin (200).
2. Resepshin boshqa o'quvchining statusini student_status_update orqali
   o'zgartira oldi. Ro'yxat va yozish doirasi bir xil emas.
3. Resepshin boshqa o'quvchiga take_grades orqali baho qo'ya oldi. Bu oxirgi
   matritsadagi "odatda yo'q" siyosatiga zid; aniq alohida ruxsat bilan yopilishi kerak.
4. Superuser bo'lmagan, faqat is_staff=True hisob lead_delete orqali
   murojaatni butunlay o'chira oldi. "Faqat super admin" talabi bajarilmagan.
5. O'qituvchining o'z o'quvchisini tahrirlashi ishlaydi; student_export va
   student_import esa 403 qaytaradi. O'quvchini arxivlash ham unga yopiq.

Bu tekshiruvdan so'ng dasturdagi ruxsatlar o'zgartirilmadi. TTga mos to'g'ri
siyosat tuzilgach list/detail/search/API/export/POST yo'llariga bir xil tatbiq
qilinishi kerak. Barcha o'quvchini ko'rish ruxsati barcha o'quvchini tahrirlash
ruxsati bilan avtomatik tenglashtirilmasin.

## Amalga oshirish tartibi

1. **Ruxsatlar:** strict super admin, ko'rish/yozish doiralari, resepshinning
   guruhga biriktirishi/tahrirlashi, o'qituvchining vakolatlari; baho/davomat
   resepshin uchun alohida yoqiladigan huquq.
2. **Kassa va muddatlar:** resepshin uchun ruxsatli to'lov reyestri,
   oy/guruh bo'yicha paid/partial/unpaid, kelishilgan to'lov kuni,
   mas'ul resepshinga CRM va shaxsiy Telegram eslatmasi.
3. **Hisobotlar:** rollarga mos sana oralig'i, kun/hafta/oy/yil kesimi,
   XLSX/DOCX eksportlar va o'qituvchi uchun nazoratli import.
4. **Muloqot:** yangi arizani darhol Telegramga yetkazish, murojaat egasiga
   CRMdan javob, muloqot jurnali; ota-ona uchun yuboriladigan hisobot.
5. **Marketing va qulaylik:** manbalarni o'quvchiga o'tishda yo'qotmaslik,
   konversiya tahlili, o'z profilini tahrirlash va chekni ulashish.

TTda "Super admin barcha amallarni qila oladi" deyilgan bo'lsa ham moliyaviy
to'lovni izsiz o'chirish tavsiya etilmaydi. Mavjud sababli bekor qilish va
o'quvchini arxivlash tartibini TTning qabul mezonlariga kiritish kerak.
