# Project QA Report

Sana: 2026-11-21, Asia/Tashkent. Loyiha: Sarget CRM va alohida botning CRM bilan HTTP integratsiyasi.

337 ta test metodi PASS, 0 ta FAIL, 0 ta skipped. Ularga kiruvchi 401 ta qo‘shimcha parametrli holat ham PASS. Auditda takrorlangan 9 ta funksional xato tuzatildi. Sinovlar yangi PostgreSQL test bazalarida bajarildi. Ishlayotgan serverning production bazasida test tranzaksiyalari bajarilmadi.

Bu natija bajarilgan ssenariylarga tegishli: barcha mumkin bo‘lgan qiymatlar, barcha brauzerlar yoki real server infratuzilmasi to‘liq sertifikatlangan degani emas. PostgreSQL backup/restore va production tekshiruvlari quyida alohida ko‘rsatilgan.

## Natijalar va dalillar

| Ko‘rsatkich | Natija |
|---|---:|
| Yakuniy test metodlari | 337 |
| PASS | 337 |
| FAIL | 0 |
| Skipped | 0 |
| Parametrli qo‘shimcha holatlar | 401 PASS, 0 FAIL |
| Qayd etilgan HTTP so‘rovlari | 1 091 |
| HTTP orqali kamida bir marta tekshirilgan nomlangan CRM yo‘llari | 131 / 131 |
| Inventarizatsiya qilingan modellar | 36 |
| Inventarizatsiya qilingan HTML shablonlar | 82 |
| Takrorlangan va tuzatilgan mahsulot xatolari | 9 |

336 ta test to‘liq regression ishga tushirilishida, qo‘shimcha haqiqiy Chromium moliyaviy testi esa alohida yangi PostgreSQL bazasida bajarildi. Parametrli holatlar 337 ta testga qo‘shib sanalmagan. Yo‘lga so‘rov yuborilishi uning barcha rol va maydon kombinatsiyalari sinovdan o‘tganini anglatmaydi.

- [Barcha testlarning kutilgan assert nazoratlari va real statuslari](../artifacts/qa/final-test-matrix.csv).
- [Yakuniy natijalar va har bir test manbasi](../artifacts/qa/final-summary.json).
- [Sahifalar, API, modellar, shablonlar va kuzatilgan HTTP statuslari](PROJECT_QA_INVENTORY_2026-11-21.md).
- [To‘liq regression jurnali](../artifacts/qa/20261121-105622-a3c762de/tests.log).
- [Parametrli holatlar natijalari](../artifacts/qa/20261121-105622-a3c762de/subtests.json).
- [HTTP so‘rovlar jurnali](../artifacts/qa/20261121-105622-a3c762de/requests.json).
- [Haqiqiy brauzer testi jurnali](../artifacts/qa/20261121-105806-73e2096d/tests.log).
- [Brauzerdagi moliyaviy dashboard tasviri](../artifacts/qa/20261121-105806-73e2096d/receipts/financial-live-dashboard.png).

## Arxitektura

Django 6.1.3 ilovasi serverda HTML chiqaradi; asosiy ilova `core`. Alohida DRF serializer qatlami yo‘q: bot API JSON javoblarini Django view funksiyalari orqali beradi. Brauzerda JavaScript, Select2, Chart.js va responsiv CSS ishlatiladi.

`sargetcrm/settings.py` bazani `.env` dagi `DB_ENGINE`, `DB_HOST`, `DB_NAME` orqali tanlaydi. Local loyiha PostgreSQL `localhost:5432/crm_sarget_db` ga ulangan. Audit testlari bu bazaga yozilmadi; har bir ishga tushirish `test_sarget_qa_*` nomli yangi bazadan foydalandi.

