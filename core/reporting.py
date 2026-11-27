"""Shared, permission-scoped report selectors for HTML, files and Telegram."""
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from calendar import monthrange

from django import forms
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q, Prefetch, Min, Sum, Exists, OuterRef, Avg
from django.utils import timezone

from .accounts import student_accounts
from .models import Attendance, Branch, Course, Enrollment, Grade, Group, Lead, Payment, Refund, Student, Teacher
from .permissions import has_capability, is_admin, is_teacher, visible_groups, visible_students, get_teacher

REPORT_KINDS = {
    'students': "O'quvchilar ro'yxati", 'attendance': 'Davomat', 'grades': 'Baholar',
    'payments': "To'lovlar reyestri", 'accounts': "To'lov holatlari va muddatli qarz",
    'advances': 'Avanslar', 'refunds': 'Pul qaytarish', 'groups': "Guruhlar to'lishi",
    'tasks': 'Bajarilmagan qayta aloqa vazifalari', 'leads': 'Murojaatlar va marketing',
    'student': "O'quvchining batafsil hisoboti",
}
FINANCIAL_KINDS = {'payments', 'accounts', 'advances', 'refunds'}


class ReportFilterForm(forms.Form):
    period = forms.ChoiceField(required=False, choices=[('', 'Sana oralig‘i'), ('day', 'Bugun'), ('week', 'Shu hafta'), ('month', 'Shu oy'), ('year', 'Shu yil')])
    date_from = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    date_to = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    as_of = forms.DateField(required=False, label='Kuzatish / qarz holati sanasi', widget=forms.DateInput(attrs={'type': 'date'}))
    observation_end = forms.DateField(required=False, label='Konversiyani kuzatish oxiri', widget=forms.DateInput(attrs={'type': 'date'}))
    month = forms.DateField(required=False, input_formats=['%Y-%m'], widget=forms.DateInput(attrs={'type': 'month'}))
    branch = forms.ModelChoiceField(required=False, queryset=Branch.objects.none())
    course = forms.ModelChoiceField(required=False, queryset=Course.objects.none())
    group = forms.ModelChoiceField(required=False, queryset=Group.objects.none())
    teacher = forms.ModelChoiceField(required=False, queryset=Teacher.objects.none())
    student = forms.ModelChoiceField(required=False, queryset=Student.objects.none())
    payment_state = forms.ChoiceField(required=False, choices=[('', 'Barcha to‘lov holatlari'), ('paid', 'To‘lagan'), ('partial', 'Qisman'), ('unpaid', 'To‘lamagan')])
    status = forms.ChoiceField(required=False, label='O‘quvchi holati', choices=[('', 'Barcha holatlar'), *Student.STATUS_CHOICES])
    student_source = forms.ChoiceField(required=False, label='O‘quvchi kelgan manba', choices=[('', 'Barcha manbalar'), *Student.SOURCE_CHOICES])
    registered_from = forms.DateField(required=False, label='Ro‘yxat sanasidan', widget=forms.DateInput(attrs={'type': 'date'}))
    registered_to = forms.DateField(required=False, label='Ro‘yxat sanasigacha', widget=forms.DateInput(attrs={'type': 'date'}))
    service_month = forms.DateField(required=False, input_formats=['%Y-%m'], label='To‘lovning xizmat oyi', widget=forms.DateInput(attrs={'type': 'month'}))
    payment_type = forms.ChoiceField(required=False, choices=[('', 'Barcha to‘lov usullari'), *Payment.PAYMENT_TYPES])
    lead_status = forms.ChoiceField(required=False, choices=[('', 'Barcha murojaat holatlari'), *Lead.STATUS])
    lead_source = forms.ChoiceField(required=False, choices=[('', 'Barcha ariza manbalari'), *Lead.SOURCE])
    assignee_scope = forms.ChoiceField(required=False, choices=[('', 'Barcha mas’ullar'), ('mine', 'Mening arizalarim'), ('unassigned', 'Biriktirilmagan'), ('work', 'Mening navbatim')])
    source = forms.CharField(required=False, max_length=150, label='Reklama manbasi')
    channel = forms.CharField(required=False, max_length=30)
    q = forms.CharField(required=False, max_length=200)

    def __init__(self, data, *, user):
        super().__init__(data=data)
        groups = visible_groups(user)
        self.fields['group'].queryset = groups
        self.fields['branch'].queryset = Branch.objects.filter(Q(groups__in=groups) | Q(student__in=visible_students(user))).distinct()
        self.fields['course'].queryset = Course.objects.filter(groups__in=groups).distinct()
        if not is_teacher(user):
            self.fields['branch'].queryset = Branch.objects.all()
            self.fields['course'].queryset = Course.objects.all()
        self.fields['teacher'].queryset = Teacher.objects.filter(pk=get_teacher(user).pk) if is_teacher(user) else Teacher.objects.all()
        self.fields['student'].queryset = visible_students(user)
        labels = {'period': 'Davr', 'month': 'Oy', 'date_from': 'Boshlanish sanasi', 'date_to': 'Tugash sanasi',
                  'branch': 'Filial', 'course': 'Kurs', 'group': 'Guruh', 'teacher': "O'qituvchi", 'student': "O'quvchi",
                  'payment_state': "To'lov holati", 'payment_type': "To'lov usuli", 'lead_status': 'Murojaat holati',
                  'lead_source': 'Ariza manbasi', 'assignee_scope': 'Mas’ul xodim', 'channel': 'Murojaat kanali', 'q': 'Ism yoki telefon bo‘yicha qidirish',
                  'as_of': 'Qarz hisoblanadigan sana', 'observation_end': 'To‘lov natijasini tekshirish sanasi',
                  'month': 'Aniq oy (davr o‘rniga)', 'service_month': 'To‘lov qaysi oy uchun'}
        for key, label in labels.items():
            self.fields[key].label = label
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-select' if isinstance(field, (forms.ChoiceField, forms.ModelChoiceField)) else 'form-control'

    def basic_fields(self):
        return [self[name] for name in ('period', 'month', 'date_from', 'date_to', 'branch', 'course', 'group', 'teacher', 'student')]

    def advanced_fields(self):
        basic = {field.name for field in self.basic_fields()}
        return [self[name] for name in self.fields if name not in basic]

    def clean(self):
        values = super().clean()
        today = timezone.localdate()
        end = values.get('date_to') or today
        start = values.get('date_from') or end.replace(day=1)
        period = values.get('period')
        if period:
            end = today
            start = {'day': today, 'week': today - timedelta(days=today.weekday()),
                     'month': today.replace(day=1), 'year': today.replace(month=1, day=1)}[period]
        if values.get('month'):
            start = values['month'].replace(day=1)
            end = start.replace(day=monthrange(start.year, start.month)[1])
        if start > end:
            raise forms.ValidationError('Boshlanish sanasi tugash sanasidan keyin bo‘lmasin.')
        as_of = values.get('as_of') or end
        observation_end = values.get('observation_end') or max(end, today)
        if observation_end < end:
            raise forms.ValidationError('Kuzatish sanasi tanlangan davr oxiridan oldin bo‘lmasin.')
        values.update(date_from=start, date_to=end, as_of=as_of, observation_end=observation_end)
        return values

    def serialized(self):
        result = {}
        for key, value in self.cleaned_data.items():
            if value is None or value == '':
                continue
            result[key] = value.isoformat() if isinstance(value, date) else str(value.pk) if hasattr(value, 'pk') else value
            if key == 'service_month':
                result[key] = value.strftime('%Y-%m')
        # Store resolved dates, not a moving "this month" preset.
        result.pop('period', None)
        result.pop('month', None)
        return result


