from datetime import date, time
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Attendance, Certificate, Grade, Group, Payment, Receptionist, Refund, Salary, StaffCapability, Student, Teacher
from .permissions import CAPABILITIES, RECEPTIONIST_OWN_SALARY, TEACHER_OWN_SALARY, assignable_capabilities


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class StaffPermissionsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model()
        cls.admin = users.objects.create_superuser('permissions-admin', 'admin@example.test', 'secret')
        cls.teacher_user = users.objects.create_user('permissions-teacher')
        cls.rec_user = users.objects.create_user('permissions-receptionist')
        cls.teacher = Teacher.objects.create(user=cls.teacher_user, name='Own teacher')
        cls.other_teacher = Teacher.objects.create(name='Other teacher')
        cls.rec = Receptionist.objects.create(user=cls.rec_user, name='Reception')
        cls.group = Group.objects.create(name='Own group', teacher=cls.teacher, monthly_fee=500000,
                                         start_time=time(9), end_time=time(10))
        cls.other_group = Group.objects.create(name='Other group', teacher=cls.other_teacher, monthly_fee=500000,
                                               start_time=time(11), end_time=time(12))
        cls.student = Student.objects.create(name='Own student', phone='+998901234567', teacher=cls.teacher, group=cls.group)
        cls.other_student = Student.objects.create(name='Other student', phone='+998901234568', teacher=cls.other_teacher,
                                                   group=cls.other_group)

    def grant(self, user, *codes):
        self.client.force_login(self.admin)
        response = self.client.post(reverse('staff_permissions'), {'user': user.pk, 'capabilities': codes})
        self.assertEqual(response.status_code, 302)
        self.client.force_login(user)

    def test_permission_editor_exposes_all_assignable_actions_for_both_roles(self):
        self.client.force_login(self.admin)
        for user, role in ((self.teacher_user, 'teacher'), (self.rec_user, 'receptionist')):
            response = self.client.get(reverse('staff_permissions'), {'user': user.pk})
            codes = {row['code'] for row in response.context['permission_rows']}
            self.assertEqual(codes, assignable_capabilities(role))
            self.assertTrue({'payments.accept', 'groups.create', 'groups.edit', 'courses.create',
                             'expenses.create', 'salary.teacher.manage'}.issubset(codes))
            self.assertIn(TEACHER_OWN_SALARY if role == 'teacher' else RECEPTIONIST_OWN_SALARY, codes)

    def test_mobile_navigation_shows_payment_receiving_only_for_authorized_users(self):
        self.client.force_login(self.teacher_user)
        response = self.client.get(reverse('dashboard'))
        payment_url = f'href="{reverse("payment_create")}"'
        self.assertNotContains(response, payment_url)

        self.grant(self.teacher_user, 'payments.accept')
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, payment_url)
        self.assertContains(response, 'mobile-nav--payments')

    def test_group_create_edit_and_revoke_work_for_both_roles(self):
        for index, user in enumerate((self.teacher_user, self.rec_user)):
            self.client.force_login(user)
            self.assertEqual(self.client.get(reverse('group_create')).status_code, 403)
            self.grant(user, 'groups.create', 'groups.edit', 'groups.delete')
            response = self.client.get(reverse('group_list'))
            self.assertContains(response, reverse('group_create'))
            response = self.client.post(reverse('group_create'), {
                'name': f'Created group {index}', 'teacher': self.other_teacher.pk,
                'days': self.group.days, 'start_time': '14:00', 'end_time': '15:00',
                'monthly_fee': '250000', 'max_students': 20, 'is_active': 'on',
            })
            self.assertEqual(response.status_code, 302, getattr(response, 'context', None))
            created = Group.objects.get(name=f'Created group {index}')
            self.assertEqual(created.teacher_id, self.teacher.pk if index == 0 else self.other_teacher.pk)
            self.assertEqual(self.client.get(reverse('group_edit', args=[created.pk])).status_code, 200)
            if index == 0:
                self.assertEqual(self.client.get(reverse('group_edit', args=[self.other_group.pk])).status_code, 404)
                self.assertEqual(self.client.post(reverse('group_delete', args=[self.other_group.pk])).status_code, 404)
            self.grant(user)
            self.assertEqual(self.client.post(reverse('group_delete', args=[created.pk])).status_code, 403)
            self.assertTrue(Group.objects.filter(pk=created.pk).exists())

    def test_teacher_can_accept_edit_refund_and_void_only_visible_payments(self):
        self.grant(self.teacher_user, 'payments.accept', 'payments.edit', 'payments.refund', 'payments.void')
        self.assertTrue(StaffCapability.objects.get(user=self.teacher_user, code='payments.view').allowed)
        self.assertTrue(StaffCapability.objects.get(user=self.teacher_user, code='students.view').allowed)
        response = self.client.post(reverse('payment_create'), {
            'student': self.student.pk, 'amount': '100000', 'month': '2026-10', 'payment_type': 'cash',
        })
        self.assertEqual(response.status_code, 302)
        payment = Payment.objects.get(student=self.student)
        self.assertEqual(payment.received_by_id, self.teacher_user.pk)
        response = self.client.post(reverse('payment_edit', args=[payment.pk]), {
            'student': self.student.pk, 'amount': '150000', 'month': '2026-10', 'payment_type': 'cash',
        })
        self.assertEqual(response.status_code, 302)
        payment.refresh_from_db()
        self.assertEqual(payment.amount, Decimal('150000'))
        response = self.client.post(reverse('refund_create', args=[payment.pk]), {'amount': '20000', 'reason': 'Returned'})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Refund.objects.filter(payment=payment, amount=20000).exists())
        foreign = Payment.objects.create(student=self.other_student, amount=100000, month=date(2026, 10, 1))
        for route in ('payment_receipt', 'payment_edit', 'payment_delete', 'refund_create'):
            self.assertEqual(self.client.get(reverse(route, args=[foreign.pk])).status_code, 404, route)
        response = self.client.post(reverse('payment_create'), {
            'student': self.other_student.pk, 'amount': '10000', 'month': '2026-10', 'payment_type': 'cash',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Payment.objects.filter(student=self.other_student).count(), 1)
        to_void = Payment.objects.create(student=self.student, amount=10000, month=date(2026, 10, 1))
        self.assertEqual(self.client.post(reverse('payment_delete', args=[to_void.pk]), {'reason': 'Duplicate'}).status_code, 302)
        to_void.refresh_from_db()
        self.assertIsNotNone(to_void.voided_at)
        self.grant(self.teacher_user)
        self.assertEqual(self.client.get(reverse('payment_list')).status_code, 403)
        self.assertEqual(self.client.post(reverse('payment_create'), {}).status_code, 403)

    def test_salary_visibility_and_management_are_separate(self):
        salary = Salary.objects.create(teacher=self.other_teacher, month=date(2026, 10, 1),
                                       total_income=100000, percent=40, salary_amount=40000)
        self.grant(self.rec_user, 'salary.teacher.view')
        response = self.client.get(reverse('salary_list'))
        self.assertContains(response, 'Other teacher')
        self.assertNotContains(response, reverse('calculate_salaries'))
        self.assertEqual(self.client.post(reverse('update_salary_status', args=[salary.pk])).status_code, 403)
        self.grant(self.rec_user, 'salary.teacher.manage')
        response = self.client.get(reverse('salary_list'))
        self.assertContains(response, reverse('calculate_salaries'))
        self.assertEqual(self.client.post(reverse('update_salary_status', args=[salary.pk])).status_code, 302)
        salary.refresh_from_db()
        self.assertTrue(salary.is_paid)

    def test_all_delegated_business_pages_render_and_staff_cannot_escalate_permissions(self):
        for user in (self.teacher_user, self.rec_user):
            self.grant(user, *CAPABILITIES)
            for route in ('teacher_list', 'teacher_create', 'receptionist_list', 'receptionist_create',
                          'course_list', 'course_create', 'group_list', 'group_create', 'payment_list',
                          'payment_create', 'salary_list', 'receptionist_salary_list', 'calculate_salaries',
                          'calculate_receptionist_salaries', 'expense_list', 'expense_create', 'assignment_history',
                          'reports', 'report_settings', 'financial_history', 'system_status', 'certificate_settings', 'lead_list'):
                response = self.client.get(reverse(route))
                self.assertEqual(response.status_code, 200, (user.username, route))
            self.assertEqual(self.client.post(reverse('staff_permissions'), {
                'user': user.pk, 'capabilities': list(CAPABILITIES),
            }).status_code, 302)
            self.assertEqual(self.client.get(reverse('financial_migration')).status_code, 302)

    def test_read_only_lists_hide_mutation_buttons(self):
        self.grant(self.rec_user, 'teachers.view', 'receptionists.view', 'courses.view', 'groups.view', 'expenses.view', 'payments.view')
        for page, create in (('teacher_list', 'teacher_create'), ('receptionist_list', 'receptionist_create'),
                             ('course_list', 'course_create'), ('group_list', 'group_create'),
                             ('expense_list', 'expense_create'), ('payment_list', 'payment_create')):
            self.assertNotContains(self.client.get(reverse(page)), reverse(create))
            self.assertEqual(self.client.post(reverse(create), {}).status_code, 403)

    def test_receptionist_can_mark_attendance_and_grades_when_granted(self):
        self.grant(self.rec_user, 'attendance.write', 'grades.write', 'grades.delete')
        response = self.client.post(reverse('take_attendance', args=[self.group.pk]), {
            f'attendance_{self.student.pk}': 'present',
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Attendance.objects.filter(student=self.student, status='present').exists())
        response = self.client.post(reverse('take_grades', args=[self.group.pk]), {
            f'score_{self.student.pk}': '92', 'grade_type': 'classwork',
        })
        self.assertEqual(response.status_code, 302)
        grade = Grade.objects.get(student=self.student)
        self.assertEqual(grade.score, 92)
        self.assertEqual(self.client.post(reverse('grade_delete', args=[grade.pk])).status_code, 302)
        self.assertFalse(Grade.objects.filter(pk=grade.pk).exists())

    def test_teacher_certificate_permissions_preserve_object_scope(self):
        own = Certificate.objects.create(student=self.student, group=self.group, course_name='Python')
        foreign = Certificate.objects.create(student=self.other_student, group=self.other_group, course_name='English')
        self.client.force_login(self.teacher_user)
        self.assertEqual(self.client.get(reverse('certificate_edit', args=[own.pk])).status_code, 403)
        self.grant(self.teacher_user, 'certificates.create', 'certificates.edit', 'certificates.delete')
        response = self.client.get(reverse('certificate_create'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context['form'].fields['student'].queryset), [self.student])
        self.assertEqual(self.client.get(reverse('certificate_edit', args=[own.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse('certificate_edit', args=[foreign.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('certificate_delete', args=[foreign.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('certificate_delete', args=[own.pk])).status_code, 302)
        self.assertFalse(Certificate.objects.filter(pk=own.pk).exists())

    def test_new_certificate_controls_preserve_existing_revocations(self):
        StaffCapability.objects.create(user=self.rec_user, code='students.create', allowed=False)
        self.client.force_login(self.rec_user)
        self.assertEqual(self.client.get(reverse('certificate_create')).status_code, 403)
        self.grant(self.rec_user, 'certificates.create')
        self.assertEqual(self.client.get(reverse('certificate_create')).status_code, 200)