Asosiy hisob yo‘li: Student va Enrollment → StudentTariff → Payment va Refund → ReceptionistCommission → Salary va ReceptionistSalary → dashboard va hisobotlar. `Payment.save()`, moliyaviy servislar va audit signallari tranzaksiyalar ichida ishlaydi. `AuditActorMiddleware` o‘zgarishni bajargan xodimni saqlaydi. `BusinessRoleMiddleware`, capability tekshiruvlari va ko‘rinadigan obyekt querysetlari kirishni cheklaydi.

`runtime.py` va management commandlar Telegram, eslatmalar va hisobot navbatini boshqaradi. Testlarda haqiqiy Telegram tokenlari va fon jarayonlari o‘chirilgan; retry, lock va scheduler xatti-harakatlari mock va test bazasi bilan tekshirildi.

## Test qilingan sahifalar va funksiyalar

| Yo‘nalish | Bajarilgan tekshiruvlar | Status va test manbasi |
|---|---|---|
| Login, profil, rollar | Login/logout, qayta login, profil nomi, rol va capability berish/bekor qilish, begona obyektlar | PASS — `tests`, `test_profiles_board`, `test_staff_permissions`, `test_reporting` |
| O‘quvchilar | Qabul, tahrirlash, status, arxiv, tiklash, olib tashlash cheklovlari, qidirish, filtr, pagination, import/export | PASS — `test_student_list`, `test_student_remove`, `test_reporting`, `tests` |
| O‘qituvchi, retsepshen, kurs, guruh | Formlar, dublikat kurs, login yaratish cheklovlari, guruhga bog‘lanish, arxiv, jadval | PASS — `tests`, `test_hardening`, `test_schedule`, `test_project_qa` |
| Qabul arizalari | Statuslar, mas’ul, claim, enrollment, qayta aloqa, board va to‘liq ro‘yxat paginationi | PASS — `test_workflow`, `test_profiles_board`, `test_schedule`, `test_telegram` |
| Davomat va baholar | Yaratish, o‘zgartirish, invalid status/ball, vakolat, dublikat cheklovi, xatoda rollback | PASS — `test_attendance_grades`, `test_hardening`, `test_project_qa` |
| To‘lovlar | To‘liq/qisman, bir necha to‘lov, qaytarim, bekor qilish, chek, tarix, idempotency, parallel so‘rov | PASS — `test_project_qa`, `test_admin_payment_delete`, moliyaviy test modullari |
| Oyliklar | O‘qituvchi ulushi, retsepshen komissiyasi va bazaviy maosh, qayta hisob, yopiq davr, parallel status | PASS — `test_payroll_periods`, `test_period_payroll`, `test_financial_reconciliation`, `test_project_qa` |
| Xarajatlar | Yaratish/o‘chirish, kategoriya/sana, noto‘g‘ri summa, admin orqali manfiy summa, foydaga ta’sir | PASS — `test_hardening`, `test_partial_payment_finance`, `test_project_qa` |
| Hisobotlar | Kun/hafta/oy/yil filtrlari, qarz, avans, tushum, payroll, eksport va yuklab olish vakolati | PASS — `test_reporting`, `test_financial_reconciliation`, `test_partial_payment_finance` |
| Sertifikatlar va markazlar | CRUD, verifikatsiya, markaz sahifalari va ko‘rinadigan amallar | PASS — `test_certificate`, `test_centers`, `test_page_smoke` |
| Bildirishnomalar | Poll, o‘qish, qo‘ng‘iroqchani tozalash, tarix saqlanishi, rol va pagination | PASS — `test_notification_history`, `test_notification_history_browser`, `tests` |
| Admin panel | Ko‘rish/eksport, bittalab va tanlab bekor qilish, sabab, ruxsat, CSRF, PostgreSQL lock SQL | PASS — `test_admin_payment_delete`, `test_reporting`, `test_project_qa` |

82 ta shablon inventarizatsiya qilindi. Ularning har biridagi barcha tugma, modal va xato ko‘rinishining barcha kombinatsiyalariga alohida brauzer testi yozilmagan; bajarilgan brauzer qamrovi quyida keltirilgan.

## API tekshiruvlari

