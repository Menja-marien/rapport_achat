"""
Vues de l'application « achats ».

Toute la page est alimentée par l'API JSON ci-dessous : le front la sonde
régulièrement (polling) afin que les changements des autres utilisateurs
apparaissent sans rechargement → effet « temps réel ».

L'accès est réservé aux utilisateurs connectés : la page redirige vers
/connexion/ et l'API répond 401 (JSON) dans ce cas.
"""
import json
from functools import wraps

from django.conf import settings
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from . import services
from .forms import SignUpForm
from .models import Article, Category, DailyEntry


# ---------------------------------------------------------------------------
# Accès : page protégée par connexion, API en JSON 401
# ---------------------------------------------------------------------------
def api_login_required(view):
    """Comme `login_required`, mais renvoie du JSON 401 pour les appels fetch."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse(
                {"error": "Authentification requise.", "login_url": settings.LOGIN_URL},
                status=401,
            )
        return view(request, *args, **kwargs)

    return wrapper


def _safe_next(raw, fallback):
    """N'accepte qu'un chemin interne (évite les redirections ouvertes)."""
    if isinstance(raw, str) and raw.startswith("/") and not raw.startswith("//"):
        return raw
    return fallback


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------
@login_required
def home(request):
    return render(
        request,
        "achats/home.html",
        {
            "currency": settings.CURRENCY,
            "poll_interval": settings.POLL_INTERVAL,
            "today": timezone.localdate(),
        },
    )


# ---------------------------------------------------------------------------
# Création de compte
# ---------------------------------------------------------------------------
def signup(request):
    """Page d'inscription : crée le compte puis connecte directement l'utilisateur."""
    if request.user.is_authenticated:
        return redirect(_safe_next(request.GET.get("next"), reverse("achats:home")))

    next_url = _safe_next(request.GET.get("next"), "")
    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect(_safe_next(request.POST.get("next"), reverse("achats:home")))
        next_url = _safe_next(request.POST.get("next"), next_url)
    else:
        form = SignUpForm()

    return render(request, "registration/signup.html", {"form": form, "next": next_url})


# ---------------------------------------------------------------------------
# Petits utilitaires
# ---------------------------------------------------------------------------
def _json(request) -> dict:
    """Charge utile JSON de la requête ({} si vide/invalide)."""
    if not request.body:
        return {}
    try:
        data = json.loads(request.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _error(message: str, status: int = 400) -> JsonResponse:
    return JsonResponse({"error": message}, status=status)


def _clean_ids(raw) -> list[int]:
    """Identifiants d'articles issus de la sélection envoyée par le front."""
    values = raw if isinstance(raw, (list, tuple, set)) else []
    ids = []
    for value in values:
        try:
            ids.append(int(value))
        except (TypeError, ValueError):
            continue
    return ids


# ---------------------------------------------------------------------------
# Articles : liste + création
# ---------------------------------------------------------------------------
@api_login_required
@require_http_methods(["GET", "POST"])
def articles_api(request):
    if request.method == "GET":
        return JsonResponse(services.build_payload(request.GET))

    # POST → création d'un article
    clean, error = services.validate_article(_json(request))
    if error:
        return _error(error)
    services.apply_article(Article(), clean)
    return JsonResponse(services.build_payload(request.GET), status=201)


# ---------------------------------------------------------------------------
# Un article : lecture / modification / suppression
# ---------------------------------------------------------------------------
@api_login_required
@require_http_methods(["GET", "PATCH", "DELETE"])
def article_api(request, pk):
    article = get_object_or_404(Article, pk=pk)

    if request.method == "GET":
        return JsonResponse(services.build_payload(request.GET))

    if request.method == "DELETE":
        # On garde l'historique : désactivation plutôt que suppression,
        # sauf si l'article n'a encore aucun marquage.
        if article.entries.exists():
            article.is_active = False
            article.save()
        else:
            article.delete()
        return JsonResponse(services.build_payload(request.GET))

    # PATCH → mise à jour
    data = _json(request)
    if "is_active" in data and len(data) == 1:
        article.is_active = bool(data["is_active"])
        article.save()
        return JsonResponse(services.build_payload(request.GET))

    clean, error = services.validate_article({**services.serialize_for_form(article), **data})
    if error:
        return _error(error)
    services.apply_article(article, clean)
    return JsonResponse(services.build_payload(request.GET))


