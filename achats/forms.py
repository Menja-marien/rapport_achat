"""Formulaires d'authentification (connexion + création de compte)."""
from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User

# Habillage commun des champs (aligné sur le reste de l'application, Tailwind).
INPUT_CLASS = (
    "w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm "
    "text-slate-900 outline-none transition placeholder:text-slate-400 "
    "focus:border-indigo-500 focus:bg-white"
)

WIDGET_ATTRS = {
    "username": {"placeholder": "ex. harina", "autocomplete": "username", "autofocus": True},
    "email": {"placeholder": "ex. moi@exemple.com", "autocomplete": "email"},
    "password": {"placeholder": "••••••••", "autocomplete": "current-password"},
    "password1": {"placeholder": "••••••••", "autocomplete": "new-password"},
    "password2": {"placeholder": "••••••••", "autocomplete": "new-password"},
}


class LoginForm(AuthenticationForm):
    """Formulaire de connexion aux champs habillés en Tailwind."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            attrs = dict(WIDGET_ATTRS.get(name, {}))
            attrs["class"] = INPUT_CLASS
            field.widget.attrs.update(attrs)
        self.fields["username"].label = "Nom d'utilisateur"
        self.fields["password"].label = "Mot de passe"


class SignUpForm(UserCreationForm):
    """Création de compte : nom d'utilisateur, e-mail facultatif, mot de passe ×2."""

    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        labels = {
            "username": "Nom d'utilisateur *",
            "email": "Adresse e-mail (facultatif)",
            "password1": "Mot de passe *",
            "password2": "Confirmation du mot de passe *",
        }
        help_texts = {
            "username": "150 caractères max. Lettres, chiffres et @ . + - _ uniquement.",
            "email": "Facultatif : servi uniquement pour retrouver votre compte.",
            "password1": "8 caractères minimum. Évitez les mots de passe trop simples.",
            "password2": "Retapez exactement le même mot de passe.",
        }

        for name, field in self.fields.items():
            attrs = dict(WIDGET_ATTRS.get(name, {}))
            attrs["class"] = INPUT_CLASS
            field.widget.attrs.update(attrs)
            field.label = labels.get(name, field.label)
            field.help_text = help_texts.get(name, field.help_text)