8 ta bot endpointi va 6 ta AJAX endpointi aniqlandi. To‘liq ro‘yxat va kuzatilgan metod/statuslar inventarda mavjud.

Botning lead yaratish, ulash, o‘quvchi ma’lumoti, xodim hisoboti, kurslar, hisob holati va lead xabari endpointlarida GET/POST/PUT/PATCH/DELETE matritsasi tekshirildi: mos metodda kalitsiz so‘rov 401, noto‘g‘ri metod 405. JSON yozuvchi endpointlarda buzilgan JSON, massiv, null, son va oddiy satr 400 bilan rad qilindi. Public health endpointi normal holatda 200 qaytardi.

Alohida botning haqiqiy HTTP klienti vaqtinchalik Django test serveriga ulanib, health, kurslar, ariza, takroriy ariza, ulanish va qarzdorlikni tekshirdi. Haqiqiy Telegramga xabar yuborilmadi.

CSRF talab qilinadigan brauzer endpointlari, API kaliti, noto‘g‘ri chat identifikatori, URL orqali kalit uzatish, ruxsatsiz rol va begona obyektlarga kirish regression testlarida tekshirildi. AJAX endpointlarning har biri uchun barcha beshta metod va barcha rol kombinatsiyalaridan iborat to‘liq ko‘paytma matritsa bajarilmadi — NOT TESTED.

Jurnaldagi 3 ta 5xx javob kutilgan ssenariylar: bahoni saqlashdagi majburiy xato va rollback (500), sozlanmagan API kaliti (503), Telegram qayta yetkazish xatosi (503). Bular tegishli test assertlari bilan tekshirilgan; yakuniy testlarda kutilmagan FAIL qolmadi.

## Moliyaviy formulalar va mustaqil nazoratlar

| Formula | Kod | Mustaqil nazorat | Natija |
|---|---|---|---|
| Chegirmali tarif | `billing.record_tariff` | 500 000 × (100 − 20) / 100 = 400 000 | PASS |
| Qarzdorlik | `accounts.account_row`, Student qarz metodlari | max(0, tarif − amaldagi sof to‘lov) | PASS |
| Sof to‘lov | `payroll.payment_net_amount` | 500 000 − 100 000 qaytarim = 400 000 | PASS |
| O‘qituvchi maoshi | `percentage_share`, `teacher_totals` | 400 000 × 40% = 160 000 | PASS |
| Retsepshen maoshi | `receptionist_total`, payroll refresh | 50 000 baza + 400 000 × 10% = 90 000 | PASS |
| Xarajat | `monthly_expense_totals` | 160 000 + 90 000 + 50 000 ijara = 300 000 | PASS |
| Sof foyda | dashboard | 400 000 − 300 000 = 100 000 | PASS |
| Pul yaxlitlash | `percentage_share` | 0.03 × 50% = 0.015 → 0.02; 123.45 × 12.5% → 15.43 | PASS |
| Qaytarimli bekor qilish | `finance.with_cancellation_amount` | 480 000 − 150 000 qaytarim = 330 000 bekor qilish; jami pul oqimi 0 | PASS |
| Oy oxiri | qarz sanalari | 31-kunli to‘lov muddati fevralda 28/29, aprelda 30 ga moslanadi | PASS |

Ichki pul formulalarida Decimal va pul ulushida ROUND_HALF_UP ishlatiladi. Chart va ayrim mavjud JSON javoblarida float ko‘rinishi saqlangan; ular balansni saqlaydigan hisob manbasi sifatida ishlatilmaydi. To‘lov maydonining mavjud limiti 12 raqam, 2 kasr xona: undan katta va kasr xonasi ortiq summalar rad etiladi.