@dataclass
class Sheet:
    title: str
    headers: list
    rows: object


def require_report(user, kind):
    if kind not in REPORT_KINDS or not has_capability(user, 'reports.view'):
        raise PermissionDenied('Hisobotga ruxsat yo‘q.')
    if kind in FINANCIAL_KINDS and not has_capability(user, 'payments.view'):
        raise PermissionDenied('Moliyaviy ma’lumotlarga ruxsat yo‘q.')
    if kind in ('leads', 'tasks') and not has_capability(user, 'leads.manage'):
        raise PermissionDenied('Murojaatlarga ruxsat yo‘q.')
    if kind == 'attendance' and not has_capability(user, 'attendance.view'):
        raise PermissionDenied('Davomatga ruxsat yo‘q.')
    if kind == 'grades' and not has_capability(user, 'grades.view'):
        raise PermissionDenied('Baholarga ruxsat yo‘q.')


class Report:
    def __init__(self, user, kind, params):
        require_report(user, kind)
        self.user, self.kind = user, kind
        self.form = ReportFilterForm(params, user=user)
        if not self.form.is_valid():
            raise ValidationError(self.form.errors.as_json())
        self.filters = self.form.cleaned_data
        self.start, self.end, self.as_of = [self.filters[key] for key in ('date_from', 'date_to', 'as_of')]
        self.observation_end = self.filters['observation_end']
        self.title = REPORT_KINDS[kind]

    def students(self):
        qs = visible_students(self.user)
        f = self.filters
        if f.get('status'):
            qs = qs.filter(status=f['status'])
        if f.get('student_source'):
            qs = qs.filter(source=f['student_source'])
        if f.get('registered_from'):
            qs = qs.filter(registration_date__gte=f['registered_from'])
        if f.get('registered_to'):
            qs = qs.filter(registration_date__lte=f['registered_to'])
        if f.get('student'):
            qs = qs.filter(pk=f['student'].pk)
        if f.get('q'):
            q = f['q']
            qs = qs.filter(Q(name__icontains=q) | Q(phone__icontains=q) | Q(parent_phone__icontains=q) | Q(pk=int(q[4:]) if q.startswith('STU-') and q[4:].isdigit() else -1))
        enrollment_filters = {}
        for field, path in [('branch', 'group__branch'), ('course', 'group__course'), ('group', 'group'), ('teacher', 'group__teacher')]:
            if f.get(field):
                enrollment_filters[f'enrollments__{path}'] = f[field]
        if enrollment_filters:
            qs = qs.filter(**enrollment_filters)
        return qs.distinct().select_related('group', 'teacher', 'branch', 'receptionist').prefetch_related(
            'tariffs', 'enrollments__group__course', 'enrollments__group__branch',
            Prefetch('payments', queryset=Payment.all_objects.prefetch_related('refunds'), to_attr='all_report_payments'),
        ).order_by('name', 'pk')

    def enrollments(self):
        qs = Enrollment.objects.filter(student__in=self.students()).select_related('group__course', 'group__branch', 'student', 'group__teacher')
        if is_teacher(self.user):
            qs = qs.filter(group__teacher=get_teacher(self.user))
        for field, path in [('branch', 'group__branch'), ('course', 'group__course'), ('group', 'group'), ('teacher', 'group__teacher')]:
            if self.filters.get(field):
                qs = qs.filter(**{path: self.filters[field]})
        return qs

    def academic(self, model):
        qs = model.objects.filter(student__in=self.students(), date__range=(self.start, self.end)).select_related('student', 'group__branch', 'group__course', 'group__teacher')
        if is_teacher(self.user):
            qs = qs.filter(group__teacher=get_teacher(self.user))
        for field, path in [('branch', 'group__branch'), ('course', 'group__course'), ('group', 'group'), ('teacher', 'group__teacher')]:
            if self.filters.get(field):
                qs = qs.filter(**{path: self.filters[field]})
        return qs.order_by('date', 'student__name', 'pk')

    def payments(self, all_records=False):
        if not has_capability(self.user, 'payments.view'):
            raise PermissionDenied()
        manager = Payment.all_objects if all_records else Payment.objects
        qs = manager.filter(student__in=visible_students(self.user))
        if self.filters.get('student'):
            qs = qs.filter(student=self.filters['student'])
        if self.filters.get('service_month'):
            qs = qs.filter(month=self.filters['service_month'].replace(day=1))
        if self.filters.get('payment_type'):
            qs = qs.filter(payment_type=self.filters['payment_type'])
        for field, path in [('branch', 'branch_at_payment'), ('course', 'course_at_payment'), ('group', 'group_at_payment'), ('teacher', 'teacher_at_payment')]:
            if self.filters.get(field):
                qs = qs.filter(**{path: self.filters[field]})
        if self.filters.get('q'):
            qs = qs.filter(Q(student__name__icontains=self.filters['q']) | Q(student__phone__icontains=self.filters['q']))
        return qs.select_related('student', 'group_at_payment', 'branch_at_payment', 'course_at_payment', 'received_by').order_by('paid_date', 'pk')

    def leads(self, task=False):
        qs = Lead.objects.filter(status='callback', follow_up_at__date__range=(self.start, self.end)) if task else Lead.all_objects.filter(created_at__date__range=(self.start, self.end))
        qs = qs.select_related('student', 'campaign_record', 'branch')
        for field in ('branch', 'channel'):
            if self.filters.get(field):
                qs = qs.filter(**{field: self.filters[field]})
        if self.filters.get('source'):
            qs = qs.filter(advertising_source=self.filters['source'])
        if self.filters.get('lead_source'):
            qs = qs.filter(source=self.filters['lead_source'])
        if self.filters.get('lead_status'):
            qs = qs.filter(status=self.filters['lead_status'])
        scope = self.filters.get('assignee_scope')
        if scope == 'mine':
            qs = qs.filter(assigned_to=self.user)
        elif scope == 'unassigned':
            qs = qs.filter(assigned_to__isnull=True)
        elif scope == 'work':
            qs = qs.filter(Q(assigned_to=self.user) | Q(assigned_to__isnull=True))
        if self.filters.get('q'):
            qs = qs.filter(Q(name__icontains=self.filters['q']) | Q(phone__icontains=self.filters['q']))
        if self.filters.get('course'):
            qs = qs.filter(course__iexact=self.filters['course'].name)
        if any(self.filters.get(field) for field in ('group', 'teacher', 'student')):
            qs = qs.filter(student__in=self.students())
        paid = Payment.all_objects.filter(student_id=OuterRef('student_id'), amount__gt=0,
                  paid_date__gte=OuterRef('created_at'), paid_date__date__lte=self.observation_end).filter(
                  Q(voided_at__isnull=True) | Q(voided_at__date__gt=self.observation_end))
        return qs.annotate(cohort_paid=Exists(paid)).order_by('created_at', 'pk')

    def account_rows(self, period_only=False):
        allowed = set(self.enrollments().values_list('pk', flat=True))
        groups = visible_groups(self.user)
        for field in ('branch', 'course', 'teacher'):
            if self.filters.get(field):
                groups = groups.filter(**{field: self.filters[field]})
        if self.filters.get('group'):
            groups = groups.filter(pk=self.filters['group'].pk)
        group_ids = set(groups.values_list('pk', flat=True))
        scoped = is_teacher(self.user) or any(self.filters.get(field) for field in ('branch', 'course', 'group', 'teacher'))
        for student in self.students().iterator(chunk_size=200):
            for row in student_accounts(student, self.as_of):
                if scoped and row['group_id'] not in group_ids:
                    continue
                if row['enrollment'] and row['enrollment'].pk not in allowed:
                    continue
                if period_only and not self.start.replace(day=1) <= row['month'] <= self.end.replace(day=1):
                    continue
                if self.filters.get('payment_state') and row['state'] != self.filters['payment_state']:
                    continue
                yield row

    def summary(self):
        enrollments = self.enrollments().filter(status='active', starts_on__lte=self.as_of).filter(Q(ends_on__isnull=True) | Q(ends_on__gte=self.as_of))
        first = Enrollment.objects.filter(student__in=self.students()).values('student_id').annotate(first=Min('starts_on'))
        result = {'active_students': enrollments.values('student_id').distinct().count(), 'active_enrollments': enrollments.count(),
                  'new_students': sum(self.start <= row['first'] <= self.end for row in first)}
        if has_capability(self.user, 'payments.view'):
            payments = self.payments(all_records=True)
            gross = payments.filter(paid_date__date__range=(self.start, self.end)).aggregate(total=Sum('amount'))['total'] or Decimal(0)
            from .finance import with_cancellation_amount
            voids = with_cancellation_amount(payments.filter(
                voided_at__date__range=(self.start, self.end),
            )).aggregate(total=Sum('cancellation_amount'))['total'] or Decimal(0)
            refunds = Refund.objects.filter(payment__in=payments, paid_at__date__range=(self.start, self.end)).aggregate(total=Sum('amount'))['total'] or Decimal(0)
            rows = list(self.account_rows())
            result.update(gross=gross, refunds=refunds, cancellations=voids, net_cash=gross - refunds - voids,
                          overdue=sum((r['balance'] for r in rows if r['due'] < self.as_of), Decimal(0)),
                          due_today=sum((r['balance'] for r in rows if r['due'] == self.as_of), Decimal(0)),
                          advance=sum((r['advance'] for r in rows), Decimal(0)))
        return result

    def cohort(self):
        result = {'valid': 0, 'invalid': 0, 'test': 0, 'paid': 0, 'sources': {}}
        for lead in self.leads().iterator(chunk_size=200):
            if lead.is_test:
                result['test'] += 1
                continue
            if lead.status == 'invalid':
                result['invalid'] += 1
                continue
            result['valid'] += 1
            paid = bool(lead.student_id and lead.cohort_paid)
            result['paid'] += int(paid)
            key = (lead.channel or 'Noma’lum', lead.advertising_source or 'Noma’lum')
            item = result['sources'].setdefault(key, {'channel': key[0], 'source': key[1], 'valid': 0, 'paid': 0, 'stages': {}})
            item['valid'] += 1
            item['paid'] += int(paid)
            item['stages'][lead.get_status_display()] = item['stages'].get(lead.get_status_display(), 0) + 1
        result['conversion'] = (Decimal(result['paid']) * 100 / result['valid']).quantize(Decimal('0.01')) if result['valid'] else Decimal(0)
        result['sources'] = list(result['sources'].values())
        return result

    def academic_summary(self):
        result = {}
        if has_capability(self.user, 'attendance.view'):
            attendance = self.academic(Attendance)
            marked = attendance.count()
            attended = attendance.filter(status__in=['present', 'late']).count()
            result.update(marked=marked, present=attendance.filter(status='present').count(),
                          late=attendance.filter(status='late').count(), absent=attendance.filter(status='absent').count(),
                          excused=attendance.filter(status='excused').count(),
                          attendance_percent=(Decimal(attended) * 100 / marked).quantize(Decimal('0.01')) if marked else None)
        if has_capability(self.user, 'grades.view'):
            grades = self.academic(Grade)
            result.update(grades_count=grades.count(), average_score=grades.aggregate(average=Avg('score'))['average'])
        return result

    def estimate(self):
        if self.kind in ('attendance', 'grades'):
            return self.academic(Attendance if self.kind == 'attendance' else Grade).count()
        if self.kind == 'payments':
            return self.payments().filter(paid_date__date__range=(self.start, self.end)).count()
        if self.kind in ('leads', 'tasks'):
            return self.leads(task=self.kind == 'tasks').count()
        if self.kind == 'refunds':
            return Refund.objects.filter(payment__in=self.payments(all_records=True), paid_at__date__range=(self.start, self.end)).count()
        if self.kind == 'groups':
            return visible_groups(self.user).count()
        if self.kind in ('accounts', 'advances'):
            starts = list(self.students().values_list('registration_date', flat=True))
            starts.extend(self.enrollments().filter(mirrors_student=False).values_list('starts_on', flat=True))
            return sum(max(0, (self.as_of.year - started.year) * 12 + self.as_of.month - started.month + 1) for started in starts) + self.payments().count()
        if self.kind == 'student':
            payments = self.payments().filter(paid_date__date__range=(self.start, self.end)).count() if has_capability(self.user, 'payments.view') else 0
            return self.academic(Attendance).count() + self.academic(Grade).count() + payments + 1
        return self.students().count()

    def sheets(self):
        kind = self.kind
        if kind == 'student':
            if not self.filters.get('student'):
                raise ValidationError('Bitta o‘quvchini tanlang.')
            sheets = [self._students_sheet()]
            if has_capability(self.user, 'attendance.view'):
                sheets.append(self._attendance_sheet())
            if has_capability(self.user, 'grades.view'):
                sheets.append(self._grades_sheet())
            if has_capability(self.user, 'payments.view'):
                sheets.append(self._payments_sheet())
            return sheets
        if kind == 'students':
            return [self._students_sheet()]
        if kind == 'attendance':
            return [self._attendance_sheet()]
        if kind == 'grades':
            return [self._grades_sheet()]
        if kind == 'payments':
            return [self._payments_sheet()]
        if kind in ('accounts', 'advances'):
            def rows():
                for r in self.account_rows(period_only=kind == 'accounts'):
                    if kind == 'advances' and r['advance'] <= 0:
                        continue
                    yield [r['student'].student_number, r['student'].name, r['group'], r['month'], r['due'], r['fee'], r['paid'], r['balance'], r['advance'], {'paid': 'To‘lagan', 'partial': 'Qisman', 'unpaid': 'To‘lamagan'}[r['state']]]
            return [Sheet(self.title, ['O‘quvchi raqami', 'Ism', 'Guruh', 'Oy', 'Muddat', 'Hisob', 'To‘langan', 'Qoldiq', 'Avans', 'Holat'], rows())]
        if kind == 'refunds':
            qs = Refund.objects.filter(payment__in=self.payments(all_records=True), paid_at__date__range=(self.start, self.end)).select_related('payment__student', 'created_by')
            return [Sheet(self.title, ['O‘quvchi', 'To‘lov raqami', 'Summa', 'Vaqt', 'Sabab', 'Xodim'],
                          ([r.payment.student.name, r.payment.receipt_number, r.amount, timezone.localtime(r.paid_at), r.reason, r.created_by.username] for r in qs.iterator()))]
        if kind == 'groups':
            qs = visible_groups(self.user)
            for field in ('branch', 'course', 'teacher'):
                if self.filters.get(field):
                    qs = qs.filter(**{field: self.filters[field]})
            if self.filters.get('group'):
                qs = qs.filter(pk=self.filters['group'].pk)
            return [Sheet(self.title, ['Guruh', 'Kurs', 'Filial', 'O‘qituvchi', 'Sig‘im', 'Faol yozilishlar', 'Bo‘sh joy'],
                          ([g.name, str(g.course or ''), str(g.branch or ''), str(g.teacher or ''), g.max_students, g.get_student_count(), max(0, g.max_students - g.get_student_count())] for g in qs.select_related('course', 'branch', 'teacher').iterator()))]
        leads = self.leads(task=kind == 'tasks')
        sheets = [Sheet(self.title, ['Ariza', 'Ism', 'Telefon', 'Kurs', 'Kanal', 'Reklama manbasi', 'Holat', 'Yaratildi', 'Keyingi aloqa'],
                      ([lead.pk, lead.name, lead.phone, lead.course, lead.channel or '', lead.advertising_source or '', lead.get_status_display(), timezone.localtime(lead.created_at), timezone.localtime(lead.follow_up_at) if lead.follow_up_at else ''] for lead in leads.iterator()))]
        if kind == 'leads':
            cohort = self.cohort()
            sheets.append(Sheet('Kohorta', ['Haqiqiy arizalar', 'Noto‘g‘ri', 'Test', 'To‘lovli', 'Konversiya %', 'Kuzatish oxiri'],
                          [[cohort['valid'], cohort['invalid'], cohort['test'], cohort['paid'], cohort['conversion'], self.observation_end]]))
            sheets.append(Sheet('Manbalar va bosqichlar', ['Kanal', 'Reklama manbasi', 'Haqiqiy arizalar', 'To‘lovli', 'Bosqichlar'],
                          ([item['channel'], item['source'], item['valid'], item['paid'], '; '.join(f'{stage}: {count}' for stage, count in item['stages'].items())] for item in cohort['sources'])))
        return sheets

    def _students_sheet(self):
        return Sheet("O'quvchilar", ['UUID', 'O‘quvchi raqami', 'Ism', 'Telefon', 'Ota-ona telefoni', 'Filial', 'Holat', 'Ro‘yxat sanasi', 'Tug‘ilgan sana', 'Izoh'],
                     ([str(s.public_id), s.student_number, s.name, s.phone, s.parent_phone, str(s.branch or ''), s.get_status_display(), s.registration_date, s.birth_date, s.notes] for s in self.students().iterator(chunk_size=200)))

    def _attendance_sheet(self):
        return Sheet('Davomat', ['O‘quvchi raqami', 'Ism', 'Guruh', 'Sana', 'Holat', 'Izoh'],
                     ([r.student.student_number, r.student.name, r.group.name, r.date, r.get_status_display(), r.note] for r in self.academic(Attendance).iterator()))

    def _grades_sheet(self):
        return Sheet('Baholar', ['O‘quvchi raqami', 'Ism', 'Guruh', 'Sana', 'Baho turi', 'Ball', 'Izoh'],
                     ([r.student.student_number, r.student.name, r.group.name, r.date, r.get_grade_type_display(), r.score, r.note] for r in self.academic(Grade).iterator()))

    def _payments_sheet(self):
        return Sheet('To‘lovlar', ['Chek', 'O‘quvchi raqami', 'Ism', 'Summa', 'Xizmat oyi', 'Pul tushgan vaqt', 'Usul', 'Guruh', 'Kurs', 'Filial', 'Xodim'],
                     ([r.receipt_number, r.student.student_number, r.student.name, r.amount, r.month, timezone.localtime(r.paid_date), r.get_payment_type_display(), str(r.group_at_payment or ''), str(r.course_at_payment or ''), str(r.branch_at_payment or ''), str(r.received_by or '')] for r in self.payments().filter(paid_date__date__range=(self.start, self.end)).iterator()))
