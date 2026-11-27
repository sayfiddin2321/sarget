"""XLSX templates -> validated preview -> atomic, owner-bound confirmation."""
import hashlib
import json
import re
import zipfile
from datetime import date, datetime, timedelta
from io import BytesIO
from xml.etree.ElementTree import ParseError
from lxml.etree import XMLSyntaxError

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from openpyxl import Workbook, load_workbook

from .models import Attendance, Grade, Group, ImportBatch, Student
from .permissions import has_capability, is_teacher, is_receptionist, get_receptionist, visible_students, visible_groups
from .report_files import cell_value

HEADERS = {
    'students': ['student_number', 'name', 'phone', 'parent_phone', 'birth_date', 'registration_date', 'group_id', 'status', 'payment_due_day', 'notes'],
    'attendance': ['student_number', 'group_id', 'date', 'status', 'note'],
    'grades': ['student_number', 'group_id', 'date', 'grade_type', 'score', 'note'],
}
STRATEGIES = [('reject', 'Dublikatni xato deb ko‘rsatish'), ('skip', 'Dublikatni o‘tkazib yuborish'),
              ('update', 'Faqat aniq raqam/kalit bo‘yicha yangilash'), ('create', 'Telefon o‘xshash bo‘lsa ham yangi shaxs yaratish')]


def import_permission(user, kind):
    if kind not in HEADERS or not has_capability(user, 'imports.students' if kind == 'students' else 'imports.academic'):
        raise PermissionDenied('Bu import turiga ruxsat yo‘q.')
    if kind in ('attendance', 'grades') and not has_capability(user, f'{kind}.write'):
        raise PermissionDenied('Davomat yoki baholarni yozish huquqi kerak.')


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()


def snapshot(instance):
    if instance is None:
        return ''
    return digest({field.attname: getattr(instance, field.attname) for field in instance._meta.concrete_fields})


def normalized_phone(raw, optional=False):
    if not raw and optional:
        return ''
    digits = re.sub(r'[^0-9]', '', str(raw))
    if len(digits) == 9:
        digits = '998' + digits
    if not re.fullmatch(r'998[0-9]{9}', digits):
        raise ValidationError('Telefon +998 va 9 ta raqam shaklida bo‘lsin.')
    return '+' + digits


def parse_date(value, optional=False):
    if not value and optional:
        return None
    try:
        return date.fromisoformat(str(value))
    except (ValueError, TypeError):
        raise ValidationError('Sana YYYY-MM-DD shaklida bo‘lsin.')


def read_xlsx(upload, kind, expected_headers=None):
    if not upload.name.lower().endswith('.xlsx') or upload.size > 5 * 1024 * 1024:
        raise ValidationError('Faqat 5 MBgacha XLSX fayl qabul qilinadi.')
    data = upload.read()
    try:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            if sum(info.file_size for info in archive.infolist()) > 50 * 1024 * 1024:
                raise ValidationError('XLSXning ochilgan hajmi juda katta.')
        workbook = load_workbook(BytesIO(data), read_only=True, data_only=False, keep_links=False)
        if len(workbook.sheetnames) != 1 or workbook.sheetnames[0] != kind:
            raise ValidationError('Faqat tanlangan turdagi bitta shablon varag‘ini yuklang. Moliyaviy tarix bu importga kirmaydi.')
        sheet = workbook[kind]
        expected_headers = expected_headers or HEADERS[kind]
        if sheet.max_row > 5001 or sheet.max_column > len(expected_headers):
            raise ValidationError('Eng ko‘pi bilan 5000 satr va shablon ustunlari ruxsat etiladi.')
        iterator = sheet.iter_rows()
        first = next(iterator, ())
        headers = [str(cell.value or '').strip() for cell in first]
        if headers != expected_headers:
            raise ValidationError('Ustunlar shablonga mos emas. Moliyaviy maydonlarni oddiy importga qo‘shmang.')
        rows = []
        for number, cells in enumerate(iterator, start=2):
            if not any(cell.value is not None for cell in cells):
                continue
            row = {}
            for header, cell in zip(headers, cells):
                if cell.data_type == 'f':
                    raise ValidationError(f'{number}-satr, {header}: formula qabul qilinmaydi.')
                value = cell.value
                if isinstance(value, datetime):
                    value = value.isoformat() if kind == 'payments_migration' else value.date().isoformat()
                row[header] = '' if value is None else str(value).strip()
            rows.append({'line': number, 'data': row})
        workbook.close()
        if not rows:
            raise ValidationError('Faylda ma’lumot satrlari yo‘q.')
        return rows
    except (zipfile.BadZipFile, KeyError, ValueError, OSError, ParseError, XMLSyntaxError) as exc:
        raise ValidationError('XLSX faylini o‘qib bo‘lmadi.') from exc


