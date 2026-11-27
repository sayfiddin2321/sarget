# Termal chekni chop etish

Chek sahifasida **Printer qog'ozi: 80 mm / 58 mm** ni tanlang. Tanlov shu
brauzerda eslab qolinadi; brauzer xotirasi o'chirilgan bo'lsa ham sahifadagi
tanlov ishlaydi. Standart: 80 mm. Chop etish yoki Ctrl/Cmd+P tugmasi logo,
QR rasmi va shriftlar yuklanishini kutadi. Dialog yopilgach chek sahifasi ochiq qoladi.

Chrome / Edge chop etish oynasida:

1. Kerakli termal printerni tanlang.
2. More settings → Headers and footers → **OFF**.
3. Margins → **None**.
4. Scale → **100%**, Pages per sheet → **1**.
5. Printer drayverida sahifadagi tanlov bilan bir xil 80 yoki 58 mm qog'ozni
   va uzluksiz rulon (Roll / Receipt) rejimini tanlang.

80 mm qog'ozda kontent kengligi 72 mm; 58 mm qog'ozda 48 mm. Bu odatiy termal
printerlarning yon chop etilmaydigan qismlari uchun joy qoldiradi. Chek yuqoridan
boshlanadi; sahifa marginlari nol, chek ichida yuqori/pastki bo'shliq 1 mm.
QR ikkala rejimda ham 30 mm bo'lib, mavjud oq himoya chegarasi saqlanadi.

JavaScript kontentni tanlangan chop etish kengligida o'lchab, `@page` ga
kenglik va balandlikni millimetrda beradi. Balandlikka yaxlitlash uchun 0.5 mm
qo'shiladi. `size: 80mm auto` CSS standarti bo'yicha yaroqli emas; shuning
uchun ikkala o'lcham ham hisoblanadi. Mobil ekrandagi tor ko'rinish sahifa
balandligi hisobiga ta'sir qilmaydi. JS ishlamasa, sahifa o'lchami drayverga bog'liq.

CSS sahifa marginlarini nol qiladi. Chrome bo'sh joy bo'lmasa avtomatik
header/footer chiqarmaydi, lekin sayt foydalanuvchining print dialogi va
printer drayveri sozlamalarini majburan o'zgartira olmaydi. Shu sababli
yuqoridagi OFF / None / 100% sozlamalarini birinchi marta tekshiring.
Manbalar: [Chrome print margins](https://developer.chrome.com/blog/print-margins),
[W3C page size](https://www.w3.org/TR/css-page-3/#page-size-prop).

A4 yoki qat'iy uzunlikdagi drayver formati tanlangan bo'lsa, drayver HTMLdagi
o'lchamni e'tiborsiz qoldirib ortiqcha qog'oz uzatishi mumkin. Roll / Receipt,
Feed va Cut sozlamalarini tekshiring. Printer kesgichi va chop etish boshi
orasidagi jismoniy masofa ham eng kam bo'shliqni belgilaydi. Haqiqiy printerda
bir dona sinov cheki chiqarib, matn chetlari va QRni telefon bilan tekshiring.

## O'zgartirilgan qismlar

- `core/templates/core/payment_receipt.html`: kenglik tanlovi, chop etish
  ko'rsatmasi, guruhga bog'langan kurs nomi, CSS/JS kesh versiyalari.
- `core/static/css/payment_receipt.css`: 80/58 mm kengliklar, ixcham
  joylashuv, uzun matn/summa, 58 mm QR joylashuvi, faqat chekni chiqaruvchi
  print qoidalari, nol sahifa marginlari.
- `core/static/js/payment_receipt.js`: haqiqiy chop etish kengligida
  balandlikni hisoblash, tanlovni saqlash, rasmlar yuklanishini kutish.
- `core/views.py`: chek uchun mavjud kurs aloqasini `select_related` bilan
  olish. To'lov yozuvlari, URLlar, autentifikatsiya, QR generatsiyasi va baza
  tuzilishi o'zgarmagan.

Serverga yangilangan statik fayllarni chiqarishda odatdagi
`python manage.py collectstatic --noinput` jarayonini bajaring.

## Tekshiruv

Oddiy Django tekshiruvlari:

```powershell
python manage.py check
python manage.py test core.test_period_payroll core.test_staff_permissions core.test_student_remove
```

Ixtiyoriy brauzer tekshiruvi uchun alohida development muhitida:

```powershell
python -m pip install playwright pypdf
python -m playwright install chromium
$env:RECEIPT_PRINT_ARTIFACTS = 'artifacts/receipt-print/optimized'
python manage.py test core.test_receipt_print
```

Mavjud Chrome/Chromium ishlatilsa `RECEIPT_PRINT_CHROMIUM` ga uning executable
yo'lini bering. Brauzer paketlari production uchun kerak emas; ular yo'q bo'lsa
ixtiyoriy test o'tkazib yuboriladi. Test haqiqiy to'lov bazasini o'zgartirmaydi:
Django sinov bazasida sun'iy ma'lumotlar yaratiladi va tashqi tarmoq so'rovlari
bloklanadi.

Test 240 px tor ekrandan 80/58 mm uchun oddiy, uzun ism/izohli katta summali va
bekor qilingan cheklarni chiqaradi. PDF bitta sahifa ekanini, kenglik/balandlik,
yuqori koordinata nol ekanini, matn kesilmasligini, brauzer URL/sahifa raqami
va boshqaruv elementlari yo'qligini tekshiradi. Chop etish tugmasi, Ctrl+P,
sekin yuklangan logo va tugmalar tiklanishi ham tekshiriladi.

2026-11-17 mahalliy tekshiruv: SQLite sinov bazasida 22 ta test o'tdi.
Chromiumda yuqoridagi oltita chek bir sahifadan chiqdi; barcha saqlangan PNG
rasmlardagi QRlar ZXing bilan tekshirish havolasiga qayta o'qildi. Oddiy chek
80 mm da taxminan 112 mm, 58 mm da 156 mm uzunlikda chiqdi. Sun'iy uzun izohlar
bilan sahifa balandligi mos ravishda oshdi; bo'sh ikkinchi sahifa chiqmadi.
Namuna PDF/PNGlar `artifacts/receipt-print/optimized/` ichida. Jismoniy termal
printer sinovi bu muhitda bajarilmagan.

## Brauzer dialogisiz chop etish

Qat'iy boshqariladigan rulon uzunligi va avtomatik kesish zarur bo'lsa,
ESC/POS qo'llovchi printer bilan lokal chop etish ko'prigi (masalan,
[QZ Tray raw printing](https://qz.io/docs/raw)) orqali print va cut buyruqlarini
yuborish mumkin. Bunda har kassada lokal dastur o'rnatish, ishonch/sertifikat
sozlash, aniq printer modeli, o'zbekcha harflar va QR sifatini tekshirish talab
etiladi. Hozirgi yechim mavjud Django chek oqimini saqlaydi; yangi servis yoki
printer integratsiyasi qo'shilmagan.
