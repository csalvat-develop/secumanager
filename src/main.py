# =====================================================
# Secu Manager — Gestion des sorties de plongée FFESSM
# Copyright (C) 2026 Cédric SALVAT
# Développé pour le club CSSA
#
# Versions 0.5.4 et antérieures :
#   distribuées sous Creative Commons BY-NC-SA 4.0
# Versions 0.6.0 et suivantes :
#   distribuées sous GNU General Public License v3.0
#   ou toute version ultérieure (GPL-3.0-or-later).
#
# Ce programme est un logiciel libre : vous pouvez le
# redistribuer et/ou le modifier suivant les termes de
# la GNU General Public License telle que publiée par
# la Free Software Foundation, version 3 de la Licence,
# ou (à votre option) toute version ultérieure.
#
# Ce programme est distribué dans l'espoir qu'il sera
# utile, mais SANS AUCUNE GARANTIE, sans même la
# garantie implicite de COMMERCIALISATION ou
# d'ADÉQUATION À UN USAGE PARTICULIER. Voir la GNU
# General Public License pour plus de détails :
# https://www.gnu.org/licenses/gpl-3.0.html
#
# Cet outil est une aide à l'organisation ; il ne se
# substitue pas à la responsabilité du directeur de
# plongée ni au respect du Code du sport et de la
# FFESSM.
# =====================================================

import flet as ft
import sqlite3
import csv
import threading
import os
import unicodedata
import json
import shutil

from datetime import datetime, timedelta, time

try:
    from fpdf import FPDF
    from fpdf.enums import XPos, YPos
    FPDF_AVAILABLE = True
except Exception:
    FPDF_AVAILABLE = False


def clean_txt(s):
    """Sanitize pour FPDF (Latin-1, sans accents
    problématiques)."""
    if s is None:
        return ""
    s = str(s)
    # Remplacer les caractères non Latin-1 par leur
    # équivalent ASCII quand possible
    try:
        s.encode("latin-1")
        return s
    except Exception:
        return (
            unicodedata.normalize("NFKD", s)
            .encode("latin-1", "ignore")
            .decode("latin-1")
        )

# =====================================================
# VERSION
# =====================================================

APP_VERSION = "0.6.0"

# =====================================================
# BASE SQLITE
# =====================================================

DB_PATH = "suivi_plongee.db"


TOUS_NIVEAUX = [

    "Débutant",

    "PE12",
    "PA12",
    "PE20",
    "PA20",
    "Niveau 1",
    "PE40",
    "Niveau 2",
    "PA40",
    "Niveau 3",
    "PE60",
    "GP",
    "E1",
    "E2",
    "E3",
    "E4",
    "Plongeur Or",
    "Plongeur Argent",
    "Plongeur Bronze",
]


