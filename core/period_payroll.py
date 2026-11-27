"""Calculate teacher shares from actual collections in a chosen date range."""
from decimal import Decimal, ROUND_HALF_UP

from django import forms
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import render
from django.utils import timezone

from .models import Payment, Teacher
from .permissions import capability_required


class PeriodFilter(forms.Form):
    date_from = forms.DateField(label='Pul tushgan sana: dan', widget=forms.DateInput(attrs={'type': 'date'}))
    date_to = forms.DateField(label='Pul tushgan sana: gacha (shu kun ham kiradi)', widget=forms.DateInput(attrs={'type': 'date'}))
    service_month = forms.DateField(label='Qaysi dars oyi uchun (ixtiyoriy)', required=False,
                                   input_formats=['%Y-%m'], widget=forms.DateInput(format='%Y-%m', attrs={'type': 'month'}))
    teacher = forms.ModelChoiceField(label="O'qituvchi", queryset=Teacher.objects.all(), required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'

    def clean(self):
        data = super().clean()
        if data.get('date_from') and data.get('date_to') and data['date_from'] > data['date_to']:
            raise forms.ValidationError('Boshlanish sanasi tugash sanasidan keyin bo‘lmasin.')
        return data


def period_calculation(data):
    payments = Payment.objects.filter(
        paid_date__date__gte=data['date_from'],
        paid_date__date__lte=data['date_to'],
        is_historical_migration=False,
    ).select_related(
        'student', 'student__teacher', 'student__group', 'teacher_at_payment'
    ).prefetch_related('refunds').order_by('paid_date', 'pk')

    if data.get('service_month'):
        month = data['service_month']
        payments = payments.filter(month__year=month.year, month__month=month.month)
    if data.get('teacher'):
        payments = payments.filter(
            Q(teacher_at_payment=data['teacher']) |
            Q(teacher_at_payment__isnull=True, student__teacher=data['teacher'])
        )

    rows, teacher_totals, month_totals = [], {}, {}
    students_map = {}
    gross_total = refund_total = salary_total = Decimal(0)

    # O'zbekcha oylar lug'ati
    uzbek_months = {
        1: 'Yanvar', 2: 'Fevral', 3: 'Mart', 4: 'Aprel',
        5: 'May', 6: 'Iyun', 7: 'Iyul', 8: 'Avgust',
        9: 'Sentabr', 10: 'Oktabr', 11: 'Noyabr', 12: 'Dekabr'
    }

    for payment in payments:
        teacher = payment.teacher_at_payment or payment.student.teacher
        percent = payment.teacher_percent_at_payment
        if percent is None:
            percent = teacher.percent if teacher else 0

        # Refund hisoboti
        refunded = sum((refund.amount for refund in payment.refunds.all()), Decimal(0))
        net = max(Decimal(0), payment.amount - refunded)
        share = (net * Decimal(percent) / 100).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)

        # Oy nomini chiroyli qilish
        m_name = f"{uzbek_months.get(payment.month.month, payment.month.strftime('%B'))} {payment.month.year}"

        row_item = {
            'payment': payment,
            'student': payment.student,
            'teacher': teacher,
            'percent': percent,
            'refunded': refunded,
            'net': net,
            'share': share,
            'service_month_name': m_name,
        }
        rows.append(row_item)

        # 1. O'qituvchilar hisobi
        t_key = teacher.pk if teacher else None
        t_summary = teacher_totals.setdefault(t_key, {
            'teacher': teacher,
            'students': set(),
            'count': 0,
            'income': Decimal(0),
            'salary': Decimal(0),
        })
        t_summary['students'].add(payment.student_id)
        t_summary['count'] += 1
        t_summary['income'] += net
        t_summary['salary'] += share

        # 2. Qaysi dars oyi uchun to'langanligi bo'yicha guruhlash (Month Breakdown)
        m_key = payment.month.strftime('%Y-%m')
        m_summary = month_totals.setdefault(m_key, {
            'month': payment.month,
            'month_key': m_key,
            'month_name': m_name,
            'students': set(),
            'count': 0,
            'gross': Decimal(0),
            'refunded': Decimal(0),
            'net': Decimal(0),
            'salary': Decimal(0),
        })
        m_summary['students'].add(payment.student_id)
        m_summary['count'] += 1
        m_summary['gross'] += payment.amount
        m_summary['refunded'] += refunded
        m_summary['net'] += net
        m_summary['salary'] += share

        # 3. O'quvchilar bo'yicha yig'ma
        st_id = payment.student_id
        st_summary = students_map.setdefault(st_id, {
            'student': payment.student,
            'payments_count': 0,
            'total_net': Decimal(0),
            'months': set(),
        })
        st_summary['payments_count'] += 1
        st_summary['total_net'] += net
        st_summary['months'].add(m_name)

        gross_total += payment.amount
        refund_total += refunded
        salary_total += share

    # Oylarni sanasi bo'yicha saralash
    sorted_months = sorted(month_totals.values(), key=lambda x: x['month'])

    return {
        'rows': rows,
        'teacher_totals': list(teacher_totals.values()),
        'month_totals': sorted_months,
        'students_list': list(students_map.values()),
        'student_count': len(students_map),
        'payment_count': len(rows),
        'gross_total': gross_total,
        'refund_total': refund_total,
        'net_total': gross_total - refund_total,
        'salary_total': salary_total,
        'center_total': gross_total - refund_total - salary_total,
    }


@login_required
@capability_required('salary.teacher.view')
def period_payroll(request):
    today = timezone.localdate()
    form = PeriodFilter(request.GET if request.GET else {
        'date_from': today.replace(day=1).isoformat(), 'date_to': today.isoformat(),
    })
    context = {'form': form}
    if form.is_valid():
        context.update(period_calculation(form.cleaned_data))
    return render(request, 'core/period_payroll.html', context)
