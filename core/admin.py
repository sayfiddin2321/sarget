from datetime import date, datetime, time
import json
from uuid import UUID

from django import forms
from django.contrib import admin, messages
from django.contrib.admin import helpers
from django.contrib.admin.utils import unquote
from django.apps import apps
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.html import format_html
from docx import Document
from openpyxl import Workbook
from .models import *


def is_sensitive_field(name):
    name = name.lower()
    return (
        name == 'password'
        or name.endswith('_password')
        or any(part in name for part in ('token', 'secret', 'api_key'))
    )


def export_fields(model):
    fields = [
        field for field in model._meta.concrete_fields
        if not is_sensitive_field(field.name)
    ]
    fields.extend(
        field for field in model._meta.many_to_many
        if not is_sensitive_field(field.name)
    )
    return fields


def export_value(value):
    if value is None:
        return ''
    if hasattr(value, 'all'):
        return ', '.join(str(item) for item in value.all())
    if hasattr(value, 'name') and not isinstance(value, type):
        value = value.name
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, default=str)
    if isinstance(value, bytes):
        return '[binary data omitted]'
    return value


def safe_spreadsheet_value(value):
    if isinstance(value, str) and value.startswith(('=', '+', '-', '@')):
        return "'" + value
    return value


class CRMModelAdmin(admin.ModelAdmin):
    actions = ['export_selected_xlsx', 'export_selected_docx']
    list_per_page = 100

    def has_module_permission(self, request):
        return request.user.is_active and request.user.is_staff

    def has_view_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_staff

    def get_exclude(self, request, obj=None):
        inherited = super().get_exclude(request, obj) or ()
        sensitive = (
            field.name for field in self.model._meta.concrete_fields
            if is_sensitive_field(field.name)
        )
        return tuple(dict.fromkeys((*inherited, *sensitive)))

    def has_add_permission(self, request):
        return (
            request.user.is_active and request.user.is_staff
            and super().has_add_permission(request)
        )

    def has_change_permission(self, request, obj=None):
        return (
            request.user.is_active and request.user.is_staff
            and super().has_change_permission(request, obj)
        )

    def has_delete_permission(self, request, obj=None):
        return (
            request.user.is_active and request.user.is_staff
            and super().has_delete_permission(request, obj)
        )

    def get_list_display(self, request):
        if self.list_display != ('__str__',):
            return super().get_list_display(request)
        fields = [
            field.name for field in self.model._meta.concrete_fields
            if field.name != 'id' and not field.many_to_many
            and not is_sensitive_field(field.name)
        ]
        return ('__str__', *fields[:4])

    def get_search_fields(self, request):
        if self.search_fields:
            return super().get_search_fields(request)
        return tuple(
            field.name for field in self.model._meta.concrete_fields
            if getattr(field, 'get_internal_type', lambda: '')() in ('CharField', 'TextField')
            and not is_sensitive_field(field.name)
        )[:8]

    def _export_response(self, request, queryset, file_format):
        fields = export_fields(self.model)
        if not fields:
            return HttpResponse('Eksport uchun maydon topilmadi.', status=400)

        relations = [field.name for field in fields if field.is_relation and field.many_to_one]
        many_relations = [field.name for field in fields if field.many_to_many]
        queryset = queryset.select_related(*relations).prefetch_related(*many_relations)
        headers = [str(field.verbose_name or field.name) for field in fields]
        def exported_rows():
            for obj in queryset.iterator(chunk_size=500):
                row = [export_value(getattr(obj, field.name)) for field in fields]
                if file_format == 'xlsx':
                    row = [safe_spreadsheet_value(value) for value in row]
                yield row

        filename = f'{self.model._meta.model_name}-{date.today():%Y%m%d}'

        if file_format == 'xlsx':
            workbook = Workbook(write_only=True)
            sheet = workbook.create_sheet(self.model._meta.verbose_name_plural[:31])
            sheet.append(headers)
            for row in exported_rows():
                sheet.append(row)
            response = HttpResponse(
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            response['Content-Disposition'] = f'attachment; filename="{filename}.xlsx"'
            workbook.save(response)
            return response

        document = Document()
        document.add_heading(str(self.model._meta.verbose_name_plural), 0)
        table = document.add_table(rows=1, cols=len(headers))
        table.style = 'Table Grid'
        for cell, header in zip(table.rows[0].cells, headers):
            cell.text = header
        for row in exported_rows():
            cells = table.add_row().cells
            for cell, value in zip(cells, row):
                cell.text = '' if value is None else str(value)
        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}.docx"'
        document.save(response)
        return response

    @admin.action(description='Tanlanganlarni Excel (.xlsx) eksport qilish')
    def export_selected_xlsx(self, request, queryset):
        return self._export_response(request, queryset, 'xlsx')

    @admin.action(description='Tanlanganlarni Word (.docx) eksport qilish')
    def export_selected_docx(self, request, queryset):
        return self._export_response(request, queryset, 'docx')


