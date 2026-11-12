# Cadence2005 — recette du prochain candidat complet Windows

Ce namespace est indépendant de `combined-next-source`404 et
`combined-2004-source`053, tous deux conservés octet pour octet. Les fulls2003
et2004 se sont arrêtés avant le build de l'application ; aucun de leurs EXE ou
MSI n'a été produit. `combined-source`0e05 et les binaires2002 restent les
comparaisons retenues.

Le full2003 avait arrêté un checkout sale sans en imprimer les chemins ; ce
symptôme n'a pas été reproduit par le mini suivant. Le défaut PNG trouvé
séparément est corrigé et ses octets amont sont conservés. Le Bootstrap fixe
core.eol=lf et affiche des métadonnées bornées si un checkout sale récidive,
sans le corriger automatiquement ni renormaliser son index.

Le full2004 a passé son Bootstrap puis exécuté35tests, dont34réussis etun
échec de compilation du nouveau test TempoMap sous GNU Windows. Deux lignes
du harnais ajoutent les macros WIN32/UNICODE/_UNICODE normalement fournies
par CMake, pour GNU comme MSVC, en respectant CXX et les critères musicaux.
Le mini Windows43206351514 a réellement compilé puis passé1024propriétés
avec GNU g++ et les mêmes1024 avec MSVC cl (un test et quatre groupes PASS par
compilateur), sur le candidatfcec/tree0ea exact. Les six sources et l'arbre sont
restés inchangés. Aucun code musical de production n'est remplacé par ce
correctif du harnais et aucun nouvel EXE de l'application n'est encore déduit
de ce mini ; la suite complète35/35 Windows reste à exécuter dans le full.

`source.json` fixe la référence officielle v4.7.6, le commit et l'arbre dérivés,
et le SHA de `changes.patch.gz`. Bootstrap vérifie les octets et l'arbre avant
la compilation ; `handoff.json` et `SHA256SUMS.txt` complètent la recette.
La présence des métadonnées ne prouve pas qu'un nouveau build existe.
Le même workflow `cadence-combined-system-aac.yml` doit être son cinquième run :
2000+run_number est protégé par le garde2005. Toute autre valeur demande une
nouvelle revue ; une relance du même run conserve son identité.

Le test Windows13 intégré du run43194829263 appartient au code5df, avec six
fichiers vérifiés, Qt6.10.2, MSVC2022x64 et SDK10.0.26100.0. Il couvre stockage,
collections, XML et identités de fichier du watcher, sans compiler l'application
ou valider son GUI. Il est distinct du précédent test FileID9 surbc3390.

Le plan de cette recette exige35tests unitaires,13scénarios de stockage dans
un test CTest,57contrôles CLI,35sorties stables comparées et5exports AAC musicaux
avec décodage externe. Ces attentes viennent de la section `qualification` du
même source.json ; elles sont liées au résultat Bootstrap puis vérifiées dans
les vrais journaux, sans zéro test, skip ou résumé partiel. Le négatif vidéo
exige code1331, zérooctet et un diagnostic dans les seuls octets de journaux frais.
Le probe GUI doit observer Home/Intro et fermer ses propres fenêtres. Chaque
probe reçoit le SHA du nouveau build authentifié ; aucun ancien EXE n'est substitué.

Le GPL de l'installateur est vérifié par le rendu source --check. Le vrai stage
compilé est archivé et retenu avant la QA de données, avec provenance et statut
expérimental, pour faciliter un diagnostic ou réempaquetage sans reconstruire.
Les vraies règles CMake de notices déterminent les fichiers à comparer ; le
guide français, GPL, inventaire et originaux requis doivent être présents,
mnxdom.lib et les archives de sources compagnons doivent être absents du runtime.

Le bundle vérifié43188835600/13929727718 est contrôlé avant Configure et son
profil est enregistré/revalidé par Build/Package. Ses265notices et deux métadonnées
supplémentaires passent au même contrôle source CMake. Les archives originales
restent dans `corresponding-sources`, conservées avant QA et copiées dans la
livraison avant l'inventaire SHA final. Le MSI installé est contrôlé contre les
textes du stage pendant que le nouveau produit est installé, avant désinstallation.
Le vérificateur et le collecteur accompagnent la recette.

VersionInfo, signatures et métadonnées du kit Qt sont recueillis sans charger
les DLL du stage ; seul qmake du développeur est interrogé. Le dossier SDK sbom,
s'il existe, est conservé intégralement avec SHA sous des bornes explicites,
sans afficher ses gros textes. Son absence est signalée. Ces documents et les
sources ne clôturent pas à eux seuls l'audit de toutes les licences transitives.

Le full2005, son installation, les nouveaux parcours GUI, contrôles visuels et
écoutes restent à qualifier. Les artefacts GitHub sont expérimentaux, demandent
l'accès GitHub et expirent après14jours ; ce n'est pas le lien cadeau public.