Dashboard va umumiy hisobot `monthly_income_totals` orqali amaldagi to‘lovlardan hisoblanadi. Bekor qilingan yozuv va uning qaytarimi bu ko‘rsatkichga kirmaydi. Hisobot markazidagi pul oqimi esa collection/refund/cancellation hodisalarining o‘z sanalarini saqlaydi. Masalan, sentyabrdagi 4 720 000 noyabrda bekor qilinganda hodisalar reyestrida +4 720 000 va −4 720 000, amaldagi tushumda esa 0 bo‘ladi. Bu ikki ko‘rsatkichning davr ma’nosi turlicha.

Alohida soliq hisoblash moduli yoki soliq endpointi inventarda aniqlanmadi — NOT TESTED, ushbu loyihadagi alohida hisob funksiyasi sifatida mavjud emas.

## To‘liq moliyaviy jarayon

`test_full_financial_user_journey_preserves_data_after_relogin` haqiqiy HTTP view va test bazasi orqali quyidagi nazoratlarni bajardi:

| Bosqich | Kutilgan natija | Real natija |
|---|---|---|
| Login, 500 000 tarifli o‘quvchi | Faol seans va aniq tarif | PASS |
| 150 000 va 350 000 to‘lov | Jami 500 000, qarz 0 | PASS |
| 50 000 ijara, 50 000 bazaviy retsepshen maoshi | Alohida xarajat/oylik yozuvlari | PASS |
| Ikkinchi to‘lovdan 100 000 qaytarim | Tushum 400 000, qarz 100 000 | PASS |
| Payroll va dashboard | O‘qituvchi 160 000; retsepshen 90 000; xarajat 300 000; foyda 100 000 | PASS |
| Logout va qayta login | Tushum 400 000 saqlanadi | PASS |
| Qaytarimli ikkinchi to‘lovni bekor qilish | Faol tushum 150 000; qarz 350 000 | PASS |
| Payroll qayta hisoblanishi | O‘qituvchi 60 000; retsepshen 65 000; xarajat 175 000; foyda −25 000 | PASS |
| Tarix va yozuvlar | 1 faol to‘lov, 2 tarixiy to‘lov, 1 qaytarim saqlanadi | PASS |

Qo‘shimcha Chromium → vaqtinchalik HTTP server → PostgreSQL testi haqiqiy login formasini to‘ldirdi, Select2 orqali o‘quvchini qidirdi, 150 000 to‘lovni saqladi, chekni ochdi, dashboardni yangiladi va qayta login qildi. DBda 1 to‘lov, 60 000 o‘qituvchi ulushi va to‘g‘ri audit xodimi tasdiqlandi. Test qamrovidagi local HTTP javoblarida 4xx/5xx va JavaScript pageerror bo‘lmadi.

## Tuzatilgan xatolar

