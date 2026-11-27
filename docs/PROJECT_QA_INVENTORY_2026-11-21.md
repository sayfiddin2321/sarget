# Project QA Inventory

Sana: 2026-11-21, Asia/Tashkent. 131 ta nomlangan CRM yo?li, 36 ta model va 82 ta HTML shablon.

Model va shablonlar handler manbasidan olindi; yordamchi servislar orqali olinadigan bog?lanishlar uchun manba ustunini ko?ring. HTTP kuzatuvi sahifaning barcha foydalanuvchi yo?llari tekshirilganini anglatmaydi. Har bir bajarilgan testning alohida statusi `artifacts/qa/final-test-matrix.csv` da.

| Sahifa yoki API | URL | Handler va manba | Bevosita modellar | Shablon | Kuzatilgan HTTP |
|---|---|---|---|---|---|
| student_remove | students/<int:pk>/remove/ | core\views.py:1223 | GuardianBinding, ReportSubscription, Student, TelegramBinding, TelegramDelivery, TelegramLinkToken | core/student_remove.html | GET 200, GET 302, POST 302, POST 403, POST 404 |
| payment_qr | receipt/verify/<str:token>/qr.png | core\payment_verification.py:58 | Payment | Dinamik/API | GET 200, GET 404, POST 404 |
| payment_verify | receipt/verify/<str:token>/ | core\payment_verification.py:105 | Payment | core/payment_verify.html | GET 200, GET 404, POST 404 |
| period_payroll | salaries/period/ | core\period_payroll.py:156 | Servis orqali | core/period_payroll.html | GET 200, GET 302, POST 302 |
| academic_center | academic/ | core\centers.py:52 | Servis orqali | Dinamik/API | GET 200, GET 302, GET 403, POST 302 |
| staff_center | staff/ | core\centers.py:52 | Servis orqali | Dinamik/API | GET 200, GET 302, GET 403, POST 302 |
| learning_center | learning/ | core\centers.py:52 | Servis orqali | Dinamik/API | GET 200, GET 302, GET 400, GET 403, POST 302 |
| salary_center | payroll/ | core\centers.py:52 | Servis orqali | Dinamik/API | GET 200, GET 302, GET 403, POST 302 |
| financial_migration | finance/migration/ | core\financial_migration.py:83 | ImportBatch | core/financial_migration.html | GET 200, GET 302, POST 302 |
| financial_migration_template | finance/migration/template/ | core\financial_migration.py:70 | Servis orqali | Dinamik/API | GET 302, POST 302 |
| financial_migration_batch | finance/migration/<uuid:public_id>/ | core\financial_migration.py:102 | ImportBatch | core/financial_migration.html | GET 302, POST 302 |
| financial_migration_confirm | finance/migration/<uuid:public_id>/confirm/ | core\financial_migration.py:110 | ImportBatch, Payment | Dinamik/API | GET 302, POST 302 |
| staff_permissions | staff/permissions/ | core\staff_views.py:25 | StaffCapability | core/staff_permissions.html | GET 200, GET 302, POST 302 |
| profile_edit | profile/ | core\staff_views.py:66 | Receptionist, Teacher | core/profile_edit.html | GET 200, GET 302, POST 200, POST 302 |
| report_settings | report-settings/ | core\staff_views.py:142 | Branch, Campaign | core/report_settings.html | GET 200, GET 302, POST 302 |
| report_center | report-center/ | core\report_views.py:79 | Servis orqali | core/report_center.html | GET 200, GET 302, GET 400, GET 403, POST 302 |
| report_export | report-center/export/ | core\report_views.py:134 | Servis orqali | Dinamik/API | GET 302, POST 302 |
| report_jobs | report-center/files/ | core\report_views.py:150 | ReportJob | core/report_jobs.html | GET 200, GET 302, POST 302 |
| report_job_download | report-center/files/<uuid:public_id>/ | core\report_views.py:161 | ReportJob | Dinamik/API | GET 200, GET 302, GET 403, GET 404, POST 302 |
| xlsx_import | imports/xlsx/ | core\report_imports.py:311 | ImportBatch | core/xlsx_import.html | GET 302, POST 200, POST 302 |
| xlsx_import_template | imports/xlsx/template/ | core\report_imports.py:291 | Servis orqali | Dinamik/API | GET 302, POST 302 |
| xlsx_import_preview | imports/xlsx/<uuid:public_id>/ | core\report_imports.py:336 | ImportBatch | core/xlsx_import_preview.html | GET 302, POST 302 |
| xlsx_import_confirm | imports/xlsx/<uuid:public_id>/confirm/ | core\report_imports.py:343 | ImportBatch | Dinamik/API | GET 302, POST 302 |
| student_report | students/<int:pk>/report/ | core\report_views.py:106 | TelegramDelivery | core/student_report.html | GET 200, GET 302, GET 404, POST 302 |
| student_report_send | students/<int:pk>/report/send/ | core\message_views.py:30 | Servis orqali | Dinamik/API | GET 302, POST 302 |
| student_report_link | students/<int:pk>/report/link-telegram/ | core\message_views.py:44 | Servis orqali | Dinamik/API | GET 302, POST 302 |
| student_report_subscribe | students/<int:pk>/report/subscribe/ | core\message_views.py:62 | ReportSubscription | Dinamik/API | GET 302, POST 302 |
| student_telegram_message | students/<int:pk>/telegram-message/ | core\message_views.py:85 | Servis orqali | Dinamik/API | GET 302, POST 302 |
| student_restore | students/<int:pk>/restore/ | core\staff_views.py:215 | Servis orqali | Dinamik/API | GET 302, POST 302 |
| enrollment_create | students/<int:student_id>/enrollments/add/ | core\staff_views.py:192 | Enrollment | core/simple_form.html | GET 200, GET 302, POST 302 |
| enrollment_edit | students/<int:student_id>/enrollments/<int:pk>/ | core\staff_views.py:192 | Enrollment | core/simple_form.html | GET 302, POST 302 |
| refund_create | payments/<int:pk>/refund/ | core\staff_views.py:228 | Payment, Refund | core/simple_form.html | GET 302, GET 404, POST 302 |
| lead_message | qabul/<int:pk>/message/ | core\message_views.py:115 | Lead, LeadActivity, TelegramDelivery | core/lead_message.html | GET 302, POST 302 |
| lead_restore | qabul/<int:pk>/restore/ | core\leads.py:184 | Lead, LeadActivity | Dinamik/API | GET 302, POST 302 |
| telegram_link | telegram/link/ | core\operations.py:55 | GuardianBinding, Receptionist, Student, Teacher, TelegramBinding, TelegramLinkToken | core/telegram_link.html | GET 200, GET 302, POST 200, POST 302, POST 403 |
| financial_history | finance/history/ | core\operations.py:16 | FinancialAudit | core/financial_history.html | GET 200, GET 302, GET 403, POST 302 |
| system_status | system/status/ | core\operations.py:31 | OperationalRun, ReportJob, TelegramDelivery | core/system_status.html | GET 200, GET 302, POST 302 |
| api_bot_create_lead | api/bot/leads/ | core\api.py:71 | Campaign, Lead, LeadActivity | Dinamik/API | DELETE 405, GET 405, PATCH 405, POST 200, POST 201, POST 400, POST 401, PUT 405 |
| api_bot_auth_user | api/bot/auth/ | core\api.py:154 | Servis orqali | Dinamik/API | DELETE 405, GET 405, PATCH 405, POST 200, POST 400, POST 401, PUT 405 |
| api_bot_student_info | api/bot/student-info/ | core\api.py:172 | Servis orqali | Dinamik/API | DELETE 405, GET 200, GET 401, GET 403, PATCH 405, POST 405, PUT 405 |
| api_bot_staff_summary | api/bot/staff-summary/ | core\api.py:232 | Lead, Student | Dinamik/API | DELETE 405, GET 200, GET 401, GET 403, PATCH 405, POST 405, PUT 405 |
| api_bot_courses_list | api/bot/courses/ | core\api.py:300 | Course | Dinamik/API | DELETE 405, GET 200, GET 401, GET 503, PATCH 405, POST 405, PUT 405 |
| api_bot_account | api/bot/account/ | core\api_bot_extra.py:20 | Student, TelegramBinding | Dinamik/API | DELETE 405, GET 200, GET 400, GET 401, PATCH 405, POST 405, PUT 405 |
| api_bot_lead_message | api/bot/lead-message/ | core\api_bot_extra.py:52 | Lead, LeadActivity | Dinamik/API | DELETE 405, GET 405, PATCH 405, POST 200, POST 400, POST 401, PUT 405 |
| api_health_check | api/bot/health/ | core\api.py:311 | Servis orqali | Dinamik/API | GET 200, POST 405 |
| lead_list | qabul/ | core\leads.py:25 | Lead, LeadActivity | core/lead_list.html | GET 200, GET 302, POST 302 |
| lead_create | qabul/create/ | core\leads.py:74 | Branch, Lead, LeadActivity | core/lead_form.html | GET 302, POST 302 |
| lead_edit | qabul/<int:pk>/edit/ | core\leads.py:74 | Branch, Lead, LeadActivity | core/lead_form.html | GET 200, GET 302, POST 200, POST 302 |
| lead_claim | qabul/<int:pk>/claim/ | core\leads.py:57 | Lead, LeadActivity | Dinamik/API | GET 302, GET 405, POST 302, POST 403 |
| lead_status_update | qabul/<int:pk>/status/ | core\leads.py:115 | Lead, LeadActivity | Dinamik/API | GET 302, POST 302 |
| lead_enroll | qabul/<int:pk>/enroll/ | core\leads.py:157 | Lead, LeadActivity, Student | Dinamik/API | GET 302, POST 302 |
| lead_delete | qabul/<int:pk>/delete/ | core\leads.py:176 | Lead | Dinamik/API | GET 302, POST 302 |
| lead_export | qabul/export/ | core\leads.py:194 | Servis orqali | Dinamik/API | GET 200, GET 302, POST 302 |
| telegram_webhook | integrations/telegram/webhook/ | core\leads.py:207 | Servis orqali | Dinamik/API | GET 405, POST 200, POST 400, POST 403, POST 503 |
| dashboard |  | core\views.py:98 | Attendance, Group, Notification, Payment, Receptionist, Salary, Student, Teacher | core/dashboard.html | GET 200, GET 302, POST 302 |
| login | login/ | core\views.py:71 | Servis orqali | core/login.html | GET 200, POST 200, POST 302 |
| logout | logout/ | core\views.py:92 | Servis orqali | Dinamik/API | GET 302, POST 302 |
| api_students_search | api/students/search/ | core\views.py:255 | Servis orqali | Dinamik/API | GET 302, POST 302 |
| api_group_students | api/groups/<int:group_id>/students/ | core\views.py:277 | Servis orqali | Dinamik/API | GET 200, GET 302, POST 302 |
| mark_notification_read | api/notifications/<int:pk>/read/ | core\views.py:285 | Notification | Dinamik/API | GET 302, GET 405, POST 200, POST 302, POST 404 |
| notification_poll | api/notifications/poll/ | core\views.py:366 | Servis orqali | Dinamik/API | GET 200, GET 302, POST 302 |
| api_notification_clear_all | api/notifications/clear-all/ | core\views.py:317 | Servis orqali | Dinamik/API | GET 302, POST 200, POST 302 |
| api_notification_read_all | api/notifications/read-all/ | core\views.py:294 | Servis orqali | Dinamik/API | GET 302, POST 302 |
| notification_list | notifications/ | core\views.py:339 | Servis orqali | core/notification_list.html | GET 200, GET 302, POST 302 |
| notification_clear_all | notifications/clear-all/ | core\views.py:317 | Servis orqali | Dinamik/API | GET 302, POST 302 |
| notification_read_all | notifications/read-all/ | core\views.py:294 | Servis orqali | Dinamik/API | GET 302, POST 302 |
| notification_open | notifications/<int:pk>/open/ | core\views.py:356 | Notification | Dinamik/API | GET 302, GET 405, POST 302, POST 404 |
| notification_delete | notifications/<int:pk>/delete/ | core\views.py:327 | Notification | Dinamik/API | GET 302, GET 405, POST 302, POST 404 |
| global_search | search/ | core\views.py:399 | Attendance, Group, Payment, Receptionist, Student, Teacher | core/search.html | GET 200, GET 302, GET 403, POST 302 |
| student_list | students/ | core\views.py:637 | Group, Student, Teacher | core/student_list.html | GET 200, GET 302, POST 302 |
| student_create | students/create/ | core\views.py:1100 | AssignmentHistory | core/student_form.html | GET 200, GET 302, POST 302 |
| student_export | students/export/ | core\views.py:730 | Servis orqali | Dinamik/API | GET 200, GET 302, POST 302 |
| student_import | students/import/ | core\report_imports.py:311 | ImportBatch | core/xlsx_import.html | GET 302, POST 302 |
| student_import_template | students/import/template/ | core\report_imports.py:291 | Servis orqali | Dinamik/API | GET 302, POST 302 |
| student_detail | students/<int:pk>/ | core\views.py:1160 | Attendance, Grade, Payment, TelegramDelivery | core/student_detail.html | GET 200, GET 302, GET 404, POST 302 |
| student_status_update | students/<int:pk>/status/ | core\views.py:712 | Student | Dinamik/API | GET 302, POST 302 |
| student_card_print | students/<int:pk>/card/ | core\views.py:2418 | Attendance, Grade | core/student_card.html | GET 200, GET 302, POST 302 |
| student_edit | students/<int:pk>/edit/ | core\views.py:1131 | AssignmentHistory | core/student_form.html | GET 200, GET 302, POST 302 |
| student_delete | students/<int:pk>/delete/ | core\views.py:1211 | Servis orqali | core/student_confirm_delete.html | GET 302, POST 302, POST 404 |
| teacher_list | teachers/ | core\views.py:1248 | Teacher | core/teacher_list.html | GET 200, GET 302, POST 302 |
| teacher_create | teachers/create/ | core\views.py:1255 | Servis orqali | core/teacher_form.html | GET 200, GET 302, POST 302, POST 403 |
| teacher_edit | teachers/<int:pk>/edit/ | core\views.py:1266 | Teacher | core/teacher_form.html | GET 302, POST 302 |
| teacher_delete | teachers/<int:pk>/delete/ | core\views.py:1280 | Teacher | core/teacher_confirm_delete.html | GET 302, POST 302 |
| receptionist_list | receptionists/ | core\views.py:1299 | Receptionist | core/receptionist_list.html | GET 200, GET 302, POST 302 |
| receptionist_create | receptionists/create/ | core\views.py:1308 | Servis orqali | core/receptionist_form.html | GET 200, GET 302, POST 302, POST 403 |
| receptionist_edit | receptionists/<int:pk>/edit/ | core\views.py:1319 | Receptionist | core/receptionist_form.html | GET 302, POST 302 |
| receptionist_delete | receptionists/<int:pk>/delete/ | core\views.py:1333 | Receptionist | core/receptionist_confirm_delete.html | GET 302, POST 302 |
| receptionist_commissions | receptionists/<int:pk>/commissions/ | core\views.py:1426 | Receptionist, ReceptionistCommission | core/receptionist_commissions.html | GET 302, POST 302 |
| receptionist_salary_list | receptionists/salaries/ | core\views.py:1351 | ReceptionistSalary | core/receptionist_salary_list.html | GET 200, GET 302, GET 403, POST 302 |
| calculate_receptionist_salaries | receptionists/salaries/calculate/ | core\views.py:1375 | Receptionist, ReceptionistSalary | core/calculate_receptionist_salary.html | GET 200, GET 302, POST 302 |
| receptionist_salary_toggle | receptionists/salaries/<int:pk>/toggle/ | core\views.py:1413 | ReceptionistSalary | Dinamik/API | GET 405, POST 302 |
| course_list | courses/ | core\views.py:1445 | Course | core/course_list.html | GET 200, GET 302, POST 302 |
| course_create | courses/create/ | core\views.py:1453 | Servis orqali | core/course_form.html | GET 200, GET 302, POST 200, POST 302, POST 403 |
| course_edit | courses/<int:pk>/edit/ | core\views.py:1467 | Course | core/course_form.html | GET 302, POST 302 |
| course_delete | courses/<int:pk>/delete/ | core\views.py:1483 | Course | Dinamik/API | GET 302, POST 302 |
| group_list | groups/ | core\views.py:1498 | Servis orqali | core/group_list.html | GET 200, GET 302, POST 302 |
| group_create | groups/create/ | core\views.py:1506 | Servis orqali | core/group_form.html | GET 200, GET 302, GET 403, POST 302, POST 403 |
| group_edit | groups/<int:pk>/edit/ | core\views.py:1520 | Servis orqali | core/group_form.html | GET 200, GET 302, GET 404, POST 302 |
| group_delete | groups/<int:pk>/delete/ | core\views.py:1535 | Servis orqali | core/group_confirm_delete.html | GET 302, POST 302, POST 403, POST 404 |
| schedule | schedule/ | core\views.py:1559 | Group, Teacher | core/schedule.html | GET 200, GET 302, POST 302 |
| payment_list | payments/ | core\views.py:1611 | Payment, Teacher | core/payment_list.html | GET 200, GET 302, GET 403, POST 302 |
| payment_create | payments/create/ | core\views.py:1682 | Servis orqali | core/payment_form.html | GET 200, GET 302, POST 200, POST 302, POST 403 |
| payment_export | payments/export/ | core\views.py:1733 | Payment | Dinamik/API | GET 302, POST 302 |
| payment_import | payments/import/ | core\financial_migration.py:83 | ImportBatch | core/financial_migration.html | GET 200, GET 302, POST 302 |
| payment_import_template | payments/import/template/ | core\financial_migration.py:70 | Servis orqali | Dinamik/API | GET 302, POST 302 |
| payment_receipt | payments/<int:pk>/receipt/ | core\views.py:1707 | Payment | core/payment_receipt.html | GET 200, GET 302, GET 404, POST 302 |
| payment_edit | payments/<int:pk>/edit/ | core\views.py:2015 | Payment | core/payment_form.html | GET 302, GET 404, POST 302 |
| payment_delete | payments/<int:pk>/delete/ | core\views.py:2033 | Payment | core/payment_confirm_delete.html | GET 302, GET 404, POST 200, POST 302 |
| salary_list | salaries/ | core\views.py:2049 | Salary | core/salary_list.html | GET 200, GET 302, GET 403, POST 302 |
| calculate_salaries | salaries/calculate/ | core\views.py:2082 | Salary, Teacher | core/calculate_salary.html | GET 200, GET 302, POST 302 |
| update_salary_status | salaries/<int:pk>/toggle/ | core\views.py:2117 | Salary | Dinamik/API | GET 405, POST 302, POST 403 |
| attendance_list | attendance/ | core\views.py:2131 | Attendance, Group | core/attendance_list.html | GET 200, GET 302, POST 302 |
| take_attendance_select | attendance/take/select/ | core\views.py:2242 | Servis orqali | core/attendance_pick.html | GET 200, GET 302, POST 302 |
| take_attendance | attendance/take/<int:group_id>/ | core\views.py:2166 | Attendance, Grade, Group | core/attendance_form.html | GET 200, GET 302, GET 403, POST 200, POST 302, POST 403, POST 500 |
| grade_list | grades/ | core\views.py:2260 | Grade, Group | core/grade_list.html | GET 200, GET 302, GET 403, POST 302 |
| take_grades_select | grades/take/select/ | core\views.py:2309 | Servis orqali | core/grade_pick.html | GET 200, GET 302, POST 302 |
| take_grades | grades/take/<int:group_id>/ | core\views.py:2326 | Grade, Group | core/grade_form.html | GET 200, GET 302, GET 403, POST 302 |
| grade_delete | grades/<int:pk>/delete/ | core\views.py:2402 | Grade | Dinamik/API | GET 302, GET 405, POST 302, POST 403 |
| assignment_history | assignments/ | core\views.py:2442 | AssignmentHistory, Student | core/assignment_history.html | GET 200, GET 302, POST 302 |
| expense_list | expenses/ | core\views.py:2457 | Expense | core/expense_list.html | GET 200, GET 302, POST 302 |
| expense_create | expenses/create/ | core\views.py:2478 | Servis orqali | core/expense_form.html | GET 200, GET 302, POST 302, POST 403 |
| expense_delete | expenses/<int:pk>/delete/ | core\views.py:2491 | Expense | core/expense_confirm_delete.html | GET 302, POST 302 |
| reports | reports/ | core\views.py:2503 | Attendance, Receptionist, ReceptionistCommission, Student, Teacher | core/reports.html | GET 200, GET 302, POST 302 |
| certificate_list | certificates/ | core\views.py:2590 | Certificate, CertificateSetting | core/certificate_list.html | GET 200, GET 302, POST 302 |
| certificate_settings | certificates/settings/ | core\views.py:2773 | CertificateSetting | core/certificate_settings.html | GET 200, GET 302, POST 302 |
| certificate_create | certificates/create/ | core\views.py:2652 | Servis orqali | core/certificate_form.html | GET 200, GET 302, GET 403, POST 302 |
| certificate_detail | certificates/<int:pk>/ | core\views.py:2688 | CertificateSetting | core/certificate_detail.html | GET 200, GET 302, POST 302 |
| certificate_edit | certificates/<int:pk>/edit/ | core\views.py:2739 | Servis orqali | core/certificate_form.html | GET 200, GET 302, GET 403, GET 404, POST 302 |
| certificate_delete | certificates/<int:pk>/delete/ | core\views.py:2760 | Servis orqali | core/certificate_confirm_delete.html | GET 302, POST 302, POST 404 |
| certificate_verify | certificate/verify/<str:number_or_code>/ | core\views.py:2788 | Certificate, CertificateSetting | core/certificate_verify.html | GET 200, POST 200 |
| certificate_verify_short | c/<str:number_or_code>/ | core\views.py:2788 | Certificate, CertificateSetting | core/certificate_verify.html | GET 200, POST 200 |