def validate_rows(user, kind, raw_rows, strategy, selected_student=None):
    import_permission(user, kind)
    rows, errors, seen, seen_phones = [], [], set(), set()
    existing_phones = set()
    if kind == 'students':
        for phone in Student.objects.exclude(phone='').values_list('phone', flat=True):
            try:
                existing_phones.add(normalized_phone(phone))
            except ValidationError:
                continue
    occupied = {}
    for raw in raw_rows:
        values, line = dict(raw['data']), raw['line']
        result = {'line': line, 'data': values, 'action': 'create', 'student_id': None, 'version': '', 'warning': ''}
        column = 'student_number'
        try:
            number = values.get('student_number', '')
            student = None
            if number:
                if not re.fullmatch(r'STU-[0-9]{1,18}', number):
                    raise ValidationError('O‘quvchi raqami STU-000001 shaklida bo‘lsin.')
                student = visible_students(user).filter(pk=int(number[4:])).first()
                if student is None:
                    raise ValidationError('O‘quvchi topilmadi yoki sizga tegishli emas.')
            if selected_student and (not student or student.pk != selected_student.pk):
                raise ValidationError('Faylda faqat tanlangan o‘quvchi bo‘lishi kerak.')
            if not student and (is_teacher(user) or not has_capability(user, 'students.create')):
                raise ValidationError('Yangi shaxs yaratish mumkin emas. Mavjud o‘quvchi raqamini kiriting.')
            if student and not has_capability(user, 'students.edit') and kind == 'students':
                raise PermissionDenied('O‘quvchini tahrirlash huquqi yo‘q.')
            result['student_id'] = student.pk if student else None
            if kind == 'students':
                column = 'name'
                if not values.get('name') or len(values['name']) > 200:
                    raise ValidationError('Ism majburiy va 200 belgidan oshmasin.')
                column = 'phone'
                values['phone'] = normalized_phone(values.get('phone'))
                column = 'parent_phone'
                values['parent_phone'] = normalized_phone(values.get('parent_phone'), optional=True)
                column = 'birth_date'
                values['birth_date'] = str(parse_date(values.get('birth_date'), optional=True) or '')
                column = 'registration_date'
                registration = parse_date(values.get('registration_date'), optional=True) or (student.registration_date if student else timezone.localdate())
                if is_teacher(user) and student and registration != student.registration_date:
                    raise ValidationError('O‘qituvchi ro‘yxat sanasini almashtirmaydi.')
                values['registration_date'] = str(registration)
                column = 'group_id'
                group = visible_groups(user).filter(pk=int(values['group_id'])).first() if values.get('group_id', '').isdigit() else None
                if values.get('group_id') and not group:
                    raise ValidationError('Guruh topilmadi yoki ruxsat yo‘q.')
                if group and (not student or group.pk != student.group_id) and not has_capability(user, 'students.assign'):
                    raise ValidationError('Guruhni almashtirish huquqi yo‘q.')
                column = 'status'
                state = values.get('status') or ('active' if group else 'pending')
                if state not in dict(Student.STATUS_CHOICES):
                    raise ValidationError('Holat active/inactive/graduated/pending bo‘lsin.')
                if is_teacher(user) and student and (state != student.status or (group.pk if group else None) != student.group_id):
                    raise ValidationError('O‘qituvchi import orqali guruh yoki holatni almashtirmaydi.')
                values['status'] = state
                column = 'payment_due_day'
                if values.get('payment_due_day') and (not values['payment_due_day'].isdigit() or not 1 <= int(values['payment_due_day']) <= 31):
                    raise ValidationError('To‘lov kuni 1–31 orasida bo‘lsin.')
                if is_teacher(user) and student and (int(values['payment_due_day']) if values.get('payment_due_day') else None) != student.payment_due_day:
                    raise ValidationError('O‘qituvchi to‘lov kunini almashtirmaydi.')
                key = ('student', student.pk) if student else ('new', values['name'].casefold(), values['phone'])
                exists = student
                if not student:
                    column = 'phone'
                    if values['phone'] in existing_phones or values['phone'] in seen_phones:
                        result['warning'] = 'Shu telefonli shaxs mavjud; avtomatik birlashtirilmaydi.'
                        if strategy == 'skip':
                            result['action'] = 'skip'
                        elif strategy != 'create':
                            raise ValidationError('O‘xshash telefon topildi. Raqam bilan yangilang yoki yangi shaxs strategiyasini tanlang.')
                    seen_phones.add(values['phone'])
                if student and strategy == 'skip':
                    result['action'] = 'skip'
                column = 'group_id'
                if result['action'] != 'skip' and group and state == 'active' and (not student or student.group_id != group.pk or student.status != 'active'):
                    occupied[group.pk] = occupied.get(group.pk, group.get_student_count()) + 1
                    if occupied[group.pk] > group.max_students:
                        raise ValidationError('Guruh sig‘imi to‘lgan.')
            else:
                if not student:
                    raise ValidationError('O‘quvchi raqami majburiy.')
                column = 'group_id'
                group = visible_groups(user).filter(pk=int(values.get('group_id', '0'))).first()
                if group is None or not student.enrollments.filter(group=group).exists():
                    raise ValidationError('O‘quvchi ushbu ruxsatli guruhga yozilmagan.')
                column = 'date'
                day = parse_date(values.get('date'))
                if day > timezone.localdate():
                    raise ValidationError('Kelajakdagi davomat yoki baho import qilinmaydi.')
                if not student.enrollments.filter(group=group, starts_on__lte=day).exclude(status__in=['planned', 'cancelled']).filter(Q(ends_on__isnull=True) | Q(ends_on__gte=day)).exists():
                    raise ValidationError('Bu sanada ushbu guruhga tegishli kursga yozilish mavjud emas.')
                filters = {'student': student, 'group': group, 'date': day}
                if kind == 'attendance':
                    column = 'status'
                    if values.get('status') not in dict(Attendance.STATUS_CHOICES):
                        raise ValidationError('Davomat holati noto‘g‘ri.')
                    exists = Attendance.objects.filter(**filters).first()
                    key = ('attendance', student.pk, group.pk, str(day))
                else:
                    column = 'grade_type'
                    if values.get('grade_type') not in dict(Grade.GRADE_TYPES):
                        raise ValidationError('Baho turi noto‘g‘ri.')
                    column = 'score'
                    if not values.get('score', '').isdigit() or not 1 <= int(values['score']) <= 100:
                        raise ValidationError('Ball 1–100 orasida bo‘lsin.')
                    filters['grade_type'] = values['grade_type']
                    exists = Grade.objects.filter(**filters).first()
                    key = ('grades', student.pk, group.pk, str(day), values['grade_type'])
            column = 'student_number' if kind == 'students' else 'date'
            if key in seen:
                raise ValidationError('Faylning o‘zida takroriy satr mavjud.')
            seen.add(key)
            if exists:
                if strategy == 'skip':
                    result['action'] = 'skip'
                elif strategy == 'update':
                    result['action'] = 'update'
                else:
                    raise ValidationError('Mavjud yozuv. Yangilash yoki o‘tkazib yuborish strategiyasini tanlang.')
            result['version'] = snapshot(exists)
        except (ValidationError, ValueError, TypeError, OverflowError) as exc:
            reason = '; '.join(exc.messages) if isinstance(exc, ValidationError) else 'Qiymat turi noto‘g‘ri.'
            errors.append({'line': line, 'column': column, 'reason': reason})
            result['action'] = 'error'
        rows.append(result)
    return rows, errors


