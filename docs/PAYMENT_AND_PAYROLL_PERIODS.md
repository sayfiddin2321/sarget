# To'lov va oylik davrlari

To'lovda dars oyi va pul tushgan sana alohida saqlanadi. Dars davri tanlangan oyning birinchi kunidan oxirgi kunigacha. Bir necha oy uchun olingan summani har bir oyga tegishli qismga ajratib, alohida to'lov sifatida kiriting.

Oylik hisob oyi — dars oyi va pul tushgan oyning keyingisi:

| Dars oyi | Pul tushgan sana | Oylikka kiradi |
| --- | --- | --- |
| 2026-noyabr | 2026-10-25 | 2026-noyabr |
| 2026-sentyabr | 2026-10-25 | 2026-oktabr |
| 2026-oktabr | 2026-10-25 | 2026-oktabr |

Bu qoida o'qituvchi ulushi va retsepshen komissiyasiga bir xil qo'llanadi. Retsepshenning asosiy maoshi hisob oyida bir marta qo'shiladi. Qisman to'lovlar alohida hisoblanadi: sentyabr uchun sentyabrda 200 ming, oktabrda 400 ming olinsa, ulushlar tegishlicha sentyabr va oktabrga kiradi.

Kassa tushumi va tushum diagrammalari pul haqiqatda tushgan sana bo'yicha yuradi. O'quvchi qarzi esa to'lovning dars oyi bo'yicha qoplanadi. O'qituvchi va retsepshenning to'lovda saqlangan foizi keyingi foiz o'zgarishlarida saqlanadi.

To'lov qo'shilsa, tahrirlansa yoki bekor qilinsa, avval hisoblangan, hali to'lanmagan tegishli oyliklar avtomatik yangilanadi. To'langan davrga yangi to'lov kiritish yoki moliyaviy ma'lumotni o'zgartirish uchun vakolatli xodim avval oylikni to'lanmagan holatga qaytarishi kerak. Izohni o'zgartirish davrni ochishni talab qilmaydi.

## Yangilash

Avval zaxira oling, so'ng `python manage.py migrate` buyrug'ini bajaring. `0020_payment_salary_months` migratsiyasi mavjud to'lovlar uchun hisob oylarini to'ldiradi va hisoblangan, hali to'lanmagan oyliklarni yangilaydi. Eski qoida asosida to'langan oyliklar va ularga tegishli to'lovlarning hisob oylari saqlanadi; bu summalar yangi oyga ikkinchi marta kiritilmaydi. Shu sabab eski to'lovda o'qituvchi va retsepshen hisob oylari turlicha ko'rinishi mumkin.
