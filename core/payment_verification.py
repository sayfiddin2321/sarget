"""Public receipt verification through signed, non-enumerable links."""
import base64
import socket
from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO

import qrcode

from django.conf import settings
from django.core import signing
from django.db.models import Sum
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.cache import never_cache

from .models import Payment

SALT = 'sarget.receipt.verification.v1'


def receipt_amount_text(amount):
    return f"{amount.quantize(Decimal('1'), rounding=ROUND_HALF_UP):,.0f}".replace(',', ' ')


def get_local_lan_ip():
    """Mahalliy tarmoqdagi (Wi-Fi) IP manzilni aniqlash."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'


def receipt_qr_png(url):
    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=4
    )
    qr.add_data(url)
    qr.make(fit=True)
    output = BytesIO()
    qr.make_image(fill_color='black', back_color='white').save(output, format='PNG')
    return output.getvalue()


def qr_image_data_uri(url):
    """HTML ga to'g'ridan-to'g'ri o'rnatish uchun Base64 PNG."""
    png_bytes = receipt_qr_png(url)
    b64 = base64.b64encode(png_bytes).decode('ascii')
    return f"data:image/png;base64,{b64}"


@never_cache
def payment_qr(request, token):
    try:
        pk = signing.loads(token, salt=SALT)
    except (signing.BadSignature, ValueError, TypeError):
        return HttpResponse(status=404)
    if not isinstance(pk, int) or not Payment.all_objects.filter(pk=pk).exists():
        return HttpResponse(status=404)
    payment = Payment.all_objects.get(pk=pk)
    url = verification_url(request, payment)
    response = HttpResponse(receipt_qr_png(url), content_type='image/png')
    response['X-Robots-Tag'] = 'noindex, nofollow'
    response['X-Content-Type-Options'] = 'nosniff'
    return response


def qr_image_url(payment):
    return reverse('payment_qr', args=[signing.dumps(payment.pk, salt=SALT)])


def verification_url(request, payment):
    token = signing.dumps(payment.pk, salt=SALT)
    path = reverse('payment_verify', args=[token])

    # 1. Agar .env yoki settings da public domen berilgan bo'lsa
    base_url = (
        getattr(settings, 'QR_VERIFY_BASE_URL', '') or
        getattr(settings, 'SITE_URL', '') or
        getattr(settings, 'TELEGRAM_PUBLIC_URL', '')
    )
    if base_url:
        return f"{base_url.rstrip('/')}{path}"

    if request is not None:
        host = request.get_host()
        # 2. Agar localhost yoki 127.0.0.1 bo'lsa, telefon skaner qila olishi uchun LAN IP ni ulaymiz
        if 'localhost' in host or '127.0.0.1' in host:
            lan_ip = get_local_lan_ip()
            if lan_ip and lan_ip != '127.0.0.1':
                port = request.get_port()
                port_str = f":{port}" if port and str(port) not in ('80', '443') else ""
                return f"{request.scheme}://{lan_ip}{port_str}{path}"
        return request.build_absolute_uri(path)

    return path


@never_cache
def payment_verify(request, token):
    payment = None
    try:
        pk = signing.loads(token, salt=SALT)
        if isinstance(pk, int):
            payment = Payment.all_objects.select_related(
                'student', 'student__group', 'student__teacher', 'received_by'
            ).filter(pk=pk).first()
    except (signing.BadSignature, ValueError, TypeError):
        pass
    refunded = Decimal(0)
    if payment:
        refunded = payment.refunds.aggregate(total=Sum('amount'))['total'] or Decimal(0)
    state = ('invalid' if payment is None else 'void' if payment.voided_at else
             'refunded' if refunded >= payment.amount else 'partial_refund' if refunded else 'paid')
    response = render(request, 'core/payment_verify.html', {
        'payment': payment,
        'state': state,
        'refunded': refunded,
        'net': payment.amount - refunded if payment else 0,
        'receipt_amount': receipt_amount_text(payment.amount) if payment else '',
        'refunded_amount': receipt_amount_text(refunded),
        'net_amount': receipt_amount_text(payment.amount - refunded) if payment else '',
    }, status=404 if payment is None else 200)
    response['X-Robots-Tag'] = 'noindex, nofollow'
    response['Referrer-Policy'] = 'no-referrer'
    return response
