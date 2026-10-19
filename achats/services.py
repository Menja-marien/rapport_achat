"""
Logique métier de l'application « achats » :
analyse des paramètres, filtres, sérialisation et calcul des totaux.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from django.db.models import Count, Q
from django.utils import timezone

from .models import Article, Category, DailyEntry

# Clé de tri -> champ de tri réel.
ORDERINGS = {
    "name": "name",
    "-name": "-name",
    "price": "base_price",
    "-price": "-base_price",
    "category": ("category__name", "name"),
    "recent": ("-created_at",),
}

# Statuts de marquage.
STATUS_TODO = "todo"
STATUS_DONE = "done"


# ---------------------------------------------------------------------------
# Analyse des paramètres
# ---------------------------------------------------------------------------
def parse_decimal(value) -> Decimal | None:
    """
    Analyse une saisie libre : « 1 200 », « 1200,50 », « 1.200 », « 1200.5 »…
    Renvoie None si la valeur est vide, lève ValueError sinon.
    """
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))

    s = str(value).strip()
    s = s.replace("\u202f", "").replace("\u00a0", "").replace(" ", "")
    if not s:
        return None

    if "," in s and "." in s:
        # Le dernier séparateur rencontré est le séparateur décimal.
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", s):
        # « 1.200 » = mille (séparateur de milliers européen).
        s = s.replace(".", "")

    try:
        return Decimal(s)
    except InvalidOperation:
        raise ValueError(f"Nombre invalide : {value!r}")


def parse_date(value) -> date | None:
    """Analyse une date au format YYYY-MM-DD (ou accepte datetime/date)."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def day_param(params) -> date:
    """Date demandée, par défaut aujourd'hui (heure locale du serveur)."""
    return parse_date(params.get("date")) or timezone.localdate()


# ---------------------------------------------------------------------------
# Filtres
# ---------------------------------------------------------------------------
def filter_articles(params) -> tuple[list, date, dict]:
    """
    Applique tous les filtres de l'interface et renvoie
    (lignes sérialisées, date, valeurs normalisées des filtres).
    """
    day = day_param(params)
    q = (params.get("q") or "").strip()
    category = (params.get("category") or "").strip()
    status = (params.get("status") or "").strip()
    ordering = params.get("ordering") or "name"
    include_inactive = str(params.get("inactive") or "") == "1"

    errors: dict[str, str] = {}
    min_price = max_price = None
    if params.get("min_price"):
        try:
            min_price = parse_decimal(params.get("min_price"))
        except ValueError:
            errors["min_price"] = "Prix minimum invalide"
    if params.get("max_price"):
        try:
            max_price = parse_decimal(params.get("max_price"))
        except ValueError:
            errors["max_price"] = "Prix maximum invalide"

    articles = Article.objects.select_related("category")

    if q:
        articles = articles.filter(Q(name__icontains=q) | Q(category__name__icontains=q))
    if category:
        if category == "none":
            articles = articles.filter(category__isnull=True)
        else:
            try:
                articles = articles.filter(category_id=int(category))
            except ValueError:
                errors["category"] = "Catégorie invalide"
    if not include_inactive:
        articles = articles.filter(is_active=True)
    if min_price is not None:
        articles = articles.filter(base_price__gte=min_price)
    if max_price is not None:
        articles = articles.filter(base_price__lte=max_price)

    order = ORDERINGS.get(ordering, ORDERINGS["name"])
    if isinstance(order, str):
        order = (order,)
    articles = list(articles.order_by(*order, "name"))

    # Marquages du jour, en une seule requête.
    entries = {
        e.article_id: e
        for e in DailyEntry.objects.filter(
            date=day, article_id__in=[a.id for a in articles]
        )
    }

    rows = [_serialize_article(a, entries.get(a.id)) for a in articles]

    if status in (STATUS_TODO, STATUS_DONE):
        want = status == STATUS_DONE
        rows = [r for r in rows if r["done"] is want]

    filters = {
        "q": q,
        "category": category,
        "status": status if status in (STATUS_TODO, STATUS_DONE) else "",
        "ordering": ordering if ordering in ORDERINGS else "name",
        "inactive": include_inactive,
        "min_price": params.get("min_price") or "",
        "max_price": params.get("max_price") or "",
        "errors": errors,
    }
    return rows, day, filters


# ---------------------------------------------------------------------------
# Sérialisation
# ---------------------------------------------------------------------------
def _money(value) -> str:
    return format(Decimal(value).normalize(), "f")


def _serialize_article(article: Article, entry: DailyEntry | None) -> dict:
    price = entry.effective_price if entry else article.base_price
    quantity = entry.quantity if entry else 1
    return {
        "id": article.id,
        "name": article.name,
        "unit": article.unit,
        "category_id": article.category_id,
        "category": article.category.name if article.category else None,
        "base_price": _money(article.base_price),
        "is_active": article.is_active,
        "done": bool(entry and entry.done),
        "entry_id": entry.id if entry else None,
        "price": _money(price),
        "quantity": quantity,
        "total": _money(Decimal(price) * quantity),
        "has_custom_price": bool(entry and entry.price is not None),
        "updated_at": article.updated_at.isoformat() if article.updated_at else None,
    }


