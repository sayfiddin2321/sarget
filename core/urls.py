from django.urls import path
from . import views, leads, api, operations, staff_views, report_views, report_imports, message_views
from . import financial_migration, centers, api_bot_extra
from . import payment_verification, period_payroll

urlpatterns = [
    path('students/<int:pk>/remove/', views.student_remove, name='student_remove'),
    path('receipt/verify/<str:token>/qr.png', payment_verification.payment_qr, name='payment_qr'),
    path('receipt/verify/<str:token>/', payment_verification.payment_verify, name='payment_verify'),
    path('salaries/period/', period_payroll.period_payroll, name='period_payroll'),
    path('academic/', centers.center_view, {'center': 'academic_center'}, name='academic_center'),
    path('staff/', centers.center_view, {'center': 'staff_center'}, name='staff_center'),
    path('learning/', centers.center_view, {'center': 'learning_center'}, name='learning_center'),
    path('payroll/', centers.center_view, {'center': 'salary_center'}, name='salary_center'),
    path('finance/migration/', financial_migration.migration_preview, name='financial_migration'),
    path('finance/migration/template/', financial_migration.migration_template, name='financial_migration_template'),
    path('finance/migration/<uuid:public_id>/', financial_migration.migration_batch, name='financial_migration_batch'),
    path('finance/migration/<uuid:public_id>/confirm/', financial_migration.migration_confirm, name='financial_migration_confirm'),
    path('staff/permissions/', staff_views.staff_permissions, name='staff_permissions'),
    path('profile/', staff_views.profile_edit, name='profile_edit'),
    path('report-settings/', staff_views.report_settings, name='report_settings'),
    path('report-center/', report_views.report_center, name='report_center'),
    path('report-center/export/', report_views.report_export, name='report_export'),
    path('report-center/files/', report_views.report_jobs, name='report_jobs'),
    path('report-center/files/<uuid:public_id>/', report_views.report_job_download, name='report_job_download'),
    path('imports/xlsx/', report_imports.xlsx_import, name='xlsx_import'),
    path('imports/xlsx/template/', report_imports.import_template, name='xlsx_import_template'),
    path('imports/xlsx/<uuid:public_id>/', report_imports.xlsx_import_preview, name='xlsx_import_preview'),
    path('imports/xlsx/<uuid:public_id>/confirm/', report_imports.xlsx_import_confirm, name='xlsx_import_confirm'),
    path('students/<int:pk>/report/', report_views.student_report, name='student_report'),
    path('students/<int:pk>/report/send/', message_views.student_report_send, name='student_report_send'),
    path('students/<int:pk>/report/link-telegram/', message_views.student_report_link, name='student_report_link'),
    path('students/<int:pk>/report/subscribe/', message_views.student_report_subscribe, name='student_report_subscribe'),
    path('students/<int:pk>/telegram-message/', message_views.student_telegram_message, name='student_telegram_message'),
    path('students/<int:pk>/restore/', staff_views.student_restore, name='student_restore'),
    path('students/<int:student_id>/enrollments/add/', staff_views.enrollment_edit, name='enrollment_create'),
    path('students/<int:student_id>/enrollments/<int:pk>/', staff_views.enrollment_edit, name='enrollment_edit'),
    path('payments/<int:pk>/refund/', staff_views.refund_create, name='refund_create'),
    path('qabul/<int:pk>/message/', message_views.lead_message, name='lead_message'),
    path('qabul/<int:pk>/restore/', leads.lead_restore, name='lead_restore'),
    path('telegram/link/', operations.telegram_link, name='telegram_link'),
    path('finance/history/', operations.financial_history, name='financial_history'),
    path('system/status/', operations.system_status, name='system_status'),
    # Bot REST API (X-CRM-API-Key himoyalangan)
    path('api/bot/leads/', api.api_bot_create_lead, name='api_bot_create_lead'),
    path('api/bot/auth/', api.api_bot_auth_user, name='api_bot_auth_user'),
    path('api/bot/student-info/', api.api_bot_student_info, name='api_bot_student_info'),
    path('api/bot/staff-summary/', api.api_bot_staff_summary, name='api_bot_staff_summary'),
    path('api/bot/courses/', api.api_bot_courses_list, name='api_bot_courses_list'),
    path('api/bot/account/', api_bot_extra.api_bot_account, name='api_bot_account'),
    path('api/bot/lead-message/', api_bot_extra.api_bot_lead_message, name='api_bot_lead_message'),
    path('api/bot/health/', api.api_health_check, name='api_health_check'),  # Public health check

    path('qabul/', leads.lead_list, name='lead_list'),
    path('qabul/create/', leads.lead_edit, name='lead_create'),
    path('qabul/<int:pk>/edit/', leads.lead_edit, name='lead_edit'),
    path('qabul/<int:pk>/claim/', leads.lead_claim, name='lead_claim'),
    path('qabul/<int:pk>/status/', leads.lead_status_update, name='lead_status_update'),
    path('qabul/<int:pk>/enroll/', leads.lead_enroll, name='lead_enroll'),
    path('qabul/<int:pk>/delete/', leads.lead_delete, name='lead_delete'),
    path('qabul/export/', leads.lead_export, name='lead_export'),
    path('integrations/telegram/webhook/', leads.telegram_webhook, name='telegram_webhook'),
    # Auth
    path('', views.dashboard, name='dashboard'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    # AJAX API
    path('api/students/search/', views.api_students_search, name='api_students_search'),
    path('api/groups/<int:group_id>/students/', views.api_group_students, name='api_group_students'),
    path('api/notifications/<int:pk>/read/', views.mark_notification_read, name='mark_notification_read'),
    path('api/notifications/poll/', views.poll_notifications, name='notification_poll'),
    path('api/notifications/clear-all/', views.clear_all_notifications, name='api_notification_clear_all'),
    path('api/notifications/read-all/', views.mark_all_notifications_read, name='api_notification_read_all'),
    path('notifications/', views.notification_list, name='notification_list'),
    path('notifications/clear-all/', views.clear_all_notifications, name='notification_clear_all'),
    path('notifications/read-all/', views.mark_all_notifications_read, name='notification_read_all'),
    path('notifications/<int:pk>/open/', views.notification_open, name='notification_open'),
    path('notifications/<int:pk>/delete/', views.notification_delete, name='notification_delete'),

    # Search
    path('search/', views.global_search, name='global_search'),

    # Students
    path('students/', views.student_list, name='student_list'),
    path('students/create/', views.student_create, name='student_create'),
    path('students/export/', views.student_export, name='student_export'),
    path('students/import/', report_imports.xlsx_import, name='student_import'),
    path('students/import/template/', report_imports.import_template, name='student_import_template'),
    path('students/<int:pk>/', views.student_detail, name='student_detail'),
    path('students/<int:pk>/status/', views.student_status_update, name='student_status_update'),
    path('students/<int:pk>/card/', views.student_card_print, name='student_card_print'),
    path('students/<int:pk>/edit/', views.student_edit, name='student_edit'),
    path('students/<int:pk>/delete/', views.student_delete, name='student_delete'),

    # Teachers
    path('teachers/', views.teacher_list, name='teacher_list'),
    path('teachers/create/', views.teacher_create, name='teacher_create'),
    path('teachers/<int:pk>/edit/', views.teacher_edit, name='teacher_edit'),
    path('teachers/<int:pk>/delete/', views.teacher_delete, name='teacher_delete'),

    # Receptionists
    path('receptionists/', views.receptionist_list, name='receptionist_list'),
    path('receptionists/create/', views.receptionist_create, name='receptionist_create'),
    path('receptionists/<int:pk>/edit/', views.receptionist_edit, name='receptionist_edit'),
    path('receptionists/<int:pk>/delete/', views.receptionist_delete, name='receptionist_delete'),
    path('receptionists/<int:pk>/commissions/', views.receptionist_commissions, name='receptionist_commissions'),
    path('receptionists/salaries/', views.receptionist_salary_list, name='receptionist_salary_list'),
    path('receptionists/salaries/calculate/', views.calculate_receptionist_salaries, name='calculate_receptionist_salaries'),
    path('receptionists/salaries/<int:pk>/toggle/', views.receptionist_salary_toggle, name='receptionist_salary_toggle'),

    # Courses
    path('courses/', views.course_list, name='course_list'),
    path('courses/create/', views.course_create, name='course_create'),
    path('courses/<int:pk>/edit/', views.course_edit, name='course_edit'),
    path('courses/<int:pk>/delete/', views.course_delete, name='course_delete'),

    # Groups
    path('groups/', views.group_list, name='group_list'),
    path('groups/create/', views.group_create, name='group_create'),
    path('groups/<int:pk>/edit/', views.group_edit, name='group_edit'),
    path('groups/<int:pk>/delete/', views.group_delete, name='group_delete'),
    path('schedule/', views.schedule_view, name='schedule'),

    # Payments
    path('payments/', views.payment_list, name='payment_list'),
    path('payments/create/', views.payment_create, name='payment_create'),
    path('payments/export/', views.payment_export, name='payment_export'),
    path('payments/import/', financial_migration.migration_preview, name='payment_import'),
    path('payments/import/template/', financial_migration.migration_template, name='payment_import_template'),
    path('payments/<int:pk>/receipt/', views.payment_receipt, name='payment_receipt'),
    path('payments/<int:pk>/edit/', views.payment_edit, name='payment_edit'),
    path('payments/<int:pk>/delete/', views.payment_delete, name='payment_delete'),

    # Teacher Salaries
    path('salaries/', views.salary_list, name='salary_list'),
    path('salaries/calculate/', views.calculate_salaries, name='calculate_salaries'),
    path('salaries/<int:pk>/toggle/', views.update_salary_status, name='update_salary_status'),

    # Attendance
    path('attendance/', views.attendance_list, name='attendance_list'),
    path('attendance/take/select/', views.take_attendance_select, name='take_attendance_select'),
    path('attendance/take/<int:group_id>/', views.take_attendance, name='take_attendance'),

    # Grades
    path('grades/', views.grade_list, name='grade_list'),
    path('grades/take/select/', views.take_grades_select, name='take_grades_select'),
    path('grades/take/<int:group_id>/', views.take_grades, name='take_grades'),
    path('grades/<int:pk>/delete/', views.grade_delete, name='grade_delete'),

    # Assignment history
    path('assignments/', views.assignment_history, name='assignment_history'),

    # Expenses
    path('expenses/', views.expense_list, name='expense_list'),
    path('expenses/create/', views.expense_create, name='expense_create'),
    path('expenses/<int:pk>/delete/', views.expense_delete, name='expense_delete'),

    # Reports
    path('reports/', views.reports, name='reports'),

    # Certificates
    path('certificates/', views.certificate_list, name='certificate_list'),
    path('certificates/settings/', views.certificate_settings, name='certificate_settings'),
    path('certificates/create/', views.certificate_create, name='certificate_create'),
    path('certificates/<int:pk>/', views.certificate_detail, name='certificate_detail'),
    path('certificates/<int:pk>/edit/', views.certificate_edit, name='certificate_edit'),
    path('certificates/<int:pk>/delete/', views.certificate_delete, name='certificate_delete'),
    path('certificate/verify/<str:number_or_code>/', views.certificate_verify, name='certificate_verify'),
    path('c/<str:number_or_code>/', views.certificate_verify, name='certificate_verify_short'),
]
