# Qualification Windows courte du lecteur de catalogue

Cette cible compile les véritables sources QtCore du store, du contrôle XML et
du lecteur d'empreinte, au commit `c2541128116014e512632da1656b140827acf4cd`.
Le manifeste vérifie les octets et SHA-256 de chacun des six fichiers avant
CMake. Aucun moteur, interface ou exécutable de remplacement n'est développé.
La compilation complète de Cadence n'est pas déclenchée par ce namespace.

Les huit scénarios antérieurs sont conservés. Le neuvième maintient un lecteur
ouvert pendant une vraie mutation :

1. Sous Windows, un `QFile` normal doit reproduire le refus de remplacement et
   préserver les octets du catalogue, sans boucle probabiliste.
2. Le même lecteur de production employé par le modèle doit autoriser le
   remplacement atomique ; son ancien snapshot reste cohérent et la nouvelle
   lecture retrouve le favori. La partition temporaire garde son empreinte.

Le résultat attendu est **9/9 sur Qt6.10.2 Windows**. Les neuf scénarios ont
déjà passé sous Linux/QtCore6.8.2, mais cela ne qualifie pas la branche Win32.
Un succès de cette cible ne vaut ni succès de l'interface bibliothèque, ni
test d'édition musicale, ni validation de l'installateur.

Le job lit aussi, sans lancer d'application, les stdout/stderr déjà retenus du
run GUI échoué43123741624, artifact13902286323. Le bandeau visible et le favori
restéfalse établissent l'anomalie ; ils ne suffisent pas à attribuer ce run
au conflit d'ouverture. Une ligne `Local library: <detail>` serait une preuve
supplémentaire. L'absence de détail dans ces logs doit rester explicite.

MSVC2022 x64, SDK10.0.26100.0 et Qt6.10.2 sont les outils de cette cible. Ils
ne constituent pas des dépendances nouvelles à installer par l'ami. Les
résultats/logs sont conservés14jours comme artefacts CI expérimentaux, pas
comme lien public du cadeau. Seul le parent publie ce pilote après revue.

Sources du défaut :

- [QFile Windows Qt6.10.2](https://github.com/qt/qtbase/blob/v6.10.2/src/corelib/io/qfsfileengine_win.cpp#L73)
  ouvre avec partage lecture/écriture, sans partage DELETE.
- [QFile::open(fd)](https://github.com/qt/qtbase/blob/v6.10.2/src/corelib/io/qfile.cpp#L1057)
  permet d'adopter le descripteur après ouverture native autorisant DELETE.

Les ajouts et copies de source gardent leurs mentions GPL-3.0-only. Les
sources correspondantes complètes de l'application restent dans le dépôt
produit ; ce petit jeu de test n'est pas une distribution installable.
