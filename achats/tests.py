"""Tests de l'application achats."""
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Article, Category, DailyEntry


class AuthedTestCase(TestCase):
    """Base : connecte un utilisateur avant chaque test (page et API protégées)."""

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(username="testeur", password="MotDePasse123!")
        self.client.force_login(self.user)


class ArticleApiTests(AuthedTestCase):
    def create_article(self, **payload):
        return self.client.post(
            reverse("achats:articles-api"), payload, content_type="application/json"
        )

    def test_creer_article(self):
        res = self.create_article(name="Riz", base_price="1 200", unit="sac")
        self.assertEqual(res.status_code, 201)
        data = res.json()
        self.assertEqual(len(data["articles"]), 1)
        self.assertEqual(data["articles"][0]["price"], "1200")
        self.assertEqual(Article.objects.count(), 1)

    def test_nom_obligatoire(self):
        res = self.create_article(name="  ", base_price="10")
        self.assertEqual(res.status_code, 400)
        self.assertIn("error", res.json())

    def test_prix_invalide(self):
        res = self.create_article(name="Lait", base_price="abc")
        self.assertEqual(res.status_code, 400)

    def test_modifier_article(self):
        art = Article.objects.create(name="Sucre", base_price=500)
        res = self.client.patch(
            reverse("achats:article-api", args=[art.id]),
            {"name": "Sucre roux", "base_price": "750,5"},
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        art.refresh_from_db()
        self.assertEqual(art.name, "Sucre roux")
        self.assertEqual(art.base_price, Decimal("750.5"))

    def test_suppression_devient_desactivation_si_historique(self):
        art = Article.objects.create(name="Pain", base_price=100)
        DailyEntry.objects.create(article=art, date=date(2026, 1, 1), done=True)
        res = self.client.delete(reverse("achats:article-api", args=[art.id]))
        self.assertEqual(res.status_code, 200)
        art.refresh_from_db()
        self.assertFalse(art.is_active)


class MarquageTests(AuthedTestCase):
    def setUp(self):
        super().setUp()
        self.art = Article.objects.create(name="Lait", base_price=1000)

    def post(self, payload):
        return self.client.post(
            reverse("achats:entry-api"), payload, content_type="application/json"
        )

    def test_marquer_un_jour(self):
        res = self.post(
            {"article_id": self.art.id, "date": "2026-10-19", "done": True, "quantity": 2}
        )
        self.assertEqual(res.status_code, 200)
        entry = DailyEntry.objects.get(article=self.art, date=date(2026, 10, 19))
        self.assertTrue(entry.done)
        self.assertEqual(entry.quantity, 2)
        self.assertEqual(entry.effective_price, 1000)

    def test_marquage_independant_par_jour(self):
        self.post({"article_id": self.art.id, "date": "2026-10-19", "done": True})
        self.post({"article_id": self.art.id, "date": "2026-10-20", "done": False})
        self.assertTrue(DailyEntry.objects.get(date=date(2026, 10, 19)).done)
        self.assertFalse(DailyEntry.objects.get(date=date(2026, 10, 20)).done)

    def test_prix_du_jour_different(self):
        self.post(
            {
                "article_id": self.art.id,
                "date": "2026-10-19",
                "done": True,
                "price": "1 500",
            }
        )
        entry = DailyEntry.objects.get(date=date(2026, 10, 19))
        self.assertEqual(entry.effective_price, 1500)

    def test_totaux(self):
        self.post({"article_id": self.art.id, "date": "2026-10-19", "done": True, "quantity": 3})
        res = self.client.get(
            reverse("achats:articles-api"), {"date": "2026-10-19"}
        ).json()["summary"]
        self.assertEqual(res["done"], 1)
        self.assertEqual(res["planned"], "3000")
        self.assertEqual(res["spent"], "3000")
        self.assertEqual(res["remaining"], "0")

    def test_marquage_groupé(self):
        Article.objects.create(name="Oeufs", base_price=500)
        res = self.client.post(
            reverse("achats:bulk-api") + "?date=2026-10-19",
            {"date": "2026-10-19", "done": True},
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(DailyEntry.objects.filter(done=True).count(), 2)


class FiltresTests(AuthedTestCase):
    def setUp(self):
        super().setUp()
        alim = Category.objects.create(name="Alimentation")
        hygiene = Category.objects.create(name="Hygiène")
        Article.objects.create(name="Riz", base_price=1200, category=alim)
        Article.objects.create(name="Savon", base_price=350, category=hygiene)
        Article.objects.create(name="Café", base_price=2500, is_active=False)

    def get(self, **params):
        return self.client.get(reverse("achats:articles-api"), params).json()

    def test_recherche(self):
        data = self.get(q="sav")
        self.assertEqual([a["name"] for a in data["articles"]], ["Savon"])

    def test_recherche_par_categorie(self):
        data = self.get(q="alimentation")
        self.assertEqual([a["name"] for a in data["articles"]], ["Riz"])

    def test_fourchette_de_prix(self):
        data = self.get(min_price="300", max_price="2000")
        self.assertEqual([a["name"] for a in data["articles"]], ["Riz", "Savon"])

    def test_tri_prix_decroissant(self):
        data = self.get(ordering="-price")
        self.assertEqual([a["name"] for a in data["articles"]], ["Riz", "Savon"])

    def test_inactifs_exclus_par_defaut(self):
        self.assertEqual(self.get()["summary"]["count"], 2)
        self.assertEqual(self.get(inactive="1")["summary"]["count"], 3)

    def test_filtre_statut(self):
        art = Article.objects.get(name="Riz")
        DailyEntry.objects.create(article=art, date=timezone.localdate(), done=True)
        self.assertEqual(self.get(status="done")["summary"]["count"], 1)
        self.assertEqual(self.get(status="todo")["summary"]["count"], 1)


class GroupementTests(AuthedTestCase):
    def test_articles_groupes_par_categorie(self):
        alim = Category.objects.create(name="Alimentation")
        hygiene = Category.objects.create(name="Hygiène")
        Article.objects.create(name="Riz", base_price=1200, category=alim)
        Article.objects.create(name="Huile", base_price=6000, category=alim)
        Article.objects.create(name="Savon", base_price=350, category=hygiene)
        Article.objects.create(name="Pain", base_price=200)  # sans catégorie

        data = self.client.get(reverse("achats:articles-api")).json()

        # Les groupes suivent l'ordre alphabétique, « sans catégorie » en dernier.
        self.assertEqual([g["name"] for g in data["groups"]],
                         ["Alimentation", "Hygiène", None])
        self.assertEqual([g["count"] for g in data["groups"]], [2, 1, 1])
        self.assertEqual(data["groups"][0]["planned"], "7200")
        self.assertEqual(data["groups"][2]["articles"][0]["name"], "Pain")
        # La liste plate est conservée pour la compatibilité.
        self.assertEqual(len(data["articles"]), 4)

    def test_groupes_respectent_les_filtres(self):
        alim = Category.objects.create(name="Alimentation")
        Article.objects.create(name="Riz", base_price=1200, category=alim)
        Article.objects.create(name="Savon", base_price=350)

        data = self.client.get(reverse("achats:articles-api"), {"q": "sav"}).json()
        self.assertEqual(len(data["groups"]), 1)
        self.assertIsNone(data["groups"][0]["name"])
        self.assertEqual(data["groups"][0]["articles"][0]["name"], "Savon")

    def test_tri_a_l_interieur_des_groupes(self):
        alim = Category.objects.create(name="Alimentation")
        Article.objects.create(name="Riz", base_price=1200, category=alim)
        Article.objects.create(name="Café", base_price=2500, category=alim)

        data = self.client.get(reverse("achats:articles-api"), {"ordering": "-price"}).json()
        names = [a["name"] for a in data["groups"][0]["articles"]]
        self.assertEqual(names, ["Café", "Riz"])


class CategoryApiTests(AuthedTestCase):
    def post(self, payload):
        return self.client.post(
            reverse("achats:categories-api"), payload, content_type="application/json"
        )

    def test_creer_categorie(self):
        res = self.post({"name": "Transport"})
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.json()["category"]["name"], "Transport")
        self.assertTrue(Category.objects.filter(name="Transport").exists())

    def test_nom_obligatoire(self):
        self.assertEqual(self.post({"name": "   "}).status_code, 400)

    def test_categorie_deja_existante(self):
        Category.objects.create(name="Transport")
        res = self.post({"name": "  transport "})
        self.assertEqual(res.status_code, 400)
        self.assertEqual(Category.objects.filter(name__iexact="transport").count(), 1)

    def test_nouvelle_categorie_depuis_article(self):
        res = self.client.post(
            reverse("achats:articles-api"),
            {"name": "Gaz", "base_price": "7000", "category_name": "Maison"},
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 201)
        art = Article.objects.get(name="Gaz")
        self.assertEqual(art.category.name, "Maison")


class PageTests(AuthedTestCase):
    def test_page_principale(self):
        res = self.client.get(reverse("achats:home"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Achats du jour")

    def test_historique(self):
        art = Article.objects.create(name="Riz", base_price=1000)
        DailyEntry.objects.create(article=art, date=timezone.localdate(), done=True, quantity=2)
        data = self.client.get(reverse("achats:history-api")).json()
        self.assertEqual(len(data["days"]), 1)
        self.assertEqual(data["days"][0]["total"], "2000")


class AuthTests(TestCase):
    """Accès protégé, pages de connexion et d'inscription."""

    def test_accueil_redirige_vers_connexion(self):
        res = self.client.get(reverse("achats:home"))
        self.assertEqual(res.status_code, 302)
        self.assertIn(reverse("achats:login"), res["Location"])
        self.assertIn(f"next={reverse('achats:home')}", res["Location"])

    def test_api_refuse_sans_connexion(self):
        for name in ("articles-api", "history-api"):
            with self.subTest(api=name):
                res = self.client.get(reverse(f"achats:{name}"))
                self.assertEqual(res.status_code, 401)
                self.assertEqual(res.json()["error"], "Authentification requise.")

    def test_api_refuse_ecriture_sans_connexion(self):
        res = self.client.post(
            reverse("achats:articles-api"),
            {"name": "Riz", "base_price": "1000"},
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 401)
        self.assertEqual(Article.objects.count(), 0)

    def test_page_connexion(self):
        res = self.client.get(reverse("achats:login"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Se connecter")
        self.assertContains(res, reverse("achats:signup"))

    def test_page_inscription(self):
        res = self.client.get(reverse("achats:signup"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Créer un compte")

    def test_connexion_avec_identifiants_valides(self):
        User.objects.create_user(username="harina", password="MotDePasse123!")
        res = self.client.post(
            reverse("achats:login"),
            {"username": "harina", "password": "MotDePasse123!"},
        )
        self.assertEqual(res.status_code, 302)
        self.assertEqual(res["Location"], reverse("achats:home"))
        self.assertEqual(self.client.get(reverse("achats:home")).status_code, 200)

    def test_connexion_avec_mauvais_mot_de_passe(self):
        User.objects.create_user(username="harina", password="MotDePasse123!")
        res = self.client.post(
            reverse("achats:login"), {"username": "harina", "password": "faux"}
        )
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "incorrect")

    def test_inscription_cree_le_compte_et_connecte(self):
        res = self.client.post(
            reverse("achats:signup"),
            {
                "username": "nouveau",
                "email": "nouveau@exemple.com",
                "password1": "MotDePasse123!",
                "password2": "MotDePasse123!",
            },
        )
        self.assertEqual(res.status_code, 302)
        self.assertTrue(User.objects.filter(username="nouveau").exists())
        # L'utilisateur est connecté : la page principale répond directement.
        self.assertEqual(self.client.get(reverse("achats:home")).status_code, 200)
        self.assertEqual(self.client.get(reverse("achats:articles-api")).status_code, 200)

    def test_inscription_mots_de_passe_differents(self):
        res = self.client.post(
            reverse("achats:signup"),
            {
                "username": "nouveau",
                "password1": "MotDePasse123!",
                "password2": "AutreMotDePasse456!",
            },
        )
        self.assertEqual(res.status_code, 200)
        self.assertFalse(User.objects.filter(username="nouveau").exists())

    def test_inscription_mot_de_passe_trop_court(self):
        res = self.client.post(
            reverse("achats:signup"),
            {"username": "nouveau", "password1": "abc", "password2": "abc"},
        )
        self.assertEqual(res.status_code, 200)
        self.assertFalse(User.objects.filter(username="nouveau").exists())

    def test_deconnexion(self):
        user = User.objects.create_user(username="harina", password="MotDePasse123!")
        self.client.force_login(user)
        res = self.client.post(reverse("achats:logout"))
        self.assertEqual(res.status_code, 302)
        self.assertEqual(self.client.get(reverse("achats:home")).status_code, 302)

    def test_destination_apres_connexion(self):
        User.objects.create_user(username="harina", password="MotDePasse123!")
        url = reverse("achats:login") + f"?next={reverse('achats:home')}"
        res = self.client.post(
            url, {"username": "harina", "password": "MotDePasse123!"}
        )
        self.assertEqual(res["Location"], reverse("achats:home"))

    def test_redirection_ouverte_refusee(self):
        res = self.client.post(
            reverse("achats:signup") + "?next=https://exemple.com/piege",
            {
                "username": "nouveau",
                "password1": "MotDePasse123!",
                "password2": "MotDePasse123!",
            },
        )
        self.assertEqual(res.status_code, 302)
        self.assertEqual(res["Location"], reverse("achats:home"))
