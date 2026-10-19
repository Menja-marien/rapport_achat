# 🛒 Achats du jour — suivi & marquage quotidien (Django)

Application Django **temps réel** pour saisir des articles et leurs prix, puis
**cocher chaque jour** les articles achetés (comme une to-do liste, mais avec
des prix et des totaux), le tout avec des **filtres**.

La page ne se recharge jamais : elle est alimentée par une API JSON et se
re-synchronise automatiquement toutes les quelques secondes. Toute modification
faite dans un autre onglet / par un autre utilisateur apparaît donc en direct.

---

## Fonctionnalités

| Bloc | Détails |
|------|---------|
| **Articles** | nom, prix de référence, unité, catégorie (création à la volée), actif/inactif |
| **Liste groupée** | les articles sont **organisés par catégorie** (sous-titre + sous-total, « Sans catégorie » en dernier), le tri s'applique à l'intérieur de chaque groupe |
| **Catégories** | bouton « ＋ Catégorie » dans la barre d'outils → création immédiate (`POST /api/categories/`) |
| **Marquage quotidien** | case à cocher par jour, quantité, **prix réel du jour** (modifiable), total de ligne |
| **Navigation dans le temps** | sélecteur de date, boutons ‹ › et « Aujourd'hui » |
| **Filtres** | recherche texte, catégorie, état (à faire / fait), prix min–max, tri (nom, prix, catégorie, récent), affichage des inactifs |
| **Totaux** | articles, à faire, faits, total prévu, dépensé, reste |
| **Actions groupées** | « Tout marquer » / « Tout décocher » sur la sélection filtrée |
| **Historique** | 30 derniers jours cliquables avec le total dépensé |
| **URL filtrable** | les filtres sont dans la barre d'adresse (partage / favoris) |
| **Temps réel** | polling silencieux (5 s par défaut) : aucune interruption d'une saisie en cours, aucun rechargement de page |
| **Sélection multiple** | case sur chaque ligne + case par catégorie (et « tout sélectionner ») : la barre flottante permet de **marquer fait**, **décocher**, **changer de catégorie** ou **supprimer** d'un coup ; `Échap` vide la sélection |
| **Accès protégé** | page et API réservées aux utilisateurs connectés (`/connexion/`), création de compte ouverte sur `/inscription/`, déconnexion depuis l'en-tête |
| **Interface** | **Tailwind CSS (CDN)** + icônes **Lucide (CDN)** — même jeu d'icônes que `lucide-react` (la page étant en Django/JS natif, c'est l'API `lucide.createIcons()` qui est utilisée) |
| **Administration** | `/admin/` (CRUD complet + historique) |

---

## Installation

```bash
pip install -r requirements.txt

python manage.py migrate
python manage.py demo          # (optionnel) articles d'exemple

python manage.py runserver
```

Puis ouvrez **http://127.0.0.1:8000/**.

La page demande une connexion : créez le premier compte depuis
**http://127.0.0.1:8000/inscription/** (le compte est connecté aussitôt).

### Compte administrateur (optionnel)

```bash
set DJANGO_SUPERUSER_PASSWORD=motdepasse
python manage.py createsuperuser --noinput --username admin --email admin@local
```

---

## Configuration

Dans `config/settings.py` :

```python
CURRENCY = "Ar"       # ariary malagasy (devise affichée partout)
POLL_INTERVAL = 5     # fréquence (secondes) des mises à jour temps réel

# Accès protégé par connexion
LOGIN_URL = "/connexion/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/connexion/"
```

---

## Structure du projet

```
manage.py
config/                  # projet Django (settings, urls, wsgi/asgi)
achats/
├── models.py            # Category, Article, DailyEntry (marquage par jour)
├── services.py          # filtres, sérialisation, totaux, historique
├── forms.py             # formulaires de connexion et d'inscription
├── views.py             # page + API JSON (accès protégé)
├── urls.py
├── admin.py
├── tests.py             # 47 tests
├── management/commands/demo.py
├── templates/achats/home.html
├── templates/registration/   # auth_base.html, login.html, signup.html
└── static/achats/       # app.js (l'habillage est 100 % Tailwind CDN)
```

### Modèle de données

- **`Article`** — `name`, `category`, `unit`, `base_price`, `is_active`
- **`DailyEntry`** — `article`, `date`, `done`, `price` (vide = prix de référence), `quantity`
  → **contrainte unique** `(article, date)` : un seul marquage par article et par jour.
  Chaque date possède son propre état et son propre prix.

---

## API JSON

| Méthode | Route | Rôle |
|---------|-------|------|
| `GET` | `/api/articles/?date=&q=&category=&status=&min_price=&max_price=&ordering=&inactive=` | liste + résumé + catégories (filtres côté serveur) |
| `POST` | `/api/articles/` | créer un article |
| `PATCH` / `DELETE` | `/api/articles/<id>/` | modifier / supprimer (désactive si historique existant) |
| `POST` | `/api/articles/bulk/` | actions groupées : `{"action": "set_category", "category_id": 3, "ids": [1, 2]}` ou `{"action": "delete", "ids": [...]}` |
| `POST` | `/api/entries/` | marquer / démarquer / fixer le prix d'un article pour une date |
| `POST` | `/api/entries/bulk/` | marquer d'un coup les articles affichés, ou seulement `{"ids": [...]}` |
| `GET` | `/api/history/` | totaux des 30 derniers jours |
| `POST` | `/api/categories/` | créer une catégorie (`{"name": "…"}`) |

Saisies de prix tolérantes : `1 200`, `1200,50`, `1.200` sont tous acceptés.
Protection CSRF standard (en-tête `X-CSRFToken` côté JS).
**Tous les points d'API exigent une session connectée** : ils répondent
`401 {"error": "Authentification requise."}` sinon (le front redirige alors vers
la page de connexion).

---

## Authentification

| Route | Rôle |
|-------|------|
| `/connexion/` | formulaire de connexion (paramètre `?next=` respecté) |
| `/inscription/` | création de compte (nom d'utilisateur, e-mail facultatif, mot de passe ×2) — connecte directement l'utilisateur |
| `/deconnexion/` | déconnexion (POST, bouton dans l'en-tête) |
| `/admin/` | administration Django (comptes de type *staff*) |

Les mots de passe passent par les validateurs Django standards
(`AUTH_PASSWORD_VALIDATORS`).

---

## Tests

```bash
python manage.py test achats
```

---

## Pistes d'évolution

- Remplacer le polling par **WebSockets** (`django-channels` + Redis) pour du temps réel instantané.
- Export **CSV/PDF** du rapport mensuel, graphiques d'évolution des prix par article.
- Espaces de travail partagés (aujourd'hui les données sont communes à tous les comptes).
