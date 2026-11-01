import logging
from decimal import Decimal, InvalidOperation

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from core.client_ip import get_client_ip
from web.models import ServiceInquiry

logger = logging.getLogger(__name__)

# Ochrana proti spamu: nejvýš 5 poptávek za hodinu z jedné IP adresy
INQUIRY_LIMIT = 5
INQUIRY_LIMIT_WINDOW = 60 * 60


def _error(message, status=400):
    return JsonResponse({'status': 'error', 'message': message}, status=status)


@require_POST
def submit_inquiry_view(request):
    """Interaktivní příjem poptávky/kalkulace z homepage bez nutnosti reloadu stránky."""
    contact_name = request.POST.get('contact_name', '').strip()
    success = JsonResponse({
        'status': 'success',
        'message': f'Děkujeme, pane/paní {contact_name}. Poptávka byla předána dispečinku. Ozveme se vám do 30 minut.'
    })

    # Skryté pole, které člověk nevidí – vyplní ho jen robot. Tváříme se, že vše prošlo.
    if request.POST.get('website'):
        logger.info("Poptávka zahozena (honeypot), IP %s", get_client_ip(request))
        return success

    rate_key = f"inquiry-rate:{get_client_ip(request)}"
    cache.add(rate_key, 0, INQUIRY_LIMIT_WINDOW)
    if cache.incr(rate_key) > INQUIRY_LIMIT:
        return _error('Odeslali jste příliš mnoho poptávek. Zavolejte nám prosím přímo na dispečink.', status=429)

    service_type = request.POST.get('service_type', ServiceInquiry.SERVICE_PHYSICAL)
    phone = request.POST.get('phone', '').strip()
    email = request.POST.get('email', '').strip()
    company_name = request.POST.get('company_name', '').strip()
    object_location = request.POST.get('object_location', '').strip()
    message = request.POST.get('message', '').strip()

    if not contact_name or not phone:
        return _error('Vyplňte prosím alespoň jméno a telefonní kontakt.')
    if service_type not in dict(ServiceInquiry.SERVICE_CHOICES):
        return _error('Neplatný typ služby.')
    if len(contact_name) > 100 or len(phone) > 30 or len(company_name) > 150 \
            or len(object_location) > 150 or len(message) > 5000:
        return _error('Některý z údajů je příliš dlouhý.')
    if email:
        try:
            validate_email(email)
        except ValidationError:
            return _error('Zkontrolujte prosím e-mailovou adresu.')

    hours_str = request.POST.get('estimated_hours_weekly', '')
    hours = int(hours_str) if hours_str.isdigit() and int(hours_str) <= 168 else None

    try:
        estimate = Decimal(request.POST.get('calculated_estimate_czk') or '')
        if not estimate.is_finite() or not 0 <= estimate < Decimal('1e10'):
            estimate = None
    except InvalidOperation:
        estimate = None

    try:
        ServiceInquiry.objects.create(
            service_type=service_type,
            contact_name=contact_name,
            phone=phone,
            email=email,
            company_name=company_name,
            object_location=object_location,
            estimated_hours_weekly=hours,
            calculated_estimate_czk=estimate,
            message=message,
        )
    except Exception:
        logger.exception("Nepodařilo se uložit poptávku z webu")
        return _error('Poptávku se nepodařilo odeslat. Zavolejte nám prosím přímo na dispečink.', status=500)

    return success