## Modellar va bog?lanishlar

| Model | Jadval | Foreign key va birga bir bog?lanishlar | Cheklovlar |
|---|---|---|---|
| Branch | core_branch | Yo?q | [] |
| Teacher | core_teacher | user ? User | [] |
| Receptionist | core_receptionist | user ? User | [] |
| Course | core_course | Yo?q | [] |
| Group | core_group | course ? Course, branch ? Branch, teacher ? Teacher | [] |
| Student | core_student | branch ? Branch, teacher ? Teacher, group ? Group, receptionist ? Receptionist, created_by ? User | [] |
| StudentTariff | core_studenttariff | student ? Student | <UniqueConstraint: fields=('student', 'effective_month') name='unique_student_tariff_month'>; <CheckConstraint: condition=(AND: ('fee__gte', 0)) name='tariff_fee_nonnegative'> |
| AssignmentHistory | core_assignmenthistory | student ? Student, teacher ? Teacher, group ? Group, changed_by ? User | [] |
| Payment | core_payment | student ? Student, enrollment ? Enrollment, group_at_payment ? Group, branch_at_payment ? Branch, course_at_payment ? Course, teacher_at_payment ? Teacher, received_by ? User | [] |
| ReceptionistCommission | core_receptionistcommission | receptionist ? Receptionist, student ? Student, payment ? Payment | [] |
| ReceptionistSalary | core_receptionistsalary | receptionist ? Receptionist | [['receptionist', 'month']] |
| Salary | core_salary | teacher ? Teacher | [['teacher', 'month']] |
| Attendance | core_attendance | student ? Student, group ? Group, marked_by ? User | [['student', 'date', 'group']] |
| Grade | core_grade | student ? Student, group ? Group, graded_by ? User | <UniqueConstraint: fields=('student', 'group', 'date', 'grade_type') name='unique_student_grade_per_day_type'> |
| Expense | core_expense | added_by ? User | [] |
| Notification | core_notification | recipient ? User, lead ? Lead, student ? Student | [] |
| Lead | core_lead | campaign_record ? Campaign, branch ? Branch, assigned_to ? User, student ? Student | [] |
| LeadActivity | core_leadactivity | lead ? Lead, user ? User | [] |
| ReminderDispatch | core_reminderdispatch | Yo?q | [] |
| TelegramSession | core_telegramsession | Yo?q | [] |
| TelegramUpdate | core_telegramupdate | Yo?q | [] |
| TelegramLinkToken | core_telegramlinktoken | created_by ? User | [] |
| TelegramBinding | core_telegrambinding | Yo?q | <UniqueConstraint: fields=('role', 'target_id') name='unique_telegram_target'> |
| FinancialAudit | core_financialaudit | actor ? User | [] |
| OperationalRun | core_operationalrun | Yo?q | [] |
| StaffCapability | core_staffcapability | user ? User | <UniqueConstraint: fields=('user', 'code') name='unique_staff_capability'> |
| Enrollment | core_enrollment | student ? Student, group ? Group | <UniqueConstraint: fields=('student',) name='unique_primary_enrollment' condition=(AND: ('is_primary', True))>; <CheckConstraint: condition=(AND: ('monthly_fee__gte', 0)) name='enrollment_fee_nonnegative'> |
| Campaign | core_campaign | Yo?q | [] |
| Refund | core_refund | payment ? Payment, created_by ? User | <CheckConstraint: condition=(AND: ('amount__gt', 0)) name='refund_amount_positive'> |
| ReportJob | core_reportjob | owner ? User | [] |
| ImportBatch | core_importbatch | owner ? User, student ? Student | [] |
| GuardianBinding | core_guardianbinding | student ? Student | <UniqueConstraint: fields=('student', 'chat_id') name='unique_guardian_student_chat'> |
| ReportSubscription | core_reportsubscription | owner ? User, student ? Student | <UniqueConstraint: fields=('student', 'recipient') name='unique_student_report_subscription'> |
| TelegramDelivery | core_telegramdelivery | report_job ? ReportJob, student ? Student, lead ? Lead, owner ? User | [] |
| CertificateSetting | core_certificatesetting | Yo?q | [] |
| Certificate | core_certificate | student ? Student, group ? Group, created_by ? User | [] |
