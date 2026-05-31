# Secu Manager

**Gestion des sorties de plongée FFESSM — Application mobile (Android)**

Version 0.6.0 — Sous licence GNU General Public License v3.0 ou ultérieure

---

## Présentation

Secu Manager est une application mobile destinée aux clubs de plongée
affiliés à la FFESSM. Elle permet :

- de gérer un référentiel de plongeurs (import des licenciés FFESSM via
  fichier Excel ou CSV),
- d'organiser des sorties de plongée multi-jours,
- de composer les palanquées dans le respect du Code du sport,
- de générer des fiches de sécurité au format PDF (portrait ou paysage),
- d'envoyer les fiches par email ou de les partager via les apps Android,
- d'exporter et sauvegarder les données pour transfert ou archivage.

L'application est conçue pour fonctionner **entièrement hors ligne** :
toutes les données restent sur l'appareil de l'utilisateur, dans une
base SQLite privée. Aucun serveur tiers n'est sollicité.

## Fonctionnalités principales

**Référentiel des plongeurs.** Import direct depuis un fichier
d'extraction FFESSM (XLSX ou CSV). Le parseur XLSX est intégré
(zipfile + xml.etree, sans dépendance externe), ce qui rend l'app
entièrement autonome sur Android.

**Gestion des sorties.** Création, ouverture, suppression de sorties
multi-jours avec configuration du nombre de plongées par jour.
Inscription des participants par sélection dans le référentiel ou
ajout manuel (plongeurs extérieurs au club).

**Palanquées et règles FFESSM.** Constitution de palanquées avec
contrôles automatiques du Code du sport (blocages absolus) et alertes
réglementaires non bloquantes (profondeurs, encadrement, niveaux
préparés). Affichage spécifique des mineurs.

**Fiches de sécurité PDF.** Génération avec logos personnalisables,
format portrait (1 palanquée par ligne) ou paysage (3 palanquées par
ligne). Envoi par email via le SMTP configuré, ou partage via la
share sheet Android.

**Protection des données.** Conformité RGPD : effacement partiel
(référentiel) ou total des données directement depuis l'application.
Stockage privé persistant, aucune transmission à des tiers à
l'initiative de l'app.

## Structure du projet

```
secu_apk/
├── pyproject.toml          Configuration du build Flet
├── README.md               Ce fichier
├── LICENSE                 Texte de la GPL v3
├── CHANGELOG.md            Historique des versions
├── privacy_policy.md       Politique de confidentialité
├── .gitignore              Fichiers exclus du dépôt Git
└── src/
    ├── main.py             Code source de l'application
    └── assets/
        ├── icon.png        Icône de l'application
        ├── logo1_default.png    Logo gauche par défaut (PDF)
        └── logo2_default.png    Logo droit par défaut (PDF)
```

## Build

L'application est construite avec [Flet](https://flet.dev) (Python +
Flutter). Prérequis : Flutter SDK, Android Studio (JDK + Android SDK),
Python 3.9+.

**Build APK pour test local** :

```
flet build apk -v
```

**Build AAB signé pour Play Store** (en une ligne) :

```
flet build aab --android-signing-key-store "C:\chemin\secumanager-upload.jks" --android-signing-key-alias secumanager-upload --android-signing-key-store-password "MDP" --android-signing-key-password "MDP"
```

Les fichiers sont produits dans `build/apk/` ou `build/aab/`.

## Conventions de versionnage

Trois valeurs doivent rester synchronisées avant chaque build :

| Emplacement                  | Format     | Exemple |
|------------------------------|-----------:|--------:|
| `APP_VERSION` dans `main.py` | string     | `0.6.0` |
| `version` dans `pyproject.toml` | string  | `0.6.0` |
| `build_number` dans `pyproject.toml` | int | `600`  |

Le `build_number` correspond au `versionCode` Android. Il doit
strictement augmenter entre chaque publication sur le Play Store.

## Politique de confidentialité

Hébergée à l'adresse :
[https://secu-manager-politique.netlify.app/](https://secu-manager-politique.netlify.app/)

## Licence

À partir de la version 0.6.0, Secu Manager est distribué sous licence
**GNU General Public License v3.0 ou toute version ultérieure**
(GPL-3.0-or-later).

Cela signifie que vous êtes libre d'utiliser, modifier et redistribuer
le code, **y compris à des fins commerciales**, à condition de :

- conserver les avis de copyright et de licence ;
- distribuer toute version modifiée également sous GPL v3 (ou
  ultérieure) ;
- fournir le code source de toute version distribuée.

Le texte complet de la licence se trouve dans le fichier `LICENSE` à
la racine du projet.

### Historique des licences

| Versions | Licence |
|---|---|
| 0.5.4 et antérieures | Creative Commons BY-NC-SA 4.0 |
| 0.6.0 et suivantes   | GNU GPL v3 ou ultérieure |

Les versions distribuées sous CC BY-NC-SA 4.0 restent disponibles sous
cette licence de façon irrévocable. Le changement ne s'applique qu'aux
versions à partir de la 0.6.0.

## Contribuer

Les contributions sont bienvenues ! Pour proposer une modification :

1. Fork le dépôt
2. Crée une branche pour ta modification
3. Ouvre une Pull Request

Toute contribution acceptée sera intégrée sous la même licence GPL v3
que le projet. Tu conserves la titularité de tes droits d'auteur sur
ta contribution.

## Auteur

**Cédric SALVAT** ([cs.develop@free.fr](mailto:cs.develop@free.fr))
Développé pour le club CSSA.

## Avertissement

Cette application est fournie « EN L'ÉTAT », SANS GARANTIE D'AUCUNE
SORTE, conformément aux termes de la GNU GPL v3. Elle constitue un
outil d'aide à l'organisation des sorties et ne se substitue pas à la
responsabilité du directeur de plongée, ni au respect du Code du sport
et des règles de sécurité de la FFESSM.
