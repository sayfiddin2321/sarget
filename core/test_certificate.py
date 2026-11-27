from datetime import date
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from django.utils import timezone
from .models import Student, Teacher, Group, Certificate, CertificateSetting, generate_unique_certificate_number
from .forms import CertificateForm


class CertificateTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('admin_user', 'admin@example.com', 'pass123')
        self.teacher_user = User.objects.create_user('teacher_user', 't@example.com', 'pass123')
        self.teacher = Teacher.objects.create(user=self.teacher_user, name="Aziz Rahimov", phone="+998901112233", subject="Python")
        self.group = Group.objects.create(
            name="Python Backend",
            teacher=self.teacher,
            days="1-3-5",
            start_time="10:00",
            end_time="12:00",
            monthly_fee=600000
        )
        self.student = Student.objects.create(
            name="Ali Valiyev",
            phone="+998901234567",
            group=self.group,
            teacher=self.teacher,
            status="active"
        )
        self.client = Client()

    def test_unique_certificate_number_generation(self):
        num1 = generate_unique_certificate_number()
        cert1 = Certificate.objects.create(
            student=self.student,
            certificate_number=num1,
            course_name="Python Backend",
            teacher_name="Aziz Rahimov"
        )
        num2 = generate_unique_certificate_number()
        self.assertNotEqual(num1, num2)

        cert2 = Certificate.objects.create(
            student=self.student,
            course_name="Frontend React",
            teacher_name="Aziz Rahimov"
        )
        self.assertTrue(cert2.certificate_number.startswith("SAR-"))
        self.assertNotEqual(cert1.certificate_number, cert2.certificate_number)
        self.assertIsNotNone(cert2.verification_code)

    def test_certificate_list_authenticated(self):
        self.client.force_login(self.admin)
        cert = Certificate.objects.create(
            student=self.student,
            course_name="Python Backend",
            teacher_name="Aziz Rahimov"
        )
        response = self.client.get(reverse('certificate_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, cert.certificate_number)
        self.assertContains(response, "Ali Valiyev")

    def test_certificate_create_view(self):
        self.client.force_login(self.admin)
        url = reverse('certificate_create')
        response = self.client.get(url, {'student': self.student.pk})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Python Backend")

        post_data = {
            'student': self.student.pk,
            'certificate_number': 'SAR-2026-99999',
            'course_name': 'Full Stack Web Development',
            'group': self.group.pk,
            'teacher_name': 'Aziz Rahimov',
            'grade_text': "A'lo (98 ball)",
            'issue_date': str(timezone.localdate()),
            'status': 'active',
            'description': 'Django va React bo\'yicha a\'lo baholarga tamomladi.',
        }
        post_resp = self.client.post(url, post_data)
        cert = Certificate.objects.filter(certificate_number='SAR-2026-99999').first()
        self.assertIsNotNone(cert)
        self.assertEqual(cert.student, self.student)
        self.assertEqual(cert.grade_text, "A'lo (98 ball)")
        self.assertRedirects(post_resp, reverse('certificate_detail', args=[cert.pk]))

    def test_certificate_detail_view(self):
        self.client.force_login(self.admin)
        cert = Certificate.objects.create(
            student=self.student,
            course_name="Python Backend",
            teacher_name="Aziz Rahimov",
            grade_text="A'lo",
            start_date=date(2026, 9, 25),
            end_date=date(2026, 11, 25),
        )
        url = reverse('certificate_detail', args=[cert.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, cert.certificate_number)
        self.assertContains(response, "Ali Valiyev")
        self.assertContains(response, "Python Backend")
        self.assertContains(response, "Aziz Rahimov")
        self.assertContains(response, 'size: A4 landscape')
        self.assertContains(response, 'width: 297mm !important')
        self.assertContains(response, 'height: 210mm !important')
        self.assertContains(response, 'certificate-print-mode')
        self.assertContains(response, '.notification-center, .notification-toasts')
        self.assertContains(response, 'certificate-capture-mode')
        self.assertContains(response, 'onclone:')
        self.assertContains(response, 'display: block !important')
        self.assertContains(response, 'overflow: visible !important')
        self.assertContains(response, 'O\'qish davri:')
        self.assertContains(response, 'font-size: 0.92rem !important')
        self.assertContains(response, 'justify-content: flex-start !important')
        self.assertContains(response, 'font-size: 2.38rem !important')
        self.assertContains(response, 'width: 460px !important')
        self.assertContains(response, 'white-space: nowrap !important')
        self.assertContains(response, '#17365d')
        self.assertContains(response, 'cert-geometric-bg')

    def test_public_qr_verification_valid_certificate(self):
        cert = Certificate.objects.create(
            student=self.student,
            course_name="Python Backend",
            teacher_name="Aziz Rahimov",
            grade_text="A'lo (95 ball)"
        )
        # Verify without login (anonymous smartphone camera scanner)
        anon_client = Client()
        verify_url = reverse('certificate_verify', args=[cert.certificate_number])
        response = anon_client.get(verify_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "RASMIY SERTIFIKAT TASDIQLANDI")
        self.assertContains(response, "Ali Valiyev")
        self.assertContains(response, cert.certificate_number)
        self.assertContains(response, "Python Backend")
        self.assertContains(response, "Aziz Rahimov")

        # Also verify by UUID
        verify_uuid_url = reverse('certificate_verify', args=[str(cert.verification_code)])
        response_uuid = anon_client.get(verify_uuid_url)
        self.assertEqual(response_uuid.status_code, 200)
        self.assertContains(response_uuid, "Ali Valiyev")

    def test_public_qr_verification_nonexistent_certificate(self):
        anon_client = Client()
        fake_url = reverse('certificate_verify', args=['SAR-FAKE-00000'])
        response = anon_client.get(fake_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "SERTIFIKAT TOPILMADI")
        self.assertContains(response, "SAR-FAKE-00000")

    def test_student_detail_shows_certificates(self):
        self.client.force_login(self.admin)
        cert = Certificate.objects.create(
            student=self.student,
            course_name="Python Backend",
            teacher_name="Aziz Rahimov"
        )
        url = reverse('student_detail', args=[self.student.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sertifikat berish")
        self.assertContains(response, cert.certificate_number)

    def test_certificate_study_period_and_validation(self):
        # 1. Test study_period_display property
        cert = Certificate.objects.create(
            student=self.student,
            course_name="Python Backend",
            teacher_name="Aziz Rahimov",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 2, 28)
        )
        self.assertEqual(cert.study_period_display, "01.09.2025 — 28.02.2026")

        cert_start_only = Certificate.objects.create(
            student=self.student,
            course_name="Frontend",
            start_date=date(2026, 1, 1)
        )
        self.assertEqual(cert_start_only.study_period_display, "01.01.2026 dan")

        cert_end_only = Certificate.objects.create(
            student=self.student,
            course_name="DevOps",
            end_date=date(2026, 5, 30)
        )
        self.assertEqual(cert_end_only.study_period_display, "30.05.2026 gacha")

        # 2. Test form validation when end_date < start_date
        form_data = {
            'student': self.student.pk,
            'certificate_number': 'SAR-2026-TEST1',
            'course_name': 'Design',
            'issue_date': str(timezone.localdate()),
            'status': 'active',
            'start_date': '2026-06-01',
            'end_date': '2026-01-01',  # invalid: before start_date
        }
        form = CertificateForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('end_date', form.errors)

    def test_certificate_settings_model_and_view(self):
        # 1. Model defaults
        setting = CertificateSetting.get_settings()
        self.assertEqual(setting.certificate_prefix, 'SAR')
        self.assertTrue('SARGET' in setting.academy_name.upper())

        # 2. View access by admin
        self.client.force_login(self.admin)
        url = reverse('certificate_settings')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sertifikat sozlamalari")

        # 3. Post updates
        post_data = {
            'academy_name': 'INNOVATIVE ACADEMY',
            'academy_subtitle': 'Zamonaviy kasblar markazi',
            'title_uz': 'BITIRUV SERTIFIKATI',
            'title_en': 'GRADUATION CERTIFICATE',
            'statement_text': 'ushbu dasturni muvaffaqiyatli tamomladi',
            'director_title': 'Akademiya direktori',
            'director_name': 'Jasur Aliyev',
            'instructor_default_title': 'Bosh instruktor',
            'seal_text_top': 'INNOVATIVE ACADEMY',
            'seal_text_mid': 'VERIFIED',
            'seal_text_bot': 'OFFICIAL',
            'certificate_prefix': 'INV',
            'accent_color': '#2563eb',
            'footer_note': 'Rasmiy reestr',
            'show_study_period': True,
            'show_grade': True,
        }
        post_resp = self.client.post(url, post_data)
        self.assertRedirects(post_resp, url)

        # Refresh setting
        setting.refresh_from_db()
        self.assertEqual(setting.academy_name, 'INNOVATIVE ACADEMY')
        self.assertEqual(setting.certificate_prefix, 'INV')

        # Test generated number prefix now matches setting
        new_num = generate_unique_certificate_number()
        self.assertTrue(new_num.startswith('INV-'))

        # Test detail view reflects new academy name
        cert = Certificate.objects.create(
            student=self.student,
            course_name="Python Backend",
            teacher_name="Aziz Rahimov",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 2, 28)
        )
        detail_resp = self.client.get(reverse('certificate_detail', args=[cert.pk]))
        self.assertContains(detail_resp, 'INNOVATIVE ACADEMY')
        self.assertContains(detail_resp, '01.09.2025 — 28.02.2026')

        # Test verify view reflects new academy name and study period
        verify_resp = self.client.get(reverse('certificate_verify', args=[cert.certificate_number]))
        self.assertContains(verify_resp, 'INNOVATIVE ACADEMY')
        self.assertContains(verify_resp, '01.09.2025 — 28.02.2026')