@transaction.atomic
def confirm_batch(batch, user):
    if batch.owner_id != user.pk:
        raise PermissionDenied()
    if batch.status != 'preview' or batch.errors:
        raise ValidationError('Import tasdiqlangan yoki xatolari bor.')
    if timezone.now() - batch.created_at > timedelta(hours=24):
        raise ValidationError('Preview muddati tugagan. Faylni qayta tekshiring.')
    claimed = ImportBatch.objects.filter(pk=batch.pk, status='preview').update(status='processing')
    if not claimed:
        raise ValidationError('Import allaqachon bajarilgan.')
    if digest(batch.rows) != batch.fingerprint:
        raise ValidationError('Preview yaxlitligi buzilgan.')
    current, errors = validate_rows(user, batch.kind, batch.rows, batch.strategy, batch.student)
    if errors or any((old['version'], old['action']) != (new['version'], new['action']) for old, new in zip(batch.rows, current)):
        raise ValidationError('Ma’lumot yoki ruxsat o‘zgargan. Yangi preview yarating.')
    count = 0
    for row in current:
        if row['action'] == 'skip':
            continue
        values = row['data']
        student = Student.objects.get(pk=row['student_id']) if row['student_id'] else None
        if batch.kind == 'students':
            student = student or Student(created_by=user, receptionist=get_receptionist(user))
            student.name, student.phone, student.parent_phone = values['name'], values['phone'], values['parent_phone']
            student.birth_date = parse_date(values.get('birth_date'), optional=True)
            student.registration_date = parse_date(values['registration_date'])
            student.notes, student.status = values.get('notes', ''), values['status']
            if not is_teacher(user):
                student.group_id = int(values['group_id']) if values.get('group_id') else None
                student.teacher = student.group.teacher if student.group_id else None
                student.payment_due_day = int(values['payment_due_day']) if values.get('payment_due_day') else None
            student.save()
        else:
            filters = {'student': student, 'group_id': int(values['group_id']), 'date': parse_date(values['date'])}
            if batch.kind == 'attendance':
                Attendance.objects.update_or_create(**filters, defaults={'status': values['status'], 'note': values.get('note', ''), 'marked_by': user})
            else:
                Grade.objects.update_or_create(**filters, grade_type=values['grade_type'], defaults={'score': int(values['score']), 'note': values.get('note', ''), 'graded_by': user})
        count += 1
    batch.status, batch.confirmed_at = 'confirmed', timezone.now()
    batch.save(update_fields=['status', 'confirmed_at'])
    return count


