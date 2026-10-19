from django.db import models
from django.utils.translation import gettext_lazy as _


class Category(models.Model):
    """Catégorie d'articles (Alimentation, Hygiène, …)."""

    name = models.CharField(_("Nom"), max_length=100, unique=True)

    class Meta:
        ordering = ("name",)
        verbose_name = _("Catégorie")
        verbose_name_plural = _("Catégories")

    def __str__(self):
        return self.name


class Article(models.Model):
    """Un article acheté régulièrement, avec son prix de référence."""

    name = models.CharField(_("Article"), max_length=200)
    category = models.ForeignKey(
        Category,
        verbose_name=_("Catégorie"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="articles",
    )
    unit = models.CharField(_("Unité"), max_length=50, default="unité")
    base_price = models.DecimalField(
        _("Prix de référence"), max_digits=12, decimal_places=2, default=0
    )
    is_active = models.BooleanField(_("Actif"), default=True)
    created_at = models.DateTimeField(_("Créé le"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Modifié le"), auto_now=True)

    class Meta:
        ordering = ("name",)
        verbose_name = _("Article")
        verbose_name_plural = _("Articles")

    def __str__(self):
        return self.name


class DailyEntry(models.Model):
    """Marquage quotidien : article fait (ou non) pour une date donnée."""

    article = models.ForeignKey(
        Article, on_delete=models.CASCADE, related_name="entries"
    )
    date = models.DateField(_("Date"))
    done = models.BooleanField(_("Fait"), default=False)
    # Prix réellement payé ce jour-là ; vide = prix de référence de l'article.
    price = models.DecimalField(
        _("Prix du jour"), max_digits=12, decimal_places=2, null=True, blank=True
    )
    quantity = models.PositiveIntegerField(_("Quantité"), default=1)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-date",)
        constraints = [
            models.UniqueConstraint(
                fields=("article", "date"), name="unique_entry_per_day"
            )
        ]
        verbose_name = _("Marquage du jour")
        verbose_name_plural = _("Marquages du jour")

    def __str__(self):
        return f"{self.article} – {self.date} – {'fait' if self.done else 'à faire'}"

    @property
    def effective_price(self):
        """Prix effectif : prix du jour, sinon prix de référence."""
        return self.price if self.price is not None else self.article.base_price
