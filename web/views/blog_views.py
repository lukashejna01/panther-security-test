from django.shortcuts import render, get_object_or_404
from django.db.models import F
from web.models import Article, ArticleCategory


def article_list_view(request):
    """Přehled článků a novinek s filtrováním dle kategorií."""
    category_slug = request.GET.get('kategorie')
    articles = Article.objects.filter(status=Article.STATUS_PUBLISHED).select_related('category')

    if category_slug:
        articles = articles.filter(category__slug=category_slug)

    categories = ArticleCategory.objects.all()

    context = {
        'articles': articles,
        'categories': categories,
        'active_category': category_slug,
    }
    return render(request, 'web/article_list.html', context)


def article_detail_view(request, slug):
    """Detail článku se čtecím progress barem a doporučenými články."""
    article = get_object_or_404(Article, slug=slug, status=Article.STATUS_PUBLISHED)
    
    # Zvýšení počtu zhlédnutí bez ovlivnění času editace
    Article.objects.filter(id=article.id).update(views_count=F('views_count') + 1)
    article.refresh_from_db(fields=['views_count'])

    related_articles = Article.objects.filter(
        status=Article.STATUS_PUBLISHED,
        category=article.category
    ).exclude(id=article.id).order_by('-published_at')[:3]

    context = {
        'article': article,
        'related_articles': related_articles,
    }
    return render(request, 'web/article_detail.html', context)