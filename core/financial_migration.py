"""Separate super-admin financial migration with preview and total reconciliation."""
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from openpyxl import Workbook

from .models import ImportBatch, Payment, Student
from .permissions import admin_required
from .report_imports import read_xlsx, digest

HEADERS = ['student_number', 'amount', 'month', 'paid_at', 'payment_type', 'comment']


class MigrationForm(forms.Form):
    file = forms.FileField(label='Moliyaviy XLSX shablon')
    expected_total = forms.DecimalField(max_digits=16, decimal_places=2, min_value=Decimal('0.01'), label='Manba reyestridagi kutilayotgan jami summa')


def validate_financial_rows(raw_rows):
    rows, errors, seen = [], [], set()
    total = Decimal(0)
    for row in raw_rows:
        data, line, column = dict(row['data']), row['line'], 'student_number'
        try:
            number = data.get('student_number', '')
            if not re.fullmatch(r'STU-[0-9]{1,18}', number):
                raise ValidationError('Aniq STU-raqam majburiy. Telefon bo‘yicha moliyaviy yozuv birlashtirilmaydi.')
            student = Student.objects.filter(pk=int(number[4:])).first()
            if not student:
                raise ValidationError('O‘quvchi topilmadi.')
            column = 'amount'
            amount = Decimal(data.get('amount', ''))
            if not amount.is_finite() or amount <= 0 or amount >= Decimal('10000000000') or amount.quantize(Decimal('.01')) != amount:
                raise ValidationError('Summa musbat, ikki kasrgacha va 10 milliarddan kichik bo‘lsin.')
            column = 'month'
            month = datetime.strptime(data.get('month', ''), '%Y-%m').date()
            column = 'paid_at'
            paid = datetime.fromisoformat(data.get('paid_at', ''))
            if timezone.is_naive(paid):
                paid = timezone.make_aware(paid)
            if paid > timezone.now():
                raise ValidationError('Tarixiy to‘lov kelajak sanasida bo‘lolmaydi.')
            column = 'payment_type'
            if data.get('payment_type') not in dict(Payment.PAYMENT_TYPES):
                raise ValidationError('Usul cash/card/bank/transfer bo‘lsin.')
            key = (student.pk, amount, month, paid)
            if key in seen or Payment.all_objects.filter(student=student, amount=amount, month=month, paid_date=paid).exists():
                raise ValidationError('Aynan shunday moliyaviy yozuv mavjud. Avval reyestrni solishtiring.')
            seen.add(key)
            data.update(amount=str(amount), month=month.strftime('%Y-%m'), paid_at=paid.isoformat())
            rows.append({'line': line, 'data': data, 'student_id': student.pk})
            total += amount
        except (ValidationError, ValueError, InvalidOperation, OverflowError) as exc:
            errors.append({'line': line, 'column': column, 'reason': '; '.join(exc.messages) if isinstance(exc, ValidationError) else 'Qiymat yoki sana noto‘g‘ri.'})
    return rows, errors, total


@login_required
@admin_required
def migration_template(request):
    workbook = Workbook()
    workbook.active.title = 'payments_migration'
    workbook.active.append(HEADERS)
    output = BytesIO()
    workbook.save(output)
    response = HttpResponse(output.getvalue(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename="payments-migration.xlsx"'
    return response


@login_required
@admin_required
def migration_preview(request):
    form = MigrationForm(request.POST or None, request.FILES or None)
    if form.is_valid():
        try:
            raw = read_xlsx(form.cleaned_data['file'], 'payments_migration', HEADERS)
            rows, errors, total = validate_financial_rows(raw)
            expected = form.cleaned_data['expected_total']
            if total != expected:
                errors.append({'line': 'Jami', 'column': 'amount', 'reason': f'Fayl jami {total}; manba reyestri jami {expected}. Mos emas.'})
            batch = ImportBatch.objects.create(owner=request.user, kind='payments_migration', strategy=str(expected),
                                               rows=rows, errors=errors, fingerprint=digest(rows))
            return redirect('financial_migration_batch', public_id=batch.public_id)
        except ValidationError as exc:
            form.add_error(None, exc)
    return render(request, 'core/financial_migration.html', {'form': form})


@login_required
@admin_required
def migration_batch(request, public_id):
    batch = get_object_or_404(ImportBatch, public_id=public_id, owner=request.user, kind='payments_migration')
    return render(request, 'core/financial_migration.html', {'batch': batch, 'rows': batch.rows[:100],
                  'total': sum((Decimal(row['data']['amount']) for row in batch.rows), Decimal(0))})


@login_required
@admin_required
@require_POST
@transaction.atomic
def migration_confirm(request, public_id):
    batch = get_object_or_404(ImportBatch, public_id=public_id, owner=request.user, kind='payments_migration')
    if batch.errors or digest(batch.rows) != batch.fingerprint or not ImportBatch.objects.filter(pk=batch.pk, status='preview').update(status='processing'):
        messages.error(request, 'Import tasdiqlangan yoki tekshiruvdan o‘tmagan.')
        return redirect('financial_migration_batch', public_id=public_id)
    rows, errors, total = validate_financial_rows(batch.rows)
    if errors or total != Decimal(batch.strategy):
        # Raise to roll back the claim; the old preview must be regenerated.
        transaction.set_rollback(True)
        messages.error(request, 'Moliyaviy reyestr o‘zgargan. Qayta preview va solishtirish talab qilinadi.')
        return redirect('financial_migration_batch', public_id=public_id)
    before = Payment.all_objects.aggregate(total=Sum('amount'))['total'] or Decimal(0)
    for row in rows:
        data = row['data']
        payment = Payment(student_id=row['student_id'], amount=Decimal(data['amount']),
                          month=datetime.strptime(data['month'], '%Y-%m').date(),
                          paid_date=datetime.fromisoformat(data['paid_at']), payment_type=data['payment_type'],
                          comment=data.get('comment', ''), received_by=request.user)
        payment.is_historical_migration = True
        payment.save()
    after = Payment.all_objects.aggregate(total=Sum('amount'))['total'] or Decimal(0)
    if after - before != total:
        raise ValidationError('Yakuniy moliyaviy solishtirish mos emas; tranzaksiya bekor qilindi.')
    batch.status, batch.confirmed_at = 'confirmed', timezone.now()
    batch.save(update_fields=['status', 'confirmed_at'])
    messages.success(request, f'{len(rows)} ta to‘lov import qilindi. Jami: {total}. Baza o‘sishi bilan solishtirildi.')
    return redirect('financial_migration_batch', public_id=public_id)
