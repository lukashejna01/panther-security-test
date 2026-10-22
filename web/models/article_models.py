from django.db import models
from django.utils.text import slugify
from django.contrib.auth.models import User


class ArticleCategory(models.Model):
    name = models.CharField("Název kategorie", max_length=100)
    slug = models.SlugField("URL slug", unique=True, max_length=120)
    icon = models.CharField("Emoji ikona", max_length=20, default="🛡️")
    order = models.PositiveIntegerField("Pořadí", default=0)

    class Meta:
        verbose_name = "Kategorie článků"
        verbose_name_plural = "Kategorie článků"
        ordering = ['order', 'name']

    def __str__(self):
        return f"{self.icon} {self.name}"


class Article(models.Model):
    STATUS_DRAFT = 'DRAFT'
    STATUS_PUBLISHED = 'PUBLISHED'
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Koncept'),
        (STATUS_PUBLISHED, 'Publikováno'),
    ]

    title = models.CharField("Titulek článku", max_length=255)
    slug = models.SlugField("URL slug", unique=True, max_length=255, blank=True)
    category = models.ForeignKey(ArticleCategory, on_delete=models.SET_NULL, null=True, related_name='articles', verbose_name="Kategorie")
    perex = models.TextField("Perex (krátký úvodník)", max_length=500)
    content = models.TextField("Obsah článku (HTML / Markdown)")
    featured_image = models.ImageField("Hlavní obrázek", upload_to='web/articles/%Y/%m/', blank=True, null=True)
    author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Autor")
    
    reading_time_minutes = models.PositiveIntegerField("Čas čtení (min)", default=3)
    views_count = models.PositiveIntegerField("Počet zhlédnutí", default=0)
    
    status = models.CharField("Stav", max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    is_featured = models.BooleanField("Doporučený článek na titulce", default=False)
    
    published_at = models.DateTimeField("Datum publikace", blank=True, null=True)
    created_at = models.DateTimeField("Vytvořeno", auto_now_add=True)
    updated_at = models.DateTimeField("Aktualizováno", auto_now=True)

    class Meta:
        verbose_name = "Článek / Zpráva"
        verbose_name_plural = "Články a novinky"
        ordering = ['-published_at', '-created_at']

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title