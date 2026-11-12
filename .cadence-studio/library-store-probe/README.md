# Stockage natif et collections — qualification Windows QtCore

Ce pilote compile six fichiers exacts du commit source indiqué dans
`source-manifest.json`, avec Qt6.10.2, MSVC2022x64 et SDK10.0.26100.0 sur un
runner GitHub Windows jetable. Le nombre de scénarios attendu vient du même
manifeste ; le vrai transcript doit contenir ce nombre de PASS et son résumé
complet. Le target CTest regroupe ces scénarios dans un seul test.

La source intégrée ajoute quatre scénarios de collections au socle de neuf :
migration v1→v2 explicite, noms/membres/ordre/relocalisation, données invalides
préservées et écritures concurrentes réelles. Les neuf cas existants couvrent
persistance Unicode, id/favoris, fichiers absents, collision, erreurs/permissions,
verrouillage et fusion, processus concurrents, garde XML et watcher réel.
Le watcher Windows énumère uniquement le dossier parent pour son identité de
fichier ; il n'ouvre aucun flux du catalogue pendant les changements de dossier.
Le cas natif exige deux remplacements atomiques de même taille/date, ID changé,
événement réel et réarmement. Les systèmes de fichiers sans identité exploitable
restent limités à la détection Qt/métadonnées et à Actualiser manuellement.

Ce petit binaire exécute les vraies classes de production ; il ne compile pas
l'application, n'exécute pas son GUI et ne valide pas les parcours d'édition.
Les hashes sont contrôlés avant et après les tests. Le code et les projets2002
retenus restent indépendants de ce pilote.

Historique conservé : erreur d'encodage du pilote43126537489 (aucun job),
lookup Get-Command multiple43178954921 (aucun C++ lancé), tentative de lecteur
SHARE_DELETE43179668680 (8/9, remplacement refusé), métadonnées sans lecteur
43184034438 (9/9), puis identité native du parent43188835467 (9/9 réels sur
Windows, commitbc3390). Ces réussites ne qualifient pas les nouveaux treize cas.
Leur état courant doit être lu dans les vrais résultats du nouveau run.

Les quatre anciens logs GUI demandés au run43123741624 ont été lus ; ils sont
vides, ce qui ne permet pas d'attribuer son LOGE original avec certitude.
La preuve du conflit et de sa correction vient des essais natifs ci-dessus.

Les artefacts GitHub restent expérimentaux, à accès GitHub et rétention14jours.
Ils ne constituent pas un lien de téléchargement cadeau sans compte.