@admin.register(Course)
class CourseAdmin(CRMModelAdmin):
    list_display = ['name', 'is_active', 'created_at']
    list_filter = ['is_active']
    search_fields = ['name', 'description']
    list_editable = ['is_active']


@admin.register(Teacher)
class TeacherAdmin(CRMModelAdmin):
    list_display = ['name', 'subject', 'percent', 'student_count', 'is_active', 'created_at']
    list_filter = ['is_active', 'subject']
    search_fields = ['name', 'phone']
    list_editable = ['percent', 'is_active']
    readonly_fields = ['created_at']
    def student_count(self, obj):
        return obj.students.filter(status='active').count()
    student_count.short_description = "O'quvchilar"

@admin.register(Receptionist)
class ReceptionistAdmin(CRMModelAdmin):
    list_display = ['name', 'phone', 'commission_percent', 'student_count', 'is_active']
    list_filter = ['is_active']
    search_fields = ['name', 'phone']
    list_editable = ['commission_percent', 'is_active']

    def student_count(self, obj):
        return obj.registered_students.filter(status='active').count()
    student_count.short_description = "Yozganlar"


@admin.register(Student)
class StudentAdmin(CRMModelAdmin):
    def has_delete_permission(self, request, obj=None):
        return False

    list_display = ['photo_preview', 'name', 'phone', 'teacher', 'group', 'receptionist', 'status', 'registration_date']
    list_filter = ['status', 'source', 'teacher', 'group']
    search_fields = ['name', 'phone', 'parent_phone', 'group__name', 'teacher__name']
    list_editable = ['status']
    raw_id_fields = ['teacher', 'group', 'receptionist']
    date_hierarchy = 'registration_date'

    def photo_preview(self, obj):
        if obj.photo:
            return format_html(
                '<img src="{}" style="width:34px;height:34px;object-fit:cover;border-radius:50%;display:block;" />',
                obj.photo.url
            )
        return '—'
    photo_preview.short_description = "Rasm"

@admin.register(Group)
class GroupAdmin(CRMModelAdmin):
    list_display = ['name', 'teacher', 'days', 'start_time', 'end_time', 'monthly_fee', 'student_count', 'is_active']
    list_filter = ['is_active', 'teacher']
    search_fields = ['name', 'room']
    list_editable = ['is_active']

    def student_count(self, obj):
        return obj.get_student_count()
    student_count.short_description = "O'quvchilar"


class PaymentCancellationForm(forms.Form):
    reason = forms.CharField(
        label="O'chirish sababi", max_length=2000,
        widget=forms.Textarea(attrs={'rows': 3, 'cols': 60}),
        error_messages={'required': "O'chirish sababini kiriting."},
    )


@admin.register(Payment)
class PaymentAdmin(CRMModelAdmin):
    actions = [*CRMModelAdmin.actions, 'delete_selected']

    def delete_view(self, request, object_id, extra_context=None):
        if not self.has_delete_permission(request):
            raise PermissionDenied
        payment = get_object_or_404(self.get_queryset(request), pk=unquote(object_id))
        return self._cancel_payments(
            request, self.get_queryset(request).filter(pk=payment.pk),
            extra_context=extra_context,
        )

    @admin.action(permissions=['delete'], description="Tanlangan to'lovlarni o'chirish")
    def delete_selected(self, request, queryset):
        return self._cancel_payments(request, queryset, bulk=True)

    def _cancel_payments(self, request, queryset, bulk=False, extra_context=None):
        if not self.has_delete_permission(request):
            raise PermissionDenied
        form = PaymentCancellationForm(
            request.POST if request.method == 'POST' and request.POST.get('post') else None,
        )
        if form.is_bound and form.is_valid():
            try:
                with transaction.atomic(using=queryset.db):
                    # Admin searches can add nullable joins; lock payment rows only.
                    payments = list(queryset.select_for_update(of=('self',)))
                    for payment in payments:
                        if not self.has_delete_permission(request, payment):
                            raise PermissionDenied
                        payment.void(form.cleaned_data['reason'])
                        self.log_change(
                            request, payment,
                            "To'lov bekor qilindi: " + form.cleaned_data['reason'],
                        )
            except ValidationError as exc:
                form.add_error(None, exc)
            else:
                self.message_user(
                    request,
                    f"{len(payments)} ta to'lov o'chirildi; yozuv va sabab tarixda saqlandi.",
                    messages.SUCCESS,
                )
                return redirect(reverse(
                    'admin:core_payment_changelist', current_app=self.admin_site.name,
                ))

        request.current_app = self.admin_site.name
        context = {
            **self.admin_site.each_context(request),
            'title': "To'lovlarni o'chirish",
            'opts': self.model._meta,
            'media': self.media + form.media,
            'form': form,
            'queryset': queryset,
            'bulk': bulk,
            'action_checkbox_name': helpers.ACTION_CHECKBOX_NAME,
            **(extra_context or {}),
        }
        return TemplateResponse(request, 'admin/core/payment/cancel_confirmation.html', context)

    def has_change_permission(self, request, obj=None):
        # Use CRM validation and the audited cancellation flow for financial edits.
        return False
    list_display = ['student', 'amount_display', 'month', 'paid_date', 'payment_type', 'received_by']
    list_filter = ['month', 'payment_type', 'student__teacher', 'student__group']
    search_fields = ['student__name', 'student__phone', 'student__parent_phone', 'student__group__name']
    date_hierarchy = 'paid_date'
    readonly_fields = ['paid_date']

    def amount_display(self, obj):
        return format_html('<b>{}</b> so\'m', f'{obj.amount:,.0f}')
    amount_display.short_description = "Summa"