def summarize(rows: list[dict]) -> dict:
    """Totaux de la sélection affichée (tient compte des filtres)."""
    done = [r for r in rows if r["done"]]
    planned = sum(Decimal(r["base_price"]) * r["quantity"] for r in rows)
    spent = sum(Decimal(r["price"]) * r["quantity"] for r in done)
    return {
        "count": len(rows),
        "done": len(done),
        "todo": len(rows) - len(done),
        "planned": _money(planned),
        "spent": _money(spent),
        "remaining": _money(planned - spent),
        "active_total": Article.objects.filter(is_active=True).count(),
    }


def group_rows(rows: list[dict]) -> list[dict]:
    """Regroupe les lignes par catégorie (catégorie inconnue en dernier)."""
    buckets: dict = {}
    for row in rows:
        buckets.setdefault(row["category"], []).append(row)

    ordered = sorted(
        buckets.items(), key=lambda kv: (kv[0] is None, (kv[0] or "").lower())
    )
    groups = []
    for name, items in ordered:
        planned = sum(Decimal(i["base_price"]) * i["quantity"] for i in items)
        groups.append(
            {
                "name": name,
                "count": len(items),
                "planned": _money(planned),
                "articles": items,
            }
        )
    return groups


def build_payload(params) -> dict:
    """Charge complète retournée à chaque (re)chargement de la page."""
    rows, day, filters = filter_articles(params)
    categories = list(
        Category.objects.annotate(n=Count("articles")).values("id", "name", "n")
    )
    return {
        "date": day.isoformat(),
        "articles": rows,
        "groups": group_rows(rows),
        "summary": summarize(rows),
        "categories": [{"id": c["id"], "name": c["name"], "count": c["n"]} for c in categories],
        "filters": filters,
    }


# ---------------------------------------------------------------------------
# Création / mise à jour d'un article
# ---------------------------------------------------------------------------
def validate_article(data: dict) -> tuple[dict | None, str | None]:
    """Valide et normalise la charge utile d'un article. (données, erreur)."""
    name = str(data.get("name") or "").strip()
    if not name:
        return None, "Le nom de l'article est obligatoire."
    if len(name) > 200:
        return None, "Le nom de l'article est trop long (200 caractères max)."

    try:
        price = parse_decimal(data.get("base_price")) or Decimal("0")
    except ValueError:
        return None, "Le prix de référence n'est pas un nombre valide."
    if price < 0:
        return None, "Le prix de référence ne peut pas être négatif."

    unit = str(data.get("unit") or "unité").strip() or "unité"
    if len(unit) > 50:
        return None, "L'unité est trop longue (50 caractères max)."

    category_id = data.get("category_id")
    category_name = str(data.get("category_name") or "").strip()
    if category_id in ("", None, 0, "0"):
        category_id = None
    elif category_id:
        try:
            category_id = int(category_id)
        except (TypeError, ValueError):
            return None, "Catégorie invalide."

    is_active = data.get("is_active")
    if isinstance(is_active, str):
        is_active = is_active.lower() in ("1", "true", "yes", "on")
    else:
        is_active = bool(True if is_active is None else is_active)

    return {
        "name": name,
        "unit": unit,
        "base_price": price,
        "category_id": category_id,
        "category_name": category_name,
        "is_active": is_active,
    }, None


def serialize_for_form(article: Article) -> dict:
    """Représentation d'un article au format attendu par validate_article()."""
    return {
        "name": article.name,
        "unit": article.unit,
        "base_price": _money(article.base_price),
        "category_id": article.category_id or "",
        "category_name": "",
        "is_active": article.is_active,
    }


def apply_article(article: Article, clean: dict) -> Article:
    """Crée ou met à jour l'article avec des données déjà validées."""
    if clean["category_name"]:
        # Création à la volée d'une catégorie inconnue (recherche insensible
        # à la casse, puis création — get_or_create ne fonctionne pas avec
        # un lookup iexact car il serait réutilisé pour l'insertion).
        category = Category.objects.filter(
            name__iexact=clean["category_name"]
        ).first()
        if category is None:
            category = Category.objects.create(name=clean["category_name"])
        article.category = category
    else:
        article.category_id = clean["category_id"]
    article.name = clean["name"]
    article.unit = clean["unit"]
    article.base_price = clean["base_price"]
    article.is_active = clean["is_active"]
    article.save()
    return article


# ---------------------------------------------------------------------------
# Historique
# ---------------------------------------------------------------------------
def history(days: int = 30) -> list[dict]:
    """Totaux dépensés par jour sur les N derniers jours."""
    from collections import defaultdict

    start = timezone.localdate() - timedelta(days=days - 1)
    totals: dict = defaultdict(lambda: {"n": 0, "total": Decimal("0")})

    for entry in DailyEntry.objects.filter(done=True, date__gte=start).select_related(
        "article"
    ):
        cell = totals[entry.date]
        cell["n"] += 1
        cell["total"] += entry.effective_price * entry.quantity

    return [
        {
            "date": day.isoformat(),
            "count": cell["n"],
            "total": _money(cell["total"]),
        }
        for day, cell in sorted(totals.items(), reverse=True)
    ]
