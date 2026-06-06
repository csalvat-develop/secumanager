# Changelog

Toutes les modifications notables apportées à Secu Manager sont
documentées dans ce fichier.

Le format suit [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/)
et le projet adhère au [Versionnage Sémantique](https://semver.org/lang/fr/).

---

## [0.7.5] — 2026-06

### Ajouté

- **Onglet « Composer »** (6e onglet, après Fiches).
  Envoi d'un email ou d'un SMS groupé à tous les participants de
  la sortie active, via l'application native du téléphone.
  - Switch pour basculer entre mode Email et mode SMS (libellé
    dynamique).
  - Compteur de destinataires valides (vert si OK, rouge sinon),
    actualisé à l'entrée dans l'onglet et au changement de mode.
  - Champ « Objet » pré-rempli à l'entrée dans l'onglet avec
    `Sortie [Nom] du [date_début] [au date_fin]`, modifiable
    librement.
  - Champ « Corps du message » multi-ligne, pleine largeur.
  - Bouton « ✉️ Ouvrir l'app pour envoyer ».
  - Mode Email : tous les destinataires en BCC (copie cachée)
    pour respecter la confidentialité.
  - Mode SMS : `sms:numéros,…?body=…` avec numéros nettoyés
    (espaces, tirets, parenthèses, points retirés).

- **Boutons d'action Email / Tél / SMS** dans les fiches
  plongeur (Onglet Participants et menu Vérification CACI).
  Trois `IconButton` colorés et centrés en bas de la fiche :
  ✉️ bleu (mailto), 📞 vert (tel), 💬 orange (sms).
  Chaque bouton est désactivé si la donnée correspondante est
  absente. Tous passent par un helper `safe_launch_url`
  compatible avec Android (voir Corrections).

- **Helper `safe_launch_url`** pour ouvrir une URL via
  `page.launch_url` avec le bon pattern coroutine async, requis
  par Flet 0.85 sur Android. Évite que les boutons mailto, tel
  ou sms restent silencieux. Pas de message snack après
  l'appel pour ne pas voler le focus à l'intent Android.

### Modifié

- **Onglet Palanquées — Pop-up Gaz** : le slider % O₂ et son
  libellé ne s'affichent plus que si « Nitrox » est sélectionné.
  En mode « Air », ces éléments sont masqués (pas d'information
  inutile à l'écran).

- **Onglet Palanquées — Compteur** : remplacement de
  « X plongeur(s) sur cette plongée » par
  « X plongeurs » (≥2) ou « X plongeur » (0 ou 1). La mention
  redondante « → voir la synthèse » est retirée (le clic sur
  le bouton ouvre toujours la synthèse).

- **Onglet Palanquées — Types de palanquée** :
  - Boutons radio « Exploration encadrée » et « Exploration
    autonome » raccourcis en « Explo. encadrée » / « Explo.
    autonome » (les valeurs internes restent inchangées pour
    préserver le code existant).
  - Les deux radios « Explo. » sont sur une même ligne, comme
    les radios « Technique » et « Baptême ». Total : 2 lignes
    au lieu de 4.

- **Onglet Palanquées — Champs profondeur / durée / DTR** :
  largeurs et labels réduits pour tenir sur une seule ligne sur
  mobile : « Prof. (m) » (100 px) — « Durée (min) » (110 px) —
  « DTR (min) » (100 px, hint « opt. »).

- **Onglet Participants — Fiche plongeur** : refonte de la
  mise en page dans l'esprit ClubMessenger.
  - En-tête sombre conservé (icône 🤿 + nom prénom blanc 18 pt,
    numéro de licence en italique gris clair).
  - Lignes label/valeur uniformes sur une seule ligne (label
    gris à gauche, valeur à droite), au lieu du label gras
    au-dessus + valeur en dessous. Lecture plus dense.
  - Sections séparées par des Dividers : identité, santé,
    plongée, contact, admin.
  - Statut CACI affiché en badge coloré (« Périmé » / « À
    renouveler » / « Valide ») en complément de la date.
  - Valeurs sélectionnables pour copier-coller (email, licence,
    téléphone).

- **Onglet Participants — Liste des brevets** : scroll
  horizontal individuel par ligne pour les noms de brevets
  longs, avec `no_wrap=True` pour empêcher le passage à la
  ligne. Le dialogue garde une largeur stable.

### Corrigé

- **Lancement d'apps externes sur Android** : `page.launch_url`
  étant une coroutine en Flet 0.85, l'ancien appel synchrone
  direct était ignoré silencieusement sur Android. Toutes les
  ouvertures (mailto, tel, sms, geo:, https:) passent
  maintenant par `safe_launch_url` qui utilise
  `page.run_task(async def: await page.launch_url(url))`.

---

## [0.7.0] — 2026-06

### Ajouté

- **Centre de plongée support** (tab1).
  Nouveau bloc dans le formulaire de sortie, sous le champ Lieu :
  un Switch active/désactive l'usage d'un centre de plongée pour
  la sortie.
  - Le Dropdown liste les centres déjà enregistrés en base
    (réutilisables d'une sortie à l'autre).
  - Bouton ℹ️ « Détails » affiche les informations du centre avec
    liens cliquables : carte (Google Maps ou geo:), téléphone
    (composeur), email (client de messagerie). Bouton supprimer
    avec confirmation.
  - Bouton ➕ « Ajouter » ouvre un dialogue de saisie d'un nouveau
    centre : nom, adresse, point GPS, téléphone, email.
  - Le centre choisi est persisté avec la sortie (table `sorties`
    enrichie d'une colonne `centre_id`, migration automatique).
  - À l'envoi des fiches PDF par email (tab5), le destinataire est
    pré-rempli avec l'email du centre de la sortie active si
    renseigné.

- **Titre dynamique de l'AppBar** : la barre supérieure affiche
  maintenant le contexte de la sortie active sous la forme
  « Sortie [Nom] (date_debut [- date_fin]) ». Le titre se met à
  jour automatiquement à chaque modification du nom ou des dates
  de la sortie, ainsi qu'à l'ouverture ou à la création d'une
  sortie.

- **Switch Portrait / Paysage** dans tab5 (sous le bouton
  « Enregistrer heures et DP »).
  - Format Paysage par défaut (3 palanquées par ligne).
  - Le libellé du Switch change selon sa position :
    « PDF en format paysage » / « PDF en format portrait ».
  - Remplace les dialogues de choix d'orientation qui s'ouvraient
    à chaque clic sur « Générer les PDF » et « Envoyer par email ».
    Plus rapide à l'usage.

- **Vérification CACI** (menu hamburger, suite de la 0.6.1).
  - Affichage des noms de niveau simplifiés (N1, Or, Déb., etc.).
  - Colonnes redimensionnées pour gagner en lisibilité sur mobile.
  - Fenêtre du dialogue agrandie (480 × 620 px).
  - Au clic sur une ligne, ouverture d'une fiche détaillée du
    plongeur (niveau, brevets, nitrox, CACI, naissance, téléphone,
    email).

### Modifié

- **Onglets principaux** : remplacement des labels numérotés
  (`1. Sortie`, `2. Participants`, …) par des couples icône + nom
  (📅 Sortie, 👥 Participants, 📋 Plongées, 👨‍👩‍👧 Palanquées,
  📄 Fiches). Plus lisible sur petits écrans.
- **Tab2 — Participants** : les Dropdown Niveau et Niveau préparé
  sont verrouillés par défaut (toggle 🔒 / 🔓 pour les déverrouiller).
  Évite les modifications accidentelles sur les données importées
  du FFESSM.
- **Tab3 — Plongées** : suppression du bouton « 💾 Enregistrer »
  redondant (l'enregistrement est automatique au changement
  d'onglet).
- **Tab4 — Palanquées** : les noms des membres dans la liste des
  checkboxes peuvent maintenant s'afficher sur deux lignes (utile
  pour les enfants en formation dont le libellé combine niveau,
  niveau préparé et âge).
- Espacement légèrement augmenté entre le bloc Centre de plongée et
  les dates dans le formulaire de sortie.

### Corrigé

- `init_db()` : utilisation correcte de `conn.execute()` au lieu de
  `c.execute()` dans la création de la table `centres_plongee` et la
  migration de la colonne `centre_id` (corrigé avant la sortie).
- Tabs : utilisation correcte du paramètre `label` (Flet 0.85), pas
  `text`, pour le texte des onglets.

---

## [0.6.1] — 2026-06 *(non publiée séparément, intégrée dans la 0.7.0)*

### Ajouté

- **Duplication de palanquées entre plongées** (tab4) avec
  vérification de la disponibilité des plongeurs dans la cible.
- **Vérification CACI** dans le menu hamburger : repère les
  plongeurs dont le CACI est périmé ou expire avant la fin de la
  sortie active (sinon dans les 30 jours).
- **Affichage enrichi des membres dans tab4** : nom (niveau)
  -> niveau préparé simplifié - âge si mineur.

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

- **Nom du club configurable** dans Paramètres avec nom court et nom
  long, utilisés pour personnaliser le sujet et le corps de l'email
  d'envoi des fiches de sécurité.
- **Aptitude « Débutant »** (affichée « Déb. ») ajoutée aux Dropdown
  d'aptitude pour les palanquées de type Exploration encadrée,
  Technique et Baptême.
- **Nouvelles règles d'âge FFESSM** dans la composition des
  palanquées (alertes non bloquantes) :
  baptême par âge, formation Débutant -> Bronze, exploration des
  Plongeurs Bronze / Argent / Or, PA40 < 17 ans en autonome.

### Modifié

- Requête SQL `dispo` du tab4 enrichie de `pc.date_naissance` pour
  permettre les règles d'âge.
- Documentation : README, CHANGELOG, gitignore et politique de
  confidentialité mis à jour pour la nouvelle licence et les
  fonctions d'effacement RGPD.

---

## [0.5.4] — 2026-05

### Ajouté

- Bouton « 🚨 Effacement total des données » dans Paramètres
  (conformité RGPD, double confirmation par saisie de « EFFACER »).
- Bouton « 🗑️ Vider la base des plongeurs » (effacement partiel du
  référentiel FFESSM).
- Simplifications d'affichage Plongeur Or / Argent / Bronze
  (sans le préfixe « Plongeur ») dans tab3, tab4 et PDF.
- Bouton « 📤 Partager » via la share sheet Android native (PDF,
  CSV, JSON, sauvegarde base).

### Corrigé

- DatePicker : décalage d'un jour sur Android (bug Flet #5923)
  corrigé par compensation +12h.
- Import FFESSM : décodage des dates Excel (numéros de série).
- Tableau participants : alignement entre en-tête et lignes de
  données.

### Publication

- Première publication sur le Play Store en test fermé et test
  interne (versionCode 504, bundle id `fr.csdev.secumanager`).
- Politique de confidentialité hébergée sur
  https://secu-manager-politique.netlify.app/.

---

## [0.5.3] — 2026-05

### Ajouté

- Installation automatique des logos par défaut (CSSA + FFESSM) au
  premier lancement, depuis le dossier `assets/`.
- Stockage persistant des logos sélectionnés par l'utilisateur.

---

## [0.5.2] — 2026-04

### Ajouté

- Détection automatique de l'environnement Android via
  `FLET_APP_STORAGE_DATA`, basculement de la base de données vers
  le stockage privé persistant.
- Helper `app_dir()` pour les chemins de sortie (PDF, exports,
  sauvegardes) compatible Android et Windows.
- Parseur XLSX natif (zipfile + xml.etree) en remplacement de
  pandas, pour la compatibilité Android.
- Export CSV des inscriptions en pur Python (UTF-8 BOM).
- En-tête de licence dans le code source.

### Modifié

- Suppression des dépendances `pandas` et `openpyxl` (incompatibles
  avec le packaging Android Flet).

---

## [0.5.1] et antérieures

Versions de développement initiales sur PC Windows (Tkinter puis
Flet Desktop), portage vers mobile Android. Ajout progressif des
fonctionnalités : participants, inscriptions, palanquées, fiches
PDF, import FFESSM, etc.