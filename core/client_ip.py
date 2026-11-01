"""
Zjištění skutečné IP adresy návštěvníka za proxy PythonAnywhere.
"""


def get_client_ip(request):
    """
    PythonAnywhere předává adresu návštěvníka v hlavičce X-Real-IP
    (REMOTE_ADDR je adresa jejich proxy). Lokálně hlavička chybí.
    """
    return request.META.get('HTTP_X_REAL_IP') or request.META.get('REMOTE_ADDR')
