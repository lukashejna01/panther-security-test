from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import HttpResponse

# Vyhledávače smí jen na veřejný web (úvod, magazín, kontakt). Adresa
# administrace tu záměrně není – robots.txt si může přečíst kdokoli.
ROBOTS_TXT = """User-agent: *
Allow: /$
Allow: /magazin/
Allow: /kontakt/
Disallow: /
"""

urlpatterns = [
    path('robots.txt', lambda request: HttpResponse(ROBOTS_TXT, content_type='text/plain')),
    path(settings.ADMIN_URL, admin.site.urls),
    
    # Veřejný web, magazín a poptávky
    path('', include('web.urls')),
    
    # Interní systém Panther Security (zaměstnanci, směny, fakturace atd.)
    path('', include('core.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)