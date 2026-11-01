"""Veřejné stránky se načtou (detail článku dřív padal na chybějící šabloně)."""

from django.test import Client, TestCase
from django.utils import timezone

from web.models import Article, ArticleCategory

HTTPS = {'HTTP_HOST': 'www.panther-security.cz', 'secure': True}


class PublicPagesTests(TestCase):
    def setUp(self):
        category = ArticleCategory.objects.create(name='Zásahy', slug='zasahy')
        self.article = Article.objects.create(title='Noční zásah', slug='nocni-zasah', category=category, perex='Perex',
                                              content='<p>Text</p>', status=Article.STATUS_PUBLISHED, published_at=timezone.now())
        Article.objects.create(title='Koncept', slug='koncept', category=category, perex='x', content='x')

    def test_pages_render(self):
        for url in ('/', '/magazin/', '/magazin/?kategorie=zasahy', '/magazin/nocni-zasah/', '/kontakt/'):
            with self.subTest(url=url):
                self.assertEqual(Client().get(url, **HTTPS).status_code, 200)

    def test_article_detail_and_draft(self):
        response = Client().get('/magazin/nocni-zasah/', **HTTPS)
        self.assertContains(response, 'Noční zásah')
        self.assertEqual(Client().get('/magazin/koncept/', **HTTPS).status_code, 404)

    def test_calculator_default_hours_fit_slider_step(self):
        # 168 h (nonstop) musí být platná hodnota posuvníku, jinak ji prohlížeč zaokrouhlí
        html = Client().get('/', **HTTPS).content.decode()
        self.assertIn('min="24" max="336" step="8" value="168"', html)
        self.assertEqual((168 - 24) % 8, 0)
