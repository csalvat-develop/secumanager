# Politique de confidentialité — Secu Manager

**Dernière mise à jour : [À COMPLÉTER PAR LA DATE DE PUBLICATION]**
**Éditeur de l'application : Cédric SALVAT**
**Contact : cs.develop@free.fr**


## 1. Présentation

Secu Manager est une application mobile destinée aux clubs de
plongée affiliés à la FFESSM. Elle permet d'organiser des sorties
de plongée, de gérer la composition des palanquées et de générer
des fiches de sécurité au format PDF.

Cette politique décrit quelles données sont traitées par
l'application, comment elles le sont, et les droits dont vous
disposez.


## 2. Données traitées par l'application

L'application traite les catégories de données suivantes, que
**vous saisissez vous-même** ou que **vous importez** depuis un
fichier de licenciés FFESSM :

- Identité des plongeurs : nom, prénom, date de naissance,
  numéro de licence FFESSM.
- Coordonnées : téléphone mobile, adresse email.
- Informations relatives à la pratique de la plongée : niveau,
  brevets obtenus, niveau préparé, type de licence, saison
  d'inscription.
- Données médicales liées à la pratique : date de validité du
  Certificat d'Absence de Contre-Indication (CACI).
- Données opérationnelles de la sortie : palanquées,
  profondeurs, durées, gaz utilisés, heures d'immersion.
- Paramètres techniques que vous configurez : logos pour les
  fiches PDF, identifiants de serveur d'envoi d'email (SMTP).


## 3. Où sont stockées vos données

**Toutes les données sont stockées localement sur votre
appareil**, dans une base de données SQLite située dans le
stockage privé de l'application (dossier inaccessible aux
autres applications).

L'éditeur de l'application n'a accès à aucune de ces données.
Aucune donnée n'est envoyée vers un serveur contrôlé par
l'éditeur, ni vers un tiers à l'initiative de l'application.


## 4. Cas où des données sortent de votre appareil

Les données ne quittent votre appareil que lorsque **vous
décidez explicitement** de les exporter ou de les transmettre.
Les opérations possibles sont :

- **Envoi par email** des fiches de sécurité PDF : la connexion
  se fait directement entre votre appareil et le serveur SMTP
  que vous avez configuré (par exemple votre boîte Gmail ou la
  boîte du club). L'éditeur de l'application n'intervient pas
  dans cette transmission. Le protocole utilisé est sécurisé
  (STARTTLS sur port 587 ou SSL sur port 465).

- **Partage de fichiers** (PDF, CSV, JSON, sauvegarde de base) :
  via le mécanisme de partage natif d'Android, vous choisissez
  vous-même la destination (Drive, Files, messagerie, etc.).

- **Export manuel** : vous pouvez exporter une sortie complète
  ou la base de données dans un fichier que vous gérez ensuite
  librement.

Dans tous les cas, vous êtes maître du transfert et de sa
destination.


## 5. Données collectées par l'application elle-même

L'application ne collecte aucune donnée d'analyse, de
télémétrie, de localisation ou de publicité. Elle n'utilise pas
de cookies ni d'identifiant publicitaire. Aucune permission
d'accès au réseau ou au stockage public n'est utilisée à des
fins de collecte.


## 6. Permissions Android utilisées

- **INTERNET** : nécessaire uniquement pour l'envoi des fiches
  par email via le serveur SMTP que vous configurez.
- **READ_EXTERNAL_STORAGE / READ_MEDIA_IMAGES** : nécessaires
  pour vous permettre de sélectionner manuellement un fichier
  de licenciés (XLSX, CSV) ou une image (logos) depuis votre
  appareil. Aucune lecture n'est effectuée sans votre action.


## 7. Durée de conservation

Les données restent sur votre appareil aussi longtemps que vous
le souhaitez. Vous pouvez à tout moment :

- Supprimer une sortie ou un participant depuis l'application.
- Vider l'intégralité du référentiel des plongeurs
  (« Paramètres → Vider la base des plongeurs »).
- Effacer la totalité des données de l'application
  (« Paramètres → Effacement total des données »).
- Désinstaller l'application : Android supprime alors
  l'ensemble de la base de données et des fichiers générés.


## 8. Vos droits (RGPD)

En tant qu'utilisateur résidant dans l'Union européenne, vous
disposez des droits prévus par le Règlement Général sur la
Protection des Données (RGPD) : accès, rectification,
effacement, portabilité, opposition, limitation.

Comme aucune donnée n'est transmise à l'éditeur, ces droits
s'exercent directement depuis votre appareil :

- **Accès et rectification** : via les menus de l'application.
- **Effacement partiel** : suppression d'une sortie ou d'un
  participant depuis l'application, ou suppression de
  l'ensemble du référentiel des plongeurs via
  « Paramètres → Vider la base des plongeurs ».
- **Effacement total** : la fonction
  « Paramètres → Effacement total des données » supprime
  définitivement l'intégralité des données de l'application
  (référentiel des plongeurs, sorties, palanquées, fiches de
  sécurité et configuration). Une confirmation explicite est
  demandée avant exécution.
- **Effacement complet alternatif** : la désinstallation de
  l'application entraîne la suppression par Android de toute la
  base de données et des fichiers générés.
- **Portabilité** : via la fonction d'export (sortie ou base).

Si vous saisissez ou importez des données concernant **d'autres
personnes** (membres de votre club par exemple), vous êtes
responsable du traitement de ces données vis-à-vis des personnes
concernées. L'application est un outil de gestion interne ;
elle ne vous dispense pas d'informer les personnes concernées
et d'obtenir leur consentement si la réglementation l'exige.


## 9. Données sensibles

L'application traite des informations relatives à l'aptitude
médicale à la pratique de la plongée (date de validité du
CACI). Bien que ces informations ne soient pas un dossier
médical complet, elles peuvent être considérées comme
sensibles. Elles restent strictement locales à votre appareil
et ne sont jamais transmises sans votre action explicite.


## 10. Sécurité

Les données sont stockées dans le stockage privé de
l'application Android, accessible uniquement par celle-ci.
Aucun chiffrement supplémentaire de la base n'est appliqué :
si vous souhaitez une protection renforcée, nous vous
recommandons de protéger votre appareil par un code d'accès
et de chiffrer le stockage Android (option système).


## 11. Modifications de la présente politique

Cette politique peut être mise à jour. La date en tête de
document indique la dernière version. Les modifications
significatives seront mentionnées dans les notes de version
de l'application.


## 12. Contact

Pour toute question concernant cette politique ou le
traitement de vos données par l'application :

- Email : cs.develop@free.fr
- Éditeur : Cédric SALVAT


## 13. Droit applicable

La présente politique est régie par le droit français. Tout
litige relèvera des juridictions françaises compétentes.