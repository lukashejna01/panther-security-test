from django.http import JsonResponse
from django.views.decorators.http import require_POST
from decimal import Decimal
from web.models import ServiceInquiry


@require_POST
def submit_inquiry_view(request):
    """Interaktivní příjem poptávky/kalkulace z homepage bez nutnosti reloadu stránky."""
    try:
        service_type = request.POST.get('service_type', ServiceInquiry.SERVICE_PHYSICAL)
        contact_name = request.POST.get('contact_name', '').strip()
        phone = request.POST.get('phone', '').strip()
        email = request.POST.get('email', '').strip()
        company_name = request.POST.get('company_name', '').strip()
        object_location = request.POST.get('object_location', '').strip()
        message = request.POST.get('message', '').strip()
        
        hours_str = request.POST.get('estimated_hours_weekly')
        hours = int(hours_str) if hours_str and hours_str.isdigit() else None

        estimate_str = request.POST.get('calculated_estimate_czk')
        estimate = Decimal(estimate_str) if estimate_str else None

        if not contact_name or not phone:
            return JsonResponse({'status': 'error', 'message': 'Vyplňte prosím alespoň jméno a telefonní kontakt.'}, status=400)

        inquiry = ServiceInquiry.objects.create(
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

        return JsonResponse({
            'status': 'success',
            'message': f'Děkujeme, pane/paní {contact_name}. Poptávka byla předána dispečinku. Ozveme se vám do 30 minut.'
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': f'Chyba při zpracování: {str(e)}'}, status=500)