def init_db():

    conn = sqlite3.connect(DB_PATH)

    # Ancienne table conservée pour compat — pas utilisée par tab2
    conn.execute("""
        CREATE TABLE IF NOT EXISTS plongeurs(

            id_plongeur TEXT PRIMARY KEY,
            nom TEXT,
            prenom TEXT,
            caci_date TEXT,
            selectionne INTEGER DEFAULT 0

        )
    """)

    # Base club : référentiel des plongeurs (importé FFESSM ou manuel)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS plongeurs_club(

            id_licence TEXT PRIMARY KEY,
            nom TEXT,
            prenom TEXT,
            niveau TEXT,
            brevets TEXT,
            brevet_moniteur TEXT,
            brevet_encadrant TEXT,
            brevet_plongeur TEXT,
            brevet_nitrox TEXT,
            caci_date TEXT,
            date_naissance TEXT,
            date_import TEXT,
            date_inscription TEXT,
            saison TEXT,
            portable TEXT,
            email TEXT,
            type_licence TEXT

        )
    """)

    # Migration : ajouter brevet_nitrox si absente
    try:
        cols_pc = [
            row[1]
            for row in conn.execute(
                "PRAGMA table_info(plongeurs_club)"
            ).fetchall()
        ]
        if "brevet_nitrox" not in cols_pc:
            conn.execute(
                "ALTER TABLE plongeurs_club"
                " ADD COLUMN brevet_nitrox TEXT"
            )
            conn.commit()
    except Exception as mig:
        print("Migration brevet_nitrox:", mig)

    # Sorties (pour rattacher les participants)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sorties(

            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nom TEXT,
            lieu TEXT,
            date_debut TEXT,
            date_fin TEXT

        )
    """)

    # --- Migration : si une ancienne table 'sorties' existe
    # sans colonne 'id', on la recrée proprement.
    try:

        cols = [

            row[1]
            for row in conn.execute(
                "PRAGMA table_info(sorties)"
            ).fetchall()
        ]

        if "id" not in cols:

            print(
                "Migration : recréation de la table"
                " 'sorties' (schéma obsolète)."
            )

            # Sauvegarde des données existantes si possible
            old_data = []

            try:

                old_data = conn.execute(
                    "SELECT * FROM sorties"
                ).fetchall()

            except Exception:
                pass

            conn.execute("ALTER TABLE sorties RENAME TO sorties_old")

            conn.execute("""
                CREATE TABLE sorties(

                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nom TEXT,
                    lieu TEXT,
                    date_debut TEXT,
                    date_fin TEXT

                )
            """)

            # Réinjection best-effort (colonnes communes)
            old_cols = [

                row[1]
                for row in conn.execute(
                    "PRAGMA table_info(sorties_old)"
                ).fetchall()
            ]

            common = [

                c
                for c in ("nom", "lieu",
                          "date_debut", "date_fin")
                if c in old_cols
            ]

            if common and old_data:

                idx = {

                    c: old_cols.index(c)
                    for c in common
                }

                for row in old_data:

                    vals = [
                        row[idx[c]]
                        for c in common
                    ]

                    placeholders = ", ".join(
                        ["?"] * len(common)
                    )

                    conn.execute(

                        f"INSERT INTO sorties"
                        f" ({', '.join(common)})"
                        f" VALUES ({placeholders})",

                        vals
                    )

            conn.execute("DROP TABLE sorties_old")

            conn.commit()

    except Exception as mig_err:

        print("Erreur migration sorties:", mig_err)

    # Participants de la sortie courante
    conn.execute("""
        CREATE TABLE IF NOT EXISTS participants(

            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sortie_id INTEGER,
            type TEXT,
            nom TEXT,
            prenom TEXT,
            niveau TEXT,
            niveau_prepa TEXT,
            lien_plongeur TEXT

        )
    """)

    # Jours de la sortie (nb de plongées par jour)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS jours_sortie(

            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sortie_id INTEGER,
            date_jour TEXT,
            nb_plongees INTEGER

        )
    """)

    # Plongées cochées par plongeur (tab3)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS plongees_realisees(

            id INTEGER PRIMARY KEY AUTOINCREMENT,
            participant_id INTEGER,
            date_jour TEXT,
            num_plongee INTEGER

        )
    """)

    # Palanquées (tab4)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS palanquees_sortie(

            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sortie_id INTEGER,
            date_jour TEXT,
            num_plongee INTEGER,
            ordre INTEGER,
            type TEXT,
            prof_max REAL,
            duree_max INTEGER,
            dtr_max INTEGER

        )
    """)

    # Migration : ajouter dtr_max si absente
    try:
        cols_ps = [
            row[1]
            for row in conn.execute(
                "PRAGMA table_info(palanquees_sortie)"
            ).fetchall()
        ]
        if "dtr_max" not in cols_ps:
            conn.execute(
                "ALTER TABLE palanquees_sortie"
                " ADD COLUMN dtr_max INTEGER"
            )
            conn.commit()
    except Exception as mig:
        print("Migration dtr_max:", mig)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS palanquee_membres(

            id INTEGER PRIMARY KEY AUTOINCREMENT,
            palanquee_id INTEGER,
            participant_id INTEGER,
            role TEXT,
            gaz TEXT,
            aptitude TEXT

        )
    """)

    # Migration : ajouter colonne aptitude si absente
    try:
        cols_pm = [
            row[1]
            for row in conn.execute(
                "PRAGMA table_info(palanquee_membres)"
            ).fetchall()
        ]
        if "aptitude" not in cols_pm:
            conn.execute(
                "ALTER TABLE palanquee_membres"
                " ADD COLUMN aptitude TEXT"
            )
            conn.commit()
    except Exception as mig:
        print("Migration aptitude:", mig)

    # Jours / nb plongées par jour de la sortie
    conn.execute("""
        CREATE TABLE IF NOT EXISTS jours_sortie(

            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sortie_id INTEGER,
            date_jour TEXT,
            nb_plongees INTEGER

        )
    """)

    # Config clé/valeur (verrou tab3, etc.)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS config(

            key TEXT PRIMARY KEY,
            value TEXT

        )
    """)

    # Fiches sécurité : heure + DP par plongée
    conn.execute("""
        CREATE TABLE IF NOT EXISTS fiches_securite(

            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sortie_id INTEGER,
            date_jour TEXT,
            num_plongee INTEGER,
            heure TEXT,
            dp TEXT

        )
    """)

    conn.commit()
    conn.close()


def calc_age(naiss_str):

    try:

        dn = datetime.strptime(
            str(naiss_str).strip(),
            "%d/%m/%Y"
        ).date()

        today = datetime.now().date()

        return (
            today.year
            - dn.year
            - (
                (today.month, today.day) < (dn.month, dn.day)
            )
        )

    except Exception:

        return None


def caci_color(caci_str):

    if not caci_str:
        return "gray"

    try:

        dt = datetime.strptime(
            str(caci_str).strip(),
            "%d/%m/%Y"
        ).date()

        today = datetime.now().date()

        if dt < today:
            return "red"

        if dt < today + timedelta(days=30):
            return "orange"

        return "green"

    except Exception:

        return "gray"


def load_plongeurs_club():

    try:

        conn = sqlite3.connect(DB_PATH)

        cur = conn.execute("""

            SELECT

                id_licence,
                nom,
                prenom,
                niveau,
                brevet_moniteur,
                brevet_encadrant,
                brevet_plongeur,
                caci_date,
                date_naissance,
                brevet_nitrox

            FROM plongeurs_club

            ORDER BY nom

        """)

        rows = cur.fetchall()
        conn.close()

        result = []

        for r in rows:

            niv = (
                r[3]
                or r[4]
                or (r[5] if r[5] else r[6])
            )

            result.append({

                "id_licence": r[0] or "",

                "nom": r[1] or "",

                "prenom": r[2] or "",

                "niveau": niv or "",

                "caci": r[7] or "",

                "naiss": r[8] or "",

                "nitrox": (
                    r[9] if len(r) > 9 and r[9] else ""
                ),
            })

        return result

    except Exception as e:

        print("Erreur chargement plongeurs:", e)

        return []


def fmt_niveau(niveau, nitrox):
    """Affiche '{niveau} - {nitrox}' si nitrox existe."""
    niveau = (niveau or "").strip()
    nitrox = (nitrox or "").strip()

    SIMPLE_AFFICHAGE = {
        "Niveau 1": "N1",
        "Niveau 2": "N2",
        "Niveau 3": "N3",
        "Débutant": "Déb.",
        "Plongeur Or": "Or",
        "Plongeur Argent": "Argent",
        "Plongeur Bronze": "Bronze",
    }
    niveau = SIMPLE_AFFICHAGE.get(niveau, niveau)

    if nitrox:
        return f"{niveau} - {nitrox}"
    return niveau


def get_nitrox_map():
    """Retourne {(NOM_MAJ, PRENOM_MAJ): brev_nx}."""
    m = {}
    try:
        conn = sqlite3.connect(DB_PATH)
        for nom, prenom, nx in conn.execute(
            "SELECT nom, prenom, brevet_nitrox"
            " FROM plongeurs_club"
        ).fetchall():
            m[
                ((nom or "").strip().upper(),
                 (prenom or "").strip().upper())
            ] = nx or ""
        conn.close()
    except Exception as e:
        print("get_nitrox_map:", e)
    return m


# =====================================================
# APPLICATION
# =====================================================

def main(page: ft.Page):
    global DB_PATH  # Permet de modifier la variable définie en haut du script

    # --- Détection de l'OS / Environnement ---
    # Sur Android, Flet injecte la variable d'environnement
    # FLET_APP_STORAGE_DATA qui pointe vers le stockage privé
    # persistant. On l'utilise directement : page.data_dir
    # peut être None à ce stade et provoquer un crash.
    _storage = os.getenv("FLET_APP_STORAGE_DATA")
    if not _storage:
        # page.data_dir comme secours éventuel
        try:
            if page.data_dir:
                _storage = page.data_dir
        except Exception:
            _storage = None

    if _storage:
        # Android : DB dans le dossier interne sécurisé
        try:
            os.makedirs(_storage, exist_ok=True)
        except Exception:
            pass
        DB_PATH = os.path.join(_storage, "suivi_plongee.db")
        print(f"[Android] Base de données : {DB_PATH}")
    else:
        # Windows (mode test / développement)
        DB_PATH = os.path.join(
            os.getcwd(), "suivi_plongee.db"
        )
        print(f"[Windows Test] Base locale : {DB_PATH}")

    # Dossier de travail pour PDF, exports, sauvegardes
    def app_dir():
        """Renvoie un dossier inscriptible."""
        storage = os.getenv("FLET_APP_STORAGE_DATA")
        if not storage:
            try:
                if page.data_dir:
                    storage = page.data_dir
            except Exception:
                storage = None
        if storage:
            try:
                os.makedirs(storage, exist_ok=True)
            except Exception:
                pass
            return storage
        return os.getcwd()

    def assets_dir():
        """Renvoie le dossier des ressources embarquées
        (assets) de l'app, en testant les emplacements
        possibles selon le mode (build Android ou test
        Windows)."""
        candidats = []
        # 1) Variable injectée par Flet lors du packaging
        env_assets = os.getenv("FLET_ASSETS_DIR")
        if env_assets:
            candidats.append(env_assets)
        # 2) Dossier 'assets' à côté du script (test PC)
        try:
            base = os.path.dirname(os.path.abspath(__file__))
            candidats.append(os.path.join(base, "assets"))
        except Exception:
            pass
        # 3) Dossier 'assets' dans le répertoire courant
        candidats.append(os.path.join(os.getcwd(), "assets"))
        for d in candidats:
            try:
                if d and os.path.isdir(d):
                    return d
            except Exception:
                pass
        return None

    def install_default_logos():
        """Copie les logos par défaut (logo1_default.png et
        logo2_default.png) depuis les assets vers le
        stockage privé, au premier lancement uniquement.
        N'écrase jamais un logo déjà choisi par
        l'utilisateur."""
        a_dir = assets_dir()
        if not a_dir:
            return

        defauts = {
            1: "logo1_default.png",
            2: "logo2_default.png",
        }

        try:
            conn = sqlite3.connect(DB_PATH)
            for num, nom_fichier in defauts.items():
                key = f"logo{num}_path"

                # Ne rien faire si un logo est déjà
                # configuré ET que son fichier existe.
                r = conn.execute(
                    "SELECT value FROM config WHERE key=?",
                    (key,)
                ).fetchone()
                if r and r[0] and os.path.exists(r[0]):
                    continue

                src = os.path.join(a_dir, nom_fichier)
                if not os.path.exists(src):
                    continue

                ext = os.path.splitext(src)[1] or ".png"
                dest = os.path.join(
                    app_dir(), f"logo{num}{ext}"
                )

                try:
                    shutil.copy2(src, dest)
                    conn.execute(
                        "INSERT OR REPLACE INTO config"
                        "(key, value) VALUES (?, ?)",
                        (key, dest)
                    )
                except Exception as cp_err:
                    print("Copie logo défaut:", cp_err)

            conn.commit()
            conn.close()
        except Exception as err:
            print("install_default_logos:", err)

    # Configuration de la page Flet
    page.title = f"Gestion sorties plongée - v{APP_VERSION}"

    # =================================================
    # CONFIGURATION MOBILE (smartphone / portrait)
    # =================================================
    try:
        page.window.width = 420
        page.window.height = 850
        page.window.min_width = 320
        page.window.min_height = 600
        try:
            page.window.resizable = True
        except Exception:
            pass
    except Exception:
        try:
            page.window_width = 420
            page.window_height = 850
        except Exception:
            pass

    page.theme_mode = ft.ThemeMode.LIGHT

    # Mobile : padding réduit, scroll vertical auto
    page.padding = 10
    page.spacing = 8

    # Hauteur min tactile (≥ 48)
    TOUCH_H = 48

    # Largeur dynamique pour les dialogues
    def _w(maxv=480):
        try:
            return min(maxv, (page.window.width or 400) - 24)
        except Exception:
            return min(maxv, 360)

    init_db()

    # Installer les logos par défaut au premier lancement
    install_default_logos()

    # =================================================
    # CHAMPS SORTIE
    # =================================================

    sortie_nom = ft.TextField(
        label="Nom sortie",
        height=52,
        expand=True
    )

    sortie_lieu = ft.TextField(
        label="Lieu",
        height=52,
        expand=True
    )

    date_debut = ft.TextField(
        label="Date début JJ/MM/AAAA",
        height=52,
        expand=True
    )

    date_fin = ft.TextField(
        label="Date fin JJ/MM/AAAA",
        height=52,
        expand=True
    )

    def open_date_picker(champ):
        """Ouvre un calendrier et remplit le champ cible
        au format JJ/MM/AAAA."""

        # Date initiale : valeur du champ si valide, sinon
        # aujourd'hui
        init = datetime.now()
        try:
            if champ.value:
                init = datetime.strptime(
                    champ.value.strip(), "%d/%m/%Y"
                )
        except Exception:
            init = datetime.now()

        def on_pick(e):
            d = e.control.value
            if d is not None:
                # Bug Flet 0.85 connu (issue #5923) : le
                # DatePicker sérialise en UTC ce qui peut
                # décaler d'un jour selon le fuseau local.
                # Astuce universelle : ajouter 12 heures
                # au datetime reçu avant de lire le jour.
                # Quel que soit le décalage UTC (entre
                # -12 et +14h), midi du jour sélectionné
                # tombe toujours sur le bon jour local.
                try:
                    d_safe = d + timedelta(hours=12)
                    champ.value = (
                        f"{d_safe.day:02d}/"
                        f"{d_safe.month:02d}/"
                        f"{d_safe.year:04d}"
                    )
                except Exception:
                    try:
                        champ.value = (
                            f"{d.day:02d}/"
                            f"{d.month:02d}/"
                            f"{d.year:04d}"
                        )
                    except Exception:
                        champ.value = d.strftime("%d/%m/%Y")
                champ.update()

        dp = ft.DatePicker(
            first_date=datetime(2000, 1, 1),
            last_date=datetime(2100, 12, 31),
            value=init,
            on_change=on_pick,
        )

        page.show_dialog(dp)

    def make_date_btn(champ):
        return ft.IconButton(
            icon=ft.Icons.CALENDAR_MONTH,
            tooltip="Choisir dans le calendrier",
            bgcolor="#e0f2fe",
            on_click=lambda e: open_date_picker(champ)
        )

    date_debut_row = ft.Row(
        [date_debut, make_date_btn(date_debut)],
        spacing=4
    )

    date_fin_row = ft.Row(
        [date_fin, make_date_btn(date_fin)],
        spacing=4
    )

    jours_column = ft.Column(
        scroll=ft.ScrollMode.AUTO,
        expand=True
    )

    # =================================================
    # ÉTAT TAB2
    # =================================================

    # ID de la sortie courante (None = pas encore enregistrée)
    state = {

        "sortie_id": None,   # défini à l'enregistrement de la sortie

        "plongeurs_club": [],

        "text_lines": [],         # plongeurs affichés (1/ligne)

        "text_selected": set(),   # indices sélectionnés

        "participants_rows": [],  # liste de dicts (1 par participant)

        "jours_entries": [],      # liste (date_str, dropdown_nb)

        "tab3_vars": {},          # (pid, date, num) -> Checkbox

        "t3_locked": False,

        "t2_locked": False,

        "t4_current": None,       # (date, num) plongée sélectionnée

        "current_tab": 0,

        "t4_edit_id": None,
    }

    # Container pour la liste des plongeurs club (cliquable, coloration CACI)
    plongeurs_list_view = ft.ListView(

        height=260,

        spacing=0
    )

    # Tableau des participants (en-tête + lignes en Column)
    participants_header = ft.Row(

        controls=[

            ft.Container(
                ft.Text(
                    "Act.",
                    weight=ft.FontWeight.BOLD,
                    size=11
                ),
                width=44,
                padding=2,
                bgcolor="#f1f5f9",
                alignment=ft.Alignment.CENTER
            ),

            ft.Container(
                ft.Text(
                    "Dét.",
                    weight=ft.FontWeight.BOLD,
                    size=11
                ),
                width=44,
                padding=2,
                bgcolor="#f1f5f9",
                alignment=ft.Alignment.CENTER
            ),

            ft.Container(
                ft.Text(
                    "Nom Prénom",
                    weight=ft.FontWeight.BOLD,
                    size=11
                ),
                width=180,
                padding=4,
                bgcolor="#f1f5f9"
            ),

            ft.Container(
                ft.Text(
                    "Niv.",
                    weight=ft.FontWeight.BOLD,
                    size=11
                ),
                width=160,
                padding=4,
                bgcolor="#f1f5f9"
            ),

            ft.Container(
                ft.Text(
                    "N. prépa.",
                    weight=ft.FontWeight.BOLD,
                    size=11
                ),
                width=160,
                padding=4,
                bgcolor="#f1f5f9"
            ),
        ],

        spacing=2
    )

    participants_rows_column = ft.Column(

        spacing=2,

        scroll=ft.ScrollMode.AUTO
    )

    # Bouton-statistiques cliquable
    stats_part_btn = ft.TextButton(

        "0 participant",

        on_click=lambda e: show_synthese_participants()
    )


    # =================================================
    # ZONES
    # =================================================

    plongees_list = ft.ListView(
        expand=True
    )

    inscrits_column = ft.Column(
        scroll=ft.ScrollMode.AUTO,
        expand=True
    )

    palanquees_column = ft.Column(
        scroll=ft.ScrollMode.AUTO,
        expand=True
    )

    fiches_column = ft.Column(
        scroll=ft.ScrollMode.AUTO,
        expand=True
    )

    # =================================================
    # MESSAGE
    # =================================================

    def show_message(message):

        try:
            sb = ft.SnackBar(
                content=ft.Text(message),
                duration=4000
            )
            page.show_dialog(sb)
        except Exception:
            # Fallback : ancienne API
            try:
                page.snack_bar = ft.SnackBar(
                    content=ft.Text(message)
                )
                page.snack_bar.open = True
                page.update()
            except Exception:
                print("MESSAGE:", message)

    # =================================================
    # NOUVELLE SORTIE
    # =================================================

    def nouvelle_sortie(e):

        sortie_nom.value = ""
        sortie_lieu.value = ""
        date_debut.value = ""
        date_fin.value = ""

        state["sortie_id"] = None

        jours_column.controls.clear()

        # Reset participants
        state["participants_rows"].clear()
        participants_rows_column.controls.clear()
        update_stats_part()
        refresh_plongeurs_listbox()

        page.update()

        show_message("Nouvelle sortie")

    # =================================================
    # OUVRIR SORTIE
    # =================================================

    def make_jour_bloc(d_str, nb_value="2"):
        """Crée un bloc jour (Card + Dropdown) et
        retourne (bloc, dropdown)."""

        nb_dropdown = ft.Dropdown(

            width=100,

            label="Nb plongées",

            value=str(nb_value),

            options=[
                ft.DropdownOption("0"),
                ft.DropdownOption("1"),
                ft.DropdownOption("2"),
                ft.DropdownOption("3"),
                ft.DropdownOption("4"),
            ]
        )

        bloc = ft.Card(

            content=ft.Container(

                padding=10,

                content=ft.Row([

                    ft.Text(
                        d_str,
                        size=18,
                        weight=ft.FontWeight.BOLD
                    ),

                    nb_dropdown
                ])
            )
        )

        return bloc, nb_dropdown

    def load_sortie(sid):
        """Charge une sortie complète depuis la base."""

        conn = sqlite3.connect(DB_PATH)

        row = conn.execute(
            "SELECT nom, lieu, date_debut, date_fin"
            " FROM sorties WHERE id=?",
            (sid,)
        ).fetchone()

        if not row:
            conn.close()
            show_message("Sortie introuvable.")
            return

        nom, lieu, d_deb, d_fin = row

        sortie_nom.value = nom or ""
        sortie_lieu.value = lieu or ""
        date_debut.value = d_deb or ""
        date_fin.value = d_fin or ""

        state["sortie_id"] = sid

        # Recharger les jours
        jours_column.controls.clear()
        state["jours_entries"] = []

        jours = conn.execute(
            "SELECT date_jour, nb_plongees FROM"
            " jours_sortie WHERE sortie_id=? ORDER BY id",
            (sid,)
        ).fetchall()

        for d_str, nb in jours:

            bloc, dd = make_jour_bloc(d_str, nb)

            jours_column.controls.append(bloc)

            state["jours_entries"].append((d_str, dd))

        # Recharger les participants
        state["participants_rows"].clear()
        participants_rows_column.controls.clear()

        parts = conn.execute(
            "SELECT id, nom, prenom, niveau, niveau_prepa"
            " FROM participants WHERE sortie_id=?"
            " ORDER BY nom",
            (sid,)
        ).fetchall()

        # Table de correspondance niveau depuis la base
        # club (source de vérité), indexée par
        # (NOM_MAJ, PRENOM_MAJ)
        club_niv = {}

        for cr in conn.execute("""

            SELECT nom, prenom, niveau,
                   brevet_moniteur, brevet_encadrant,
                   brevet_plongeur

            FROM plongeurs_club

        """).fetchall():

            niv_club = (
                cr[2] or cr[3] or cr[4] or cr[5] or ""
            )

            club_niv[
                (
                    (cr[0] or "").strip().upper(),
                    (cr[1] or "").strip().upper()
                )
            ] = niv_club

        conn.close()

        for p_id, p_nom, p_pren, p_niv, p_prepa in parts:

            # Priorité au niveau de la base club si
            # disponible (corrige les données périmées)
            key = (
                (p_nom or "").strip().upper(),
                (p_pren or "").strip().upper()
            )

            niveau_final = club_niv.get(key) or p_niv or ""

            add_participant_row(
                p_nom,
                p_pren,
                niveau_final,
                p_prepa or "",
                participant_id=p_id
            )

        update_stats_part()
        refresh_plongeurs_listbox()

        page.update()

        show_message(f"Sortie « {nom} » ouverte.")

    def ouvrir_sortie(e):

        conn = sqlite3.connect(DB_PATH)

        sorties = conn.execute(
            "SELECT id, nom, lieu, date_debut, date_fin"
            " FROM sorties ORDER BY id DESC"
        ).fetchall()

        conn.close()

        if not sorties:

            show_message(
                "Aucune sortie enregistrée."
            )

            return

        items = []

        for sid, nom, lieu, d_deb, d_fin in sorties:

            label = f"{nom or '(sans nom)'}"

            sub = " — ".join(
                x for x in (
                    lieu,
                    (
                        f"{d_deb} → {d_fin}"
                        if d_deb or d_fin
                        else ""
                    )
                ) if x
            )

            def make_handler(the_id):

                def handler(ev):

                    close_dialog(open_dlg)
                    load_sortie(the_id)

                return handler

            items.append(

                ft.ListTile(

                    title=ft.Text(label),

                    subtitle=(
                        ft.Text(sub, size=11)
                        if sub
                        else None
                    ),

                    leading=ft.Icon(
                        ft.Icons.SAILING
                    ),

                    on_click=make_handler(sid)
                )
            )

        open_dlg = ft.AlertDialog(

            modal=True,

            title=ft.Text(
                "📂 Ouvrir une sortie",
                weight=ft.FontWeight.BOLD
            ),

            content=ft.Container(

                width=_w(460),

                height=400,

                content=ft.Column(
                    controls=items,
                    scroll=ft.ScrollMode.AUTO,
                    tight=True
                )
            ),

            actions=[

                ft.TextButton(
                    "Annuler",
                    on_click=lambda ev:
                        close_dialog(open_dlg)
                )
            ]
        )

        page.show_dialog(open_dlg)

    # =================================================
    # SUPPRIMER SORTIE
    # =================================================

    def supprimer_sortie(e):

        sid = state["sortie_id"]

        if sid is None:

            show_message(
                "Aucune sortie ouverte à supprimer."
                " Ouvrez d'abord une sortie."
            )

            return

        nom_sortie = (sortie_nom.value or "").strip() \
            or f"sortie #{sid}"

        def confirmer(ev):

            conn = sqlite3.connect(DB_PATH)

            # Supprimer participants + inscriptions +
            # palanquées + jours + la sortie elle-même
            part_ids = [
                r[0]
                for r in conn.execute(
                    "SELECT id FROM participants"
                    " WHERE sortie_id=?",
                    (sid,)
                ).fetchall()
            ]

            if part_ids:
                ph = ",".join("?" * len(part_ids))
                conn.execute(
                    f"DELETE FROM plongees_realisees"
                    f" WHERE participant_id IN ({ph})",
                    part_ids
                )

            conn.execute(
                "DELETE FROM participants"
                " WHERE sortie_id=?",
                (sid,)
            )

            conn.execute(
                "DELETE FROM jours_sortie"
                " WHERE sortie_id=?",
                (sid,)
            )

            try:
                conn.execute(
                    "DELETE FROM palanquees_sortie"
                    " WHERE sortie_id=?",
                    (sid,)
                )
            except Exception:
                pass

            conn.execute(
                "DELETE FROM sorties WHERE id=?",
                (sid,)
            )

            conn.commit()
            conn.close()

            close_dialog(del_dlg)

            # Réinitialiser l'interface
            nouvelle_sortie(None)

            show_message(
                f"Sortie « {nom_sortie} » supprimée."
            )

        del_dlg = ft.AlertDialog(

            modal=True,

            title=ft.Text(
                "⚠️ Supprimer la sortie",
                weight=ft.FontWeight.BOLD
            ),

            content=ft.Text(
                f"Supprimer définitivement la sortie"
                f" « {nom_sortie} » ainsi que tous ses"
                f" participants, inscriptions et"
                f" palanquées ?\n\nCette action est"
                f" irréversible."
            ),

            actions=[

                ft.TextButton(
                    "Annuler",
                    on_click=lambda ev:
                        close_dialog(del_dlg)
                ),

                ft.FilledButton(
                    "Supprimer",
                    bgcolor="#ef4444",
                    color="white",
                    on_click=confirmer
                ),
            ]
        )

        page.show_dialog(del_dlg)

    # =================================================
    # ENREGISTRER SORTIE
    # =================================================

    def enregistrer_sortie(e):

        nom = (sortie_nom.value or "").strip()
        lieu = (sortie_lieu.value or "").strip()
        d_deb = (date_debut.value or "").strip()
        d_fin = (date_fin.value or "").strip()

        if not nom:

            show_message(
                "Le nom de la sortie est obligatoire."
            )

            return

        conn = sqlite3.connect(DB_PATH)

        if state["sortie_id"] is None:

            cur = conn.execute("""

                INSERT INTO sorties(
                    nom, lieu, date_debut, date_fin
                )

                VALUES (?, ?, ?, ?)

            """, (nom, lieu, d_deb, d_fin))

            state["sortie_id"] = cur.lastrowid

        else:

            conn.execute("""

                UPDATE sorties

                SET nom=?, lieu=?,
                    date_debut=?, date_fin=?

                WHERE id=?

            """, (
                nom, lieu, d_deb, d_fin,
                state["sortie_id"]
            ))

        # Sauvegarde des jours
        sid = state["sortie_id"]

        conn.execute(
            "DELETE FROM jours_sortie WHERE sortie_id=?",
            (sid,)
        )

        for d_str, dd in state.get("jours_entries", []):

            try:
                nb = int(dd.value)
            except Exception:
                nb = 0

            conn.execute("""

                INSERT INTO jours_sortie(
                    sortie_id, date_jour, nb_plongees
                )

                VALUES (?, ?, ?)

            """, (sid, d_str, nb))

        conn.commit()
        conn.close()

        # Participants : via la fonction qui PRÉSERVE
        # les id (sinon les inscriptions tab3 sont
        # orphelinées).
        save_participants_silent()

        show_message(
            f"Sortie « {nom} » enregistrée"
            f" (id {sid})."
        )

        page.update()

    # =================================================
    # GÉNÉRATION JOURS
    # =================================================

    def generate_days(e):

        jours_column.controls.clear()

        state["jours_entries"] = []

        try:

            d1 = datetime.strptime(
                date_debut.value,
                "%d/%m/%Y"
            )

            d2 = datetime.strptime(
                date_fin.value,
                "%d/%m/%Y"
            )

            current = d1

            while current <= d2:

                d_str = current.strftime("%d/%m/%Y")

                bloc, nb_dropdown = make_jour_bloc(
                    d_str, "2"
                )

                jours_column.controls.append(bloc)

                # (date_str, dropdown) — pour tab3/tab4
                state["jours_entries"].append(
                    (d_str, nb_dropdown)
                )

                current += timedelta(days=1)

            page.update()

        except Exception as err:

            print(err)

            show_message("Dates invalides")

    # =================================================
    # IMPORT FFESSM
    # =================================================

    file_picker = ft.FilePicker()

    page.services.append(file_picker)

    # Service de partage (share sheet native Android/iOS)
    # Permet aux utilisateurs d'envoyer les PDF générés
    # vers Drive, Files, Gmail, WhatsApp, etc.
    try:
        share_service = ft.Share()
        page.services.append(share_service)
    except Exception as err:
        # Si ft.Share n'existe pas (vieille version Flet),
        # on désactive simplement le bouton Partager.
        share_service = None
        print("ft.Share indisponible:", err)

    def norm_date(v):

        if v is None:
            return ""

        # Si c'est déjà un objet datetime
        if hasattr(v, "strftime"):
            try:
                return v.strftime("%d/%m/%Y")
            except Exception:
                pass

        # Convertir en string
        s = str(v).strip()

        if not s or s.lower() in ("nan", "nat", "none"):
            return ""

        # Certaines valeurs Excel arrivent sous forme "2024-05-12 00:00:00"
        s = s.split(" ")[0]

        # Formats possibles
        formats = (
            "%d/%m/%Y",
            "%Y-%m-%d",
            "%d-%m-%Y",
            "%d/%m/%y",
        )

        for fmt in formats:
            try:
                return datetime.strptime(s, fmt).strftime("%d/%m/%Y")
            except Exception:
                pass

        # Numéro de série Excel : nombre de jours depuis
        # le 1er janvier 1900 (avec le bug historique
        # Excel qui considère 1900 comme bissextile —
        # d'où la base 1899-12-30 en pratique).
        # Exemples : 45427 -> 15/05/2024, 46258 -> 24/08/2026.
        try:
            n = float(s.replace(",", "."))
            if 1 <= n < 100000:
                base = datetime(1899, 12, 30)
                d = base + timedelta(days=n)
                return d.strftime("%d/%m/%Y")
        except Exception:
            pass

        # Si aucun format ne correspond → renvoyer tel quel
        return s

        if v is None:
            return ""

        try:
            if pd.isna(v):
                return ""
        except Exception:
            pass

        if hasattr(v, "strftime"):
            try:
                return v.strftime("%d/%m/%Y")
            except Exception:
                pass

        s = str(v).strip()

        if not s or s in ("nan", "NaT"):
            return ""

        s = s.split(" ")[0]

        for fmt in (
            "%d/%m/%Y", "%Y-%m-%d",
            "%d-%m-%Y", "%d/%m/%y"
        ):
            try:
                return datetime.strptime(
                    s, fmt
                ).strftime("%d/%m/%Y")
            except Exception:
                pass

        return s

    def extract_brevets(brevets_str):
        """Retourne (moniteur, encadrant, plongeur, nitrox).
        Recherche STRICTE par éléments exacts."""

        elements = [
            b.strip()
            for b in str(brevets_str).split(",")
        ]
        eset = set(elements)

        def has_exact(label):
            return label in eset

        plongeur_order = [
            "Niveau 3",
            "Plongeur autonome 40 mètres",
            "Niveau 2",
            "Plongeur encadré 60 mètres",
            "Plongeur encadré 40 mètres",
            "Niveau 1",
            "Plongeur autonome 12 mètres",
            "Plongeur encadré 12 mètres",
            "Plongeur Or",
            "Plongeur Argent",
            "Plongeur Bronze",
        ]

        SIMPLIFICATIONS_BREVETS = {
            "Niveau 3": "Niveau 3",
            "Plongeur encadré 60 mètres": "PE60",
            "Plongeur autonome 40 mètres": "PA40",
            "Niveau 2": "Niveau 2",
            "Plongeur encadré 40 mètres": "PE40",
            "Plongeur autonome 20 mètres": "PA20",
            "Niveau 1": "Niveau 1",
            "Plongeur autonome 12 mètres": "PA12",
            "Plongeur encadré 12 mètres": "PE12",
            "Plongeur Or": "Plongeur Or",
            "Plongeur Argent": "Plongeur Argent",
            "Plongeur Bronze": "Plongeur Bronze",
        }

        p = "Débutant"
        for label in plongeur_order:
            if has_exact(label):
                p = SIMPLIFICATIONS_BREVETS.get(
                    label, label
                )
                break

        m = ""
        for code in ("E4", "E3", "E2", "E1"):
            if any(code in el for el in elements):
                m = code
                break

        enc = (
            "GP"
            if any("GP" in el for el in elements)
            else ""
        )

        nx_order = [
            "Moniteur Nitrox Confirmé",
            "Plongeur Nitrox confirmé",
            "Plongeur Nitrox",
        ]

        SIMPLIFICATIONS_BREVETS_NITROX = {
            "Moniteur Nitrox Confirmé": "MNx",
            "Plongeur Nitrox confirmé": "PNC",
            "Plongeur Nitrox": "PN",
        }

        nx = ""
        for label in nx_order:
            if has_exact(label):
                nx = SIMPLIFICATIONS_BREVETS_NITROX[label]
                break

        return m, enc, p, nx


    def process_excel_file(filepath):
        try:
            print("Fichier :", filepath)
            records = []

            # --- 1) Lecture du fichier XLSX (100% compatible Android & sans dépendance externe) ---
            if filepath.lower().endswith(".xlsx"):
                import zipfile
                import xml.etree.ElementTree as ET

                # Lecture directe de la structure XML du fichier XLSX
                with zipfile.ZipFile(filepath, 'r') as z:
                    # 1. Récupérer la table des chaînes partagées (Shared Strings)
                    shared_strings = []
                    if "xl/sharedStrings.xml" in z.namelist():
                        ss_xml = z.read("xl/sharedStrings.xml")
                        root_ss = ET.fromstring(ss_xml)
                        ns = {'ns': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
                        # Parcourir toutes les balises de texte <t>
                        for t in root_ss.findall('.//ns:t', ns):
                            shared_strings.append(t.text)

                    # 2. Lire la première feuille de calcul (sheet1.xml)
                    sheet_xml = z.read("xl/worksheets/sheet1.xml")
                    root_sheet = ET.fromstring(sheet_xml)
                    ns = {'ns': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
                    
                    rows_data = []
                    for row in root_sheet.findall('.//ns:row', ns):
                        row_cells = []
                        for c in row.findall('ns:c', ns):
                            t = c.get('t')  # Type de cellule
                            v_elem = c.find('ns:v', ns)
                            v = v_elem.text if v_elem is not None else ""
                            
                            # Si c'est une chaîne partagée, on récupère le texte via l'index
                            if t == 's' and v.isdigit():
                                row_cells.append(shared_strings[int(v)])
                            else:
                                row_cells.append(v)
                        if row_cells:
                            rows_data.append(row_cells)

                if not rows_data:
                    show_message("Le fichier Excel est vide.")
                    return

                # Convertir les lignes brutes en liste de dictionnaires (comme le faisait pyexcel)
                headers = rows_data[0]
                for row in rows_data[1:]:
                    # Combler les cellules vides si la ligne est plus courte que les en-têtes
                    while len(row) < len(headers):
                        row.append("")
                    record = {headers[i]: row[i] for i in range(len(headers))}
                    records.append(record)

            # --- 2) Lecture du fichier CSV (Déjà géré dans votre application) ---
            elif filepath.lower().endswith((".csv", ".txt")):
                with open(filepath, "r", encoding="latin1") as f:
                    reader = csv.DictReader(f, delimiter=";")
                    records = list(reader)
            else:
                show_message("Format de fichier non supporté.")
                return
            
            # Si aucun enregistrement
            if not records:
                show_message("Fichier vide ou illisible.")
                return

            # Colonnes obligatoires
            cols_requises = [
                "Identifiant", "Nom", "Prénom",
                "Brevets", "Date Fin Validité CACI",
                "Date Naissance"
            ]

            missing = [c for c in cols_requises if c not in records[0]]
            if missing:
                show_message(
                    "Colonnes manquantes : "
                    + ", ".join(missing)
                    + ". Vérifier qu'il s'agit d'une extraction licenciés FFESSM."
                )
                return

            # Colonnes optionnelles
            opt_cols = {
                "Date Inscription": "date_inscription",
                "Saison": "saison",
                "Portable": "portable",
                "Email": "email",
                "Type de licence": "type_licence",
            }

            conn = sqlite3.connect(DB_PATH)
            now_str = datetime.now().strftime("%d/%m/%Y %H:%M")

            existing = {
                r[0]
                for r in conn.execute(
                    "SELECT id_licence FROM plongeurs_club"
                ).fetchall()
            }

            nb_ins = 0
            nb_upd = 0

            # --- 2) Parcours des lignes ---
            for row in records:

                licence = str(row.get("Identifiant", "")).strip()
                if not licence or licence.lower() == "nan":
                    continue

                nom = str(row.get("Nom", "")).strip().upper()
                prenom = str(row.get("Prénom", "")).strip().title()

                brevets = str(row.get("Brevets", "")).strip()
                if brevets.lower() == "nan":
                    brevets = ""

                caci_d = norm_date(row.get("Date Fin Validité CACI", ""))
                naiss = norm_date(row.get("Date Naissance", ""))

                brev_m, brev_e, brev_p, brev_nx = extract_brevets(brevets)
                niveau = brev_m or brev_e or brev_p

                print(
                    f"  {nom} {prenom} | brevets='{brevets}' -> niveau='{niveau}'"
                    f" (M={brev_m}, E={brev_e}, P={brev_p}, Nx={brev_nx})"
                )

                # Optionnelles
                def opt(col):
                    v = row.get(col, "")
                    if v is None:
                        return ""
                    v = str(v).strip()
                    return "" if v.lower() in ("nan", "nat") else v

                date_insc = norm_date(row.get("Date Inscription", ""))
                saison = opt("Saison")
                portable = opt("Portable")
                email = opt("Email")
                type_lic = opt("Type de licence")

                # --- 3) UPDATE ou INSERT ---
                if licence in existing:

                    conn.execute("""
                        UPDATE plongeurs_club SET
                            nom=?, prenom=?, niveau=?,
                            brevets=?, brevet_moniteur=?,
                            brevet_encadrant=?, brevet_plongeur=?,
                            brevet_nitrox=?, caci_date=?,
                            date_naissance=?, date_import=?,
                            date_inscription=?, saison=?,
                            portable=?, email=?, type_licence=?
                        WHERE id_licence=?
                    """, (
                        nom, prenom, niveau, brevets,
                        brev_m, brev_e, brev_p, brev_nx,
                        caci_d, naiss, now_str,
                        date_insc, saison, portable,
                        email, type_lic, licence
                    ))

                    nb_upd += 1

                else:

                    conn.execute("""
                        INSERT INTO plongeurs_club(
                            id_licence, nom, prenom,
                            niveau, brevets,
                            brevet_moniteur, brevet_encadrant,
                            brevet_plongeur, brevet_nitrox,
                            caci_date, date_naissance,
                            date_import, date_inscription,
                            saison, portable, email, type_licence
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        licence, nom, prenom, niveau,
                        brevets, brev_m, brev_e, brev_p,
                        brev_nx, caci_d, naiss, now_str,
                        date_insc, saison, portable,
                        email, type_lic
                    ))

                    nb_ins += 1

            conn.commit()
            conn.close()

            reload_plongeurs_club()

            show_message(
                f"Import FFESSM terminé : {nb_ins} ajout(s), {nb_upd} maj."
            )

        except Exception as err:
            print(err)
            show_message(str(err))

    async def import_excel(e):

        try:
            files = await file_picker.pick_files(
                allow_multiple=False,
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["xlsx", "xls", "csv"]
            )

            if not files:
                return

            filepath = files[0].path
            process_excel_file(filepath)

        except Exception as err:
            print(err)
            show_message(str(err))

    # =================================================
    # FONCTIONS TAB 2 — PARTICIPANTS
    # =================================================

    COLOR_CACI = {

        "red": "#ef4444",

        "orange": "#f59e0b",

        "green": "#10b981",

        "gray": "#475569",
    }

    def reload_plongeurs_club():

        state["plongeurs_club"] = load_plongeurs_club()

        # Diagnostic : afficher les niveaux chargés
        print("=== Base club rechargée ===")
        for p in state["plongeurs_club"][:10]:
            print(
                f"  {p['nom']} {p['prenom']}"
                f" niveau='{p['niveau']}'"
            )
        print(
            f"  ... total"
            f" {len(state['plongeurs_club'])} plongeurs"
        )

        refresh_plongeurs_listbox()

    t2_lock_btn = ft.FilledButton(
        " 🔓 ",
        bgcolor="#f59e0b",
        color="white"
    )

    def t2_apply_lock_style():
        if state.get("t2_locked"):
            t2_lock_btn.content = ft.Text(
                " 🔒 ", color="white"
            )
            t2_lock_btn.bgcolor = "#10b981"
        else:
            t2_lock_btn.content = ft.Text(
                " 🔓 ", color="white"
            )
            t2_lock_btn.bgcolor = "#f59e0b"

    def t2_toggle_lock(e):
        state["t2_locked"] = not state.get(
            "t2_locked", False
        )
        # Appliquer aux dropdowns existants
        for r in state["participants_rows"]:
            try:
                r["niveau"].disabled = state["t2_locked"]
                r["niveau_prepa"].disabled = \
                    state["t2_locked"]
            except Exception:
                pass
        t2_apply_lock_style()
        page.update()

    t2_lock_btn.on_click = t2_toggle_lock

    def update_stats_part():

        n_p = sum(

            1
            for r in state["participants_rows"]
            if r["type"] == "plongeur"
        )

        stats_part_btn.content = ft.Text(

            f"📊 {n_p} plongeur"

            f"{'s' if n_p > 1 else ''}"

            f"   (cliquer pour la synthèse)"
        )

        page.update()

    def refresh_plongeurs_listbox():

        plongeurs_list_view.controls.clear()

        state["text_selected"] = set()
        state["text_lines"] = []

        # Exclure ceux déjà dans les participants
        deja = {

            (
                r["nom"].value.strip(),
                r["prenom"].value.strip()
            )

            for r in state["participants_rows"]

            if r["type"] == "plongeur"
        }

        for p in state["plongeurs_club"]:

            if (p["nom"], p["prenom"]) in deja:
                continue

            age = calc_age(p.get("naiss", ""))

            mineur = age is not None and age < 18

            caci_str = p.get("caci", "") or "?"

            ccolor = COLOR_CACI[caci_color(caci_str)]

            line_idx = len(state["text_lines"])

            spans = [

                ft.TextSpan(

                    f"{p['nom']} {p['prenom']} "

                    f"({p['niveau']})",

                    style=ft.TextStyle(
                        color="#1e293b"
                    )
                )
            ]

            if mineur:

                spans.append(

                    ft.TextSpan(

                        f"  —  {age} ans",

                        style=ft.TextStyle(

                            color="#ef4444",

                            weight=ft.FontWeight.BOLD
                        )
                    )
                )

            spans.append(

                ft.TextSpan(

                    "   CACI : ",

                    style=ft.TextStyle(
                        color="#1e293b"
                    )
                )
            )

            spans.append(

                ft.TextSpan(

                    caci_str,

                    style=ft.TextStyle(
                        color=ccolor
                    )
                )
            )

            def make_on_click(idx):

                def handler(e):

                    if idx in state["text_selected"]:

                        state["text_selected"].discard(idx)

                    else:

                        state["text_selected"].add(idx)

                    refresh_plongeurs_listbox_styles()

                return handler

            row_ctrl = ft.Container(

                content=ft.Text(

                    spans=spans,

                    size=12
                ),

                padding=ft.Padding(
                    left=6,
                    right=6,
                    top=3,
                    bottom=3
                ),

                bgcolor="white",

                ink=True,

                on_click=make_on_click(line_idx)
            )

            plongeurs_list_view.controls.append(row_ctrl)

            state["text_lines"].append(p)

        refresh_plongeurs_listbox_styles()

        page.update()

    def refresh_plongeurs_listbox_styles():

        for idx, ctrl in enumerate(

            plongeurs_list_view.controls
        ):

            ctrl.bgcolor = (

                "#bfdbfe"

                if idx in state["text_selected"]

                else "white"
            )

        page.update()

    def add_plongeurs_selected(e):

        if state["sortie_id"] is None:

            show_message(

                "Veuillez d'abord enregistrer la sortie"

                " (onglet 1) avant d'ajouter des"

                " participants."
            )

            return

        for idx in sorted(state["text_selected"]):

            if 0 <= idx < len(state["text_lines"]):

                p = state["text_lines"][idx]

                print(
                    f"[AJOUT] {p['nom']} {p['prenom']}"
                    f" niveau='{p['niveau']}'"
                )

                add_participant_row(

                    p["nom"],
                    p["prenom"],
                    p["niveau"]
                )

        refresh_plongeurs_listbox()

    def add_participant_row(

        nom,
        prenom,
        niveau="",
        niveau_prepa="",
        lien_plongeur="",
        participant_id=None
    ):

        # Nom et prénom : objets conservés pour la
        # persistance (lecture .value), non affichés
        # séparément.
        e_nom = ft.Text(value=nom)
        e_prenom = ft.Text(value=prenom)

        # Affichage concaténé "NOM Prénom"
        nom_complet_txt = ft.Text(
            f"{nom} {prenom}",
            size=12,
            weight=ft.FontWeight.W_500
        )

        btn_fiche = ft.IconButton(
            icon=ft.Icons.VISIBILITY,
            icon_size=18,
            tooltip="Voir la fiche",
            bgcolor="#e0f2fe"
        )

        btn_del = ft.IconButton(
            icon=ft.Icons.DELETE,
            icon_size=18,
            icon_color="#ef4444",
            tooltip="Supprimer"
        )

        # Col Niveau
        niveau_initial = niveau or "Niveau 1"

        niv_combo = ft.Dropdown(

            value=niveau_initial,

            options=[

                ft.DropdownOption(n)

                for n in TOUS_NIVEAUX
            ],

            dense=True,

            width=160,

            text_size=12,

            disabled=state.get("t2_locked", False)
        )

        # Col Prépa
        prepa_combo = ft.Dropdown(

            value=niveau_prepa or "",

            options=[
                ft.DropdownOption("")
            ] + [

                ft.DropdownOption(n)

                for n in TOUS_NIVEAUX
            ],

            dense=True,

            width=160,

            text_size=12,

            disabled=state.get("t2_locked", False)
        )

        # Ligne en grille :
        # Act. | Dét. | Nom Prénom | Niv. | N. prépa.
        row_ctrl = ft.Row(

            controls=[

                ft.Container(
                    btn_del,
                    width=44,
                    alignment=ft.Alignment.CENTER
                ),

                ft.Container(
                    btn_fiche,
                    width=44,
                    alignment=ft.Alignment.CENTER
                ),

                ft.Container(
                    nom_complet_txt,
                    width=180,
                    padding=ft.Padding(
                        left=4, right=4, top=0, bottom=0
                    )
                ),

                ft.Container(niv_combo, width=160),

                ft.Container(prepa_combo, width=160),
            ],

            spacing=2,

            vertical_alignment=ft.CrossAxisAlignment.CENTER
        )

        entry_dict = {

            "type": "plongeur",

            "id": participant_id,

            "nom": e_nom,

            "prenom": e_prenom,

            "niveau": niv_combo,

            "niveau_prepa": prepa_combo,

            "niveau_init": niveau_initial,

            "prepa_init": niveau_prepa or "",

            "row": row_ctrl,
        }

        # Synchroniser niveau_init quand l'utilisateur
        # change le Dropdown (sécurité contre la perte
        # de .value en Flet 0.85)
        def on_niv_change(e, ed=entry_dict, dd=niv_combo):
            if dd.value:
                ed["niveau_init"] = dd.value

        niv_combo.on_change = on_niv_change

        def on_prepa_change(
            e, ed=entry_dict, dd=prepa_combo
        ):
            ed["prepa_init"] = dd.value or ""

        prepa_combo.on_change = on_prepa_change

        # Brancher les callbacks
        def del_row(e):

            state["participants_rows"].remove(entry_dict)

            participants_rows_column.controls.remove(

                row_ctrl
            )

            update_stats_part()
            refresh_plongeurs_listbox()

            page.update()

        btn_del.on_click = del_row

        btn_fiche.on_click = (

            lambda e:
            show_plongeur_fiche(entry_dict)
        )

        state["participants_rows"].append(entry_dict)

        participants_rows_column.controls.append(row_ctrl)

        update_stats_part()

        page.update()

    def show_plongeur_fiche(entry_dict):

        nom = (entry_dict["nom"].value or "").strip()

        pren = (entry_dict["prenom"].value or "").strip()

        if not nom and not pren:

            show_message(

                "Saisir au moins le nom ou le"

                " prénom pour afficher la fiche."
            )

            return

        conn = sqlite3.connect(DB_PATH)

        r = conn.execute("""

            SELECT

                id_licence,
                nom,
                prenom,
                niveau,
                brevets,
                brevet_moniteur,
                brevet_encadrant,
                brevet_plongeur,
                caci_date,
                date_naissance,
                date_inscription,
                saison,
                portable,
                email,
                type_licence

            FROM plongeurs_club

            WHERE UPPER(nom)=UPPER(?)
              AND UPPER(prenom)=UPPER(?)

            LIMIT 1

        """, (nom, pren)).fetchone()

        conn.close()

        if not r:

            show_message(

                f"Aucun plongeur « {nom} {pren} »"

                " trouvé dans la base club."
            )

            return

        (
            lic, nom_b, pren_b, niveau_b, brevets,
            brev_mon, brev_enc, brev_pl,
            caci, naiss, inscription, saison,
            portable, email, type_lic
        ) = r

        age_str = naiss or "—"

        age = calc_age(naiss)

        if age is not None:

            age_str = f"{age} ans"

        liste_brevets = []

        if brevets:

            for b in str(brevets).split(","):

                b = b.strip()

                if b:
                    liste_brevets.append(b)

        if not liste_brevets:

            for v in (brev_mon, brev_enc, brev_pl):

                if v:
                    liste_brevets.append(v)

        prepa_value = ""

        try:

            prepa_value = (

                entry_dict["niveau_prepa"].value
                or ""
            )

        except Exception:
            pass

        ccol = COLOR_CACI[caci_color(caci)]

        def line(label, value, color=None, bold=False):

            # Mobile : label au-dessus, valeur en dessous
            return ft.Container(
                padding=ft.Padding(
                    left=0, right=0, top=2, bottom=2
                ),
                content=ft.Column(
                    tight=True,
                    spacing=0,
                    controls=[
                        ft.Text(
                            label,
                            size=11,
                            weight=ft.FontWeight.BOLD,
                            color="#475569"
                        ),
                        ft.Text(
                            value or "—",
                            size=14,
                            color=color or "#1e293b",
                            weight=(
                                ft.FontWeight.BOLD
                                if bold
                                else ft.FontWeight.NORMAL
                            ),
                            selectable=True
                        ),
                    ]
                )
            )

        def line_link(label, value, url_prefix):
            """Label au-dessus, lien cliquable en dessous."""

            if not value:
                return line(label, "—")

            v = str(value).strip()

            if url_prefix == "tel:":
                url = url_prefix + v.replace(" ", "")
            else:
                url = url_prefix + v

            return ft.Container(
                padding=ft.Padding(
                    left=0, right=0, top=2, bottom=2
                ),
                content=ft.Column(
                    tight=True,
                    spacing=0,
                    controls=[
                        ft.Text(
                            label,
                            size=11,
                            weight=ft.FontWeight.BOLD,
                            color="#475569"
                        ),
                        ft.TextButton(
                            content=ft.Text(
                                v,
                                size=14,
                                color="#0ea5e9"
                            ),
                            url=url,
                            style=ft.ButtonStyle(
                                padding=ft.Padding(
                                    left=0, right=0,
                                    top=0, bottom=0
                                )
                            )
                        ),
                    ]
                )
            )

        brevets_btn = (

            ft.TextButton(

                f"📜 Voir la liste ({len(liste_brevets)})",

                on_click=lambda ev:
                    show_brevets_list_dialog(

                        nom_b,
                        pren_b,

                        liste_brevets
                    )
            )

            if liste_brevets

            else ft.Text(
                "—",
                color="#94a3b8"
            )
        )

        fiche_dialog = ft.AlertDialog(

            modal=True,

            title=ft.Container(

                content=ft.Column(

                    controls=[

                        ft.Text(

                            f"🤿 {nom_b} {pren_b}",

                            size=18,

                            weight=ft.FontWeight.BOLD,

                            color="white"
                        ),

                        ft.Text(

                            f"Licence : {lic}",

                            size=10,

                            italic=True,

                            color="#cbd5e1"
                        ),
                    ],

                    tight=True
                ),

                bgcolor="#1e3a5f",

                padding=12
            ),

            content=ft.Container(

                width=_w(440),

                content=ft.Column(

                    tight=True,

                    spacing=6,

                    scroll=ft.ScrollMode.AUTO,

                    controls=[

                        line("Nom :", nom_b),

                        line("Prénom :", pren_b),

                        line("Âge :", age_str),

                        line(

                            "Fin validité CACI :",

                            caci or "—",

                            color=ccol,

                            bold=True
                        ),

                        line("Saison :", saison),

                        ft.Container(
                            padding=ft.Padding(
                                left=0, right=0,
                                top=2, bottom=2
                            ),
                            content=ft.Column(
                                tight=True,
                                spacing=0,
                                controls=[
                                    ft.Text(
                                        "Brevets :",
                                        size=11,
                                        weight=ft.FontWeight.BOLD,
                                        color="#475569"
                                    ),
                                    brevets_btn,
                                ]
                            )
                        ),

                        line(

                            "Niveau en préparation :",

                            prepa_value
                        ),

                        line(

                            "Type de licence :",

                            type_lic
                        ),

                        line_link(
                            "Portable :", portable, "tel:"
                        ),

                        line_link(
                            "Email :", email, "mailto:"
                        ),

                        ft.Divider(),

                        line(

                            "Date d'inscription :",

                            inscription
                        ),
                    ]
                )
            ),

            actions=[

                ft.TextButton(

                    "Fermer",

                    on_click=lambda ev: close_dialog(
                        fiche_dialog
                    )
                )
            ]
        )

        page.show_dialog(fiche_dialog)

    def show_brevets_list_dialog(nom_b, pren_b, brevets):

        items = []

        for i, b in enumerate(brevets, 1):

            bg = "#f8fafc" if i % 2 == 0 else "white"

            items.append(

                ft.Container(

                    content=ft.Row(

                        controls=[

                            ft.Text(
                                f"{i:2d}.",
                                width=32,
                                color="#94a3b8",
                                size=11
                            ),

                            ft.Text(b, size=12)
                        ]
                    ),

                    bgcolor=bg,

                    padding=4
                )
            )

        dlg = ft.AlertDialog(

            modal=True,

            title=ft.Text(

                f"🎓 Brevets de {nom_b} {pren_b} "

                f"({len(brevets)})",

                size=14,

                weight=ft.FontWeight.BOLD
            ),

            content=ft.Container(

                width=_w(400),

                height=400,

                content=ft.Column(

                    controls=items,

                    scroll=ft.ScrollMode.AUTO,

                    tight=True
                )
            ),

            actions=[

                ft.TextButton(

                    "Fermer",

                    on_click=lambda e: close_dialog(dlg)
                )
            ]
        )

        page.show_dialog(dlg)

    def close_dialog(dlg):

        page.pop_dialog()

    def show_synthese_participants():

        ENCADRANTS_LVL = ["GP", "E1", "E2", "E3", "E4"]

        A_ENCADRER_LVL = [

            "Plongeur Or",
            "Plongeur Argent",
            "Plongeur Bronze",
            "PE12",
            "PE20",
            "Niveau 1",
            "PE40",
        ]

        encadrants = {n: [] for n in ENCADRANTS_LVL}
        en_formation = {}
        a_encadrer = {n: [] for n in A_ENCADRER_LVL}
        autonomes = []

        for r in state["participants_rows"]:

            if r["type"] != "plongeur":
                continue

            nom_aff = (

                f"{r['nom'].value.strip()} "

                f"{r['prenom'].value.strip()}"
            )

            niv = (get_niveau(r) or "").strip()

            prepa = (get_prepa(r) or "").strip()

            if prepa:

                en_formation.setdefault(
                    prepa,
                    []
                ).append(

                    f"{nom_aff} ({niv or '?'})"
                )

                continue

            if niv in encadrants:

                encadrants[niv].append(nom_aff)

            elif niv in a_encadrer:

                a_encadrer[niv].append(nom_aff)

            else:

                autonomes.append(

                    f"{nom_aff} ({niv or '?'})"
                )

        def make_section(titre, bg, data, total_label):

            total = (

                sum(len(v) for v in data.values())

                if isinstance(data, dict)

                else len(data)
            )

            inner = []

            if isinstance(data, dict):

                for niv, noms in data.items():

                    if not noms:
                        continue

                    inner.append(

                        ft.Row(

                            controls=[

                                ft.Container(

                                    content=ft.Text(

                                        f"{niv} ({len(noms)})",

                                        size=11,

                                        weight=ft.FontWeight.BOLD
                                    ),

                                    width=140
                                ),

                                ft.Text(

                                    ", ".join(noms),

                                    size=11,

                                    color="#475569",

                                    expand=True
                                )
                            ]
                        )
                    )

            else:

                if data:

                    inner.append(

                        ft.Text(

                            ", ".join(data),

                            size=11,

                            color="#475569"
                        )
                    )

                else:

                    inner.append(

                        ft.Text(

                            "(aucun)",

                            size=11,

                            italic=True,

                            color="#94a3b8"
                        )
                    )

            return ft.Container(

                content=ft.Column(

                    controls=[

                        ft.Text(

                            f"  {titre}"

                            f"  ({total} {total_label})",

                            weight=ft.FontWeight.BOLD,

                            size=12
                        ),

                        ft.Divider(height=1),
                    ] + inner,

                    tight=True,

                    spacing=4
                ),

                bgcolor=bg,

                padding=8,

                border_radius=6
            )

        n_p = sum(

            1
            for r in state["participants_rows"]
            if r["type"] == "plongeur"
        )

        synth_dlg = ft.AlertDialog(

            modal=True,

            title=ft.Text(

                "📊 Synthèse des plongeurs",

                size=16,

                weight=ft.FontWeight.BOLD
            ),

            content=ft.Container(

                width=640,

                height=500,

                content=ft.Column(

                    scroll=ft.ScrollMode.AUTO,

                    spacing=8,

                    controls=[

                        ft.Text(

                            f"{n_p} plongeur(s)",

                            size=11,

                            italic=True,

                            color="#64748b"
                        ),

                        make_section(

                            "🎓 Encadrants",

                            "#dbeafe",

                            encadrants,

                            "encadrant(s)"
                        ),

                        make_section(

                            "📚 En formation",

                            "#fef3c7",

                            en_formation,

                            "en formation"
                        ),

                        make_section(

                            "🤿 À encadrer",

                            "#fce7f3",

                            a_encadrer,

                            "à encadrer"
                        ),

                        make_section(

                            "💪 Plongeurs autonomes",

                            "#dcfce7",

                            autonomes,

                            "autonome(s)"
                        ),
                    ]
                )
            ),

            actions=[

                ft.TextButton(

                    "Fermer",

                    on_click=lambda e:
                        close_dialog(synth_dlg)
                )
            ]
        )

        page.show_dialog(synth_dlg)

    def add_plongeur_manual(e):

        e_lic = ft.TextField(

            label=(
                "Numéro de licence "
                "(vide si extérieur)"
            ),

            dense=True
        )

        e_nom_m = ft.TextField(

            label="Nom *",

            dense=True
        )

        e_pren_m = ft.TextField(

            label="Prénom *",

            dense=True
        )

        e_niv_m = ft.Dropdown(

            label="Niveau",

            dense=True,

            options=[
                ft.DropdownOption("")
            ] + [

                ft.DropdownOption(n)

                for n in TOUS_NIVEAUX
            ]
        )

        e_naiss_m = ft.TextField(

            label="Naissance (JJ/MM/AAAA)",

            dense=True
        )

        e_caci_m = ft.TextField(

            label="Fin validité CACI",

            dense=True
        )

        e_port_m = ft.TextField(

            label="Portable",

            dense=True
        )

        e_email_m = ft.TextField(

            label="Email",

            dense=True
        )

        def do_save_manual(ev):

            lic = (e_lic.value or "").strip()
            nom = (e_nom_m.value or "").strip().upper()
            pren = (
                e_pren_m.value or ""
            ).strip().title()
            niv = (e_niv_m.value or "").strip()
            naiss = (e_naiss_m.value or "").strip()
            caci = (e_caci_m.value or "").strip()
            port = (e_port_m.value or "").strip()
            email = (e_email_m.value or "").strip()

            if not nom or not pren:

                show_message(
                    "Nom et prénom obligatoires."
                )

                return

            conn = sqlite3.connect(DB_PATH)

            if not lic:

                base = (

                    "EXT-"

                    + datetime.now().strftime(
                        "%Y%m%d-%H%M"
                    )
                )

                lic = base
                n = 1

                while conn.execute(

                    "SELECT 1 FROM plongeurs_club"
                    " WHERE id_licence=?",

                    (lic,)

                ).fetchone():

                    n += 1
                    lic = f"{base}-{n}"

            else:

                r_exist = conn.execute(

                    "SELECT id_licence FROM"
                    " plongeurs_club WHERE id_licence=?",

                    (lic,)

                ).fetchone()

                if r_exist:

                    conn.execute(

                        "DELETE FROM plongeurs_club"
                        " WHERE id_licence=?",

                        (lic,)
                    )

            brev_mon = (

                niv if niv in ("E1","E2","E3","E4") else ""
            )

            brev_enc = niv if niv == "GP" else ""

            brev_pl = (

                niv

                if niv and niv not in (
                    "E1","E2","E3","E4","GP"
                )

                else ""
            )

            conn.execute("""

                INSERT INTO plongeurs_club(

                    id_licence, nom, prenom, niveau,
                    brevets, brevet_moniteur,
                    brevet_encadrant, brevet_plongeur,
                    caci_date, date_naissance,
                    date_import, date_inscription,
                    saison, portable, email,
                    type_licence

                )

                VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?
                )

            """, (

                lic, nom, pren, niv, niv,

                brev_mon, brev_enc, brev_pl,

                caci, naiss,

                datetime.now().strftime(
                    "%d/%m/%Y %H:%M"
                ) + " (manuel)",

                "", "", port, email, ""
            ))

            conn.commit()
            conn.close()

            show_message(
                f"{nom} {pren} ajouté à la base club."
            )

            reload_plongeurs_club()

            close_dialog(manual_dlg)

        manual_dlg = ft.AlertDialog(

            modal=True,

            title=ft.Text(

                "🧑‍🤿 Nouveau plongeur (base club)",

                size=15,

                weight=ft.FontWeight.BOLD
            ),

            content=ft.Container(

                width=_w(420),

                content=ft.Column(

                    tight=True,

                    spacing=8,

                    controls=[

                        e_lic,
                        e_nom_m,
                        e_pren_m,
                        e_niv_m,
                        e_naiss_m,
                        e_caci_m,
                        e_port_m,
                        e_email_m,

                        ft.Text(

                            "* obligatoires — "
                            "Si pas de licence, "
                            "un id EXT-... sera généré.",

                            size=10,

                            italic=True,

                            color="#94a3b8"
                        ),
                    ]
                )
            ),

            actions=[

                ft.TextButton(

                    "Annuler",

                    on_click=lambda ev:
                        close_dialog(manual_dlg)
                ),

                ft.FilledButton(

                    "💾 Enregistrer",

                    on_click=do_save_manual
                ),
            ]
        )

        page.show_dialog(manual_dlg)

    # =================================================
    # PERSISTANCE PARTICIPANTS (pour tab3/tab4)
    # =================================================

    def get_niveau(r):
        """Lit le niveau d'un participant avec fallback
        sur niveau_init si le Dropdown a perdu sa value."""

        try:
            v = r["niveau"].value
        except Exception:
            v = None

        if v:
            return v

        return r.get("niveau_init", "") or ""

    def get_prepa(r):

        try:
            v = r["niveau_prepa"].value
        except Exception:
            v = None

        if v:
            return v

        return r.get("prepa_init", "") or ""


    def save_participants_silent():
        """Écrit les participants en base en préservant
        leurs id existants (UPDATE si id connu, sinon
        INSERT). Supprime uniquement ceux qui ne sont
        plus présents — pour ne pas casser les
        références dans plongees_realisees."""

        sid = state["sortie_id"]

        if sid is None:
            return

        conn = sqlite3.connect(DB_PATH)

        c = conn.cursor()

        # IDs actuellement en mémoire (déjà persistés)
        ids_memoire = set()

        for r in state["participants_rows"]:

            niv = get_niveau(r)
            prepa = get_prepa(r)

            nom = (r["nom"].value or "").strip()
            prenom = (r["prenom"].value or "").strip()

            print(
                f"[SAVE] {nom} {prenom} niveau="
                f"'{niv}' (init="
                f"'{r.get('niveau_init', '')}')"
            )

            if r.get("id"):

                # Participant déjà en base → UPDATE
                c.execute("""

                    UPDATE participants

                    SET type=?, nom=?, prenom=?,
                        niveau=?, niveau_prepa=?

                    WHERE id=?

                """, (
                    r["type"], nom, prenom,
                    niv, prepa, r["id"]
                ))

                ids_memoire.add(r["id"])

            else:

                # Nouveau participant → INSERT
                c.execute("""

                    INSERT INTO participants(

                        sortie_id, type, nom, prenom,
                        niveau, niveau_prepa, lien_plongeur

                    )

                    VALUES (?, ?, ?, ?, ?, ?, ?)

                """, (
                    sid, r["type"], nom, prenom,
                    niv, prepa, ""
                ))

                r["id"] = c.lastrowid

                ids_memoire.add(r["id"])

        # Supprimer de la base les participants qui ne
        # sont plus dans la liste (et leurs inscriptions)
        existants = [
            row[0]
            for row in c.execute(
                "SELECT id FROM participants"
                " WHERE sortie_id=?",
                (sid,)
            ).fetchall()
        ]

        a_supprimer = [
            pid
            for pid in existants
            if pid not in ids_memoire
        ]

        if a_supprimer:

            ph = ",".join("?" * len(a_supprimer))

            c.execute(
                f"DELETE FROM participants"
                f" WHERE id IN ({ph})",
                a_supprimer
            )

            c.execute(
                f"DELETE FROM plongees_realisees"
                f" WHERE participant_id IN ({ph})",
                a_supprimer
            )

        conn.commit()
        conn.close()

    def get_plongees_list():
        """Liste [(date_str, num)] à partir des jours saisis."""

        plongees = []

        for d_str, dd in state.get("jours_entries", []):

            try:
                nb = int(dd.value)
            except Exception:
                nb = 0

            for k in range(1, nb + 1):

                plongees.append((d_str, k))

        return plongees

    def jour_fr(d_str):

        try:

            d = datetime.strptime(
                d_str,
                "%d/%m/%Y"
            ).date()

            tr = {
                "Monday": "Lun",
                "Tuesday": "Mar",
                "Wednesday": "Mer",
                "Thursday": "Jeu",
                "Friday": "Ven",
                "Saturday": "Sam",
                "Sunday": "Dim",
            }

            return tr.get(d.strftime("%A"), "")

        except Exception:

            return ""

    # =================================================
    # FONCTIONS TAB 3 — INSCRIPTIONS
    # =================================================

    tab3_grid_column = ft.Column(

        scroll=ft.ScrollMode.AUTO,

        expand=True
    )

    tab3_stats_lbl = ft.Text(

        "",

        italic=True,

        color="#64748b",

        size=12
    )

    t3_lock_btn = ft.FilledButton(

        " 🔓 ",

        bgcolor="#f59e0b",

        color="white"
    )

    t3_save_btn = ft.FilledButton(
        " 💾 ",
        bgcolor="#10b981",
        color="white"
    )

    t3_export_btn = ft.FilledButton(
        "📊 Export csv",
        bgcolor="#16a34a",
        color="white"
    )

    def update_tab3_stats():

        total_coche = sum(
            1
            for v in state["tab3_vars"].values()
            if v.value
        )

        total = len(state["tab3_vars"])

        tab3_stats_lbl.value = (

            f"{total_coche} plongée(s) cochée(s) "

            f"sur {total} possible(s)"
        )

        page.update()

    def t3_apply_lock_style():

        if state["t3_locked"]:

            t3_lock_btn.content = ft.Text(
                " 🔒 ",
                color="white"
            )

            t3_lock_btn.bgcolor = "#10b981"

        else:

            t3_lock_btn.content = ft.Text(
                " 🔓 ",
                color="white"
            )

            t3_lock_btn.bgcolor = "#f59e0b"

    def t3_apply_lock_state():

        for v in state["tab3_vars"].values():

            v.disabled = state["t3_locked"]

    def t3_toggle_lock(e):

        if state["sortie_id"] is None:

            show_message("Aucune sortie active.")

            return

        state["t3_locked"] = not state["t3_locked"]

        conn = sqlite3.connect(DB_PATH)

        conn.execute(

            "INSERT OR REPLACE INTO config(key, value)"
            " VALUES (?, ?)",

            (
                f"t3_locked_{state['sortie_id']}",

                "1" if state["t3_locked"] else "0"
            )
        )

        conn.commit()
        conn.close()

        t3_apply_lock_style()
        t3_apply_lock_state()

        page.update()

    t3_lock_btn.on_click = t3_toggle_lock

    def t3_export_excel(e):

        if state["sortie_id"] is None:
            show_message("Aucune sortie ouverte.")
            return

        plongees = get_plongees_list()

        plongeurs = [
            r for r in state["participants_rows"]
            if r["type"] == "plongeur" and r.get("id")
        ]

        if not plongeurs or not plongees:
            show_message("Rien à exporter.")
            return

        # --- Récupération CACI ---
        caci_map = {}
        conn = sqlite3.connect(DB_PATH)
        for cr in conn.execute(
            "SELECT nom, prenom, caci_date FROM plongeurs_club"
        ).fetchall():
            caci_map[
                ((cr[0] or "").strip().upper(),
                 (cr[1] or "").strip().upper())
            ] = cr[2] or ""
        conn.close()

        # --- En-têtes ---
        headers = ["Plongeur", "Niveau", "En formation", "CACI"]
        for dj, num in plongees:
            headers.append(f"{dj} P{num}")

        # --- Fonction CACI ---
        def caci_lbl(s):
            if not s:
                return "?"
            try:
                dt = datetime.strptime(s.strip(), "%d/%m/%Y").date()
                today = datetime.now().date()
                if dt < today:
                    return "PERIME"
                if dt < today + timedelta(days=30):
                    return "ALERTE"
                return "VALIDE"
            except Exception:
                return "?"

        # --- Construction des lignes ---
        rows = [headers]

        for p in plongeurs:
            pid = p["id"]
            key = (
                (p["nom"].value or "").strip().upper(),
                (p["prenom"].value or "").strip().upper()
            )

            row = [
                f"{p['nom'].value} {p['prenom'].value}",
                get_niveau(p) or "",
                get_prepa(p) or "",
                caci_lbl(caci_map.get(key, "")),
            ]

            for dj, num in plongees:
                v = state["tab3_vars"].get((pid, dj, num))
                row.append("X" if (v and v.value) else "")

            rows.append(row)

        # --- Nom du fichier (Changement d'extension .xlsx -> .csv) ---
        nom_sortie = (sortie_nom.value or "sortie").strip()
        safe = "".join(
            c if c.isalnum() or c in " -_" else "_"
            for c in nom_sortie
        ).strip()

        path = os.path.join(
            app_dir(), f"Inscriptions_{safe}.csv"
        )
        

        # --- Export CSV pur-Python (100% compatible Android) ---
        try:
            # utf-8-sig permet à Excel d'ouvrir directement le CSV avec les bons accents
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f, delimiter=";")
                writer.writerows(rows)

            show_message(f"Export CSV créé : {path}")

            # Proposer le partage natif (Drive, Files, mail...)
            if share_service is not None:
                offer_share_files(
                    [path],
                    mime_type="text/csv",
                    titre_dialogue="📤 Partager l'export",
                    label_fichier="export CSV",
                    sujet=f"Inscriptions — {nom_sortie}",
                    texte=(
                        f"Liste des inscriptions"
                        f" de la sortie {nom_sortie}"
                    ),
                )
        except Exception as err:
            show_message(f"Erreur export : {err}")

    def save_plongees_realisees(e):

        if state["sortie_id"] is None:

            show_message("Aucune sortie active.")

            return

        ids = list({
            pid
            for (pid, _, _) in state["tab3_vars"].keys()
        })

        if not ids:
            return

        conn = sqlite3.connect(DB_PATH)

        c = conn.cursor()

        ph = ",".join("?" * len(ids))

        c.execute(
            f"DELETE FROM plongees_realisees"
            f" WHERE participant_id IN ({ph})",
            ids
        )

        for (pid, dj, num), v in state["tab3_vars"].items():

            if v.value:

                c.execute(
                    "INSERT INTO plongees_realisees"
                    "(participant_id, date_jour, num_plongee)"
                    " VALUES (?, ?, ?)",
                    (pid, dj, num)
                )

        conn.commit()
        conn.close()

        show_message("Inscriptions sauvegardées.")

    t3_save_btn.on_click = save_plongees_realisees
    t3_export_btn.on_click = t3_export_excel

    def refresh_tab3_grid():

        # Persiste les participants pour qu'ils aient un id
        if (
            state["sortie_id"] is not None
            and state["participants_rows"]
        ):
            save_participants_silent()

        state["tab3_vars"] = {}

        tab3_grid_column.controls.clear()

        # Restaurer l'état verrou
        if state["sortie_id"] is not None:

            conn = sqlite3.connect(DB_PATH)

            r = conn.execute(
                "SELECT value FROM config WHERE key=?",
                (f"t3_locked_{state['sortie_id']}",)
            ).fetchone()

            conn.close()

            state["t3_locked"] = (
                r is not None and r[0] == "1"
            )

        else:

            state["t3_locked"] = False

        t3_apply_lock_style()

        plongees = get_plongees_list()

        if state["sortie_id"] is None:

            tab3_grid_column.controls.append(
                ft.Text(
                    "Aucune sortie ouverte.",
                    italic=True,
                    color="#94a3b8"
                )
            )

            tab3_stats_lbl.value = ""
            page.update()
            return

        if not plongees:

            tab3_grid_column.controls.append(
                ft.Text(
                    "Aucune plongée définie. Renseigner"
                    " les dates et le nombre de plongées"
                    " par jour (onglet 1).",
                    italic=True,
                    color="#94a3b8"
                )
            )

            tab3_stats_lbl.value = ""
            page.update()
            return

        plongeurs = [
            r
            for r in state["participants_rows"]
            if r["type"] == "plongeur" and r.get("id")
        ]

        if not plongeurs:

            tab3_grid_column.controls.append(
                ft.Text(
                    "Aucun plongeur dans la sortie."
                    " Ajouter des participants (onglet 2).",
                    italic=True,
                    color="#94a3b8"
                )
            )

            tab3_stats_lbl.value = ""
            page.update()
            return

        # Cases déjà cochées
        deja = set()

        ids_p = [r["id"] for r in plongeurs]

        conn = sqlite3.connect(DB_PATH)

        ph = ",".join("?" * len(ids_p))

        rows = conn.execute(
            f"SELECT participant_id, date_jour, num_plongee"
            f" FROM plongees_realisees"
            f" WHERE participant_id IN ({ph})",
            ids_p
        ).fetchall()

        conn.close()

        for r in rows:
            deja.add((r[0], r[1], r[2]))

        # Récupérer les dates CACI depuis la base club
        caci_map = {}
        conn = sqlite3.connect(DB_PATH)
        for cr in conn.execute(
            "SELECT nom, prenom, caci_date"
            " FROM plongeurs_club"
        ).fetchall():
            caci_map[
                (
                    (cr[0] or "").strip().upper(),
                    (cr[1] or "").strip().upper()
                )
            ] = cr[2] or ""
        conn.close()

        nitrox_map = get_nitrox_map()

        # En-tête : Plongeur | En formation | CACI | Tout | P1 P2 ...
        header_cells = [

            ft.Container(
                ft.Text(
                    "Plongeur",
                    color="white",
                    weight=ft.FontWeight.BOLD,
                    size=12
                ),
                width=210,
                bgcolor="#1e3a5f",
                padding=6
            ),

            ft.Container(
                ft.Text(
                    "Niv. prep.",
                    color="white",
                    weight=ft.FontWeight.BOLD,
                    size=11
                ),
                width=70,
                bgcolor="#1e3a5f",
                padding=6
            ),

            ft.Container(
                ft.Text(
                    "CACI",
                    color="white",
                    weight=ft.FontWeight.BOLD,
                    size=11
                ),
                width=70,
                bgcolor="#1e3a5f",
                padding=6,
                alignment=ft.Alignment.CENTER
            ),

            ft.Container(
                ft.Text(
                    "Tout",
                    color="white",
                    weight=ft.FontWeight.BOLD,
                    size=11
                ),
                width=50,
                bgcolor="#1e3a5f",
                padding=6,
                alignment=ft.Alignment.CENTER
            ),
        ]

        def make_toggle_col(dj=None, num=None):
            """Coche/décoche toute une colonne (plongée)."""
            def handler(e):
                if state["t3_locked"]:
                    show_message(
                        "Inscriptions verrouillées."
                    )
                    return
                vars_col = [
                    state["tab3_vars"].get((p["id"], dj, num))
                    for p in plongeurs
                ]
                vars_col = [
                    v for v in vars_col if v is not None
                ]
                if not vars_col:
                    return
                tout = all(v.value for v in vars_col)
                for v in vars_col:
                    v.value = not tout
                update_tab3_stats()
                page.update()
            return handler

        for dj, num in plongees:

            header_cells.append(

                ft.Container(

                    ft.Column(
                        [
                            ft.Text(
                                f"{jour_fr(dj)} {dj[:5]}\nP{num}",
                                color="white",
                                weight=ft.FontWeight.BOLD,
                                size=10,
                                text_align=ft.TextAlign.CENTER
                            ),
                            ft.IconButton(
                                icon=ft.Icons.CHECKLIST,
                                icon_size=14,
                                icon_color="white",
                                tooltip="Cocher/décocher"
                                " la colonne",
                                on_click=make_toggle_col(
                                    dj, num
                                )
                            ),
                        ],
                        spacing=0,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        tight=True
                    ),

                    width=70,

                    bgcolor="#3b82f6",

                    padding=2,

                    alignment=ft.Alignment.CENTER
                )
            )

        tab3_grid_column.controls.append(
            ft.Row(header_cells, spacing=1)
        )

        CACI_COLORS = {
            "VALIDE": "#10b981",
            "ALERTE": "#f59e0b",
            "PERIME": "#ef4444",
        }

        def caci_status(caci_str):
            if not caci_str:
                return "?", "#94a3b8"
            try:
                dt = datetime.strptime(
                    caci_str.strip(), "%d/%m/%Y"
                ).date()
                today = datetime.now().date()
                if dt < today:
                    return "PERIME", CACI_COLORS["PERIME"]
                if dt < today + timedelta(days=30):
                    return "ALERTE", CACI_COLORS["ALERTE"]
                return "VALIDE", CACI_COLORS["VALIDE"]
            except Exception:
                return "?", "#94a3b8"

        # Lignes plongeurs
        for i, p in enumerate(plongeurs):

            pid = p["id"]

            bg = "#f8fafc" if i % 2 == 0 else "white"

            niv = get_niveau(p) or "—"
            prepa = get_prepa(p) or ""

            key = (
                (p['nom'].value or "").strip().upper(),
                (p['prenom'].value or "").strip().upper()
            )

            nx = nitrox_map.get(key, "")

            label = (
                f"{p['nom'].value} {p['prenom'].value}"
                f"  ({fmt_niveau(niv, nx)})"
            )

            caci_str = caci_map.get(key, "")
            caci_lbl, caci_col = caci_status(caci_str)

            row_cells = [

                ft.Container(
                    ft.Text(label, size=11),
                    width=210,
                    bgcolor=bg,
                    padding=6
                ),

                ft.Container(
                    ft.Text(
                        fmt_niveau(prepa, "") if prepa
                        else "—",
                        size=11,
                        color=(
                            "#7c3aed" if prepa
                            else "#cbd5e1"
                        ),
                        weight=(
                            ft.FontWeight.BOLD if prepa
                            else ft.FontWeight.NORMAL
                        ),
                        text_align=ft.TextAlign.CENTER
                    ),
                    width=70,
                    bgcolor=bg,
                    padding=6
                ),

                ft.Container(
                    ft.Text(
                        caci_lbl,
                        size=10,
                        color="white",
                        weight=ft.FontWeight.BOLD,
                        text_align=ft.TextAlign.CENTER
                    ),
                    width=70,
                    bgcolor=caci_col,
                    padding=6,
                    alignment=ft.Alignment.CENTER
                ),
            ]

            # Bouton tout cocher/décocher (ligne)
            def make_toggle_all(pid=pid):

                def handler(e):

                    if state["t3_locked"]:
                        show_message(
                            "Inscriptions verrouillées."
                        )
                        return

                    vars_row = [
                        state["tab3_vars"].get((pid, dj, num))
                        for dj, num in plongees
                    ]

                    vars_row = [
                        v for v in vars_row if v is not None
                    ]

                    if not vars_row:
                        return

                    tout = all(v.value for v in vars_row)

                    for v in vars_row:
                        v.value = not tout

                    update_tab3_stats()

                    page.update()

                return handler

            row_cells.append(

                ft.Container(

                    ft.IconButton(
                        icon=ft.Icons.CHECKLIST,
                        icon_size=18,
                        tooltip="Tout cocher/décocher",
                        on_click=make_toggle_all(pid)
                    ),

                    width=50,

                    bgcolor=bg,

                    alignment=ft.Alignment.CENTER
                )
            )

            for dj, num in plongees:

                cb = ft.Checkbox(
                    value=(pid, dj, num) in deja,
                    disabled=state["t3_locked"],
                    on_change=lambda e: update_tab3_stats()
                )

                state["tab3_vars"][(pid, dj, num)] = cb

                row_cells.append(

                    ft.Container(
                        cb,
                        width=70,
                        bgcolor=bg,
                        alignment=ft.Alignment.CENTER
                    )
                )

            tab3_grid_column.controls.append(
                ft.Row(row_cells, spacing=1)
            )

        # Boutons enregistrer + export
        update_tab3_stats()

        page.update()

    # =================================================
    # FONCTIONS TAB 4 — PALANQUÉES
    # =================================================

    # Dropdown utilisé dans la pop-up de sélection
    t4_plongee_combo = ft.Dropdown(

        label="Plongée",

        width=_w(360),

        options=[]
    )

    # Bouton affichant la plongée courante (ouvre la pop-up)
    t4_plongee_btn = ft.FilledButton(
        "Choisir une plongée",
        bgcolor="#3b82f6",
        color="white",
        icon=ft.Icons.SCUBA_DIVING
    )

    def t4_open_plongee_dialog(e=None):

        if not t4_plongee_combo.options:
            show_message(
                "Aucune plongée. Générez les jours"
                " et enregistrez la sortie."
            )
            return

        def valider(ev):
            close_dialog(sel_dlg)
            t4_on_plongee_selected(None)

        sel_dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(
                "Sélectionner une plongée",
                weight=ft.FontWeight.BOLD
            ),
            content=ft.Container(
                width=_w(400),
                content=ft.Column(
                    tight=True,
                    spacing=12,
                    controls=[
                        ft.Text(
                            "Choisir la plongée à"
                            " constituer :",
                            size=12
                        ),
                        t4_plongee_combo,
                    ]
                )
            ),
            actions=[
                ft.TextButton(
                    "Annuler",
                    on_click=lambda ev:
                        close_dialog(sel_dlg)
                ),
                ft.FilledButton(
                    "Valider",
                    on_click=valider
                ),
            ]
        )
        page.show_dialog(sel_dlg)

    t4_plongee_btn.on_click = t4_open_plongee_dialog

    t4_info_btn = ft.TextButton(

        "(aucune plongée sélectionnée)",

        on_click=lambda e: t4_show_synthese()
    )

    t4_type_radio = ft.RadioGroup(

        value="Exploration encadrée",

        content=ft.Column([

            ft.Radio(
                value="Exploration encadrée",
                label="Exploration encadrée"
            ),

            ft.Radio(
                value="Exploration autonome",
                label="Exploration autonome"
            ),

            ft.Radio(
                value="Technique",
                label="Technique"
            ),

            ft.Radio(
                value="Baptême",
                label="Baptême"
            ),
        ], tight=True, spacing=0)
    )

    t4_chef_combo = ft.Dropdown(
        label="Encadrant (chef de palanquée)",
        options=[]
    )

    t4_sf_combo = ft.Dropdown(
        label="Serre-file",
        options=[]
    )

    # Boutons d'ouverture des pop-ups chef / serre-file
    t4_chef_btn = ft.FilledButton(
        "🚩 Encadrant : (aucun)",
        bgcolor="#3b82f6",
        color="white"
    )

    t4_sf_btn = ft.FilledButton(
        "🔚 Serre-file : (aucun)",
        bgcolor="#6366f1",
        color="white"
    )

    def t4_maj_chef_btn():
        v = t4_chef_combo.value or "(aucun)"
        t4_chef_btn.content = ft.Text(
            f"🚩 Encadrant : {v}", color="white"
        )

    def t4_maj_sf_btn():
        v = t4_sf_combo.value or "(aucun)"
        t4_sf_btn.content = ft.Text(
            f"🔚 Serre-file : {v}", color="white"
        )

    def t4_open_chef_dialog(e=None):
        def valider(ev):
            close_dialog(dlg)
            t4_maj_chef_btn()
            t4_refresh_membres()
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(
                "🚩 Choisir l'encadrant",
                weight=ft.FontWeight.BOLD
            ),
            content=ft.Container(
                width=_w(400),
                content=ft.Column(
                    [t4_chef_combo],
                    tight=True
                )
            ),
            actions=[
                ft.TextButton(
                    "Annuler",
                    on_click=lambda ev: close_dialog(dlg)
                ),
                ft.FilledButton(
                    "Valider", on_click=valider
                ),
            ]
        )
        page.show_dialog(dlg)

    def t4_open_sf_dialog(e=None):
        def valider(ev):
            close_dialog(dlg)
            t4_maj_sf_btn()
            t4_refresh_membres()
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(
                "🔚 Choisir le serre-file",
                weight=ft.FontWeight.BOLD
            ),
            content=ft.Container(
                width=_w(400),
                content=ft.Column(
                    [t4_sf_combo],
                    tight=True
                )
            ),
            actions=[
                ft.TextButton(
                    "Annuler",
                    on_click=lambda ev: close_dialog(dlg)
                ),
                ft.FilledButton(
                    "Valider", on_click=valider
                ),
            ]
        )
        page.show_dialog(dlg)

    t4_chef_btn.on_click = t4_open_chef_dialog
    t4_sf_btn.on_click = t4_open_sf_dialog

    t4_membres_column = ft.Column(spacing=2)

    t4_prof_field = ft.TextField(
        label="Prof. max (m)",
        value="20",
        width=120,
        dense=True
    )

    t4_duree_field = ft.TextField(
        label="Durée max (min)",
        value="45",
        width=130,
        dense=True
    )

    t4_dtr_field = ft.TextField(
        label="DTR max (min)",
        value="",
        hint_text="facultatif",
        width=120,
        dense=True
    )

    t4_apercu_column = ft.Column(spacing=2)

    t4_palanquees_column = ft.Column(
        spacing=8,
        scroll=ft.ScrollMode.AUTO,
        expand=True
    )

    t4_save_btn = ft.FilledButton(
        "💾 Enregistrer palanquée",
        bgcolor="#10b981",
        color="white"
    )

    # État membres : {label: checkbox}, {label: id}, {label: niveau}
    t4_state = {

        "dispo": [],          # rows (id, nom, prenom, niveau)

        "membre_checks": {},  # label -> Checkbox

        "label_to_id": {},

        "label_to_niveau": {},

        "label_to_prepa": {},

        "label_to_age": {},

        "gas": {},            # label -> {"gaz": Dropdown, "pct": Slider}
    }

    def t4_refresh_combo():

        if (
            state["sortie_id"] is not None
            and state["participants_rows"]
        ):
            save_participants_silent()

        plongees = get_plongees_list()

        labels = []

        state["_t4_map"] = {}

        for d, n in plongees:

            lbl = f"{jour_fr(d)} {d} — Plongée {n}"

            labels.append(lbl)

            state["_t4_map"][lbl] = (d, n)

        t4_plongee_combo.options = [
            ft.DropdownOption(l) for l in labels
        ]

        if labels:

            if t4_plongee_combo.value not in labels:
                t4_plongee_combo.value = labels[0]

            t4_on_plongee_selected(None)

        else:

            t4_plongee_combo.value = None
            state["t4_current"] = None
            t4_plongee_btn.content = ft.Text(
                "Choisir une plongée",
                color="white"
            )
            t4_info_btn.content = ft.Text(
                "(aucune plongée)"
            )

        page.update()

    def t4_on_plongee_selected(e):

        lbl = t4_plongee_combo.value

        if not lbl or lbl not in state.get("_t4_map", {}):

            state["t4_current"] = None
            t4_info_btn.content = ft.Text(
                "(aucune plongée sélectionnée)"
            )
            page.update()
            return

        dj, num = state["_t4_map"][lbl]

        state["t4_current"] = (dj, num)

        # Mettre à jour le libellé du bouton
        t4_plongee_btn.content = ft.Text(
            f" {lbl}",
            color="white"
        )

        # Plongeurs présents (réalisées, sinon tous)
        conn = sqlite3.connect(DB_PATH)

        ids_real = {
            r[0]
            for r in conn.execute(
                "SELECT participant_id FROM"
                " plongees_realisees"
                " WHERE date_jour=? AND num_plongee=?",
                (dj, num)
            ).fetchall()
        }

        rows = conn.execute(
            "SELECT pa.id, pa.nom, pa.prenom, pa.niveau,"
            " pc.brevet_nitrox, pa.niveau_prepa,"
            " pc.date_naissance"
            " FROM participants pa"
            " LEFT JOIN plongeurs_club pc"
            " ON UPPER(pc.nom)=UPPER(pa.nom)"
            " AND UPPER(pc.prenom)=UPPER(pa.prenom)"
            " WHERE pa.sortie_id=?"
            " AND pa.type='plongeur' ORDER BY pa.nom",
            (state["sortie_id"],)
        ).fetchall()

        conn.close()

        if ids_real:
            t4_state["dispo"] = [
                r for r in rows if r[0] in ids_real
            ]
        else:
            t4_state["dispo"] = rows

        n = len(t4_state["dispo"])

        t4_info_btn.content = ft.Text(
            f"📊  {n} plongeur(s) sur cette plongée "
            f"\n —> voir la synthèse"
        )

        t4_reset_form()
        t4_refresh_palanquees_display()

        page.update()

    def t4_get_occupes():

        if state["t4_current"] is None:
            return set()

        dj, num = state["t4_current"]

        conn = sqlite3.connect(DB_PATH)

        rows = conn.execute("""

            SELECT pm.participant_id
            FROM palanquee_membres pm
            JOIN palanquees_sortie p
              ON p.id = pm.palanquee_id
            WHERE p.sortie_id=? AND p.date_jour=?
              AND p.num_plongee=?
              AND (? IS NULL OR p.id != ?)

        """, (
            state["sortie_id"], dj, num,
            state["t4_edit_id"], state["t4_edit_id"]
        )).fetchall()

        conn.close()

        return {r[0] for r in rows}

    def label_p(r):
        nx = r[4] if len(r) > 4 else ""
        return f"{r[1]} {r[2]} ({fmt_niveau(r[3] or '—', nx)})"

    def t4_refresh_membres():

        if not t4_state["dispo"]:
            return

        occupes = t4_get_occupes()

        chef_sel = t4_chef_combo.value or ""
        sf_sel = t4_sf_combo.value or ""

        t4_state["label_to_id"] = {
            label_p(r): r[0]
            for r in t4_state["dispo"]
        }

        t4_state["label_to_niveau"] = {
            label_p(r): (r[3] or "")
            for r in t4_state["dispo"]
        }

        t4_state["label_to_prepa"] = {
            label_p(r): (
                r[5] if len(r) > 5 and r[5] else ""
            )
            for r in t4_state["dispo"]
        }

        # Index âge -> nécessaire pour les règles
        # FFESSM par tranche d'âge (Bronze, Argent, Or,
        # baptême enfant, PA40 < 17 ans, etc.)
        t4_state["label_to_age"] = {
            label_p(r): calc_age(
                r[6] if len(r) > 6 else ""
            )
            for r in t4_state["dispo"]
        }

        dispo = [
            r for r in t4_state["dispo"]
            if r[0] not in occupes
        ]

        labels_dispo = [label_p(r) for r in dispo]

        ttype = t4_type_radio.value

        # Encadrant : GP/E1-E4
        elig_chef = [
            label_p(r) for r in dispo
            if (r[3] or "") in ("GP","E1","E2","E3","E4")
        ]

        t4_chef_combo.options = [
            ft.DropdownOption("")
        ] + [ft.DropdownOption(l) for l in elig_chef]

        if chef_sel in [""] + elig_chef:
            t4_chef_combo.value = chef_sel
        else:
            t4_chef_combo.value = ""

        # Serre-file : GP/E2-E4
        elig_sf = [
            l for l, r in zip(labels_dispo, dispo)
            if (r[3] or "") in ("GP","E2","E3","E4")
            and l != t4_chef_combo.value
        ]

        t4_sf_combo.options = [
            ft.DropdownOption("")
        ] + [ft.DropdownOption(l) for l in elig_sf]

        if sf_sel in [""] + elig_sf:
            t4_sf_combo.value = sf_sel
        else:
            t4_sf_combo.value = ""

        # Membres : tout sauf chef/serre-file
        exclus = {
            t4_chef_combo.value,
            t4_sf_combo.value
        } - {""}

        t4_membres_column.controls.clear()
        t4_state["membre_checks"] = {}

        for l, r in zip(labels_dispo, dispo):

            if l in exclus:
                continue

            cb = ft.Checkbox(
                label=l,
                value=False,
                on_change=lambda e: t4_refresh_apercu()
            )

            t4_state["membre_checks"][l] = cb

            t4_membres_column.controls.append(cb)

        t4_refresh_apercu()

        page.update()

    def t4_on_type_changed(e):

        ttype = t4_type_radio.value

        # Serre-file masqué en Autonome et Baptême
        t4_sf_btn.visible = ttype not in (
            "Exploration autonome", "Baptême"
        )

        # Encadrant masqué en Autonome
        t4_chef_btn.visible = (
            ttype != "Exploration autonome"
        )

        t4_refresh_membres()

        page.update()

    t4_type_radio.on_change = t4_on_type_changed

    def t4_refresh_apercu():

        # Sauver l'état gaz courant
        old_gas = {}
        prev_apts = {}

        for lbl, w in t4_state["gas"].items():

            try:
                old_gas[lbl] = {
                    "gaz": w["gaz"].value,
                    "pct": w["pct"].value
                }
            except Exception:
                pass

            try:
                if w.get("aptitude") is not None:
                    prev_apts[lbl] = w["aptitude"].value or ""
            except Exception:
                pass

        t4_apercu_column.controls.clear()
        t4_state["gas"] = {}

        ttype = t4_type_radio.value
        chef = (t4_chef_combo.value or "").strip()
        sf = (t4_sf_combo.value or "").strip()

        membres = [
            l
            for l, cb in t4_state["membre_checks"].items()
            if cb.value
        ]

        COULEURS_T = {
            "Exploration encadrée": "#dbeafe",
            "Exploration autonome": "#dcfce7",
            "Technique": "#ede9fe",
            "Baptême": "#fce7f3",
        }

        bg = COULEURS_T.get(ttype, "#f1f5f9")

        t4_apercu_column.controls.append(
            ft.Text(
                ttype,
                weight=ft.FontWeight.BOLD,
                size=12
            )
        )

        dtr_txt = (
            f"   ⬆ DTR {t4_dtr_field.value} min"
            if (t4_dtr_field.value or "").strip()
            else ""
        )

        t4_apercu_column.controls.append(
            ft.Text(
                f"⬇ {t4_prof_field.value} m"
                f"   ⏱ {t4_duree_field.value} min"
                f"{dtr_txt}",
                size=11,
                color="#475569"
            )
        )

        t4_apercu_column.controls.append(ft.Divider(height=1))

        def build_gas_row(label, icon, bold, gaz_val, pct_val):
            """Bouton ouvrant une pop-up pour choisir
            Air ou Nitrox (+%). Les dialogues se
            rafraîchissent indépendamment de la colonne,
            ce qui contourne le bug de mise à jour de
            Flet 0.85."""

            nom_court = label.split(" (")[0]

            try:
                pv = int(pct_val)
            except Exception:
                pv = 32

            if pv < 21:
                pv = 32

            # État mutable du gaz pour ce membre
            gas_state = {
                "gaz": gaz_val,
                "pct": pv,
            }

            def libelle():
                if gas_state["gaz"] == "Nitrox":
                    return f"Nx{gas_state['pct']}"
                return "Air"

            def couleur_btn():
                return (
                    "#0ea5e9"
                    if gas_state["gaz"] == "Nitrox"
                    else "#94a3b8"
                )

            gaz_btn = ft.FilledButton(
                libelle(),
                bgcolor=couleur_btn(),
                color="white",
                width=110
            )

            # Pour la compat avec t4_get_gaz et la
            # sauvegarde : on expose des objets ayant un
            # attribut .value (comme avant).
            class _Val:
                def __init__(self, d, k):
                    self._d = d
                    self._k = k

                @property
                def value(self):
                    return self._d[self._k]

                @value.setter
                def value(self, v):
                    self._d[self._k] = v

            t4_state["gas"][label] = {
                "gaz": _Val(gas_state, "gaz"),
                "pct": _Val(gas_state, "pct"),
            }

            # Rôle déduit de l'icône
            is_chef = (icon == "🚩")
            is_sf = (icon == "🔚")

            if is_chef or is_sf:

                # Pas de dropdown : valeur fixe ENC / SF
                fct_state = {
                    "v": "ENC" if is_chef else "SF"
                }

                class _FixedVal:
                    def __init__(self, d):
                        self._d = d

                    @property
                    def value(self):
                        return self._d["v"]

                    @value.setter
                    def value(self, x):
                        pass  # non modifiable

                apt_widget = ft.Container(
                    content=ft.Text(
                        "ENC" if is_chef else "SF",
                        size=11,
                        weight=ft.FontWeight.BOLD,
                        color=(
                            "#1e40af" if is_chef
                            else "#b45309"
                        )
                    ),
                    width=100,
                    alignment=ft.Alignment.CENTER
                )

                t4_state["gas"][label]["aptitude"] = \
                    _FixedVal(fct_state)

            else:

                # Dropdown Aptitude selon le type de plongée
                ttype = t4_type_radio.value or ""

                if ttype in (
                    "Exploration encadrée", "Technique"
                ):
                    apt_opts = ["", "Déb.", "PE12", "PE20",
                                "PE40", "PE60"]
                elif ttype == "Exploration autonome":
                    apt_opts = ["", "PA12", "PA20",
                                "PA40", "PA60"]
                else:  # Baptême
                    apt_opts = ["", "Déb."]

                prev_apt = prev_apts.get(label, "")
                if prev_apt not in apt_opts:
                    prev_apt = ""

                apt_dd = ft.Dropdown(
                    value=prev_apt,
                    width=100,
                    dense=True,
                    text_size=11,
                    disabled=(ttype == "Baptême"),
                    options=[
                        ft.DropdownOption(o)
                        for o in apt_opts
                    ]
                )

                apt_widget = apt_dd

                t4_state["gas"][label]["aptitude"] = apt_dd

            def open_gas_dialog(e):

                choix_gaz = ft.RadioGroup(
                    value=gas_state["gaz"],
                    content=ft.Row([
                        ft.Radio(value="Air", label="Air"),
                        ft.Radio(
                            value="Nitrox",
                            label="Nitrox"
                        ),
                    ])
                )

                pct_value_lbl = ft.Text(
                    f"{gas_state['pct']} % O₂",
                    size=14,
                    weight=ft.FontWeight.BOLD
                )

                pct_choice = ft.Slider(
                    min=21,
                    max=40,
                    divisions=19,
                    value=gas_state["pct"],
                    label="{value}%"
                )

                def on_slider(ev, lbl=pct_value_lbl,
                              sl=pct_choice):
                    lbl.value = f"{int(sl.value)} % O₂"
                    lbl.update()

                pct_choice.on_change = on_slider

                def valider(ev):
                    gas_state["gaz"] = (
                        choix_gaz.value or "Air"
                    )
                    try:
                        gas_state["pct"] = int(
                            pct_choice.value
                        )
                    except Exception:
                        gas_state["pct"] = 32

                    gaz_btn.content = ft.Text(
                        libelle(),
                        color="white"
                    )
                    gaz_btn.bgcolor = couleur_btn()
                    gaz_btn.update()

                    close_dialog(gas_dlg)

                gas_dlg = ft.AlertDialog(
                    modal=True,
                    title=ft.Text(
                        f"Gaz — {nom_court}",
                        weight=ft.FontWeight.BOLD,
                        size=14
                    ),
                    content=ft.Container(
                        width=_w(320),
                        content=ft.Column(
                            tight=True,
                            spacing=12,
                            controls=[
                                choix_gaz,
                                pct_value_lbl,
                                pct_choice,
                                ft.Text(
                                    "Le % n'est utilisé"
                                    " que pour le Nitrox.",
                                    size=10,
                                    italic=True,
                                    color="#94a3b8"
                                ),
                            ]
                        )
                    ),
                    actions=[
                        ft.TextButton(
                            "Annuler",
                            on_click=lambda ev:
                                close_dialog(gas_dlg)
                        ),
                        ft.FilledButton(
                            "Valider",
                            on_click=valider
                        ),
                    ]
                )

                page.show_dialog(gas_dlg)

            gaz_btn.on_click = open_gas_dialog

            # Largeur nom réduite sur mobile + scroll
            # horizontal pour accéder au bouton gaz et au
            # dropdown aptitude
            row = ft.Row(
                [
                    ft.Text(
                        f"{icon} {nom_court}",
                        size=11,
                        weight=(
                            ft.FontWeight.BOLD
                            if bold
                            else ft.FontWeight.NORMAL
                        ),
                        width=140
                    ),

                    gaz_btn,

                    apt_widget,
                ],
                scroll=ft.ScrollMode.AUTO,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=6
            )

            return row

        def add_gas_row(label, icon, bold=False):

            prev = old_gas.get(label, {})
            prev_gaz = prev.get("gaz", "Air")
            prev_pct = prev.get("pct", 32)

            row = build_gas_row(
                label, icon, bold, prev_gaz, prev_pct
            )

            t4_apercu_column.controls.append(row)

        if chef:
            add_gas_row(chef, "🚩", bold=True)

        if sf:
            add_gas_row(sf, "🔚")

        for m in membres:
            add_gas_row(m, "•")

        nb_total = (
            (1 if chef else 0)
            + (1 if sf else 0)
            + len(membres)
        )

        t4_apercu_column.controls.append(ft.Divider(height=1))

        t4_apercu_column.controls.append(
            ft.Text(
                f"Total : {nb_total} plongeur(s)",
                weight=ft.FontWeight.BOLD,
                size=11
            )
        )

        page.update()

    t4_prof_field.on_change = lambda e: t4_refresh_apercu()
    t4_duree_field.on_change = lambda e: t4_refresh_apercu()
    t4_dtr_field.on_change = lambda e: t4_refresh_apercu()

    def t4_reset_form():

        state["t4_edit_id"] = None
        # On conserve type, prof et durée comme valeurs
        # par défaut (dernières utilisées). On ne
        # réinitialise que chef, serre-file, DTR et gaz.
        t4_chef_combo.value = ""
        t4_sf_combo.value = ""
        t4_maj_chef_btn()
        t4_maj_sf_btn()
        t4_dtr_field.value = ""
        t4_state["gas"] = {}

        t4_save_btn.content = ft.Text(
            "💾 Enregistrer palanquée",
            color="white"
        )

        t4_on_type_changed(None)

    def t4_get_gaz(label):

        w = t4_state["gas"].get(label)

        if not w:
            return "Air"

        if w["gaz"].value == "Nitrox":
            return f"Nx{int(w['pct'].value)}"

        return "Air"

    def t4_get_apt(label):

        w = t4_state["gas"].get(label)

        if not w or w.get("aptitude") is None:
            return ""

        v = w["aptitude"].value or ""

        # ENC/SF sont des fonctions, pas des aptitudes :
        # on ne les stocke pas comme aptitude.
        if v in ("ENC", "SF"):
            return ""

        return v

    def t4_save_palanquee(e):

        if state["t4_current"] is None:
            show_message("Sélectionner une plongée.")
            return

        dj, num = state["t4_current"]

        ttype = t4_type_radio.value
        chef_lbl = (t4_chef_combo.value or "").strip()
        sf_lbl = (t4_sf_combo.value or "").strip()

        mem_lbls = [
            l
            for l, cb in t4_state["membre_checks"].items()
            if cb.value
        ]

        if not chef_lbl and not mem_lbls:
            show_message("Sélectionner au moins un plongeur.")
            return

        try:
            prof = float(
                t4_prof_field.value.replace(",", ".")
            )
        except Exception:
            prof = 0

        try:
            duree = int(t4_duree_field.value)
        except Exception:
            duree = 0

        dtr_str = (t4_dtr_field.value or "").strip()
        try:
            dtr = int(dtr_str) if dtr_str else None
        except Exception:
            dtr = None

        # ══════════════════════════════════════════════
        # RÈGLES CODE DU SPORT — BLOCAGES
        # ══════════════════════════════════════════════
        l2n = t4_state["label_to_niveau"]
        chef_niv = l2n.get(chef_lbl, "") if chef_lbl else ""
        niveaux_membres = [
            l2n.get(m, "") for m in mem_lbls
        ]
        nb_membres = len(mem_lbls)

        blocages = []

        if ttype == "Exploration autonome":
            if nb_membres > 3:
                blocages.append(
                    "🚫 Autonome : 3 plongeurs max."
                )
            if nb_membres < 2:
                blocages.append(
                    "🚫 Autonome : 2 plongeurs min."
                )

        if ttype == "Baptême":
            if not chef_lbl:
                blocages.append(
                    "🚫 Baptême : moniteur (E1-E4)"
                    " obligatoire."
                )
            elif chef_niv not in ("E1","E2","E3","E4"):
                blocages.append(
                    "🚫 Baptême : encadrant doit être"
                    " moniteur."
                )
            if nb_membres != 1:
                blocages.append("🚫 Un baptême, c'est un moniteur pour un élève (Code du sport).")
            if prof > 6:
                blocages.append("🚫 Un baptême se fait dans la zone 0-6m (Code du sport).")       
            
        if ttype in ("Exploration encadrée", "Technique"):
            if not chef_lbl:
                blocages.append("🚫 Palanquée encadrée / technique : un encadrant est obligatoire.")
            if nb_membres > 4:
                blocages.append("🚫 Palanquée encadrée / technique : 4 plongeurs maximum en plus de l'encadrant (Code du sport).")
            if nb_membres < 1:
                blocages.append("🚫 Palanquée encadrée / technique : doit comporter au moins un plongeur à encadrer.")
            # E1 limité à 0-6 m
            if chef_niv == "E1" and prof > 6:
                blocages.append("🚫 Un initiateur E1 ne peut encadrer que dans la zone 0-6 m (Code du sport).")
            # E2 en Technique limité à 0-20 m
            if ttype == "Technique" and chef_niv == "E2" and prof > 20:
                blocages.append("🚫 En formation, un E2 ne peut encadrer que dans la zone 0-20 m (Code du sport).")
            # Serre-file interdit > 40 m
            if sf_lbl and prof > 40:
                blocages.append("🚫 Serre-file interdit pour une profondeur maximale strictement supérieure à 40 m.")
            # > 40 m : E4 requis
            if chef_niv and chef_niv != "E4" and prof > 40:
                blocages.append("🚫 L'encadrant doit être moniteur E4 pour une profondeur maximale strictement supérieure à 40 m.")

        if ttype == "Technique" and chef_niv and chef_niv not in ("E1", "E2", "E3", "E4"):
            blocages.append("🚫 Plongée Technique : le responsable doit être moniteur (E1 -> E4).")

        # Règles de profondeur selon le niveau préparé de
        # chaque membre (formation technique)
        if ttype == "Technique":
            l2p = t4_state["label_to_prepa"]
            for m in mem_lbls:
                niv_m = l2n.get(m, "")
                prepa_m = l2p.get(m, "")
                if (
                    niv_m == "Débutant"
                    and (not prepa_m or prepa_m == "Baptême")
                    and prof > 6
                ):
                    blocages.append(
                        "🚫 Un débutant se forme dans la"
                        " zone 0-6 m (Code du sport)."
                    )
                if prepa_m in ("PE12", "PA12") and prof > 12:
                    blocages.append(
                        "🚫 Une formation PE12 / PA12 se"
                        " fait dans la zone 0-12 m"
                        " (Code du sport)."
                    )
                if prepa_m in ("PE20", "PA20") and prof > 20:
                    blocages.append(
                        "🚫 Une formation PE20 / PA20 se"
                        " fait dans la zone 0-20 m"
                        " (Code du sport)."
                    )
                if (
                    prepa_m in ("PE40", "PA40")
                    and prof > 40
                ):
                    blocages.append(
                        "🚫 Une formation PE40 ou PA40"
                        " se fait dans la zone"
                        " 0-40 m (Code du sport)."
                    )
                    

        # Dédoublonner les messages
        blocages = list(dict.fromkeys(blocages))

        if blocages:
            show_message(" / ".join(blocages))
            return

        # ══════════════════════════════════════════════
        # RÈGLES CODE DU SPORT — ALERTES (non bloquantes)
        # ══════════════════════════════════════════════
        alertes = []
        if ttype == "Exploration autonome":
            if "Niveau 2" in niveaux_membres and prof > 20:
                alertes.append(
                    "⚠️ Un Niveau 2 est présent :"
                    " profondeur maximale 20 m en"
                    " autonome."
                )
            if "PA20" in niveaux_membres and prof > 20:
                alertes.append(
                    "⚠️ Un PA20 est présent :"
                    " profondeur maximale 20 m en"
                    " autonome."
                )
            if "PA40" in niveaux_membres and prof > 40:
                alertes.append(
                    "⚠️ Un PA40 est présent : profondeur"
                    " maximale 40 m en autonome."
                )
            if "Débutant" in niveaux_membres:
                alertes.append(
                    "⚠️ Un Débutant en exploration"
                    " autonome : non conforme FFESSM."
                )
            if "PE12" in niveaux_membres:
                alertes.append(
                    "⚠️ Un PE12 en exploration"
                    " autonome : non conforme FFESSM."
                )
            if "PE20" in niveaux_membres:
                alertes.append(
                    "⚠️ Un PE20 en exploration"
                    " autonome : non conforme FFESSM."
                )
            if "Niveau 1" in niveaux_membres:
                alertes.append(
                    "⚠️ Un Niveau 1 en exploration"
                    " autonome : non conforme FFESSM."
                )

        if ttype == "Exploration encadrée":
            if "PE12" in niveaux_membres and prof > 12:
                alertes.append(
                    "⚠️ Un PE12 est présent :"
                    " profondeur maximale 12 m."
                )
            if "Niveau 1" in niveaux_membres and prof > 20:
                alertes.append(
                    "⚠️ Un Niveau 1 est présent :"
                    " profondeur maximale 20 m."
                )
            if "PE20" in niveaux_membres and prof > 20:
                alertes.append(
                    "⚠️ Un PE20 est présent :"
                    " profondeur maximale 20 m."
                )

        # ══════════════════════════════════════════════
        # RÈGLES FFESSM PAR ÂGE (alertes non bloquantes)
        # ══════════════════════════════════════════════
        l2age = t4_state.get("label_to_age", {})
        l2niv = t4_state["label_to_niveau"]
        l2prepa = t4_state.get("label_to_prepa", {})

        # Construire la liste de tous les membres
        # (chef + sf + membres) avec leur info utile
        tous_lbls = []
        if chef_lbl:
            tous_lbls.append(chef_lbl)
        if sf_lbl:
            tous_lbls.append(sf_lbl)
        tous_lbls.extend(mem_lbls)

        # Pour les règles d'effectif "+1 si N1+ présent"
        # on regarde si un brevet adulte est présent.
        N1_PLUS = {"Niveau 1", "Niveau 2", "Niveau 3",
                   "GP", "E1", "E2", "E3", "E4",
                   "PE40", "PA40", "PE60"}
        has_n1_plus = any(
            l2niv.get(l, "") in N1_PLUS
            for l in tous_lbls
        )

        # Nombre de membres à encadrer (hors chef et sf)
        nb_encadres = len(mem_lbls)

        # --- Règle A : Baptême par âge ---
        if ttype == "Baptême":
            for lbl in tous_lbls:
                age_p = l2age.get(lbl)
                if age_p is None:
                    continue
                nom_court = lbl.split(" (")[0]
                if age_p < 8:
                    alertes.append(
                        f"⚠️ {nom_court} ({age_p} ans) :"
                        " pas de plongée en scaphandre"
                        " avant 8 ans (FFESSM)."
                    )
                elif age_p < 10 and prof > 2:
                    alertes.append(
                        f"⚠️ {nom_court} ({age_p} ans) :"
                        " baptême 8-10 ans dans la zone"
                        " 0-2 m (FFESSM)."
                    )
                elif age_p <= 14 and prof > 3:
                    alertes.append(
                        f"⚠️ {nom_court} ({age_p} ans) :"
                        " baptême 10-14 ans dans la zone"
                        " 0-3 m (FFESSM)."
                    )

        # --- Règle B : Formation Débutant -> Bronze ---
        if ttype == "Technique":
            nb_form_bronze = 0
            for lbl in mem_lbls:
                age_p = l2age.get(lbl)
                niv_p = l2niv.get(lbl, "")
                prepa_p = l2prepa.get(lbl, "")
                if (
                    age_p is not None and 8 <= age_p <= 14
                    and niv_p == "Débutant"
                    and prepa_p == "Plongeur Bronze"
                ):
                    nb_form_bronze += 1
                    nom_court = lbl.split(" (")[0]
                    if prof > 6:
                        alertes.append(
                            f"⚠️ {nom_court} ({age_p} ans)"
                            " en formation Bronze : zone"
                            " 0-6 m (FFESSM)."
                        )
            if nb_form_bronze > 1:
                alertes.append(
                    "⚠️ Formation Bronze : 1 enfant"
                    " maximum par encadrant (2 toléré"
                    " en fin de formation, FFESSM)."
                )

        # --- Règle C : Bronze en exploration 8-14 ans ---
        if ttype in (
            "Exploration encadrée", "Exploration autonome"
        ):
            nb_bronze_jeunes = 0
            for lbl in tous_lbls:
                age_p = l2age.get(lbl)
                niv_p = l2niv.get(lbl, "")
                if (
                    age_p is not None and 8 <= age_p <= 14
                    and niv_p == "Plongeur Bronze"
                ):
                    nb_bronze_jeunes += 1
                    nom_court = lbl.split(" (")[0]
                    if prof > 6:
                        alertes.append(
                            f"⚠️ {nom_court} ({age_p} ans)"
                            " Plongeur Bronze : zone"
                            " 0-6 m en exploration"
                            " (FFESSM)."
                        )
                    # Doit être encadré E1-E4
                    if (
                        ttype == "Exploration autonome"
                        or chef_niv not in
                        ("E1", "E2", "E3", "E4")
                    ):
                        alertes.append(
                            f"⚠️ {nom_court} ({age_p} ans)"
                            " Plongeur Bronze doit être"
                            " encadré par un moniteur"
                            " (E1-E4)."
                        )
            if nb_bronze_jeunes > 2:
                alertes.append(
                    "⚠️ Plongeurs Bronze 8-14 ans :"
                    " 2 maximum par encadrant (FFESSM)."
                )

        # --- Règle D : Argent en exploration 8-14 ans ---
        if ttype in (
            "Exploration encadrée", "Exploration autonome"
        ):
            nb_argent_jeunes = 0
            for lbl in tous_lbls:
                age_p = l2age.get(lbl)
                niv_p = l2niv.get(lbl, "")
                if (
                    age_p is not None and 8 <= age_p <= 14
                    and niv_p == "Plongeur Argent"
                ):
                    nb_argent_jeunes += 1
                    nom_court = lbl.split(" (")[0]
                    if prof > 6:
                        alertes.append(
                            f"⚠️ {nom_court} ({age_p} ans)"
                            " Plongeur Argent : zone"
                            " 0-6 m (FFESSM)."
                        )
            if nb_argent_jeunes > 0:
                max_eff = 3 if has_n1_plus else 2
                if nb_encadres > max_eff:
                    alertes.append(
                        f"⚠️ Plongeur Argent 8-14 ans :"
                        f" {max_eff} plongeurs maximum"
                        + (
                            " (3 si un N1+ présent)"
                            if has_n1_plus
                            else " (2 seuls, 3 si"
                                 " un N1+ présent)"
                        )
                        + " (FFESSM)."
                    )

        # --- Règle E : Or en exploration ---
        if ttype in (
            "Exploration encadrée", "Exploration autonome"
        ):
            nb_or_jeunes = 0
            for lbl in tous_lbls:
                age_p = l2age.get(lbl)
                niv_p = l2niv.get(lbl, "")
                if (
                    age_p is not None
                    and niv_p == "Plongeur Or"
                ):
                    nom_court = lbl.split(" (")[0]
                    if 10 <= age_p < 12:
                        nb_or_jeunes += 1
                        if prof > 12:
                            alertes.append(
                                f"⚠️ {nom_court}"
                                f" ({age_p} ans)"
                                " Plongeur Or : zone"
                                " 0-12 m (FFESSM)."
                            )
                    elif 12 <= age_p < 14:
                        nb_or_jeunes += 1
                        if prof > 20:
                            alertes.append(
                                f"⚠️ {nom_court}"
                                f" ({age_p} ans)"
                                " Plongeur Or : zone"
                                " 0-20 m (FFESSM)."
                            )
            if nb_or_jeunes > 0:
                max_eff = 3 if has_n1_plus else 2
                if nb_encadres > max_eff:
                    alertes.append(
                        f"⚠️ Plongeur Or 10-14 ans :"
                        f" {max_eff} plongeurs maximum"
                        + (
                            " (3 si un N1+ présent)"
                            if has_n1_plus
                            else " (2 seuls, 3 si"
                                 " un N1+ présent)"
                        )
                        + " (FFESSM)."
                    )

        # --- Règle F : PA40 < 17 ans en autonome ---
        if ttype == "Exploration autonome":
            for lbl in tous_lbls:
                age_p = l2age.get(lbl)
                niv_p = l2niv.get(lbl, "")
                if (
                    age_p is not None and age_p < 17
                    and niv_p == "PA40"
                ):
                    nom_court = lbl.split(" (")[0]
                    alertes.append(
                        f"⚠️ {nom_court} ({age_p} ans)"
                        " PA40 : pas de prérogative"
                        " d'autonomie avant 17 ans"
                        " (Code du sport)."
                    )

        alertes = list(dict.fromkeys(alertes))

        # Closure : écriture effective en base
        def _finaliser():
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()

            if state["t4_edit_id"]:
                c.execute(
                    "UPDATE palanquees_sortie SET type=?,"
                    " prof_max=?, duree_max=?, dtr_max=?"
                    " WHERE id=?",
                    (ttype, prof, duree, dtr,
                     state["t4_edit_id"])
                )
                c.execute(
                    "DELETE FROM palanquee_membres"
                    " WHERE palanquee_id=?",
                    (state["t4_edit_id"],)
                )
                pal_id = state["t4_edit_id"]
            else:
                ordre = (conn.execute(
                    "SELECT COALESCE(MAX(ordre), 0) FROM"
                    " palanquees_sortie WHERE sortie_id=?"
                    " AND date_jour=? AND num_plongee=?",
                    (state["sortie_id"], dj, num)
                ).fetchone()[0] or 0) + 1
                c.execute(
                    "INSERT INTO palanquees_sortie"
                    "(sortie_id, date_jour, num_plongee,"
                    " ordre, type, prof_max, duree_max,"
                    " dtr_max)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        state["sortie_id"], dj, num,
                        ordre, ttype, prof, duree, dtr
                    )
                )
                pal_id = c.lastrowid

            l2id = t4_state["label_to_id"]

            if chef_lbl:
                c.execute(
                    "INSERT INTO palanquee_membres"
                    "(palanquee_id, participant_id, role,"
                    " gaz, aptitude)"
                    " VALUES (?, ?, 'chef', ?, ?)",
                    (pal_id, l2id[chef_lbl],
                     t4_get_gaz(chef_lbl),
                     t4_get_apt(chef_lbl))
                )

            if sf_lbl:
                c.execute(
                    "INSERT INTO palanquee_membres"
                    "(palanquee_id, participant_id, role,"
                    " gaz, aptitude)"
                    " VALUES (?, ?, 'serre_file', ?, ?)",
                    (pal_id, l2id[sf_lbl],
                     t4_get_gaz(sf_lbl),
                     t4_get_apt(sf_lbl))
                )

            for m in mem_lbls:
                c.execute(
                    "INSERT INTO palanquee_membres"
                    "(palanquee_id, participant_id, role,"
                    " gaz, aptitude)"
                    " VALUES (?, ?, 'membre', ?, ?)",
                    (pal_id, l2id[m], t4_get_gaz(m),
                     t4_get_apt(m))
                )

            conn.commit()
            conn.close()

            show_message("Palanquée enregistrée.")

            t4_reset_form()
            t4_refresh_palanquees_display()
            t4_refresh_membres()

        # Pas d'alerte → enregistrement direct
        if not alertes:
            _finaliser()
            return

        # Alertes → dialogue de confirmation
        def confirmer(ev):
            close_dialog(alerte_dlg)
            _finaliser()

        alerte_dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(
                "⚠️ Alertes réglementaires",
                weight=ft.FontWeight.BOLD
            ),
            content=ft.Container(
                width=_w(440),
                content=ft.Column(
                    tight=True,
                    spacing=10,
                    scroll=ft.ScrollMode.AUTO,
                    controls=[
                        ft.Text(a, size=13)
                        for a in alertes
                    ] + [
                        ft.Text(
                            "Enregistrer quand même ?",
                            weight=ft.FontWeight.BOLD,
                            size=13
                        )
                    ]
                )
            ),
            actions=[
                ft.TextButton(
                    "Annuler",
                    on_click=lambda ev:
                        close_dialog(alerte_dlg)
                ),
                ft.FilledButton(
                    "Enregistrer quand même",
                    bgcolor="#f59e0b", color="white",
                    on_click=confirmer
                ),
            ]
        )
        page.show_dialog(alerte_dlg)

    t4_save_btn.on_click = t4_save_palanquee

    def t4_refresh_palanquees_display():

        t4_palanquees_column.controls.clear()

        if state["t4_current"] is None:
            page.update()
            return

        dj, num = state["t4_current"]

        conn = sqlite3.connect(DB_PATH)

        pals = conn.execute(
            "SELECT id, type, prof_max, duree_max, ordre,"
            " dtr_max"
            " FROM palanquees_sortie WHERE sortie_id=?"
            " AND date_jour=? AND num_plongee=?"
            " ORDER BY ordre",
            (state["sortie_id"], dj, num)
        ).fetchall()

        COULEURS = {
            "Exploration encadrée": ("#dbeafe", "#3b82f6"),
            "Exploration autonome": ("#dcfce7", "#10b981"),
            "Technique": ("#ede9fe", "#7c3aed"),
            "Baptême": ("#fce7f3", "#ec4899"),
        }

        for i, p in enumerate(pals, 1):

            bg, hdr = COULEURS.get(
                p[1], ("#f1f5f9", "#64748b")
            )

            membres = conn.execute(
                "SELECT pm.role, pa.nom, pa.prenom,"
                " pa.niveau, pm.gaz, pm.aptitude,"
                " pc.brevet_nitrox, pc.date_naissance"
                " FROM palanquee_membres pm"
                " JOIN participants pa"
                " ON pa.id = pm.participant_id"
                " LEFT JOIN plongeurs_club pc"
                " ON UPPER(pc.nom)=UPPER(pa.nom)"
                " AND UPPER(pc.prenom)=UPPER(pa.prenom)"
                " WHERE pm.palanquee_id=?"
                " ORDER BY CASE pm.role"
                " WHEN 'chef' THEN 0"
                " WHEN 'serre_file' THEN 1 ELSE 2 END",
                (p[0],)
            ).fetchall()

            membre_texts = []

            for m in membres:

                icone = {
                    "chef": "🚩",
                    "serre_file": "🔚",
                    "membre": "•"
                }.get(m[0], "•")

                # Fonction / aptitude
                if m[0] == "chef":
                    fct = " [ENC]"
                elif m[0] == "serre_file":
                    fct = " [SF]"
                elif m[5]:
                    fct = f" [{m[5]}]"
                else:
                    fct = ""

                niv_aff = fmt_niveau(
                    m[3] or "—",
                    m[6] if len(m) > 6 else ""
                )

                est_chef_sf = m[0] in ("chef", "serre_file")

                age = calc_age(
                    m[7] if len(m) > 7 else ""
                )

                ligne_controls = [
                    ft.Text(
                        f"{icone} {m[1]} {m[2]}",
                        size=11,
                        weight=(
                            ft.FontWeight.BOLD
                            if est_chef_sf
                            else ft.FontWeight.NORMAL
                        )
                    )
                ]

                if age is not None and age < 18:
                    ligne_controls.append(
                        ft.Text(
                            f"{age} ans",
                            size=11,
                            weight=ft.FontWeight.BOLD,
                            color="#dc2626"
                        )
                    )

                ligne_controls.append(
                    ft.Text(
                        f"({niv_aff}){fct}"
                        f" — {m[4] or 'Air'}",
                        size=11,
                        weight=(
                            ft.FontWeight.BOLD
                            if est_chef_sf
                            else ft.FontWeight.NORMAL
                        )
                    )
                )

                membre_texts.append(
                    ft.Row(
                        ligne_controls,
                        spacing=5,
                        wrap=True
                    )
                )

            def make_edit(pid=p[0]):
                return lambda e: t4_edit_palanquee(pid)

            def make_del(pid=p[0]):
                return lambda e: t4_delete_palanquee(pid)

            card = ft.Container(

                bgcolor=bg,

                border_radius=6,

                content=ft.Column(

                    spacing=4,

                    controls=[

                        ft.Container(

                            bgcolor=hdr,

                            padding=6,

                            content=ft.Text(
                                f"P{i} — {p[1]}"
                                f"  ⬇ {p[2] or 0:g} m"
                                f"  ⏱ {p[3] or 0} min"
                                + (
                                    f"  ⬆ DTR {p[5]} min"
                                    if p[5] is not None
                                    else ""
                                ),
                                color="white",
                                weight=ft.FontWeight.BOLD,
                                size=12
                            )
                        ),

                        ft.Container(
                            padding=8,
                            content=ft.Column(
                                membre_texts,
                                spacing=2
                            )
                        ),

                        ft.Row([

                            ft.TextButton(
                                "✏️ Modifier",
                                on_click=make_edit()
                            ),

                            ft.TextButton(
                                "🗑️ Supprimer",
                                on_click=make_del()
                            ),
                        ])
                    ]
                )
            )

            t4_palanquees_column.controls.append(card)

        conn.close()

        page.update()

    def t4_edit_palanquee(pal_id):

        state["t4_edit_id"] = pal_id

        conn = sqlite3.connect(DB_PATH)

        row = conn.execute(
            "SELECT type, prof_max, duree_max, dtr_max"
            " FROM palanquees_sortie WHERE id=?",
            (pal_id,)
        ).fetchone()

        if not row:
            conn.close()
            return

        t4_type_radio.value = row[0] or "Exploration encadrée"
        t4_prof_field.value = str(row[1] or 0)
        t4_duree_field.value = str(row[2] or 0)
        t4_dtr_field.value = (
            str(row[3]) if row[3] is not None else ""
        )

        membres = conn.execute(
            "SELECT participant_id, role, gaz, aptitude"
            " FROM palanquee_membres WHERE palanquee_id=?",
            (pal_id,)
        ).fetchall()

        conn.close()

        t4_on_type_changed(None)
        t4_refresh_membres()

        id_to_label = {
            v: k
            for k, v in t4_state["label_to_id"].items()
        }

        for pid, role, gaz, apt in membres:

            lbl = id_to_label.get(pid)

            if not lbl:
                continue

            if role == "chef":
                t4_chef_combo.value = lbl
            elif role == "serre_file":
                t4_sf_combo.value = lbl

        t4_maj_chef_btn()
        t4_maj_sf_btn()

        t4_refresh_membres()

        # Re-cocher les membres
        for pid, role, gaz, apt in membres:

            if role == "membre":

                lbl = id_to_label.get(pid)

                if lbl in t4_state["membre_checks"]:
                    t4_state["membre_checks"][lbl].value = True

        t4_refresh_apercu()

        # Restaurer les gaz
        for pid, role, gaz, apt in membres:

            lbl = id_to_label.get(pid)

            if not lbl or lbl not in t4_state["gas"]:
                continue

            w = t4_state["gas"][lbl]

            if gaz and gaz.startswith("Nx"):
                w["gaz"].value = "Nitrox"
                try:
                    w["pct"].value = int(gaz[2:])
                except Exception:
                    pass
                w["pct"].visible = True
            else:
                w["gaz"].value = "Air"

            # Restaurer l'aptitude
            try:
                if w.get("aptitude") is not None and apt:
                    w["aptitude"].value = apt
            except Exception:
                pass

        t4_save_btn.content = ft.Text(
            "🔄 Mettre à jour palanquée",
            color="white"
        )

        # Rebuild pour afficher les bons libellés gaz
        # et aptitudes restaurés
        t4_refresh_apercu()

        page.update()

    def t4_delete_palanquee(pal_id):

        conn = sqlite3.connect(DB_PATH)

        conn.execute(
            "DELETE FROM palanquees_sortie WHERE id=?",
            (pal_id,)
        )

        conn.execute(
            "DELETE FROM palanquee_membres"
            " WHERE palanquee_id=?",
            (pal_id,)
        )

        conn.commit()
        conn.close()

        if state["t4_edit_id"] == pal_id:
            t4_reset_form()

        t4_refresh_palanquees_display()
        t4_refresh_membres()

    def t4_show_synthese():

        if not t4_state["dispo"]:
            show_message("Aucun plongeur sur cette plongée.")
            return

        dj, num = state["t4_current"]

        conn = sqlite3.connect(DB_PATH)
        affectes = set()
        for (pid,) in conn.execute(
            "SELECT pm.participant_id"
            " FROM palanquee_membres pm"
            " JOIN palanquees_sortie ps"
            " ON ps.id = pm.palanquee_id"
            " WHERE ps.sortie_id=? AND ps.date_jour=?"
            " AND ps.num_plongee=?",
            (state["sortie_id"], dj, num)
        ).fetchall():
            affectes.add(pid)

        prepa_map = {}
        for r in conn.execute(
            "SELECT id, niveau_prepa FROM participants"
            " WHERE sortie_id=?",
            (state["sortie_id"],)
        ).fetchall():
            prepa_map[r[0]] = (r[1] or "").strip()
        conn.close()

        ENCADRANTS_LVL = ["E4", "E3", "E2", "E1", "GP"]
        A_ENCADRER_LVL = [
            "Plongeur Or", "Plongeur Argent",
            "Plongeur Bronze", "PE12", "PE20",
            "Niveau 1", "PE40"
        ]

        enc_total = {n: 0 for n in ENCADRANTS_LVL}
        enc_rest = {n: 0 for n in ENCADRANTS_LVL}
        form_total = {}
        form_rest = {}
        ae_total = {n: 0 for n in A_ENCADRER_LVL}
        ae_rest = {n: 0 for n in A_ENCADRER_LVL}
        auto_total = 0
        auto_rest = 0

        for r in t4_state["dispo"]:
            pid = r[0]
            niv = (r[3] or "").strip()
            prepa = prepa_map.get(pid, "")
            occ = pid in affectes

            if prepa:
                form_total[prepa] = \
                    form_total.get(prepa, 0) + 1
                if not occ:
                    form_rest[prepa] = \
                        form_rest.get(prepa, 0) + 1
            elif niv in enc_total:
                enc_total[niv] += 1
                if not occ:
                    enc_rest[niv] += 1
            elif niv in ae_total:
                ae_total[niv] += 1
                if not occ:
                    ae_rest[niv] += 1
            else:
                auto_total += 1
                if not occ:
                    auto_rest += 1

        def cell(txt, w, bold=False, bg=None,
                 color="#1e293b", align="center"):
            return ft.Container(
                ft.Text(
                    txt, size=11,
                    weight=(
                        ft.FontWeight.BOLD if bold
                        else ft.FontWeight.NORMAL
                    ),
                    color=color,
                    text_align=(
                        ft.TextAlign.CENTER
                        if align == "center"
                        else ft.TextAlign.LEFT
                    )
                ),
                width=w, padding=5, bgcolor=bg,
                alignment=(
                    ft.Alignment.CENTER
                    if align == "center"
                    else ft.Alignment.CENTER_LEFT
                )
            )

        def make_table(titre, hdr_color, keys,
                       dtotal, drest, label_col="Niveau"):

            tot_sum = sum(dtotal.get(k, 0) for k in keys)
            rest_sum = sum(drest.get(k, 0) for k in keys)

            shown = [
                k for k in keys if dtotal.get(k, 0) > 0
            ]

            table_rows = [
                ft.Row([
                    cell(label_col, 100, bold=True,
                         bg=hdr_color, color="white",
                         align="left"),
                    cell("Inscrits", 70, bold=True,
                         bg=hdr_color, color="white"),
                    cell("Restants", 70, bold=True,
                         bg=hdr_color, color="white"),
                ], spacing=1)
            ]

            if not shown:
                table_rows.append(
                    ft.Row([
                        cell("(aucun)", 240,
                             color="#94a3b8",
                             align="left")
                    ], spacing=1)
                )
            else:
                for i, k in enumerate(shown):
                    bg = "#f8fafc" if i % 2 else "white"
                    tv = dtotal.get(k, 0)
                    rv = drest.get(k, 0)
                    table_rows.append(
                        ft.Row([
                            cell(fmt_niveau(k, ""), 100,
                                 bg=bg,
                                 align="left"),
                            cell(str(tv), 70, bold=True,
                                 bg=bg),
                            cell(
                                str(rv), 70, bold=True,
                                bg=bg,
                                color=(
                                    "#10b981" if rv == 0
                                    else "#ef4444"
                                )
                            ),
                        ], spacing=1)
                    )

            # Ligne total
            table_rows.append(
                ft.Row([
                    cell("Total", 100, bold=True,
                         bg="#dbeafe", color="#1e3a5f",
                         align="left"),
                    cell(str(tot_sum), 70, bold=True,
                         bg="#dbeafe", color="#1e3a5f"),
                    cell(str(rest_sum), 70, bold=True,
                         bg="#dbeafe", color="#1e3a5f"),
                ], spacing=1)
            )

            return ft.Container(
                margin=ft.Margin(
                    left=0, right=0, top=4, bottom=4
                ),
                content=ft.Column([
                    ft.Text(
                        f"{titre}  ({rest_sum} / {tot_sum})",
                        weight=ft.FontWeight.BOLD,
                        size=12
                    ),
                    ft.Column(table_rows, spacing=1),
                ], tight=True, spacing=4)
            )

        keys_form = sorted(
            form_total.keys(),
            key=lambda k: (
                TOUS_NIVEAUX.index(k)
                if k in TOUS_NIVEAUX else 99
            )
        )

        total_n = len(t4_state["dispo"])
        rest_n = sum(
            1 for r in t4_state["dispo"]
            if r[0] not in affectes
        )

        blocs = ft.Column(
            [
                ft.Text(
                    f"{total_n} plongeur(s) inscrit(s),"
                    f" {rest_n} restant(s) à affecter",
                    italic=True, size=11,
                    color="#64748b"
                ),
                make_table(
                    "🎓 Encadrants", "#1e3a5f",
                    ENCADRANTS_LVL, enc_total, enc_rest
                ),
                make_table(
                    "📚 Plongeurs en formation",
                    "#b45309", keys_form,
                    form_total, form_rest,
                    label_col="Niveau préparé"
                ),
                make_table(
                    "🤿 Plongeurs à encadrer",
                    "#be185d", A_ENCADRER_LVL,
                    ae_total, ae_rest
                ),
                make_table(
                    "💪 Plongeurs autonomes",
                    "#166534", ["Autonomes"],
                    {"Autonomes": auto_total},
                    {"Autonomes": auto_rest},
                    label_col="Catégorie"
                ),
            ],
            tight=True,
            spacing=6,
            scroll=ft.ScrollMode.AUTO
        )

        synth = ft.AlertDialog(
            modal=True,
            title=ft.Text(
                f"📊 Synthèse — {dj} Plongée {num}",
                weight=ft.FontWeight.BOLD
            ),
            content=ft.Container(
                width=_w(420),
                height=560,
                content=blocs
            ),
            actions=[
                ft.TextButton(
                    "Fermer",
                    on_click=lambda e: close_dialog(synth)
                )
            ]
        )

        page.show_dialog(synth)

    # =================================================
    # MENU LATÉRAL (mobile : menu sous forme de dialogue)
    # Le NavigationDrawer natif de Flet 0.85 reste bloqué
    # ouvert ; on utilise un AlertDialog qui se ferme de
    # façon fiable via pop_dialog().
    # =================================================

    def _menu_action(idx):
        if idx == 0:
            nouvelle_sortie(None)
        elif idx == 1:
            enregistrer_sortie(None)
        elif idx == 2:
            ouvrir_sortie(None)
        elif idx == 3:
            supprimer_sortie(None)
        elif idx == 4:
            page.run_task(import_excel, None)
        elif idx == 5:
            open_parametres()

    def open_drawer(e):

        items = [
            (0, ft.Icons.ADD, "Nouvelle sortie"),
            (1, ft.Icons.SAVE, "Enregistrer la sortie"),
            (2, ft.Icons.FOLDER_OPEN, "Ouvrir une sortie"),
            (3, ft.Icons.DELETE, "Supprimer la sortie"),
            (4, ft.Icons.UPLOAD_FILE, "Import FFESSM"),
            (5, ft.Icons.SETTINGS, "Paramètres"),
        ]

        def make_handler(i):
            def h(ev):
                # Fermer le menu PUIS lancer l'action
                try:
                    page.pop_dialog()
                except Exception:
                    pass
                _menu_action(i)
            return h

        tiles = [
            ft.Container(
                padding=ft.Padding(
                    left=8, right=8, top=4, bottom=4
                ),
                content=ft.Text(
                    f"🤿 Sorties plongée  v{APP_VERSION}",
                    weight=ft.FontWeight.BOLD,
                    size=14,
                    color="#1e3a5f"
                )
            ),
            ft.Divider(),
        ]

        for idx, icon, label in items:
            tiles.append(
                ft.ListTile(
                    leading=ft.Icon(icon),
                    title=ft.Text(label),
                    on_click=make_handler(idx)
                )
            )

        menu_dlg = ft.AlertDialog(
            modal=False,
            content=ft.Container(
                width=_w(300),
                content=ft.Column(
                    tiles,
                    tight=True,
                    spacing=2,
                    scroll=ft.ScrollMode.AUTO
                )
            ),
        )

        page.show_dialog(menu_dlg)

    # =================================================
    # ONGLET 1
    # =================================================

    tab1 = ft.Container(

        expand=True,

        padding=10,

        content=ft.Column(

            scroll=ft.ScrollMode.AUTO,

            spacing=10,

            controls=[

                ft.Text(
                    "🧾 Paramètres de la sortie",
                    weight=ft.FontWeight.BOLD,
                    size=15
                ),

                # Champs empilés verticalement (mobile)
                sortie_nom,
                sortie_lieu,
                date_debut_row,
                date_fin_row,

                ft.FilledButton(
                    "📅 Générer les jours",
                    height=TOUCH_H,
                    bgcolor="#3b82f6",
                    color="white",
                    on_click=generate_days
                ),

                ft.Divider(),

                jours_column,

                ft.Divider(),

                ft.FilledButton(
                    "💾 Enregistrer la sortie",
                    height=TOUCH_H,
                    bgcolor="#10b981",
                    color="white",
                    on_click=enregistrer_sortie
                ),
            ]
        )
    )

    # =================================================
    # ONGLET 2 — PARTICIPANTS
    # =================================================

    tab2 = ft.Container(

        expand=True,

        padding=15,

        content=ft.Column(

            scroll=ft.ScrollMode.AUTO,

            expand=True,

            controls=[

                # Section haute : ajout participants
                ft.Container(

                    border=ft.Border.all(
                        1,
                        "#cbd5e1"
                    ),

                    border_radius=6,

                    padding=12,

                    content=ft.Column(

                        spacing=8,

                        controls=[

                            ft.Text(

                                " 👥 Ajouter des participants",

                                weight=ft.FontWeight.BOLD,

                                size=13
                            ),

                            ft.Text(

                                "Sélectionner depuis la base"
                                " club :",

                                weight=ft.FontWeight.BOLD,

                                size=11
                            ),

                            ft.Container(

                                border=ft.Border.all(
                                    1,
                                    "#cbd5e1"
                                ),

                                border_radius=4,

                                content=plongeurs_list_view
                            ),

                            ft.Row(

                                wrap=True,

                                controls=[

                                    ft.FilledButton(

                                        "➕ Ajouter les"
                                        " plongeurs"
                                        " sélectionnés",

                                        bgcolor="#3b82f6",

                                        color="white",

                                        on_click=add_plongeurs_selected
                                    ),

                                    ft.FilledButton(

                                        "🤿 Ajouter un plongeur"
                                        " hors club",

                                        bgcolor="#0ea5e9",

                                        color="white",

                                        on_click=add_plongeur_manual
                                    ),
                                ]
                            ),
                        ]
                    )
                ),

                # Section basse : tableau participants
                ft.Container(

                    border=ft.Border.all(
                        1,
                        "#cbd5e1"
                    ),

                    border_radius=6,

                    padding=12,

                    expand=True,

                    content=ft.Column(

                        spacing=6,

                        expand=True,

                        controls=[

                            ft.Row([

                                ft.Text(

                                    " 📋 Participants de la sortie",

                                    weight=ft.FontWeight.BOLD,

                                    size=13
                                ),

                                t2_lock_btn,
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN),

                            ft.Row(

                                expand=True,

                                scroll=ft.ScrollMode.AUTO,

                                vertical_alignment=ft.CrossAxisAlignment.START,

                                controls=[

                                    ft.Column(

                                        expand=True,

                                        spacing=6,

                                        controls=[

                                            participants_header,

                                            ft.Container(

                                                content=participants_rows_column,

                                                expand=True
                                            ),
                                        ]
                                    )
                                ]
                            ),

                            stats_part_btn,
                        ]
                    )
                ),
            ]
        )
    )

    # =================================================
    # ONGLET 3 — INSCRIPTIONS
    # =================================================

    tab3 = ft.Container(

        expand=True,

        padding=15,

        content=ft.Column(

            expand=True,

            controls=[

                ft.Row(

                    alignment=ft.MainAxisAlignment.END,

                    wrap=True,

                    controls=[

                        ft.Row([
                            t3_save_btn,
                            t3_export_btn,
                            t3_lock_btn,
                        ]),
                    ]
                ),

                ft.Divider(),

                ft.Container(

                    expand=True,

                    content=ft.Row(

                        expand=True,

                        scroll=ft.ScrollMode.AUTO,

                        vertical_alignment=ft.CrossAxisAlignment.START,

                        controls=[
                            tab3_grid_column
                        ]
                    )
                ),

                tab3_stats_lbl,
            ]
        )
    )

    # =================================================
    # ONGLET 4 — PALANQUÉES
    # =================================================

    tab4 = ft.Container(

        expand=True,

        padding=15,

        content=ft.Column(

            expand=True,

            controls=[

                ft.Column([

                    ft.Text(
                        "Plongée :",
                        weight=ft.FontWeight.BOLD
                    ),

                    t4_plongee_btn,

                    t4_info_btn,
                ], tight=True, spacing=6),

                ft.Divider(),

                ft.ResponsiveRow(

                    expand=True,

                    vertical_alignment=ft.CrossAxisAlignment.START,

                    controls=[

                        # Colonne gauche : formulaire
                        ft.Container(

                            col={"xs": 12, "md": 6},

                            border=ft.Border.all(1, "#cbd5e1"),

                            border_radius=6,

                            padding=12,

                            content=ft.Column(

                                scroll=ft.ScrollMode.AUTO,

                                spacing=8,

                                controls=[

                                    ft.Text(
                                        "📝 Constitution de la"
                                        " palanquée",
                                        weight=ft.FontWeight.BOLD
                                    ),

                                    ft.Text(
                                        "Type :",
                                        weight=ft.FontWeight.BOLD
                                    ),
                                    t4_type_radio,

                                    t4_chef_btn,

                                    t4_sf_btn,

                                    ft.Text(
                                        "Membres :",
                                        weight=ft.FontWeight.BOLD
                                    ),

                                    ft.Container(
                                        border=ft.Border.all(
                                            1, "#cbd5e1"
                                        ),
                                        border_radius=4,
                                        padding=6,
                                        content=t4_membres_column
                                    ),

                                    ft.Row([
                                        t4_prof_field,
                                        t4_duree_field,
                                        t4_dtr_field,
                                    ], wrap=True),

                                    ft.Row([
                                        t4_save_btn,
                                        ft.OutlinedButton(
                                            "Annuler",
                                            on_click=lambda e:
                                                t4_reset_form()
                                        ),
                                    ], wrap=True),
                                    

                                    ft.Container(
                                        bgcolor="#f8fafc",
                                        border_radius=6,
                                        padding=8,
                                        content=ft.Column([
                                            ft.Text(
                                                "👁 Aperçu"
                                                " palanquée",
                                                weight=ft.FontWeight.BOLD,
                                                size=12
                                            ),
                                            t4_apercu_column,
                                        ], tight=True)
                                    ),
                                ]
                            )
                        ),

                        # Colonne droite : palanquées existantes
                        ft.Container(

                            col={"xs": 12, "md": 6},

                            border=ft.Border.all(1, "#cbd5e1"),

                            border_radius=6,

                            padding=12,

                            content=ft.Column(

                                expand=True,

                                controls=[

                                    ft.Text(
                                        "🤿 Palanquées de la"
                                        " plongée",
                                        weight=ft.FontWeight.BOLD
                                    ),

                                    ft.Divider(),

                                    t4_palanquees_column,
                                ]
                            )
                        ),
                    ]
                ),
            ]
        )
    )

    # =================================================
    # ONGLET 5 — FICHES DE SÉCURITÉ
    # =================================================

    t5_rows = {}   # (date, num) -> {"check":..., "heure":..., "dp":...}

    t5_grid = ft.Column(spacing=2, scroll=ft.ScrollMode.AUTO, expand=True)

    t5_stats = ft.Text("", size=11, italic=True, color="#64748b")

    t5_dp_unique_field = ft.TextField(
        label="DP unique",
        width=240,
        dense=True
    )

    def t5_load_fiches():
        """Charge heure/DP enregistrés pour la sortie."""
        result = {}
        if state["sortie_id"] is None:
            return result
        conn = sqlite3.connect(DB_PATH)
        for dj, num, heure, dp in conn.execute(
            "SELECT date_jour, num_plongee, heure, dp"
            " FROM fiches_securite WHERE sortie_id=?",
            (state["sortie_id"],)
        ).fetchall():
            result[(dj, num)] = {"heure": heure or "", "dp": dp or ""}
        conn.close()
        return result

    def t5_count_palanquees(dj, num):
        """Retourne (nb_palanquees, nb_plongeurs)."""
        if state["sortie_id"] is None:
            return 0, 0
        conn = sqlite3.connect(DB_PATH)
        pals = conn.execute(
            "SELECT id FROM palanquees_sortie"
            " WHERE sortie_id=? AND date_jour=?"
            " AND num_plongee=?",
            (state["sortie_id"], dj, num)
        ).fetchall()
        nb_pal = len(pals)
        nb_pl = 0
        for (pid,) in pals:
            nb_pl += conn.execute(
                "SELECT COUNT(*) FROM palanquee_membres"
                " WHERE palanquee_id=?",
                (pid,)
            ).fetchone()[0]
        conn.close()
        return nb_pal, nb_pl

    def open_time_picker(champ):
        """Ouvre un sélecteur d'heure et remplit le champ
        au format HH:MM."""

        # Heure initiale depuis le champ si valide
        init = None
        try:
            if champ.value and ":" in champ.value:
                hh, mm = champ.value.strip().split(":")
                init = time(int(hh), int(mm))
        except Exception:
            init = None

        def on_pick(e):
            t = e.control.value
            if t is not None:
                champ.value = f"{t.hour:02d}:{t.minute:02d}"
                champ.update()

        tp = ft.TimePicker(
            value=init,
            on_change=on_pick,
        )
        page.show_dialog(tp)

    def refresh_tab5():

        t5_grid.controls.clear()
        t5_rows.clear()

        if state["sortie_id"] is None:
            t5_grid.controls.append(
                ft.Text(
                    "Enregistrez d'abord la sortie.",
                    italic=True, color="#94a3b8"
                )
            )
            t5_stats.value = ""
            page.update()
            return

        saved = t5_load_fiches()

        # En-tête
        t5_grid.controls.append(
            ft.Row([
                ft.Container(
                    ft.IconButton(
                        icon=ft.Icons.CHECKLIST,
                        icon_size=18,
                        icon_color="white",
                        tooltip="Tout cocher / décocher",
                        on_click=lambda e: t5_toggle_smart()
                    ),
                    width=40, padding=0, bgcolor="#1e3a5f",
                    alignment=ft.Alignment.CENTER
                ),
                ft.Container(
                    ft.Text("Plongée", weight=ft.FontWeight.BOLD,
                            size=11, color="white"),
                    width=200, padding=4, bgcolor="#1e3a5f"
                ),
                ft.Container(
                    ft.Text("Heure", weight=ft.FontWeight.BOLD,
                            size=11, color="white"),
                    width=110, padding=4, bgcolor="#1e3a5f"
                ),
                ft.Container(
                    ft.Text("DP", weight=ft.FontWeight.BOLD,
                            size=11, color="white"),
                    width=200, padding=4, bgcolor="#1e3a5f"
                ),
                ft.Container(
                    ft.Text("Pal.", weight=ft.FontWeight.BOLD,
                            size=11, color="white"),
                    width=60, padding=4, bgcolor="#1e3a5f"
                ),
                ft.Container(
                    ft.Text("Pl.", weight=ft.FontWeight.BOLD,
                            size=11, color="white"),
                    width=60, padding=4, bgcolor="#1e3a5f"
                ),
            ], spacing=2)
        )

        plongees = get_plongees_list()

        nb_total_pal = 0

        for dj, num in plongees:

            nb_pal, nb_pl = t5_count_palanquees(dj, num)
            nb_total_pal += nb_pal

            sv = saved.get((dj, num), {})

            chk = ft.Checkbox(value=nb_pal > 0)

            heure_f = ft.TextField(
                value=sv.get("heure", ""),
                hint_text="HH:MM",
                width=72, dense=True, text_size=11
            )

            heure_btn = ft.IconButton(
                icon=ft.Icons.SCHEDULE,
                icon_size=18,
                tooltip="Choisir l'heure",
                on_click=lambda e, hf=heure_f:
                    open_time_picker(hf)
            )

            dp_f = ft.TextField(
                value=sv.get("dp", ""),
                width=190, dense=True, text_size=11
            )

            t5_rows[(dj, num)] = {
                "check": chk,
                "heure": heure_f,
                "dp": dp_f,
            }

            t5_grid.controls.append(
                ft.Row([
                    ft.Container(chk, width=40, padding=2),
                    ft.Container(
                        ft.Text(
                            f"{jour_fr(dj)} {dj} — "
                            f"Plongée {num}",
                            size=11
                        ),
                        width=200, padding=4
                    ),
                    ft.Container(
                        ft.Row(
                            [heure_f, heure_btn],
                            spacing=0,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER
                        ),
                        width=120, padding=2
                    ),
                    ft.Container(dp_f, width=200, padding=2),
                    ft.Container(
                        ft.Text(str(nb_pal), size=11),
                        width=60, padding=4
                    ),
                    ft.Container(
                        ft.Text(str(nb_pl), size=11),
                        width=60, padding=4
                    ),
                ], spacing=2)
            )

        t5_stats.value = (
            f"{len(plongees)} plongée(s), "
            f"{nb_total_pal} palanquée(s) au total."
        )

        page.update()

    def t5_toggle_all(val):
        for r in t5_rows.values():
            r["check"].value = val
        page.update()

    def t5_toggle_smart():
        # Si tout est coché → décocher, sinon cocher tout
        if not t5_rows:
            return
        tout = all(
            r["check"].value for r in t5_rows.values()
        )
        t5_toggle_all(not tout)

    def t5_apply_dp_unique(e):
        dp = (t5_dp_unique_field.value or "").strip()
        if not dp:
            show_message("Saisir un nom de DP.")
            return
        for r in t5_rows.values():
            r["dp"].value = dp
        page.update()
        show_message("DP appliqué à toutes les plongées.")

    def t5_save_heures_dp(e=None, silent=False):
        if state["sortie_id"] is None:
            return
        conn = sqlite3.connect(DB_PATH)
        sid = state["sortie_id"]
        conn.execute(
            "DELETE FROM fiches_securite WHERE sortie_id=?",
            (sid,)
        )
        for (dj, num), r in t5_rows.items():
            conn.execute(
                "INSERT INTO fiches_securite"
                "(sortie_id, date_jour, num_plongee,"
                " heure, dp) VALUES (?, ?, ?, ?, ?)",
                (
                    sid, dj, num,
                    (r["heure"].value or "").strip(),
                    (r["dp"].value or "").strip()
                )
            )
        conn.commit()
        conn.close()
        if not silent:
            show_message("Heures et DP enregistrés.")

    def t5_render_paysage(pdf, conn, pals, page_w):
        """Rendu paysage : 3 palanquées par ligne, chacune
        en bloc vertical compact."""

        n_cols = 3
        gap = 5
        col_w = (page_w - gap * (n_cols - 1)) / n_cols
        x0 = pdf.l_margin

        pdf.set_y(pdf.get_y() + 4)

        i = 0
        while i < len(pals):

            ligne = pals[i:i + n_cols]

            # Pré-charger membres + calculer la hauteur max
            blocs = []
            h_max = 0

            for p in ligne:
                membres = t5_get_membres(conn, p[0])
                # hauteur : titre(6)+params(5)+entete(5)
                # +membres(5*n)+realises(5)
                h = 6 + 5 + 5 + 5 * len(membres) + 5
                blocs.append((p, membres, h))
                h_max = max(h_max, h)

            # Saut de page si besoin
            espace = pdf.h - pdf.b_margin - pdf.get_y()
            if h_max + 6 > espace:
                pdf.add_page()
                pdf.set_y(pdf.get_y() + 4)

            y_start = pdf.get_y()

            for j, (p, membres, h) in enumerate(blocs):

                x = x0 + j * (col_w + gap)
                pdf.set_xy(x, y_start)

                ptype = p[1] or ""
                dtr = p[5]
                ordre = p[4]
                is_tech = (ptype == "Technique")

                # Titre
                pdf.set_fill_color(200, 220, 255)
                pdf.set_font("Helvetica", 'B', 8)
                pdf.cell(
                    col_w, 6,
                    clean_txt(f" Palanquée {ordre} - {ptype}"),
                    border=1, fill=True,
                    new_x=XPos.LEFT, new_y=YPos.NEXT
                )

                # Largeurs des colonnes membres (calculées
                # avant pour aligner les lignes params)
                if is_tech:
                    wa = col_w * 0.11
                    wn = col_w * 0.48
                    wb = col_w * 0.16
                    wf = col_w * 0.16
                    wg = col_w * 0.09
                else:
                    wa = col_w * 0.11
                    wn = col_w * 0.52
                    wb = col_w * 0.28
                    wg = col_w * 0.09

                # Params prévus : label "Max prévus" à
                # gauche (largeur wa) + 3 sous-colonnes
                pdf.set_x(x)
                pdf.set_font("Helvetica", 'B', 5)
                pdf.set_fill_color(240, 240, 240)
                dtr_p = (
                    f"{dtr}" if dtr is not None else "-"
                )
                reste = col_w - wa
                w9 = reste / 9
                pdf.cell(
                    wa, 5, "Max\nprév.",
                    border=1, fill=True
                )
                pdf.set_font("Helvetica", '', 6)
                pdf.cell(
                    2*w9, 5,
                    clean_txt(f" Prof. : {p[2] or 0:g}m"),
                    border=1, fill=True
                )
                pdf.cell(
                    2*w9, 5,
                    clean_txt(f" Durée : {p[3] or 0}min"),
                    border=1, fill=True
                )
                pdf.cell(
                    2*w9, 5,
                     clean_txt(f" DTR : {dtr_p}"),
                    border=1, fill=True
                )                
                pdf.cell(
                    reste - 6 * w9, 5,
                    clean_txt(f" IMMERSION : __"),
                    border=1, fill=True,
                    new_x=XPos.LEFT, new_y=YPos.NEXT
                )

                # En-tête colonnes membres
                pdf.set_x(x)
                pdf.set_font("Helvetica", 'B', 6)
                pdf.set_fill_color(220, 220, 220)

                pdf.cell(wa, 5, " Fct.",
                         border=1, fill=True)
                pdf.cell(wn, 5, " Nom", border=1, fill=True)
                pdf.cell(wb, 5, " Brevet(s)",
                         border=1, fill=True)
                if is_tech:
                    pdf.cell(wf, 5, " Formation",
                             border=1, fill=True)
                pdf.cell(wg, 5, " Gaz", border=1,
                         fill=True,
                         new_x=XPos.LEFT, new_y=YPos.NEXT)

                # Membres
                for m in membres:
                    role = m[0]

                    # Aptitude / fonction
                    if role == "chef":
                        apt_fct = "ENC"
                    elif role == "serre_file":
                        apt_fct = "SF"
                    else:
                        apt_fct = m[6] or ""

                    # Style du nom : gras=encadrant,
                    # italique=serre-file
                    if role == "chef":
                        nom_style = 'B'
                    elif role == "serre_file":
                        nom_style = 'I'
                    else:
                        nom_style = ''

                    nom_complet = f"{m[1]} {m[2]}"

                    age_m = calc_age(
                        m[8] if len(m) > 8 else ""
                    )
                    est_mineur = (
                        age_m is not None and age_m < 18
                    )
                    if est_mineur:
                        nom_complet = (
                            f"{nom_complet} ({age_m} ans)"
                        )

                    pdf.set_x(x)

                    pdf.set_font("Helvetica", nom_style, 6)
                    pdf.cell(
                        wa, 5,
                        clean_txt(f"{apt_fct}"),
                        border=1
                    )

                    pdf.set_font(
                        "Helvetica", nom_style, 6
                    )
                    pdf.cell(
                        wn, 5,
                        clean_txt(f" {nom_complet}"),
                        border=1
                    )

                    pdf.set_font("Helvetica", nom_style, 6)
                    nx_m = m[7] if len(m) > 7 else ""
                    pdf.cell(
                        wb, 5,
                        clean_txt(
                            fmt_niveau(m[3] or '', nx_m)
                        ),
                        border=1
                    )
                    if is_tech:
                        pdf.cell(
                            wf, 5,
                            clean_txt(
                                f"{fmt_niveau(m[5], '') or ''}"
                            ),
                            border=1
                        )
                    pdf.cell(
                        wg, 5,
                        clean_txt(f"{m[4] or 'Air'}"),
                        border=1,
                        new_x=XPos.LEFT, new_y=YPos.NEXT
                    )

                # Réalisés : label "Réalisés" à gauche
                # + 3 sous-colonnes
                pdf.set_x(x)
                pdf.set_font("Helvetica", 'B', 5)
                pdf.set_fill_color(255, 250, 220)
                pdf.cell(
                    wa, 5, "Réalisés",
                    border=1, fill=True
                )
                pdf.set_font("Helvetica", 'I', 6)
                pdf.cell(
                    2*w9, 5, "Prof. : __",
                    border=1, fill=True
                )
                pdf.cell(
                    2*w9, 5, "Durée : __",
                    border=1, fill=True
                )
                pdf.cell(
                    2*w9, 5, "DTR : __",
                    border=1, fill=True
                )                
                pdf.cell(
                    reste - 6 * w9, 5, "SORTIE : __",
                    border=1, fill=True,
                    new_x=XPos.LEFT, new_y=YPos.NEXT
                )

            # Avancer sous la ligne la plus haute
            pdf.set_y(y_start + h_max + 6)

            i += n_cols

    def t5_get_membres(conn, pal_id):
        return conn.execute(
            "SELECT pm.role, pa.nom, pa.prenom,"
            " pa.niveau, pm.gaz, pa.niveau_prepa,"
            " pm.aptitude, pc.brevet_nitrox,"
            " pc.date_naissance"
            " FROM palanquee_membres pm"
            " JOIN participants pa ON pa.id ="
            " pm.participant_id"
            " LEFT JOIN plongeurs_club pc"
            " ON UPPER(pc.nom)=UPPER(pa.nom)"
            " AND UPPER(pc.prenom)=UPPER(pa.prenom)"
            " WHERE pm.palanquee_id=?"
            " ORDER BY CASE pm.role WHEN 'chef' THEN 0"
            " WHEN 'serre_file' THEN 1 ELSE 2 END",
            (pal_id,)
        ).fetchall()

    def t5_build_pdf(filepath, dj, num, heure, dp,
                     mode="portrait"):
        """Construit la fiche PDF d'une plongée.
        mode = 'portrait' (1 palanquée/ligne) ou
        'paysage' (3 palanquées/ligne)."""

        sid = state["sortie_id"]

        conn = sqlite3.connect(DB_PATH)

        pals = conn.execute(
            "SELECT id, type, prof_max, duree_max, ordre,"
            " dtr_max"
            " FROM palanquees_sortie WHERE sortie_id=?"
            " AND date_jour=? AND num_plongee=?"
            " ORDER BY ordre",
            (sid, dj, num)
        ).fetchall()

        if not pals:
            conn.close()
            raise ValueError("Aucune palanquée")

        total = 0
        for p in pals:
            total += conn.execute(
                "SELECT COUNT(*) FROM palanquee_membres"
                " WHERE palanquee_id=?",
                (p[0],)
            ).fetchone()[0]

        nom_sortie = (sortie_nom.value or "").strip()
        lieu = (sortie_lieu.value or "            ").strip()

        orient = "L" if mode == "paysage" else "P"
        pdf = FPDF(orientation=orient)
        pdf.add_page()

        # Logos (chemins stockés en config)
        logo1 = None
        logo2 = None
        r1 = conn.execute(
            "SELECT value FROM config WHERE key='logo1_path'"
        ).fetchone()
        if r1 and r1[0] and os.path.exists(r1[0]):
            logo1 = r1[0]
        r2 = conn.execute(
            "SELECT value FROM config WHERE key='logo2_path'"
        ).fetchone()
        if r2 and r2[0] and os.path.exists(r2[0]):
            logo2 = r2[0]

        page_w = pdf.w - pdf.l_margin - pdf.r_margin

        if logo1:
            try:
                pdf.image(logo1, x=pdf.l_margin, y=8, h=20)
            except Exception:
                pass
        if logo2:
            try:
                pdf.image(
                    logo2, x=pdf.w - pdf.r_margin - 30,
                    y=8, h=20
                )
            except Exception:
                pass

        pdf.set_font("Helvetica", 'B', 16)
        pdf.cell(0, 10, "FICHE DE SECURITE",
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT,
                 align='C')
        pdf.set_font("Helvetica", 'B', 11)
        pdf.cell(
            0, 8,
            clean_txt(
                f"Sortie : {nom_sortie}  |  "
                f"Nombre Total de Plongeurs : {total}"
            ),
            new_x=XPos.LMARGIN, new_y=YPos.NEXT,
            align='C'
        )
        pdf.set_font("Helvetica", '', 10)
        pdf.cell(
            0, 6,
            clean_txt(
                f"DP: {dp} | Lieu: {lieu} | "
                f"Date: {dj} | Heure: {heure} | "
                f"Plongée {num}"
            ),
            new_x=XPos.LMARGIN, new_y=YPos.NEXT,
            align='C'
        )

        if mode == "paysage":
            t5_render_paysage(
                pdf, conn, pals, page_w
            )
            conn.close()
            pdf.output(filepath)
            return

        H_SEP = 8

        for i, p in enumerate(pals, 1):

            ptype = p[1] or ""
            dtr = p[5]

            # Colonne "En formation" seulement si Technique
            is_technique = (ptype == "Technique")

            membres = t5_get_membres(conn, p[0])

            current_y = pdf.get_y()
            pdf.set_y(current_y + H_SEP)

            # Hauteur nécessaire pour la palanquée
            # complète : titre(8) + prévus(7) + en-tête(7)
            # + membres(7*n) + réalisés(7)
            hauteur_bloc = (
                8 + 7 + 7
                + 7 * len(membres)
                + 7
            )

            # Saut de page si le bloc ne tient pas dans
            # l'espace restant (marge basse ~15mm)
            espace_restant = (
                pdf.h - pdf.b_margin - pdf.get_y()
            )

            if hauteur_bloc > espace_restant:
                pdf.add_page()

            # Titre palanquée
            pdf.set_fill_color(200, 220, 255)
            pdf.set_font("Helvetica", 'B', 10)
            pdf.cell(
                190, 8,
                clean_txt(
                    f" Palanquée {i} - {ptype}"
                ),
                border=1, fill=True,
                new_x=XPos.LMARGIN, new_y=YPos.NEXT
            )

            # Ligne paramètres PRÉVUS (avec DTR)
            pdf.set_font("Helvetica", 'B', 9)
            pdf.set_fill_color(240, 240, 240)
            dtr_prev = (
                f"{dtr} min" if dtr is not None else ""
            )
            pdf.cell(
                48, 7,
                clean_txt(f"Prof. Prévue : {p[2] or 0:g} m"),
                border=1, fill=True
            )
            pdf.cell(
                48, 7,
                clean_txt(f"Durée Prévue : {p[3] or 0} min"),
                border=1, fill=True
            )
            pdf.cell(
                44, 7,
                clean_txt(f"DTR Prévue : {dtr_prev}"),
                border=1, fill=True
            )
            pdf.cell(
                50, 7, clean_txt("IMMERSION : ___:___"),
                border=1, fill=True,
                new_x=XPos.LMARGIN, new_y=YPos.NEXT
            )

            # En-tête colonnes membres
            pdf.set_fill_color(220, 220, 220)
            pdf.set_font("Helvetica", 'B', 8)

            if is_technique:
                # Nom +50%, Apt/Fct à gauche, gaz réduit
                w_nom, w_apt, w_brev, w_form, w_gaz = (
                    72, 32, 30, 36, 20
                )
            else:
                w_nom, w_apt, w_brev, w_gaz = (
                    90, 40, 40, 20
                )

            pdf.cell(w_nom, 7, " NOM Prénom",
                     border=1, fill=True)
            pdf.cell(w_apt, 7, " Apt. / Fct.",
                     border=1, fill=True)
            pdf.cell(w_brev, 7, " Brevet(s)",
                     border=1, fill=True)
            if is_technique:
                pdf.cell(w_form, 7, " En formation",
                         border=1, fill=True)
            pdf.cell(w_gaz, 7, " Gaz",
                     border=1, fill=True,
                     new_x=XPos.LMARGIN, new_y=YPos.NEXT)

            # Lignes membres
            pdf.set_font("Helvetica", '', 8)
            for m in membres:
                role = m[0]

                nom_complet = f"{m[1]} {m[2]}"
                nx_m = m[7] if len(m) > 7 else ""
                brevet = fmt_niveau(m[3] or "-", nx_m)
                gaz = m[4] or "Air"
                prepa = m[5] or ""

                age_m = calc_age(
                    m[8] if len(m) > 8 else ""
                )
                est_mineur = (
                    age_m is not None and age_m < 18
                )
                if est_mineur:
                    nom_complet = (
                        f"{nom_complet} ({age_m} ans)"
                    )

                # Aptitude / fonction
                if role == "chef":
                    apt_fct = "ENC"
                elif role == "serre_file":
                    apt_fct = "SF"
                else:
                    apt_fct = m[6] or "-"

                if est_mineur:
                    pdf.set_font("Helvetica", 'B', 8)
                pdf.cell(
                    w_nom, 7,
                    clean_txt(f" {nom_complet}"),
                    border=1
                )
                if est_mineur:
                    pdf.set_font("Helvetica", '', 8)
                pdf.cell(
                    w_apt, 7,
                    clean_txt(f" {apt_fct}"),
                    border=1
                )
                pdf.cell(
                    w_brev, 7,
                    clean_txt(f" {brevet}"),
                    border=1
                )
                if is_technique:
                    pdf.cell(
                        w_form, 7,
                        clean_txt(
                            f" {fmt_niveau(prepa, '') or '-'}"
                        ),
                        border=1
                    )
                pdf.cell(
                    w_gaz, 7,
                    clean_txt(f" {gaz}"),
                    border=1,
                    new_x=XPos.LMARGIN, new_y=YPos.NEXT
                )

            # Ligne paramètres RÉALISÉS (avec DTR)
            pdf.set_font("Helvetica", 'I', 8)
            pdf.set_fill_color(255, 250, 220)
            pdf.cell(48, 7, "Prof. réelle : ___ m",
                     border=1, fill=True)
            pdf.cell(48, 7, "Durée réelle : ___ min",
                     border=1, fill=True)
            pdf.cell(44, 7, "DTR réelle : ___ min",
                     border=1, fill=True)
            pdf.cell(50, 7, "SORTIE : ___:___",
                     border=1, fill=True,
                     new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        conn.close()
        pdf.output(filepath)

    def t5_generate_pdfs(e, mode="portrait"):

        if not FPDF_AVAILABLE:
            show_message(
                "Module fpdf non installé."
                " Lancez : pip install fpdf2"
            )
            return

        if state["sortie_id"] is None:
            show_message("Enregistrez d'abord la sortie.")
            return

        # Sauvegarder heures/DP avant
        t5_save_heures_dp(silent=True)

        selected = [
            (dj, num)
            for (dj, num), r in t5_rows.items()
            if r["check"].value
        ]

        if not selected:
            show_message(
                "Aucune plongée sélectionnée."
            )
            return

        # Dossier de sortie
        nom_sortie = (sortie_nom.value or "sortie").strip()
        safe_nom = "".join(
            c if c.isalnum() or c in " -_" else "_"
            for c in nom_sortie
        ).strip()

        out_dir = os.path.join(
            app_dir(),
            f"Fiches_{safe_nom}"
        )
        os.makedirs(out_dir, exist_ok=True)

        ok = 0
        erreurs = []

        # Suivi des fichiers effectivement créés (pour le partage)
        fichiers_crees = []

        for dj, num in selected:

            r = t5_rows[(dj, num)]
            heure = (r["heure"].value or "").strip()
            dp = (r["dp"].value or "").strip()

            dj_safe = dj.replace("/", "-")
            fn = os.path.join(
                out_dir,
                f"Fiche_{dj_safe}_P{num}.pdf"
            )

            try:
                t5_build_pdf(
                    fn, dj, num, heure, dp, mode=mode
                )
                ok += 1
                fichiers_crees.append(fn)
            except Exception as err:
                erreurs.append(
                    f"{dj} P{num}: {err}"
                )

        msg = f"{ok} fiche(s) PDF générée(s) dans {out_dir}"
        if erreurs:
            msg += f" — {len(erreurs)} erreur(s) : " \
                + "; ".join(erreurs[:3])

        show_message(msg)

        # Proposer le partage de tous les fichiers générés
        # (share sheet Android native : Drive, Files, mail...)
        if fichiers_crees and share_service is not None:
            t5_offer_share(fichiers_crees)

    def offer_share_files(
        fichiers,
        mime_type="application/octet-stream",
        titre_dialogue="📤 Partager le(s) fichier(s)",
        label_fichier="fichier",
        sujet="Partage de fichier",
        texte=None,
    ):
        """Helper générique : propose le partage natif
        d'une liste de fichiers via la share sheet.
        - fichiers : liste de chemins absolus
        - mime_type : application/pdf, application/json,
          application/octet-stream (DB), text/csv, etc.
        - label_fichier : ex 'fiche', 'sortie', 'sauvegarde'
        - sujet / texte : métadonnées pour la share sheet
        """
        if not fichiers or share_service is None:
            return

        async def do_share(ev):
            close_dialog(share_dlg)
            try:
                share_files = []
                for fn in fichiers:
                    if not os.path.exists(fn):
                        continue
                    try:
                        sf = ft.ShareFile.from_path(
                            fn, mime_type=mime_type
                        )
                    except Exception:
                        try:
                            sf = ft.ShareFile(path=fn)
                        except Exception:
                            sf = None
                    if sf is not None:
                        share_files.append(sf)

                if not share_files:
                    show_message(
                        "Aucun fichier à partager."
                    )
                    return

                await share_service.share_files(
                    share_files,
                    text=texte or sujet,
                    subject=sujet,
                )
            except Exception as err:
                show_message(f"Erreur partage : {err}")

        nb = len(fichiers)
        pluriel = "s" if nb > 1 else ""
        share_dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(
                titre_dialogue,
                weight=ft.FontWeight.BOLD
            ),
            content=ft.Container(
                width=_w(400),
                content=ft.Column(
                    tight=True,
                    spacing=10,
                    controls=[
                        ft.Text(
                            f"{nb} {label_fichier}{pluriel}"
                            f" prêt{pluriel} à être"
                            f" partagé{pluriel}.",
                            size=12
                        ),
                        ft.Text(
                            "Choisissez ensuite Drive,"
                            " Files, Gmail, etc. dans"
                            " la fenêtre Android.",
                            size=11,
                            italic=True,
                            color="#64748b"
                        ),
                    ]
                )
            ),
            actions=[
                ft.TextButton(
                    "Plus tard",
                    on_click=lambda ev:
                        close_dialog(share_dlg)
                ),
                ft.FilledButton(
                    "📤 Partager",
                    bgcolor="#0ea5e9", color="white",
                    on_click=do_share
                ),
            ]
        )
        page.show_dialog(share_dlg)

    def t5_offer_share(fichiers):
        """Wrapper rétro-compatible pour le partage PDF
        depuis la génération de fiches de sécurité."""
        nom_sortie = (sortie_nom.value or "").strip()
        offer_share_files(
            fichiers,
            mime_type="application/pdf",
            titre_dialogue="📤 Partager les fiches",
            label_fichier="fiche PDF",
            sujet=f"Fiches de sécurité ({len(fichiers)} PDF)",
            texte=f"Fiches de sécurité — {nom_sortie}",
        )


    # --- Choix des logos ---
    def t5_pick_logo(num):
        """Ouvre un FilePicker pour choisir un logo
        (1 ou 2) et stocke son chemin en config."""

        async def pick(e):
            try:
                files = await file_picker.pick_files(
                    allow_multiple=False,
                    file_type=ft.FilePickerFileType.IMAGE
                )
                if not files:
                    return
                src = files[0].path

                # Copier le logo dans le stockage privé
                # persistant de l'app : le chemin renvoyé
                # par le sélecteur Android est souvent
                # temporaire et peut devenir invalide.
                # On garde une copie stable à côté de la
                # base de données.
                try:
                    ext = os.path.splitext(src)[1] or ".png"
                    path = os.path.join(
                        app_dir(), f"logo{num}{ext}"
                    )
                    shutil.copy2(src, path)
                except Exception:
                    # Si la copie échoue, on retombe sur
                    # le chemin d'origine (mode test PC).
                    path = src

                conn = sqlite3.connect(DB_PATH)
                conn.execute(
                    "INSERT OR REPLACE INTO config"
                    "(key, value) VALUES (?, ?)",
                    (f"logo{num}_path", path)
                )
                conn.commit()
                conn.close()
                show_message(
                    f"Logo {num} enregistré : "
                    f"{os.path.basename(path)}"
                )
            except Exception as err:
                show_message(str(err))

        page.run_task(pick, None)

    # --- Config SMTP ---
    def t5_get_smtp_config():
        conn = sqlite3.connect(DB_PATH)
        cfg = {}
        for k in (
            "smtp_host", "smtp_port", "smtp_user",
            "smtp_pass", "smtp_from"
        ):
            r = conn.execute(
                "SELECT value FROM config WHERE key=?",
                (k,)
            ).fetchone()
            cfg[k] = r[0] if r else ""
        conn.close()
        return cfg

    def t5_config_smtp(e):

        cfg = t5_get_smtp_config()

        f_host = ft.TextField(
            label="Serveur SMTP",
            value=cfg["smtp_host"],
            hint_text="smtp.gmail.com",
            dense=True
        )
        f_port = ft.TextField(
            label="Port",
            value=cfg["smtp_port"] or "587",
            width=120, dense=True
        )
        f_user = ft.TextField(
            label="Identifiant (email)",
            value=cfg["smtp_user"],
            dense=True
        )
        f_pass = ft.TextField(
            label="Mot de passe / clé d'application",
            value=cfg["smtp_pass"],
            password=True,
            can_reveal_password=True,
            dense=True
        )
        f_from = ft.TextField(
            label="Expéditeur (si différent)",
            value=cfg["smtp_from"],
            dense=True
        )

        def save_smtp(ev):
            conn = sqlite3.connect(DB_PATH)
            for k, w in [
                ("smtp_host", f_host),
                ("smtp_port", f_port),
                ("smtp_user", f_user),
                ("smtp_pass", f_pass),
                ("smtp_from", f_from),
            ]:
                conn.execute(
                    "INSERT OR REPLACE INTO config"
                    "(key, value) VALUES (?, ?)",
                    (k, (w.value or "").strip())
                )
            conn.commit()
            conn.close()
            close_dialog(smtp_dlg)
            show_message("Configuration SMTP enregistrée.")

        smtp_dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(
                "⚙️ Configuration email (SMTP)",
                weight=ft.FontWeight.BOLD
            ),
            content=ft.Container(
                width=_w(420),
                content=ft.Column(
                    tight=True, spacing=10,
                    controls=[
                        f_host, f_port, f_user,
                        f_pass, f_from,
                        ft.Text(
                            "Pour Gmail : utilisez un mot"
                            " de passe d'application"
                            " (pas votre mot de passe"
                            " habituel).",
                            size=10, italic=True,
                            color="#94a3b8"
                        ),
                    ]
                )
            ),
            actions=[
                ft.TextButton(
                    "Annuler",
                    on_click=lambda ev:
                        close_dialog(smtp_dlg)
                ),
                ft.FilledButton(
                    "Enregistrer",
                    on_click=save_smtp
                ),
            ]
        )
        page.show_dialog(smtp_dlg)

    # =================================================
    # EXPORT / IMPORT SORTIE  +  SAUVEGARDE / RESTAURE BASE
    # =================================================

    def export_sortie(e=None):
        """Exporte la sortie courante (tous les onglets)
        dans un fichier JSON."""

        if state["sortie_id"] is None:
            show_message(
                "Ouvrez d'abord une sortie à exporter."
            )
            return

        sid = state["sortie_id"]
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row

        data = {"_format": "sortie_export_v1"}

        # Sortie
        srow = conn.execute(
            "SELECT * FROM sorties WHERE id=?", (sid,)
        ).fetchone()
        if not srow:
            conn.close()
            show_message("Sortie introuvable.")
            return
        data["sortie"] = dict(srow)

        # Participants
        parts = conn.execute(
            "SELECT * FROM participants WHERE sortie_id=?",
            (sid,)
        ).fetchall()
        data["participants"] = [dict(r) for r in parts]
        part_ids = [r["id"] for r in parts]

        # Jours
        data["jours"] = [
            dict(r) for r in conn.execute(
                "SELECT * FROM jours_sortie WHERE sortie_id=?",
                (sid,)
            ).fetchall()
        ]

        # Inscriptions (plongees_realisees) par participant
        data["plongees_realisees"] = []
        if part_ids:
            ph = ",".join("?" * len(part_ids))
            data["plongees_realisees"] = [
                dict(r) for r in conn.execute(
                    f"SELECT * FROM plongees_realisees"
                    f" WHERE participant_id IN ({ph})",
                    part_ids
                ).fetchall()
            ]

        # Palanquées
        pals = conn.execute(
            "SELECT * FROM palanquees_sortie"
            " WHERE sortie_id=?",
            (sid,)
        ).fetchall()
        data["palanquees"] = [dict(r) for r in pals]
        pal_ids = [r["id"] for r in pals]

        # Membres de palanquées
        data["palanquee_membres"] = []
        if pal_ids:
            ph = ",".join("?" * len(pal_ids))
            data["palanquee_membres"] = [
                dict(r) for r in conn.execute(
                    f"SELECT * FROM palanquee_membres"
                    f" WHERE palanquee_id IN ({ph})",
                    pal_ids
                ).fetchall()
            ]

        # Fiches sécurité
        data["fiches_securite"] = [
            dict(r) for r in conn.execute(
                "SELECT * FROM fiches_securite"
                " WHERE sortie_id=?",
                (sid,)
            ).fetchall()
        ]

        conn.close()

        nom = (sortie_nom.value or "sortie").strip()
        safe = "".join(
            c if c.isalnum() or c in " -_" else "_"
            for c in nom
        ).strip()
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        path = os.path.join(
            app_dir(),
            f"Sortie_{safe}_{ts}.json"
        )

        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(
                    data, f, ensure_ascii=False, indent=2
                )
            show_message(f"Sortie exportée : {path}")

            # Proposer le partage natif
            if share_service is not None:
                offer_share_files(
                    [path],
                    mime_type="application/json",
                    titre_dialogue="📤 Partager la sortie",
                    label_fichier="export de sortie",
                    sujet=f"Export sortie — {nom}",
                    texte=(
                        f"Sauvegarde complète de la"
                        f" sortie « {nom} »"
                    ),
                )
        except Exception as err:
            show_message(f"Erreur export : {err}")

    def import_sortie(e=None):
        """Importe une sortie depuis un JSON (créée comme
        nouvelle sortie)."""

        async def pick(ev):
            try:
                files = await file_picker.pick_files(
                    allow_multiple=False,
                    file_type=ft.FilePickerFileType.CUSTOM,
                    allowed_extensions=["json"]
                )
                if not files:
                    return

                path = files[0].path
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                if data.get("_format") != \
                        "sortie_export_v1":
                    show_message(
                        "Fichier non reconnu"
                        " (format invalide)."
                    )
                    return

                conn = sqlite3.connect(DB_PATH)
                c = conn.cursor()

                # Créer la sortie (nouvel id)
                s = data["sortie"]
                c.execute(
                    "INSERT INTO sorties"
                    "(nom, lieu, date_debut, date_fin)"
                    " VALUES (?, ?, ?, ?)",
                    (
                        s.get("nom"), s.get("lieu"),
                        s.get("date_debut"),
                        s.get("date_fin")
                    )
                )
                new_sid = c.lastrowid

                # Jours
                for j in data.get("jours", []):
                    c.execute(
                        "INSERT INTO jours_sortie"
                        "(sortie_id, date_jour, nb_plongees)"
                        " VALUES (?, ?, ?)",
                        (
                            new_sid, j.get("date_jour"),
                            j.get("nb_plongees")
                        )
                    )

                # Participants (mapping ancien id -> nouveau)
                pid_map = {}
                for p in data.get("participants", []):
                    c.execute(
                        "INSERT INTO participants"
                        "(sortie_id, type, nom, prenom,"
                        " niveau, niveau_prepa,"
                        " lien_plongeur)"
                        " VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (
                            new_sid, p.get("type"),
                            p.get("nom"), p.get("prenom"),
                            p.get("niveau"),
                            p.get("niveau_prepa"),
                            p.get("lien_plongeur")
                        )
                    )
                    pid_map[p["id"]] = c.lastrowid

                # Inscriptions
                for pr in data.get(
                    "plongees_realisees", []
                ):
                    new_pid = pid_map.get(
                        pr.get("participant_id")
                    )
                    if new_pid:
                        c.execute(
                            "INSERT INTO plongees_realisees"
                            "(participant_id, date_jour,"
                            " num_plongee)"
                            " VALUES (?, ?, ?)",
                            (
                                new_pid,
                                pr.get("date_jour"),
                                pr.get("num_plongee")
                            )
                        )

                # Palanquées (mapping ancien id -> nouveau)
                pal_map = {}
                for pl in data.get("palanquees", []):
                    c.execute(
                        "INSERT INTO palanquees_sortie"
                        "(sortie_id, date_jour,"
                        " num_plongee, ordre, type,"
                        " prof_max, duree_max, dtr_max)"
                        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            new_sid, pl.get("date_jour"),
                            pl.get("num_plongee"),
                            pl.get("ordre"),
                            pl.get("type"),
                            pl.get("prof_max"),
                            pl.get("duree_max"),
                            pl.get("dtr_max")
                        )
                    )
                    pal_map[pl["id"]] = c.lastrowid

                # Membres
                for m in data.get(
                    "palanquee_membres", []
                ):
                    new_pal = pal_map.get(
                        m.get("palanquee_id")
                    )
                    new_pid = pid_map.get(
                        m.get("participant_id")
                    )
                    if new_pal and new_pid:
                        c.execute(
                            "INSERT INTO palanquee_membres"
                            "(palanquee_id, participant_id,"
                            " role, gaz, aptitude)"
                            " VALUES (?, ?, ?, ?, ?)",
                            (
                                new_pal, new_pid,
                                m.get("role"),
                                m.get("gaz"),
                                m.get("aptitude")
                            )
                        )

                # Fiches sécurité
                for fs in data.get("fiches_securite", []):
                    c.execute(
                        "INSERT INTO fiches_securite"
                        "(sortie_id, date_jour,"
                        " num_plongee, heure, dp)"
                        " VALUES (?, ?, ?, ?, ?)",
                        (
                            new_sid, fs.get("date_jour"),
                            fs.get("num_plongee"),
                            fs.get("heure"), fs.get("dp")
                        )
                    )

                conn.commit()
                conn.close()

                show_message(
                    "Sortie importée. Ouvrez-la via"
                    " « Ouvrir une sortie »."
                )

            except Exception as err:
                show_message(f"Erreur import : {err}")

        page.run_task(pick, None)

    def sauvegarder_base(e=None):
        """Copie le fichier de base de données."""
        try:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            dest = os.path.join(
                app_dir(),
                f"backup_suivi_plongee_{ts}.db"
            )
            shutil.copy2(DB_PATH, dest)
            show_message(f"Base sauvegardée : {dest}")

            # Proposer le partage natif (utile pour
            # transférer la base vers PC, Drive, etc.)
            if share_service is not None:
                offer_share_files(
                    [dest],
                    mime_type="application/octet-stream",
                    titre_dialogue="📤 Partager la sauvegarde",
                    label_fichier="sauvegarde",
                    sujet="Sauvegarde Secu Manager",
                    texte=(
                        "Sauvegarde de la base de"
                        " données Secu Manager"
                    ),
                )
        except Exception as err:
            show_message(f"Erreur sauvegarde : {err}")

    def restaurer_base(e=None):
        """Restaure la base depuis un fichier .db choisi."""

        def confirmer_restore(path):

            def do_restore(ev):
                close_dialog(confirm_dlg)
                try:
                    # Sauvegarde de sécurité avant
                    ts = datetime.now().strftime(
                        "%Y%m%d_%H%M%S"
                    )
                    shutil.copy2(
                        DB_PATH,
                        os.path.join(
                            app_dir(),
                            f"avant_restore_{ts}.db"
                        )
                    )
                    shutil.copy2(path, DB_PATH)
                    show_message(
                        "Base restaurée. Redémarrez"
                        " l'application pour appliquer"
                        " les changements."
                    )
                except Exception as err:
                    show_message(
                        f"Erreur restauration : {err}"
                    )

            confirm_dlg = ft.AlertDialog(
                modal=True,
                title=ft.Text(
                    "⚠️ Restaurer la base",
                    weight=ft.FontWeight.BOLD
                ),
                content=ft.Text(
                    "La base actuelle sera remplacée"
                    " (une copie de sécurité est créée"
                    " automatiquement). Continuer ?"
                ),
                actions=[
                    ft.TextButton(
                        "Annuler",
                        on_click=lambda ev:
                            close_dialog(confirm_dlg)
                    ),
                    ft.FilledButton(
                        "Restaurer",
                        bgcolor="#ef4444", color="white",
                        on_click=do_restore
                    ),
                ]
            )
            page.show_dialog(confirm_dlg)

        async def pick(ev):
            try:
                files = await file_picker.pick_files(
                    allow_multiple=False,
                    file_type=ft.FilePickerFileType.CUSTOM,
                    allowed_extensions=["db"]
                )
                if not files:
                    return
                confirmer_restore(files[0].path)
            except Exception as err:
                show_message(f"Erreur : {err}")

        page.run_task(pick, None)

    def vider_base_plongeurs(e=None):
        """Vide entièrement le référentiel des plongeurs
        du club (table plongeurs_club). Utile pour le
        droit à l'effacement (RGPD) ou pour repartir
        d'une base propre avant un nouvel import FFESSM.
        N'affecte PAS les sorties déjà enregistrées."""

        # Compter d'abord pour informer l'utilisateur
        try:
            conn = sqlite3.connect(DB_PATH)
            nb = conn.execute(
                "SELECT COUNT(*) FROM plongeurs_club"
            ).fetchone()[0]
            conn.close()
        except Exception:
            nb = 0

        if nb == 0:
            show_message(
                "La base des plongeurs est déjà vide."
            )
            return

        def confirmer(ev):
            try:
                conn = sqlite3.connect(DB_PATH)
                conn.execute("DELETE FROM plongeurs_club")
                conn.commit()
                conn.close()

                # Rafraîchir l'affichage en mémoire
                reload_plongeurs_club()

                close_dialog(vider_dlg)
                show_message(
                    f"{nb} plongeur(s) supprimé(s)"
                    " de la base du club."
                )
            except Exception as err:
                close_dialog(vider_dlg)
                show_message(f"Erreur : {err}")

        vider_dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(
                "⚠️ Vider la base des plongeurs",
                weight=ft.FontWeight.BOLD
            ),
            content=ft.Text(
                f"Cette action va supprimer"
                f" définitivement les {nb} plongeur(s)"
                f" du référentiel du club.\n\n"
                f"Les sorties déjà enregistrées ne sont"
                f" pas affectées, mais vous ne pourrez"
                f" plus ajouter ces plongeurs sans les"
                f" réimporter.\n\n"
                f"Cette action est irréversible."
            ),
            actions=[
                ft.TextButton(
                    "Annuler",
                    on_click=lambda ev:
                        close_dialog(vider_dlg)
                ),
                ft.FilledButton(
                    "Tout supprimer",
                    bgcolor="#ef4444", color="white",
                    on_click=confirmer
                ),
            ]
        )
        page.show_dialog(vider_dlg)

    def effacement_total(e=None):
        """Efface TOUTES les données de l'application :
        référentiel des plongeurs, sorties, participants,
        palanquées, inscriptions, fiches de sécurité ET
        configuration (logos, SMTP). Remet l'application
        dans son état initial. Pour le droit à
        l'effacement (RGPD) complet."""

        TABLES = [
            "plongeurs",
            "plongeurs_club",
            "sorties",
            "participants",
            "jours_sortie",
            "plongees_realisees",
            "palanquees_sortie",
            "palanquee_membres",
            "config",
            "fiches_securite",
        ]

        # Deuxième confirmation (saisie obligatoire)
        # vu le caractère radical de l'opération.
        confirm_field = ft.TextField(
            label="Tapez EFFACER pour confirmer",
            dense=True
        )

        def confirmer_final(ev):
            if (confirm_field.value or "").strip().upper() \
                    != "EFFACER":
                show_message(
                    "Saisie incorrecte."
                    " Tapez EFFACER en majuscules."
                )
                return
            try:
                conn = sqlite3.connect(DB_PATH)
                for t in TABLES:
                    try:
                        conn.execute(f"DELETE FROM {t}")
                    except Exception as t_err:
                        print(f"Effacement {t}:", t_err)
                conn.commit()
                conn.close()

                # Réinitialiser l'état mémoire et l'UI
                state["sortie_id"] = None
                state["participants_rows"].clear()
                try:
                    participants_rows_column.controls.clear()
                except Exception:
                    pass
                try:
                    jours_column.controls.clear()
                except Exception:
                    pass
                sortie_nom.value = ""
                sortie_lieu.value = ""
                date_debut.value = ""
                date_fin.value = ""

                reload_plongeurs_club()
                update_stats_part()

                close_dialog(efface_dlg)
                show_message(
                    "Toutes les données ont été"
                    " effacées. L'application est"
                    " réinitialisée."
                )
                page.update()
            except Exception as err:
                close_dialog(efface_dlg)
                show_message(f"Erreur : {err}")

        efface_dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(
                "🚨 Effacement total des données",
                weight=ft.FontWeight.BOLD,
                color="#dc2626"
            ),
            content=ft.Container(
                width=_w(440),
                content=ft.Column(
                    tight=True,
                    spacing=12,
                    scroll=ft.ScrollMode.AUTO,
                    controls=[
                        ft.Text(
                            "Cette action supprime"
                            " DÉFINITIVEMENT :",
                            weight=ft.FontWeight.BOLD,
                            size=13
                        ),
                        ft.Text(
                            "• tous les plongeurs du"
                            " référentiel\n"
                            "• toutes les sorties et"
                            " leurs participants\n"
                            "• toutes les palanquées et"
                            " inscriptions\n"
                            "• toutes les fiches de"
                            " sécurité\n"
                            "• la configuration (logos,"
                            " réglages email)",
                            size=12
                        ),
                        ft.Text(
                            "Rien ne pourra être"
                            " récupéré. Pensez à"
                            " sauvegarder la base avant"
                            " si nécessaire.",
                            size=12,
                            italic=True,
                            color="#dc2626"
                        ),
                        confirm_field,
                    ]
                )
            ),
            actions=[
                ft.TextButton(
                    "Annuler",
                    on_click=lambda ev:
                        close_dialog(efface_dlg)
                ),
                ft.FilledButton(
                    "Tout effacer définitivement",
                    bgcolor="#dc2626", color="white",
                    on_click=confirmer_final
                ),
            ]
        )
        page.show_dialog(efface_dlg)

    def open_club_dialog(e=None):
        """Dialogue : saisie du nom court et nom long du
        club, utilisés dans le sujet et corps de l'email."""

        # Lire valeurs actuelles
        conn = sqlite3.connect(DB_PATH)
        court_row = conn.execute(
            "SELECT value FROM config"
            " WHERE key='club_nom_court'"
        ).fetchone()
        long_row = conn.execute(
            "SELECT value FROM config"
            " WHERE key='club_nom_long'"
        ).fetchone()
        conn.close()

        court_field = ft.TextField(
            label="Nom court (ex : CSSA)",
            value=court_row[0] if court_row else "",
            dense=True,
            max_length=30
        )
        long_field = ft.TextField(
            label="Nom long (ex : Cercle Sportif"
                  " Sous-marin d'Aubagne)",
            value=long_row[0] if long_row else "",
            dense=True,
            max_length=120
        )

        def enregistrer(ev):
            try:
                conn = sqlite3.connect(DB_PATH)
                conn.execute(
                    "INSERT OR REPLACE INTO config"
                    " (key, value) VALUES (?, ?)",
                    ("club_nom_court",
                     (court_field.value or "").strip())
                )
                conn.execute(
                    "INSERT OR REPLACE INTO config"
                    " (key, value) VALUES (?, ?)",
                    ("club_nom_long",
                     (long_field.value or "").strip())
                )
                conn.commit()
                conn.close()
                close_dialog(club_dlg)
                show_message("Nom du club enregistré.")
                open_parametres()
            except Exception as err:
                close_dialog(club_dlg)
                show_message(f"Erreur : {err}")

        club_dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(
                "🏛️ Nom du club",
                weight=ft.FontWeight.BOLD
            ),
            content=ft.Container(
                width=_w(420),
                content=ft.Column(
                    tight=True,
                    spacing=12,
                    controls=[
                        ft.Text(
                            "Ces noms apparaissent dans"
                            " le sujet et le corps des"
                            " emails d'envoi des fiches"
                            " de sécurité.",
                            size=11,
                            italic=True,
                            color="#64748b"
                        ),
                        court_field,
                        long_field,
                    ]
                )
            ),
            actions=[
                ft.TextButton(
                    "Annuler",
                    on_click=lambda ev: (
                        close_dialog(club_dlg),
                        open_parametres()
                    )
                ),
                ft.FilledButton(
                    "Enregistrer",
                    bgcolor="#0ea5e9", color="white",
                    on_click=enregistrer
                ),
            ]
        )
        page.show_dialog(club_dlg)

    def open_parametres():
        """Menu Paramètres : logos + config email."""

        # Afficher les logos actuels et le nom du club
        conn = sqlite3.connect(DB_PATH)
        l1 = conn.execute(
            "SELECT value FROM config"
            " WHERE key='logo1_path'"
        ).fetchone()
        l2 = conn.execute(
            "SELECT value FROM config"
            " WHERE key='logo2_path'"
        ).fetchone()
        club_court_row = conn.execute(
            "SELECT value FROM config"
            " WHERE key='club_nom_court'"
        ).fetchone()
        club_long_row = conn.execute(
            "SELECT value FROM config"
            " WHERE key='club_nom_long'"
        ).fetchone()
        conn.close()

        club_court = (
            club_court_row[0] if club_court_row else ""
        ) or ""
        club_long = (
            club_long_row[0] if club_long_row else ""
        ) or ""

        l1_txt = (
            os.path.basename(l1[0])
            if l1 and l1[0] else "(aucun)"
        )
        l2_txt = (
            os.path.basename(l2[0])
            if l2 and l2[0] else "(aucun)"
        )

        # Libellé du bouton nom du club
        if club_court:
            club_btn_label = (
                f"🏛️ {club_court}"
                + (f" — {club_long}" if club_long else "")
            )
        else:
            club_btn_label = "🏛️ Définir le nom du club"

        param_dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(
                "⚙️ Paramètres",
                weight=ft.FontWeight.BOLD
            ),
            content=ft.Container(
                width=_w(400),
                height=440,
                content=ft.Column(
                    tight=True,
                    spacing=14,
                    scroll=ft.ScrollMode.AUTO,
                    controls=[
                        ft.Text(
                            "Nom du club",
                            weight=ft.FontWeight.BOLD,
                            size=12
                        ),
                        ft.Row([
                            ft.OutlinedButton(
                                club_btn_label,
                                on_click=lambda e: (
                                    close_dialog(param_dlg),
                                    open_club_dialog()
                                )
                            ),
                        ], wrap=True),
                        ft.Divider(),
                        ft.Text(
                            "Logos des fiches PDF",
                            weight=ft.FontWeight.BOLD,
                            size=12
                        ),
                        ft.Row([
                            ft.OutlinedButton(
                                "🖼 Choisir Logo 1",
                                on_click=lambda e: (
                                    close_dialog(param_dlg),
                                    t5_pick_logo(1)
                                )
                            ),
                            ft.Text(
                                l1_txt, size=11,
                                color="#64748b"
                            ),
                        ]),
                        ft.Row([
                            ft.OutlinedButton(
                                "🖼 Choisir Logo 2",
                                on_click=lambda e: (
                                    close_dialog(param_dlg),
                                    t5_pick_logo(2)
                                )
                            ),
                            ft.Text(
                                l2_txt, size=11,
                                color="#64748b"
                            ),
                        ]),
                        ft.Divider(),
                        ft.Text(
                            "Email",
                            weight=ft.FontWeight.BOLD,
                            size=12
                        ),
                        ft.FilledButton(
                            "✉️ Configuration email (SMTP)",
                            bgcolor="#0ea5e9",
                            color="white",
                            on_click=lambda e: (
                                close_dialog(param_dlg),
                                t5_config_smtp(None)
                            )
                        ),
                        ft.Divider(),
                        ft.Text(
                            "Données",
                            weight=ft.FontWeight.BOLD,
                            size=12
                        ),
                        ft.Row([
                            ft.OutlinedButton(
                                "📤 Exporter la sortie",
                                on_click=lambda e: (
                                    close_dialog(param_dlg),
                                    export_sortie()
                                )
                            ),
                            ft.OutlinedButton(
                                "📥 Importer une sortie",
                                on_click=lambda e: (
                                    close_dialog(param_dlg),
                                    import_sortie()
                                )
                            ),
                        ], wrap=True),
                        ft.Row([
                            ft.OutlinedButton(
                                "💾 Sauvegarder la base",
                                on_click=lambda e: (
                                    close_dialog(param_dlg),
                                    sauvegarder_base()
                                )
                            ),
                            ft.OutlinedButton(
                                "♻️ Restaurer la base",
                                on_click=lambda e: (
                                    close_dialog(param_dlg),
                                    restaurer_base()
                                )
                            ),
                        ], wrap=True),
                        ft.Divider(),
                        ft.Text(
                            "Confidentialité (RGPD)",
                            weight=ft.FontWeight.BOLD,
                            size=12
                        ),
                        ft.Text(
                            "Supprime tous les plongeurs"
                            " importés du référentiel du"
                            " club. Les sorties déjà"
                            " enregistrées sont"
                            " conservées.",
                            size=10,
                            italic=True,
                            color="#94a3b8"
                        ),
                        ft.Row([
                            ft.OutlinedButton(
                                "🗑️ Vider la base des"
                                " plongeurs",
                                style=ft.ButtonStyle(
                                    color="#ef4444"
                                ),
                                on_click=lambda e: (
                                    close_dialog(param_dlg),
                                    vider_base_plongeurs()
                                )
                            ),
                        ], wrap=True),
                        ft.Row([
                            ft.FilledButton(
                                "🚨 Effacement total des"
                                " données",
                                bgcolor="#dc2626",
                                color="white",
                                on_click=lambda e: (
                                    close_dialog(param_dlg),
                                    effacement_total()
                                )
                            ),
                        ], wrap=True),
                    ]
                )
            ),
            actions=[
                ft.TextButton(
                    "Fermer",
                    on_click=lambda e:
                        close_dialog(param_dlg)
                )
            ]
        )
        page.show_dialog(param_dlg)

    def t5_send_emails(e, mode="portrait"):

        if not FPDF_AVAILABLE:
            show_message("Module fpdf non installé.")
            return

        if state["sortie_id"] is None:
            show_message("Enregistrez d'abord la sortie.")
            return

        cfg = t5_get_smtp_config()

        if not cfg["smtp_host"] or not cfg["smtp_user"]:
            show_message(
                "Configurez d'abord le SMTP"
                " (bouton ⚙️ Config email)."
            )
            return

        # Demander le(s) destinataire(s)
        f_dest = ft.TextField(
            label="Destinataire(s), séparés par ;",
            dense=True
        )

        def do_send(ev):

            dests = [
                d.strip()
                for d in (f_dest.value or "").split(";")
                if d.strip()
            ]

            if not dests:
                show_message("Saisir au moins un destinataire.")
                return

            close_dialog(send_dlg)

            t5_save_heures_dp(silent=True)

            selected = [
                (dj, num)
                for (dj, num), r in t5_rows.items()
                if r["check"].value
            ]

            if not selected:
                show_message("Aucune plongée sélectionnée.")
                return

            # Générer les PDF dans un dossier temp
            nom_sortie = (
                sortie_nom.value or "sortie"
            ).strip()
            safe_nom = "".join(
                c if c.isalnum() or c in " -_" else "_"
                for c in nom_sortie
            ).strip()
            out_dir = os.path.join(
                app_dir(), f"Fiches_{safe_nom}"
            )
            os.makedirs(out_dir, exist_ok=True)

            fichiers = []
            for dj, num in selected:
                r = t5_rows[(dj, num)]
                heure = (r["heure"].value or "").strip()
                dp = (r["dp"].value or "").strip()
                dj_safe = dj.replace("/", "-")
                fn = os.path.join(
                    out_dir,
                    f"Fiche_{dj_safe}_P{num}.pdf"
                )
                try:
                    t5_build_pdf(
                        fn, dj, num, heure, dp, mode=mode
                    )
                    fichiers.append(fn)
                except Exception as err:
                    print("PDF err:", err)

            if not fichiers:
                show_message("Aucun PDF généré.")
                return

            # Envoi SMTP
            def envoyer():
                try:
                    import smtplib
                    from email.message import EmailMessage

                    msg = EmailMessage()
                    expediteur = (
                        cfg["smtp_from"]
                        or cfg["smtp_user"]
                    )

                    # Récupérer nom du club et dates
                    # de la sortie pour personnaliser
                    # le sujet et le corps de l'email.
                    conn = sqlite3.connect(DB_PATH)
                    club_court_row = conn.execute(
                        "SELECT value FROM config"
                        " WHERE key='club_nom_court'"
                    ).fetchone()
                    club_long_row = conn.execute(
                        "SELECT value FROM config"
                        " WHERE key='club_nom_long'"
                    ).fetchone()
                    dates_row = conn.execute(
                        "SELECT date_debut, date_fin"
                        " FROM sorties WHERE id=?",
                        (state["sortie_id"],)
                    ).fetchone()
                    conn.close()

                    club_court = (
                        club_court_row[0]
                        if club_court_row
                        and club_court_row[0]
                        else nom_sortie
                    )
                    club_long = (
                        club_long_row[0]
                        if club_long_row
                        and club_long_row[0]
                        else ""
                    )

                    if dates_row:
                        date_debut = dates_row[0] or ""
                        date_fin = dates_row[1] or ""
                    else:
                        date_debut = ""
                        date_fin = ""

                    # Format de la mention de date
                    if (
                        date_debut and date_fin
                        and date_debut != date_fin
                    ):
                        date_str = (
                            f"du {date_debut} au"
                            f" {date_fin}"
                        )
                    elif date_debut:
                        date_str = f"du {date_debut}"
                    else:
                        date_str = ""

                    # Sujet de l'email
                    msg["From"] = expediteur
                    msg["To"] = ", ".join(dests)
                    msg["Subject"] = (
                        f"Fiches de sécurités"
                        f" ({len(fichiers)} plongée(s))"
                        f" du {club_court}"
                    )

                    # Corps de l'email
                    nom_club_complet = club_court
                    if club_long:
                        nom_club_complet = (
                            f"{club_court}, {club_long}"
                        )
                    corps = (
                        f"Bonjour,\n\n"
                        f"Veuillez trouver ci-joint"
                        f" les fiches de sécurité"
                        f" du {nom_club_complet}"
                    )
                    if date_str:
                        corps += (
                            f" pour la sortie {date_str}"
                        )
                    corps += ".\n\nCordialement,"

                    msg.set_content(corps)

                    for fn in fichiers:
                        with open(fn, "rb") as fp:
                            data = fp.read()
                        msg.add_attachment(
                            data,
                            maintype="application",
                            subtype="pdf",
                            filename=os.path.basename(fn)
                        )

                    port = int(cfg["smtp_port"] or 587)

                    if port == 465:
                        server = smtplib.SMTP_SSL(
                            cfg["smtp_host"], port,
                            timeout=30
                        )
                    else:
                        server = smtplib.SMTP(
                            cfg["smtp_host"], port,
                            timeout=30
                        )
                        server.starttls()

                    server.login(
                        cfg["smtp_user"],
                        cfg["smtp_pass"]
                    )
                    server.send_message(msg)
                    server.quit()

                    show_message(
                        f"Email envoyé à {len(dests)}"
                        f" destinataire(s) avec"
                        f" {len(fichiers)} fiche(s)."
                    )

                except Exception as err:
                    show_message(
                        f"Erreur envoi : {err}"
                    )

            # Envoi dans un thread (réseau bloquant)
            threading.Thread(
                target=envoyer, daemon=True
            ).start()

            show_message("Envoi en cours...")

        send_dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(
                "✉️ Envoyer les fiches par email",
                weight=ft.FontWeight.BOLD
            ),
            content=ft.Container(
                width=_w(400),
                content=ft.Column(
                    tight=True, spacing=10,
                    controls=[
                        ft.Text(
                            "Les plongées cochées seront"
                            " générées en PDF et jointes.",
                            size=11, color="#64748b"
                        ),
                        f_dest,
                    ]
                )
            ),
            actions=[
                ft.TextButton(
                    "Annuler",
                    on_click=lambda ev:
                        close_dialog(send_dlg)
                ),
                ft.FilledButton(
                    "Envoyer",
                    on_click=do_send
                ),
            ]
        )
        page.show_dialog(send_dlg)

    def t5_choose_orientation(action):
        """Ouvre une pop-up de choix portrait/paysage,
        puis appelle t5_generate_pdfs ou t5_send_emails
        avec le mode choisi. action = 'generate' ou
        'email'."""

        mode_radio = ft.RadioGroup(
            value="portrait",
            content=ft.Column([
                ft.Radio(
                    value="portrait",
                    label="Portrait (1 palanquée par ligne)"
                ),
                ft.Radio(
                    value="paysage",
                    label="Paysage (3 palanquées par ligne)"
                ),
            ])
        )

        def valider(ev):
            mode = mode_radio.value or "portrait"
            close_dialog(orient_dlg)
            if action == "generate":
                t5_generate_pdfs(None, mode=mode)
            else:
                t5_send_emails(None, mode=mode)

        titre = (
            "📄 Générer les PDF"
            if action == "generate"
            else "✉️ Envoyer par email"
        )

        orient_dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(
                titre, weight=ft.FontWeight.BOLD
            ),
            content=ft.Container(
                width=_w(360),
                content=ft.Column(
                    tight=True,
                    spacing=10,
                    controls=[
                        ft.Text(
                            "Choisir l'orientation"
                            " du document :",
                            size=12
                        ),
                        mode_radio,
                    ]
                )
            ),
            actions=[
                ft.TextButton(
                    "Annuler",
                    on_click=lambda ev:
                        close_dialog(orient_dlg)
                ),
                ft.FilledButton(
                    "Continuer",
                    on_click=valider
                ),
            ]
        )
        page.show_dialog(orient_dlg)

    tab5 = ft.Container(

        expand=True,

        padding=15,

        content=ft.Column(

            expand=True,

            spacing=10,

            controls=[

                ft.Text(
                    "Générer les fiches de sécurité PDF"
                    " pour les plongées sélectionnées.",
                    italic=True, size=11, color="#64748b"
                ),

                # Barre d'actions
                ft.Row(
                    wrap=True,
                    controls=[
                        ft.FilledButton(
                            "💾 Enregistrer heures et DP",
                            bgcolor="#10b981", color="white",
                            on_click=t5_save_heures_dp
                        ),
                        ft.FilledButton(
                            "📄 Générer les PDF sélectionnés",
                            bgcolor="#ef4444", color="white",
                            on_click=lambda e:
                                t5_choose_orientation(
                                    "generate"
                                )
                        ),
                        ft.FilledButton(
                            "✉️ Envoyer par email",
                            bgcolor="#0ea5e9", color="white",
                            on_click=lambda e:
                                t5_choose_orientation(
                                    "email"
                                )
                        ),
                    ]
                ),

                # DP unique
                ft.Container(
                    bgcolor="#fffbeb",
                    border=ft.Border.all(1, "#fde68a"),
                    border_radius=6,
                    padding=10,
                    content=ft.Row(
                        wrap=True,
                        controls=[
                            ft.Text(
                                "DP unique :",
                                weight=ft.FontWeight.BOLD,
                                size=11
                            ),
                            t5_dp_unique_field,
                            ft.FilledButton(
                                "↓ Appliquer à toutes",
                                bgcolor="#f59e0b",
                                color="white",
                                on_click=t5_apply_dp_unique
                            ),
                        ]
                    )
                ),

                # Tableau scrollable
                ft.Container(
                    expand=True,
                    content=ft.Row(
                        expand=True,
                        scroll=ft.ScrollMode.AUTO,
                        controls=[t5_grid]
                    )
                ),

                t5_stats,
            ]
        )
    )

    # =================================================
    # CONTENU CENTRAL
    # =================================================

    content_area = ft.Container(

        expand=True,

        content=tab1
    )

    # =================================================
    # CHANGEMENT ONGLET
    # =================================================

    def on_tab_change(e):

        idx = e.control.selected_index

        # Si on QUITTE l'onglet 3, sauvegarder les
        # inscriptions automatiquement.
        if (
            state.get("current_tab") == 2
            and idx != 2
            and state["sortie_id"] is not None
        ):
            try:
                save_plongees_realisees(None)
            except Exception as err:
                print("Auto-save tab3:", err)

        state["current_tab"] = idx

        if idx == 0:
            content_area.content = tab1

        elif idx == 1:
            content_area.content = tab2

        elif idx == 2:
            content_area.content = tab3
            refresh_tab3_grid()

        elif idx == 3:
            content_area.content = tab4
            t4_refresh_combo()

        elif idx == 4:
            content_area.content = tab5
            refresh_tab5()

        page.update()

    # =================================================
    # TABS
    # =================================================

    tabs = ft.Tabs(

        length=5,

        selected_index=0,

        animation_duration=300,

        on_change=on_tab_change,

        content=ft.Column(

            controls=[

                ft.TabBar(

                    scrollable=True,

                    tabs=[

                        ft.Tab(label="1. Sortie"),

                        ft.Tab(label="2. Participants"),

                        ft.Tab(label="3. Plongées"),

                        ft.Tab(label="4. Palanquées"),

                        ft.Tab(label="5. Fiches"),
                    ]
                )
            ]
        )
    )

    # =================================================
    # AFFICHAGE PRINCIPAL — version mobile
    # =================================================

    # AppBar mobile compacte avec bouton menu (hamburger)
    page.appbar = ft.AppBar(
        leading=ft.IconButton(
            icon=ft.Icons.MENU,
            on_click=open_drawer,
            tooltip="Menu"
        ),
        title=ft.Text(
            "Sorties plongée",
            size=15,
            weight=ft.FontWeight.BOLD
        ),
        center_title=False,
        bgcolor="#1e3a5f",
        color="white",
        toolbar_height=52,
    )

    page.add(

        ft.Column(

            expand=True,

            spacing=8,

            scroll=ft.ScrollMode.AUTO,

            controls=[

                tabs,

                content_area,
            ]
        )
    )

    reload_plongeurs_club()
    update_stats_part()


# =====================================================
# LANCEMENT
# =====================================================
# IMPORTANT : sur Android/iOS, Flet IMPORTE ce module et
# n'exécute pas le bloc "if __name__ == '__main__'".
# L'appel à ft.run(main) doit donc se faire au niveau
# module pour que l'app démarre (sinon écran noir).

ft.run(main)