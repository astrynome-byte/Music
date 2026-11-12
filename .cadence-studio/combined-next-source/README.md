# Cadence2003 — recette du candidat complet Windows

Ce snapshot se reconstruit à partir de `source.json` et `changes.patch.gz` :
référence officielle v4.7.6, commit source dérivé, arbre Git et SHA du patch y
sont fixés. Bootstrap vérifie le tag, les octets du patch et l'arbre reconstitué
avant de compiler. `handoff.json` décrit la préparation et `SHA256SUMS.txt`
inventorie les fichiers de ce namespace. La présence des métadonnées ne prouve
pas qu'un exécutable Windows2003 ait déjà été produit ou qualifié.

Ce namespace reste indépendant de `combined-source`0e05/treef95 et des artefacts
2002 retenus comme comparaison. Aucun de leurs fichiers n'est modifié.
Le workflow `cadence-combined-system-aac.yml` calcule2000+run_number ; le garde
explicite exige2003, donc le troisième run de ce workflow. Une relance du même
run conserve son numéro ; tout autre numéro demande une nouvelle revue.

La source intégrée5dfceb25d9995d2b6f5b9c5a4c7f57429fc41579 a réellement passé
13/13scénarios de stockage/collections/XML/watcher sur Windows Qt6.10.2,
MSVC2022x64 et SDK10.0.26100.0 (run43194829263). Les six fichiers de ce test ont
été vérifiés par SHA avant et après son exécution. Ce petit target QtCore ne
compile pas l'application et ne valide pas ses parcours GUI. Il est distinct
du précédent test FileID9/9 surbc3390 et du binaire2002.

Le plan du candidat exige34tests unitaires,13scénarios de stockage regroupés
dans un test CTest,57contrôles CLI,35comparaisons de sorties stables et5exports
AAC musicaux décodés par un outil externe. Ces comptes proviennent de la section
`qualification` du même `source.json` que le patch. Commit, arbre, référence et
SHA du patch doivent correspondre au résultat du Bootstrap ; les comptes sont
ensuite contrôlés dans les vrais journaux, sans zéro test, skip ou résumé partiel.
Le négatif vidéo exige code1331, zérooctet et diagnostic dans les seuls octets
de journaux frais. Le probe GUI doit observer Home/Intro et fermer ses propres
fenêtres. Chaque probe reçoit le SHA authentifié du nouveau build via
`CADENCE_QA_EXPECTED_EXECUTABLE_SHA256` ; aucun ancien EXE n'est substitué.

Le préflight GPL compare l'RTF de l'installateur à LICENSE.txt avec `--check`.
Le stage compilé est archivé puis retenu avant les qualifications de données,
avec l'étiquette expérimentale avant QA et sa provenance, pour permettre un
diagnostic ou réempaquetage sans reconstruire l'application. Le contrôle des
notices crée un projet CMake de données uniquement à partir des vraies règles
source et compare chaque texte attendu au stage, sans nombre constant. Le guide
français, GPL et inventaire sont exigés ; mnxdom.lib doit être absent.

Le bundle original du collecteur réussi43188835600/13929727718 est vérifié avant
Configure. Ses vrais paramètres sont enregistrés dans l'état du build ; le
même profil passe au contrôle CMake de notices et couvre les265textes et deux
métadonnées supplémentaires. Les archives originales restent dans un dossier
compagnon `corresponding-sources`, conservé avant QA puis copié dans la livraison
avant les SHA finaux. Elles sont exclues du runtime. Pendant l'essai MSI, les
textes réellement installés sont comparés au rapport SHA du stage avant la
désinstallation. Vérificateur et collecteur accompagnent la recette de reprise.

Les métadonnées VersionInfo/Authenticode des DLL et les informations du kit Qt
sont recueillies sans charger de code du stage ; seul qmake du développeur est
interrogé. Les archives complètes de l'application et du composantzlib, les
sources compagnons, la recette et les notices sont conservées. Leur présence
ne clôt pas l'audit de toutes les licences transitives. L'empreinte finale couvre
les fichiers livrés après les ajouts. Le nouveau full2003, son installation,
ses parcours GUI, contrôles visuels et écoutes restent à qualifier réellement.
Les artefacts GitHub sont expérimentaux, réservés aux accès GitHub et retenus
14jours ; ils ne constituent pas encore le lien cadeau public sans compte.
