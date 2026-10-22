from django.shortcuts import render
from django.conf import settings
from web.models import Article, ArticleCategory


def home_page_view(request):
    """Hlavní úvodní stránka Panther Security."""
    featured_articles = Article.objects.filter(
        status=Article.STATUS_PUBLISHED
    ).select_related('category').order_by('-is_featured', '-published_at')[:3]

    categories = ArticleCategory.objects.all()

    context = {
        'featured_articles': featured_articles,
        'categories': categories,
    }
    return render(request, 'web/home.html', context)


def contact_page_view(request):
    """Přehledná a čistá kontaktní stránka Panther Security s vedením a odděleními."""
    company_info = {
        'name': getattr(settings, 'COMPANY_NAME', 'Panther Security s.r.o.'),
        'ico': getattr(settings, 'COMPANY_ICO', '22525882'),
        'dic': getattr(settings, 'COMPANY_DIC', 'CZ22525882'),
        'street': getattr(settings, 'COMPANY_STREET', 'Varšavská 715/36'),
        'city': getattr(settings, 'COMPANY_CITY', 'Praha 2'),
        'zip': getattr(settings, 'COMPANY_ZIP', '120 00'),
        
        # Jednatel společnosti
        'executive_name': 'Lukáš Hejna',
        'executive_role': 'Jednatel společnosti',
        'executive_phone': '+420 608 255 197',
        'executive_email': 'lukas.hejna@panther-security.cz',
        
        # Oddělení
        'email_sales': 'obchod@panther-security.cz',
        'email_operations': 'provoz@panther-security.cz',
        'email_billing': 'ucto@panther-security.cz',
    }
    return render(request, 'web/contact.html', {'company': company_info})