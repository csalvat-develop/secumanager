# Changelog

Toutes les modifications notables apportées à Secu Manager sont
documentées dans ce fichier.

Le format suit [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/)
et le projet adhère au [Versionnage Sémantique](https://semver.org/lang/fr/).

---

## [0.6.0] — 2026-06

### Changements importants

- **Changement de licence** : passage de Creative Commons BY-NC-SA 4.0
  à **GNU General Public License v3.0 ou ultérieure**
  (GPL-3.0-or-later). L'usage commercial est désormais autorisé. Les
  versions 0.5.4 et antérieures restent disponibles de façon
  irrévocable sous CC BY-NC-SA 4.0.
- **Publication du code source sur GitHub** sous la nouvelle licence.

### Ajouté

- **Nom du club configurable**. Dans Paramètres, nouvelle section
  « Nom du club » (avant les logos) avec un bouton qui ouvre un
  dialogue de saisie d'un nom court (ex. CSSA) et d'un nom long
  (ex. Cercle Sportif Sous-marin d'Aubagne). Ces valeurs sont
  stockées dans la table `config` sous les clés `club_nom_court`
  et `club_nom_long`.

- **Personnalisation de l'email d'envoi des fiches**. Le sujet
  devient `Fiches de sécurités (X plongée(s)) du <nom_court>`.
  Le corps : `Bonjour, Veuillez trouver ci-joint les fiches de
  sécurité du <nom_court>, <nom_long> pour la sortie du <date_debut>
  au <date_fin>. Cordialement,`. Si les deux dates sont identiques,
  affichage simplifié « du <date> ». Si le nom du club n'est pas
  configuré, retombe sur le nom de la sortie (rétro-compatibilité).

- **Aptitude « Débutant »** (affichée « Déb. ») ajoutée aux Dropdown
  d'aptitude pour les palanquées de type Exploration encadrée,
  Technique et Baptême.

- **Nouvelles règles d'âge FFESSM** dans la composition des
  palanquées (alertes non bloquantes, le DP garde le dernier mot
  via le dialogue de confirmation) :

  - **Baptême par âge** :
    - âge < 8 ans → alerte « Pas de plongée en scaphandre avant
      8 ans (FFESSM) »
    - 8 ≤ âge < 10 ans → alerte si profondeur > 2 m
    - 10 ≤ âge ≤ 14 ans → alerte si profondeur > 3 m

  - **Formation Débutant → Plongeur Bronze, 8-14 ans** : alerte si
    profondeur > 6 m, alerte si plus d'un enfant en formation Bronze
    par encadrant (2 toléré en fin de formation).

  - **Plongeur Bronze 8-14 ans en exploration** : alerte si
    profondeur > 6 m, alerte si non encadré par E1-E4, alerte si
    effectif > 2 plongeurs encadrés.

  - **Plongeur Argent 8-14 ans en exploration** : alerte si
    profondeur > 6 m, alerte si effectif > 2 plongeurs (ou > 3 si
    un N1+ est présent dans la palanquée).

  - **Plongeur Or en exploration** :
    - 10 ≤ âge < 12 → alerte si profondeur > 12 m
    - 12 ≤ âge < 14 → alerte si profondeur > 20 m
    - Effectif > 2 (ou > 3 si N1+ présent) → alerte

  - **PA40 < 17 ans en exploration autonome** : alerte « pas de
    prérogative d'autonomie avant 17 ans (Code du sport) ».

### Modifié

- Requête SQL `dispo` du tab4 enrichie de `pc.date_naissance`
  (nécessaire au calcul d'âge des membres pour les nouvelles règles).
- Structure interne `t4_state` enrichie d'un index `label_to_age`
  rempli automatiquement au rafraîchissement des membres.

### Documentation

- README mis à jour avec la nouvelle licence GPL-3.0 et le tableau
  historique des licences.
- En-tête de licence dans le code source mis à jour (mention
  transitionnelle CC BY-NC-SA pour les versions <= 0.5.4, GPL-3.0
  pour les versions >= 0.6.0).
- Ajout d'un `CHANGELOG.md` (ce fichier).
- Ajout d'un `.gitignore` strict (protège clés de signature, base
  de données et données personnelles RGPD).

---

## [0.5.4] — 2026-05

### Ajouté

- Bouton « 🚨 Effacement total des données » dans Paramètres
  (conformité RGPD : droit à l'effacement complet, avec double
  confirmation par saisie du mot « EFFACER »).
- Bouton « 🗑️ Vider la base des plongeurs » dans Paramètres
  (effacement partiel du référentiel FFESSM).
- Simplifications d'affichage Plongeur Or / Argent / Bronze
  (sans le préfixe « Plongeur ») dans tab3, tab4 et PDF.
- Bouton « 📤 Partager » via la share sheet Android native, ajouté à
  la génération des PDF, à l'export CSV des inscriptions, à l'export
  JSON des sorties et à la sauvegarde de la base.
- Helper unique `offer_share_files()` factorisant les quatre partages.

### Corrigé

- DatePicker : décalage d'un jour sur Android (bug Flet #5923) corrigé
  par compensation via `+12h` au datetime reçu.
- Import FFESSM : les dates Excel (numéros de série, ex. 46258)
  étaient affichées brutes. Décodage ajouté dans `norm_date()`.
- Tableau participants : alignement entre en-tête et lignes de données
  (widths à 160 pour les colonnes Niveau et N. prépa.).

### Publication

- Première publication sur le Play Store en test fermé et test interne
  (versionCode 504, bundle id `fr.csdev.secumanager`).
- Politique de confidentialité hébergée sur
  https://secu-manager-politique.netlify.app/.

---

## [0.5.3] — 2026-05

### Ajouté

- Installation automatique des logos par défaut (CSSA + FFESSM) au
  premier lancement, depuis le dossier `assets/`.
- Stockage persistant des logos sélectionnés par l'utilisateur :
  copie immédiate dans le stockage privé (correction du bug Android
  des chemins temporaires).

---

## [0.5.2] — 2026-04

### Ajouté

- Détection automatique de l'environnement Android via
  `FLET_APP_STORAGE_DATA`, basculement de la base de données vers le
  stockage privé persistant.
- Helper `app_dir()` pour les chemins de sortie (PDF, exports,
  sauvegardes) compatible Android et Windows.
- Parseur XLSX natif (zipfile + xml.etree) en remplacement de pandas,
  pour la compatibilité Android.
- Export CSV des inscriptions en pur Python (UTF-8 BOM) en
  remplacement de openpyxl.
- En-tête de licence dans le code source.

### Modifié

- Suppression des dépendances `pandas` et `openpyxl` (incompatibles
  avec le packaging Android Flet).

---

## [0.5.1] et antérieures

Versions de développement initiales sur PC Windows (Tkinter puis Flet
Desktop), portage vers mobile Android. Ajout progressif des
fonctionnalités : participants, inscriptions, palanquées, fiches PDF,
import FFESSM, etc.

### Versions notables

- Règles du Code du sport dans la composition des palanquées
  (blocages + alertes non bloquantes).
- Affichage spécifique des mineurs (âge en gras dans tab4 et PDF).
- Helper `fmt_niveau()` pour la simplification de l'affichage des
  niveaux (Niveau 1 -> N1, Plongeur Or -> Or, etc.).
- Synthèse des plongeurs (encadrants, en formation, à encadrer,
  autonomes) en tab2 et tab4.
- DatePicker et TimePicker.
- Gestion des gaz par membre (Air/Nitrox + pourcentage).
- Export/import JSON des sorties.
- Sauvegarde/restauration de la base de données.
- Configuration SMTP et envoi des fiches par email.
