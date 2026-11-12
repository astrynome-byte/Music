# Diagnostic concurrent du watcher de bibliothèque

Préparé et non exécuté sous Windows. Aucun correctif applicatif n'est appliqué.
Le store et son helper de surveillance sont extraits du commit applicatif 2005
`961c80b235d413dc9d123ea8f669ddb7f84ecd09`, arbre
`c4780f1487559744fd4b2c2040b86ac37bb8c67b`, sans modification de leurs octets.

Le diagnostic compare, sur des fixtures créées pour lui :

- aucune surveillance, contrôle des échecs du store sans watcher ;
- fichier et répertoire parent, avec le vrai `watchLocalCatalog` de 2005 ;
- parent seul, sans aucune inscription du fichier, avec le même stamp/FileID.

Un worker distinct appelle les vraies transactions QLockFile/QSaveFile pendant
que la boucle Qt principale traite de vraies notifications et réarmements.
Chaque phase tente 2 000 mutations (activation des collections puis favoris),
avec budget de 30 secondes ; les nombres réellement tentés sont conservés.
Deux ordres inversés produisent six phases et séparent un effet d'ordre.
Les callbacks lisent uniquement le stamp de métadonnées/identité : aucun lecteur
de contenu du catalogue n'est ajouté. Validation du catalogue et empreinte du
score interviennent après join du worker et destruction/join du watcher.

Si tous les modes du Temp par défaut restent sans erreur sous Windows, les
six phases sont aussi exécutées dans des enfants atomiquement neufs du
LocalAppData renvoyé par QStandardPaths/les Known Folders Windows. Aucun dossier
Cadence existant n'est ouvert. QTemporaryDir possède et retire ces fixtures.
Avant d'armer chaque phase : volume, type de FS, attributs, permissions Qt,
état NTFS-permissions et descripteur de sécurité du dossier sont relevés.
Cela permet de comparer le Temp souvent sur D: au volume C: du profil GUI.
Les droits ne sont pas interrogés pendant les commits.

Le rapport distingue erreurs par mode/round/emplacement, événements observés,
callbacks chevauchant une transaction, changements de stamp, données préservées
et échantillons bornés d'erreurs. Le statut « expérience terminée » ne signifie
pas « correctif prouvé ». `selective_file_watch_conflict_observed` est vrai
uniquement si Windows observe des erreurs fichier+parent, aucune erreur du
contrôle sans watcher ou parent seul, des chevauchements et aucune altération
des données. Un résultat négatif conserve sa portée bornée ; il ne démontre
pas l'absence du défaut dans la GUI ou les causes possibles non exercées.

Lecture de Qt 6.10.2 : le thread Windows réinterroge PathInfo hors QLockFile,
et addPaths appelle QFileInfo.stat(). Toutefois ownerId/groupId sont constants
sur Windows ; fillPermissions utilise GetNamedSecurityInfo seulement lorsque
les vérifications NTFS sont activées, et sinon _waccess/attributs. Aucune
activation NTFS n'a été trouvée dans Cadence. Ces faits justifient la comparaison,
sans prouver qu'un handle ACL est la cause de l'AccessDenied observé en GUI.
Les sources Qt exactes examinées sont conservées localement sous qt-source/,
avec provenance d'archive ; elles ne sont pas nécessaires au mini exécutable.

Vérifications Linux : compilation C++17 stricte QtCore 6.8.2 réussie, six phases,
12 000 mutations, zéro erreur, données préservées et 31 458 callbacks chevauchant
les transactions. Le volet LocalAppData/ACL natif n'est pas compilé/exécuté par
ce contrôle Linux. Aucun succès Windows ou applicatif déduit. Le code a aussi
été relu pour les durées de vie/threads par qualification_resume, sans nouveau
défaut concret repéré. Le helper PowerShell et les deux blocs du workflow
passent le parseur ; gardes source/protocole réelles contrôlées sur Linux.

Le nouveau namespace CI est `.cadence-studio/library-watch-mode-stress`, avec
workflow `.github/workflows/cadence-library-watch-mode-stress.yml`. Il utilise
Qt 6.10.2/MSVC 17.14/SDK 26100, vérifie les cinq entrées de compilation avant
et après, et borne l'exécution totale à huit minutes. Tous les arbres sont
neufs ; les profils Cadence, sources applicatives et anciens namespaces restent
intacts. Aucun lancement/publication autonome n'a été effectué.
