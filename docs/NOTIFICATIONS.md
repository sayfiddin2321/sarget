# Bildirishnomalar tarixi

Asosiy menyu → **Bildirishnomalar**, yoki `/notifications/` sahifasini oching.
Qo'ng'iroqchadagi **Barcha bildirishnomalar** havolasi ham shu sahifaga olib keladi.

- Sanadan va sanagacha tanlab saralang. Ikkala kun ham to'liq kiradi, Toshkent vaqti ishlatiladi.
- Sanalar bo'sh bo'lsa, barcha kunlardagi tarix ko'rinadi; yozuvlar yangi sanadan eskisiga tartiblanadi.
- Holati, turi yoki sarlavha/xabar matni orqali qidiring.
- Xabarlar kunlar bo'yicha guruhlanadi. 50 tadan keyingi yozuvlar keyingi sahifalarda ko'rinadi;
  sahifa almashtirilganda tanlangan filtrlar saqlanadi.
- **O'qildi deb belgilash** yozuvni tarixdan olib tashlamaydi.
- **Tanlanganlarni o'qilgan qilish** faqat amaldagi filtrga mos yozuvlarga ta'sir qiladi.
- Qo'ng'iroqchadagi **Barchasini o'qilgan qilish** yangi xabarlar ro'yxatini tozalaydi;
  barcha xabarlar alohida tarix sahifasida saqlanadi.
- Eski clear-all/delete URLlariga murojaat ham tarixni jismonan o'chirmaydi.

Har bir foydalanuvchi o'ziga kelgan va amaldagi ruxsatlariga mos bildirishnomalarni ko'radi.
Moliyaviy xabarlar va arizalar bo'yicha mavjud ruxsat cheklovlari saqlanadi.

Yangi baza migratsiyasi kerak emas. Serverga yangilangandan keyin statik fayllarni
ham yangilang (`venv/bin/python manage.py collectstatic --noinput`) va CRM xizmatini
qayta ishga tushiring. Jonli serverga bu suhbat davomida o'rnatilmadi.

Avval eski "o'chirish" amali bilan bazadan butunlay o'chirilgan yozuvlar avtomatik
qaytmaydi. Ularni tiklash uchun o'chirishdan oldingi zaxira yoki boshqa asl manba kerak.