@login_required
def import_template(request):
    kind = request.GET.get('kind', 'students')
    import_permission(request.user, kind)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = kind
    sheet.append(HEADERS[kind])
    if request.GET.get('student', '').isdigit():
        student = get_object_or_404(visible_students(request.user), pk=request.GET['student'])
        if kind == 'students':
            sheet.append([cell_value(value) for value in [student.student_number, student.name, student.phone, student.parent_phone,
                          str(student.birth_date or ''), str(student.registration_date), student.group_id or '', student.status, student.payment_due_day or '', student.notes]])
    output = BytesIO()
    workbook.save(output)
    response = HttpResponse(output.getvalue(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="{kind}-import-template.xlsx"'
    return response


@login_required
def xlsx_import(request):
    kind = request.POST.get('kind', request.GET.get('kind', 'students'))
    import_permission(request.user, kind)
    selected = request.POST.get('student', request.GET.get('student', ''))
    student = get_object_or_404(visible_students(request.user), pk=selected) if selected.isdigit() else None
    context = {'kind': kind, 'student': student, 'strategies': STRATEGIES}
    if request.method == 'POST':
        strategy = request.POST.get('strategy', 'reject')
        try:
            if strategy not in dict(STRATEGIES):
                raise ValidationError('Dublikat strategiyasi noto‘g‘ri.')
            upload = request.FILES.get('file')
            if upload is None:
                raise ValidationError('XLSX fayl tanlang.')
            raw = read_xlsx(upload, kind)
            rows, errors = validate_rows(request.user, kind, raw, strategy, student)
            batch = ImportBatch.objects.create(owner=request.user, kind=kind, strategy=strategy, student=student,
                                               rows=rows, errors=errors, fingerprint=digest(rows))
            return redirect('xlsx_import_preview', public_id=batch.public_id)
        except ValidationError as exc:
            context['error'] = '; '.join(exc.messages)
    return render(request, 'core/xlsx_import.html', context)


@login_required
def xlsx_import_preview(request, public_id):
    batch = get_object_or_404(ImportBatch, public_id=public_id, owner=request.user)
    import_permission(request.user, batch.kind)
    return render(request, 'core/xlsx_import_preview.html', {'batch': batch, 'rows': batch.rows[:100], 'row_count': len(batch.rows)})


@login_required
@require_POST
def xlsx_import_confirm(request, public_id):
    batch = get_object_or_404(ImportBatch, public_id=public_id, owner=request.user)
    try:
        count = confirm_batch(batch, request.user)
    except ValidationError as exc:
        messages.error(request, '; '.join(exc.messages))
    else:
        messages.success(request, f'{count} ta yozuv import qilindi.')
    return redirect('xlsx_import_preview', public_id=batch.public_id)
