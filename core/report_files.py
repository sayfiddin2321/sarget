"""Fixed XLSX/DOCX report templates; private downloads, no public media URLs."""
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone
from openpyxl import Workbook
from docx import Document

from .models import ReportJob
from .permissions import has_capability, visible_students, visible_groups
from .reporting import Report

DOCX_KINDS = {'students', 'attendance', 'grades', 'payments', 'student'}


def safe_text(value):
    if not isinstance(value, str):
        return value
    value = ''.join(ch for ch in value if ch in '\n\r\t' or ord(ch) >= 32)
    return "'" + value if value.lstrip().startswith(('=', '+', '-', '@', '\t', '\r')) else value


def cell_value(value):
    if isinstance(value, datetime) and timezone.is_aware(value):
        return timezone.localtime(value).replace(tzinfo=None)
    return safe_text(value)


def build_file(report, file_format):
    if file_format not in ('xlsx', 'docx'):
        raise ValidationError('Format XLSX yoki DOCX bo‘lishi kerak.')
    if file_format == 'docx' and report.kind not in DOCX_KINDS:
        raise ValidationError('DOCX uchun ushbu hisobot shabloni mavjud emas. XLSX tanlang.')
    sheets = report.sheets()
    output = BytesIO()
    metadata = [('Hisobot', report.title), ('Davr', f'{report.start} — {report.end}'),
                ('Qarz holati sanasi', str(report.as_of)), ('Kuzatish oxiri', str(report.observation_end)),
                ('Yaratildi', timezone.localtime().strftime('%Y-%m-%d %H:%M'))]
    if report.kind in ('student', 'attendance', 'grades'):
        labels = {'marked': 'Davomat belgilangan', 'present': 'Keldi', 'late': 'Kechikdi', 'absent': 'Kelmadi',
                  'excused': 'Sababli kelmadi', 'attendance_percent': 'Davomat foizi (keldi + kechikdi)',
                  'grades_count': 'Baholar soni', 'average_score': 'O‘rtacha ball'}
        metadata.extend((labels[key], value if value is not None else 'Ma’lumot yo‘q') for key, value in report.academic_summary().items())
    for key, value in report.form.serialized().items():
        if key not in ('date_from', 'date_to', 'as_of', 'observation_end'):
            field = report.form.fields[key]
            display = report.filters[key]
            if hasattr(field, 'choices') and not hasattr(display, 'pk'):
                display = dict(field.choices).get(display, display)
            metadata.append((field.label or key, str(display)))
    if file_format == 'xlsx':
        workbook = Workbook(write_only=True)
        cover = workbook.create_sheet('Hisobot haqida')
        for row in metadata:
            cover.append([cell_value(value) for value in row])
        for sheet in sheets:
            worksheet = workbook.create_sheet(sheet.title[:31])
            worksheet.append(sheet.headers)
            for row in sheet.rows:
                worksheet.append([cell_value(value) for value in row])
        workbook.save(output)
    else:
        document = Document()
        document.add_heading(report.title, 0)
        for label, value in metadata:
            document.add_paragraph(f'{label}: {value}')
        for sheet in sheets:
            document.add_heading(sheet.title, level=1)
            table = document.add_table(rows=1, cols=len(sheet.headers))
            table.style = 'Light Shading Accent 1'
            for cell, header in zip(table.rows[0].cells, sheet.headers):
                cell.text = header
            for row in sheet.rows:
                cells = table.add_row().cells
                for cell, value in zip(cells, row):
                    cell.text = str(value if value is not None else '')
        document.save(output)
    return output.getvalue()


def private_path(file_name):
    if not file_name or Path(file_name).name != file_name:
        raise ValidationError('Fayl yo‘li noto‘g‘ri.')
    root = Path(settings.BASE_DIR) / 'private' / 'reports'
    root.mkdir(parents=True, exist_ok=True)
    return root / file_name


def create_job(user, kind, params, file_format):
    if not has_capability(user, 'reports.export'):
        raise PermissionDenied()
    report = Report(user, kind, params)
    if file_format not in ('xlsx', 'docx') or file_format == 'docx' and kind not in DOCX_KINDS:
        raise ValidationError('Bu hisobot uchun format mavjud emas.')
    return ReportJob.objects.create(owner=user, kind=kind, filters=report.form.serialized(), file_format=file_format)


def generate_job(job):
    if not has_capability(job.owner, 'reports.export'):
        raise PermissionDenied('Eksport huquqi bekor qilingan.')
    report = Report(job.owner, job.kind, job.filters)
    scope_ids = list(report.students().values_list('pk', flat=True))
    job.filters['_capabilities'] = [code for code in ('students.view', 'attendance.view', 'grades.view', 'payments.view', 'leads.manage') if has_capability(job.owner, code)]
    job.filters['_groups'] = list(visible_groups(job.owner).values_list('pk', flat=True))
    data = build_file(report, job.file_format)
    file_name = f'{job.public_id}.{job.file_format}'
    target = private_path(file_name)
    partial = target.with_suffix('.partial-' + uuid4().hex)
    try:
        partial.write_bytes(data)
        partial.replace(target)
    finally:
        partial.unlink(missing_ok=True)
    job.file_name, job.scope_ids = file_name, scope_ids
    job.status, job.error = 'ready', ''
    job.completed_at = timezone.now()
    job.save(update_fields=['file_name', 'scope_ids', 'status', 'error', 'completed_at', 'filters'])


def validate_job_access(job, user):
    if job.owner_id != user.pk or not has_capability(user, 'reports.export'):
        raise PermissionDenied('Bu fayl sizga tegishli emas yoki huquqingiz o‘zgargan.')
    Report(user, job.kind, job.filters)
    if any(not has_capability(user, code) for code in job.filters.get('_capabilities', [])):
        raise PermissionDenied('Hisobot tarkibiga bo‘lgan huquq o‘zgargan. Qayta yarating.')
    if not set(job.filters.get('_groups', [])).issubset(set(visible_groups(user).values_list('pk', flat=True))):
        raise PermissionDenied('Guruhlar doirasi o‘zgargan. Qayta yarating.')
    visible = set(visible_students(user).filter(pk__in=job.scope_ids).values_list('pk', flat=True))
    if not set(job.scope_ids).issubset(visible):
        raise PermissionDenied('O‘quvchilar doirasi o‘zgargan. Hisobotni qayta yarating.')