@admin.register(ReceptionistCommission)
class ReceptionistCommissionAdmin(CRMModelAdmin):
    list_display = ['receptionist', 'student', 'month', 'payment_amount', 'commission_percent', 'commission_amount']
    list_filter = ['receptionist', 'month']
    search_fields = ['student__name', 'receptionist__name']
    readonly_fields = ['created_at']


@admin.register(ReceptionistSalary)
class ReceptionistSalaryAdmin(CRMModelAdmin):
    list_display = ['receptionist', 'month', 'base_salary', 'total_commission', 'total_salary', 'is_paid']
    list_filter = ['month', 'is_paid', 'receptionist']
    list_editable = ['is_paid']


@admin.register(Salary)
class SalaryAdmin(CRMModelAdmin):
    list_display = ['teacher', 'month', 'total_income', 'percent', 'salary_amount', 'is_paid']
    list_filter = ['month', 'is_paid', 'teacher']
    list_editable = ['is_paid']
    readonly_fields = ['calculated_at']


@admin.register(Attendance)
class AttendanceAdmin(CRMModelAdmin):
    list_display = ['student', 'group', 'date', 'status', 'marked_by']
    list_filter = ['date', 'status', 'group']
    search_fields = ['student__name']
    date_hierarchy = 'date'


@admin.register(Grade)
class GradeAdmin(CRMModelAdmin):
    list_display = ['student', 'group', 'date', 'grade_type', 'score', 'graded_by']
    list_filter = ['grade_type', 'date', 'group']
    search_fields = ['student__name', 'note']
    date_hierarchy = 'date'


@admin.register(Expense)
class ExpenseAdmin(CRMModelAdmin):
    list_display = ['title', 'category', 'amount', 'date', 'added_by']
    list_filter = ['category', 'date']
    search_fields = ['title']
    date_hierarchy = 'date'


@admin.register(AssignmentHistory)
class AssignmentHistoryAdmin(CRMModelAdmin):
    list_display = ['student', 'teacher', 'group', 'assigned_date', 'changed_by']
    list_filter = ['assigned_date', 'teacher']
    search_fields = ['student__name']


admin.site.site_header = "EduCRM Admin"
admin.site.site_title = "EduCRM"
admin.site.index_title = "Boshqaruv paneli"


@admin.register(FinancialAudit)
class FinancialAuditAdmin(CRMModelAdmin):
    list_display = ['created_at', 'entity', 'object_id', 'action', 'actor_name']
    list_filter = ['entity', 'action']
    readonly_fields = ['entity', 'object_id', 'action', 'actor', 'actor_name', 'before', 'after', 'created_at']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False



@admin.register(Certificate)
class CertificateAdmin(CRMModelAdmin):
    list_display = ['certificate_number', 'student', 'course_name', 'issue_date', 'status', 'created_at']
    list_filter = ['status', 'issue_date']
    search_fields = ['certificate_number', 'student__name', 'course_name', 'teacher_name']
    readonly_fields = ['verification_code', 'created_at', 'updated_at']
    date_hierarchy = 'issue_date'



@admin.register(CertificateSetting)
class CertificateSettingAdmin(CRMModelAdmin):
    list_display = ['academy_name', 'certificate_prefix', 'accent_color', 'updated_at']


for model in apps.get_app_config('core').get_models():
    if model not in admin.site._registry:
        admin.site.register(model, CRMModelAdmin)
