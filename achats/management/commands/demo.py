"""Crée un jeu de données d'exemple : python manage.py demo"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from achats.models import Article, Category, DailyEntry

DEMO = [
    ("Alimentation", [
        ("Riz parfumé", "sac 25 kg", 15000),
        ("Huile d'arachide", "bidon 5 L", 6500),
        ("Lait concentré", "boîte", 700),
        ("Sucre", "kg", 900),
        ("Café moulu", "paquet", 1200),
    ]),
    ("Hygiène", [
        ("Savon de Marseille", "pièce", 500),
        ("Savon liquide", "litre", 2500),
        ("Papier hygiénique", "lot de 8", 1800),
    ]),
    ("Maison", [
        ("Gaz (bouteille)", "bouteille", 7000),
        ("Sacs-poubelle", "lot", 1000),
    ]),
]


class Command(BaseCommand):
    help = "Insère des articles et marquages d'exemple (uniquement si la base est vide)."

    def handle(self, *args, **options):
        if Article.objects.exists():
            self.stdout.write(
                self.style.WARNING("Des articles existent déjà : rien fait.")
            )
            return

        today = timezone.localdate()
        for cat_name, items in DEMO:
            category, _ = Category.objects.get_or_create(name=cat_name)
            for i, (name, unit, price) in enumerate(items):
                article = Article.objects.create(
                    name=name, unit=unit, base_price=price, category=category
                )
                # Les deux premiers articles sont déjà marqués aujourd'hui.
                if i < 2:
                    DailyEntry.objects.create(article=article, date=today, done=True)

        self.stdout.write(
            self.style.SUCCESS(
                f"{Article.objects.count()} articles et "
                f"{DailyEntry.objects.count()} marquages d'exemple créés."
            )
        )
