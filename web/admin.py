from django.contrib import admin
from .models.article_models import Article, ArticleCategory
from .models.inquiry_models import ServiceInquiry


# ==========================================
# ČLÁNKY & KATEGORIE
# ==========================================
@admin.register(ArticleCategory)
class ArticleCategoryAdmin(admin.ModelAdmin):
    list_display = ('icon', 'name', 'slug', 'order')
    list_editable = ('order',)
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ('name',)


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = (
        'title',
        'category',
        'status',
        'is_featured',
        'author',
        'views_count',
        'published_at',
    )
    list_filter = ('status', 'is_featured', 'category', 'published_at')
    search_fields = ('title', 'perex', 'content')
    prepopulated_fields = {'slug': ('title',)}
    list_editable = ('status', 'is_featured')
    date_hierarchy = 'published_at'


# ==========================================
# POPTÁVKY SLUŽEB Z WEBOVÉHO FORMULÁŘE
# ==========================================
@admin.register(ServiceInquiry)
class ServiceInquiryAdmin(admin.ModelAdmin):
    list_display = (
        'contact_name',
        'service_type',
        'company_name',
        'phone',
        'email',
        'calculated_estimate_czk',
        'is_processed',
        'created_at',
    )
    list_filter = ('service_type', 'is_processed', 'created_at')
    search_fields = ('contact_name', 'company_name', 'phone', 'email', 'message')
    list_editable = ('is_processed',)
    date_hierarchy = 'created_at'