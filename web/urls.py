from django.urls import path
from . import views

app_name = 'web'

urlpatterns = [
    # Veřejná úvodní stránka
    path('', views.home_page_view, name='home'),
    
    # Magazín a články
    path('magazin/', views.article_list_view, name='article_list'),
    path('magazin/<slug:slug>/', views.article_detail_view, name='article_detail'),
    
    # Samostatná kontaktní stránka
    path('kontakt/', views.contact_page_view, name='contact'),
    
    # Zpracování poptávky / zprávy (AJAX)
    path('poptavka/odeslat/', views.submit_inquiry_view, name='submit_inquiry'),
]