| ID va daraja | Takrorlash va oldingi natija | Sabab va tuzatish | Fayl va regression testi |
|---|---|---|---|
| QA01 High — takroriy to‘lov | Bir xil forma qayta POST: 2 ta to‘lov; bitta so‘rov kaliti bilan o‘zgargan summa ham yangi yozuv yaratardi | Yashirin UUID, DB unique cheklovi va atomic get_or_create; boshqa mazmundagi kalit qayta ishlatilishi rad etiladi | `payments.py`, `models.py`, `forms.py`, `payment_form.html`, migratsiya 0024; replay/key/conflicting/parallel retry testlari |
| QA02 High — parallel bekor qilish | 2 parallel void: ikkalasi saqlanib, 2 ta void hodisasi chiqardi | Eski Payment holati FOR UPDATE OF self bilan olinadi; ikkinchi amal bekor qilingan holatni ko‘radi | `models.py`; `test_concurrent_cancellations_create_only_one_void_event` |
| QA03 Critical — to‘langan oylikda noto‘g‘ri tushum | Yangi to‘lov bilan parallel paid status: 2 ta 100 000 to‘lov bo‘lsa ham oylik tushumi 100 000 qolardi | Unpaid qatori ham bloklanadi; payroll hisoblash/status amallari atomic va row lock bilan; status faqat is_paid ni yozadi | `models.py`, `views.py`; `test_payment_and_salary_paid_status_keep_the_same_total` |
| QA04 High — noto‘g‘ri pul aniqligi | Modelga NaN, limitdan katta yoki 0.001: istisno yoki yashirin yaxlitlash | DecimalField clean orqali finite, max_digits va decimal_places tekshiruvi; admin formiga musbat summa validatsiyasi | `models.py`; amount matrix va admin payment validation testlari |
| QA05 High — retsepshen bazaviy maoshi | 10 000 000 000, 1e1000 yoki 0.001: PostgreSQL overflow yoki yashirin yaxlitlash | Field aniqligi va diapazoni saqlashdan oldin tekshiriladi | `views.py`; `test_receptionist_salary_out_of_range_is_rejected` |
| QA06 Medium — uzun davomat izohi | 201 belgili izoh bilan POST: PostgreSQL DataError | 200 belgi chegarasi barcha qatorlar yozilishidan oldin tekshiriladi; forma xatosi va rollback | `views.py`; `test_attendance_overlong_note_is_rejected_without_partial_save` |
| QA07 Medium — bog‘langan kursni o‘chirish | Guruhga bog‘langan kurs DELETE/POST: ProtectedError va 500 | Bog‘lanish saqlanadi, tushunarli xabar bilan kurslar ro‘yxatiga qaytiladi | `views.py`; `test_protected_course_delete_returns_message_instead_of_500` |
| QA08 Medium — uzun ariza matni | 1360 px ekran, qabul jadvalidagi uzun so‘z: sahifa kengligi 2118 px | So‘z o‘ralishi va ism/kurs ustunining kenglik chegarasi; rang va dizayn almashtirilmadi | `style.css`; light/dark va 320/390/768/1360 px roster testi |
| QA09 High — admin manfiy xarajat | Admin orqali −1 xarajat saqlanib, foydani sun’iy oshirardi | Expense model clean va save tekshiruvi; asosiy CRM va admin bir xil musbat summa qoidasiga amal qiladi | `models.py`; `test_admin_cannot_create_negative_expense` |

Har bir xato avval test yoki brauzer tekshiruvida takrorlandi. Tuzatishdan keyin tegishli testlar va keyin to‘liq regression bajarildi. Yangi E2E testining tarixiy sana nazoratidagi test-harness tuzatishlari mahsulot xatolari soniga qo‘shilmagan.

## Ma’lumotlar bazasi va xavfsizlik

PASS: real PostgreSQL row locking, parallel qaytarimning to‘lov summasidan oshmasligi, bitta submission uchun bitta yozuv, moliyaviy audit, protected foreign key, attendance/grade atomikligi, ruxsatlar va CSRF. Testlar ko‘pi Django TestCase tranzaksiyalarida; haqiqiy konkurent sinovlar TransactionTestCase va alohida DB ulanishlarida bajarildi.

Test runner dastlab bazaning NAME qiymatini yangi tasodifiy test nomiga almashtiradi. Shuning uchun oddiy test ulanishi ham joriy ilova bazasiga kira olmaydi. Sinov tugagach faqat tegishli test bazasi o‘chiriladi. Test mediani vaqtinchalik papka saqlaydi; screenshot/PDF va jurnallar `artifacts` ichida qoladi.

Sinovlardan keyin, local ilova ishlashini saqlash uchun faqat `0024_payment_submission_key` additiv migratsiyasi local bazaga qo‘llandi. Oldindan HOST, baza nomi, PostgreSQL loopback manzili va migratsiya rejasi tekshirildi. Oldin/keyin sonlar o‘zgarmadi: 7 ta tarixiy to‘lov, 4 ta o‘quvchi, 0 ta qaytarim. Bu test tranzaksiyasi emas; foydalanuvchi yozuvlarini tahrirlash yoki o‘chirish bajarilmadi. Serverdagi production bazaga migratsiya qo‘llanmadi.

Model va migratsiya muvofiqligi: `makemigrations core --check --dry-run` → o‘zgarish aniqlanmadi. Django system check → 0 muammo. Local `/login/`, `/api/bot/health/` va `/static/css/style.css` migratsiyadan keyin 200 qaytardi.

