#!/usr/bin/env bash
# Arrête le script en cas d'erreur
set -o errexit

# Installe les dépendances
pip install -r requirements.txt

# Rassemble les fichiers statiques (WhiteNoise)
python manage.py collectstatic --no-input

# Applique les migrations de la base de données
python manage.py migrate
