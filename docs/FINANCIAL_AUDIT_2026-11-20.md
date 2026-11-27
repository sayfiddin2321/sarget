# Moliya va Telegram bot tekshiruvi — 2026-11-20

Lokal CRM va alohida bot kodi tekshirildi. Jonli crm.milliycrm.uz serverida
faqat o'qish so'rovlari bajarildi; uning moliyaviy bazasi tekshirilgani yoki
tuzatishlar serverga o'rnatilgani ushbu natijalardan kelib chiqmaydi.

## Natijalar

| Tekshiruv | Natija |
| --- | --- |
| CRMning to'liq Django testlari, PostgreSQL | 290 ta test, OK |
| Alohida botning unittest sinovlari | 20 ta test, OK |
| Django tizim tekshiruvi | Xato yo'q |
| Model va migratsiyalar mosligi | Qo'shimcha sxema o'zgarishi yo'q |
| Mahalliy bazadagi qarz, oylik va komissiyalarni qayta solishtirish | Mos; to'lov yozuvlari o'zgarmadi |
| Chrome: oddiy, uzun va bekor qilingan chek; 58/80 mm | 6 holat, bitta sahifa, gorizontal chiqib ketish yo'q |
| Jonli CRM `/api/bot/health/` | 200, OK |
| Jonli CRM `/api/bot/courses/`, bot kaliti bilan | 200, OK |
| Telegram `getMe` | 200, OK; @sarget_academy_bot |
| Telegram `getWebhookInfo` | 200, webhook yo'q, kutilayotgan yangilanish 0, webhook xatosi yo'q |
| Mahalliy CRM va bot sozlamalari | API kalitlari/tokenlari mos, CRM polling rejimi disabled |

Telegram getMe so'rovi dastlab bir marta timeout berdi; qayta tekshiruvda
muvaffaqiyatli javob qaytdi. Bu doimiy tarmoq mavjudligiga kafolat bermaydi.

## Tekshirilgan hisoblar va amallar

- 490 000 so'm tarifga 480 000 so'm to'lov: qarz 10 000, 40% o'qituvchi ulushi 192 000.
- 2 060 000 tushum, 0 qaytarim, 480 000 o'qituvchi ulushi: markazda 1 580 000 qoladi,
  retsepshen maoshi va boshqa xarajatlardan oldin.
- Bir xil sana filtri qo'llanganda to'lovlar ro'yxati va oraliq hisobot tushumi mos.
- Qisman to'lovlar, keyingi to'ldirish, oldindan va kechikkan to'lovlar tegishli oylarga kiradi.
- To'lovni tahrirlash yoki bekor qilish ochiq oyliklarni yangilaydi.
- Oylikni hisoblashni takrorlash yoki to'langanini belgilash xarajatni takror qo'shmaydi.
- Qaytarim qarzni qayta oshiradi, to'lanmagan o'qituvchi ulushi va retsepshen komissiyasini kamaytiradi.
- To'langan oylik qayta hisoblash yoki yangi qaytarim bilan yashirincha o'zgarmaydi.
- Qo'shimcha kurs to'lovi shu kurs o'qituvchisiga tegishli; kursni tuzatishda ochiq ulush ko'chadi.
- Ulushlar har bir to'lovda 0.01 aniqlikda bir xil usulda yaxlitlanadi.
- Dashboard va yillik hisobot qaytarimlar, bekor qilishlar va hisoblangan maoshlarni hisobga oladi.
- XLSX/DOCX, hisobot navbati, ruxsatlar va takroriy so'rovlar sinovlardan o'tdi.
- Alohida botning haqiqiy HTTP mijozi Django test serveriga ulandi: kod bilan hisob ulash,
  takroriy ulash so'rovi, 480 000 to'lovdan keyin 10 000 qarz va 100 000 qaytarimdan
  keyin 110 000 qarz bot API javobi hamda bot matnida mos chiqdi.

## Tuzatishlar

Qaytarimdan keyin oylik va komissiyaning ortiqcha qolishi, dashboard/yillik
tushumdan qaytarim ayrilmasligi, qo'shimcha kurs to'lovining asosiy o'qituvchiga
yozilishi va oylik bilan oraliq hisobot yaxlitlanishining farqi tuzatildi.
Fon vazifasi boshqa kod ochgan tranzaksiya ulanishini yopmasligi ta'minlandi.
Fayl yuklash testi oqimli javobni Django test mijozi tartibida to'liq o'qiydi.

0022 migratsiyasi yetishmayotgan oyliklarni yaratadi; 0023 ochiq hisoblarni
qaytarimlar bilan moslaydi. Mahalliy bazada ikkalasi qo'llangan, undan oldin
`backups/` papkasiga zaxira olingan. To'langan oyliklar saqlanadi.

## Tasdiqlash chegarasi

Bu tekshirilgan kod va sinov holatlari uchun tasdiqdir. Jonli serverdagi barcha
tarixiy yozuvlar, joriy polling jarayoni va haqiqiy foydalanuvchiga xabar/fayl
yetib borishi serverga kirishsiz tasdiqlanmadi. Haqiqiy Telegram xabarlari
yuborilmadi; yuborish navbati va javoblarni qayta ishlash testlarda tekshirildi.

Mahalliy bazada 3 ta faol to'lov o'qituvchiga biriktirilmagan; ular jonli
serverdagi yozuvlar ekanligi tasdiqlanmagan. Biriktirilmagan yoki noto'g'ri
biriktirilgan eski to'lovlar taxmin bilan taqsimlanmaydi. Tarixiy import
yozuvlari yangi oylikka qo'shilmaydi. Qo'lda xarajatga yozilgan maosh bilan
avtomatik hisoblangan maosh aynan bir to'lov bo'lsa, uni ikki marta kiritmaslik kerak.

Jonli tekshiruvni yakunlash uchun serverga kodni joylash, migratsiyalarni
bajarish, xizmatlarni qayta ishga tushirish va real to'lovlar reyestrini
oylik/qarz hisobi bilan solishtirish zarur.