# ---------------------------------------------------------------------------
# Articles : actions groupées sur une sélection
# ---------------------------------------------------------------------------
@api_login_required
@require_http_methods(["POST"])
def articles_bulk_api(request):
    """Applique une action à plusieurs articles sélectionnés.

    `action` : `set_category` (category_id vide = « Sans catégorie ») ou `delete`.
    La suppression désactive l'article s'il a déjà un historique, sinon le supprime.
    """
    data = _json(request)
    ids = _clean_ids(data.get("ids"))
    if not ids:
        return _error("Aucun article sélectionné.")

    articles = list(Article.objects.filter(pk__in=ids))
    if not articles:
        return _error("Articles introuvables.")

    action = str(data.get("action") or "")

    if action == "set_category":
        raw = data.get("category_id")
        category = None
        if raw not in (None, "", "0"):
            try:
                category = Category.objects.get(pk=int(raw))
            except (TypeError, ValueError):
                return _error("Catégorie invalide.")
            except Category.DoesNotExist:
                return _error("Catégorie introuvable.")
        for article in articles:
            article.category = category
            article.save(update_fields=["category", "updated_at"])
        return JsonResponse(services.build_payload(request.GET))

    if action == "delete":
        deleted = disabled = 0
        for article in articles:
            if article.entries.exists():
                article.is_active = False
                article.save(update_fields=["is_active", "updated_at"])
                disabled += 1
            else:
                article.delete()
                deleted += 1
        payload = services.build_payload(request.GET)
        payload["bulk"] = {"deleted": deleted, "disabled": disabled}
        return JsonResponse(payload)

    return _error("Action groupée inconnue.")


# ---------------------------------------------------------------------------
# Marquage quotidien
# ---------------------------------------------------------------------------
@api_login_required
@require_http_methods(["POST"])
def entry_api(request):
    """Coche / décoche / met à jour le prix d'un article pour une date."""
    data = _json(request)
    try:
        article_id = int(data.get("article_id"))
    except (TypeError, ValueError):
        return _error("Article manquant ou invalide.")

    article = get_object_or_404(Article, pk=article_id)
    day = services.parse_date(data.get("date")) or timezone.localdate()

    quantity = data.get("quantity", 1)
    try:
        quantity = max(1, int(quantity))
    except (TypeError, ValueError):
        return _error("La quantité doit être un entier ≥ 1.")

    entry, _created = DailyEntry.objects.get_or_create(
        article=article, date=day, defaults={"done": False}
    )
    entry.done = bool(data.get("done"))
    entry.quantity = quantity

    if "price" in data:
        try:
            entry.price = services.parse_decimal(data.get("price"))
        except ValueError:
            return _error("Le prix saisi n'est pas un nombre valide.")
        if entry.price is not None and entry.price < 0:
            return _error("Le prix ne peut pas être négatif.")

    entry.save()
    return JsonResponse(services.build_payload(request.GET))


@api_login_required
@require_http_methods(["POST"])
def bulk_api(request):
    """Marque / démarque d'un coup une sélection, sinon tous les articles affichés."""
    data = _json(request)
    day = services.parse_date(data.get("date")) or timezone.localdate()
    done = bool(data.get("done"))

    # `ids` = sélection explicite du front ; absent = tout l'affichage courant.
    if "ids" in data:
        ids = _clean_ids(data.get("ids"))
    else:
        rows, _day, _filters = services.filter_articles(request.GET)
        ids = [r["id"] for r in rows]

    if not ids:
        return _error("Aucun article sélectionné.")

    entries = {
        e.article_id: e
        for e in DailyEntry.objects.filter(date=day, article_id__in=ids)
    }
    to_create, to_update = [], []
    for article_id in ids:
        entry = entries.get(article_id)
        if entry is None:
            to_create.append(
                DailyEntry(article_id=article_id, date=day, done=done, quantity=1)
            )
        elif entry.done != done:
            entry.done = done
            to_update.append(entry)
    if to_create:
        DailyEntry.objects.bulk_create(to_create, ignore_conflicts=True)
    if to_update:
        DailyEntry.objects.bulk_update(to_update, ["done"])

    return JsonResponse(services.build_payload(request.GET))


# ---------------------------------------------------------------------------
# Historique
# ---------------------------------------------------------------------------
@api_login_required
@require_http_methods(["GET"])
def history_api(request):
    return JsonResponse({"days": services.history(30)})


@api_login_required
@require_http_methods(["POST"])
def categories_api(request):
    """Création d'une catégorie depuis l'interface."""
    data = _json(request)
    name = str(data.get("name") or "").strip()
    if not name:
        return _error("Le nom de la catégorie est obligatoire.")
    if len(name) > 100:
        return _error("Le nom est trop long (100 caractères max).")
    if Category.objects.filter(name__iexact=name).exists():
        return _error("Cette catégorie existe déjà.")
    category = Category.objects.create(name=name)
    return JsonResponse(
        {"ok": True, "category": {"id": category.id, "name": category.name, "count": 0}},
        status=201,
    )
