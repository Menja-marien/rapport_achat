from django.contrib.auth import views as auth_views
from django.urls import path

from . import views
from .forms import LoginForm

app_name = "achats"

urlpatterns = [
    # --- Authentification -------------------------------------------------
    path(
        "connexion/",
        auth_views.LoginView.as_view(
            template_name="registration/login.html",
            authentication_form=LoginForm,
            redirect_authenticated_user=True,
        ),
        name="login",
    ),
    path("deconnexion/", auth_views.LogoutView.as_view(), name="logout"),
    path("inscription/", views.signup, name="signup"),

    # --- Application ------------------------------------------------------
    path("", views.home, name="home"),
    path("api/articles/", views.articles_api, name="articles-api"),
    path("api/articles/<int:pk>/", views.article_api, name="article-api"),
    path("api/entries/", views.entry_api, name="entry-api"),
    path("api/entries/bulk/", views.bulk_api, name="bulk-api"),
    path("api/history/", views.history_api, name="history-api"),
    path("api/categories/", views.categories_api, name="categories-api"),
]