## Brauzer va frontend qamrovi

PASS: Chrome’da light/dark, 320/390/768/1360 px ro‘yxatlar; ichki gorizontal scroll; uzun ism va kurslar; bildirishnoma filtri va tarix; 58/80 mm chek geometriyasi, PDF va print tugmalari; real to‘lov formasi va qayta login.

Print testi 6 ta PDF nazoratini chiqardi: normal/uzun/bekor chek × 58/80 mm. Haqiqiy termoprinterda qog‘oz chiqarish NOT TESTED. Safari, Firefox, mobil qurilma hardware va barcha modal/dropdown kombinatsiyalari NOT TESTED. Live brauzer testida jQuery/Select2 mahalliy Django distributividan berildi; tashqi CDN, font va Chart.js yetkazilishi bu testning predmeti emas.

## Qolgan ishlar va cheklovlar

| Holat | Daraja | Tekshiruv yoki risk |
|---|---|---|
| BLOCKED | High | Loyihadagi `backup_database` / `create_backup` faqat SQLite arxivini qo‘llaydi. PostgreSQL uchun pg_dump/pg_restore va izolyatsiyalangan tiklash sinovi ushbu buyruqlarda mavjud emas. Serverning tashqi backup tizimi tekshirilmadi. Production tayyorligi uchun bu alohida yopilishi kerak. |
| NOT TESTED | High | Haqiqiy serverning .env, PostgreSQL hosti, backup jadvali, TLS, Nginx/systemd va deploy holati. Ushbu audit local kod va test muhitiga tegishli. |
| NOT TESTED | Medium | Real Telegram yetkazilishi, webhook domeni va tashqi CDN uzilishlari. Ichki retry/permission/HTTP contract testlari PASS. |
| NOT TESTED | Medium | Uzoq muddatli yuklama, minglab parallel so‘rov, barcha rol × maydon × qiymat kombinatsiyalari va maxsus penetration testing. |
| NOT TESTED | Medium | Yig‘indi pul maydonlari chegarasiga yetadigan real ish hajmi va barcha yillik agregatlarning stress sinovi. Sinovlar mavjud field limitlari doirasidagi nazoratlarni qoplaydi. |

Submission idempotency yangi formadagi `submission_key` yuborilganda ishlaydi. Kalitsiz eski ichki POSTlar moslik uchun qabul qilinadi va alohida to‘lov deb qaraladi; integratsiya orqali retry yuborilsa, kalit ham yuborilishi kerak. Bir xil summa bilan ikki xil kalit ikki qonuniy to‘lov yaratishi test bilan tasdiqlangan.

## O‘zgartirilgan fayllar va qayta ishga tushirish

Ilova: `core/models.py`, `core/views.py`, `core/forms.py`, yangi `core/payments.py`, `core/migrations/0024_payment_submission_key.py`, `core/templates/core/payment_form.html`, `core/templates/core/base.html`, `core/static/css/style.css`. CSS URL versiyasi yangilandi, shunda eski brauzer keshi tuzatilgan uslublarni to‘sib qolmaydi.

Test va audit: yangi `core/test_project_qa.py`, yangi `core/test_financial_browser_qa.py`, `core/test_mobile_rosters.py`, `core/test_admin_payment_delete.py`, yangi `scripts/run_project_qa.py`, ushbu hisobot, inventar va `artifacts/qa` dalillari.

To‘liq izolyatsiyalangan PostgreSQL tekshiruvi:

```powershell
.\venv\Scripts\python.exe scripts/run_project_qa.py
```

Serverga ushbu kod joylashtirilganda odatdagi deploy jarayonida avval PostgreSQL zaxirasi tekshirilsin, so‘ng `python manage.py migrate` va servis restart bajarilsin. Serverga kod yuklash va production migratsiyasi ushbu auditda bajarilmadi.
