# Windows QtCore : filtre de métadonnées et surveillance native

Source réelle a07bd3af9bd8ba328363ccac80aaf77311433413 ; six fichiers exacts
identifiés dans source-manifest.json. Cette cible compile le vrai store,
le helper de métadonnées/surveillance et ses neuf groupes de tests ; elle ne
construit ni ne lance Cadence complet. Le namespace ancien reste dans les
commits de l'historique ; localcatalogsnapshot.h n'est plus compilé ni publié.

L'ancien run43126537489 avait zéro job, à cause de fichiers base64 littéraux.
Le run43178954921 a vérifié les six sources puis échoué avant C++ : lookup
PowerShell de deux installations CMake concaténé en faux chemin. Le correctif
Select-Object -First 1 est conservé pour CMake/Ninja/MSVC.
Le vrai run43179668680 a compilé mais donné8/9 : SHARE_DELETE ne permet pas le
remplacement Qt FileRenameInfo d'une cible ouverte. Cet échec est conservé ;
il n'est pas réétiqueté comme un défaut du pilote.

La correction actuelle n'ouvre plus de flux du catalogue pour filtrer les
notifications de répertoire. Les notifications de fichier forcent la relecture
même quand les métadonnées sont identiques et réarment la surveillance après
remplacement. QLockFile, QSaveFile, les fichiers de partitions et le schéma JSON
ne changent pas. Le neuvième groupe vérifie l'ancien refus sous Windows puis
QFileSystemWatcher réel : deux mutations atomiques de titres de même taille
avec date forcée identique, événements reçus, réarmement, favori, score intact
et filtrage de la seule activité du verrou.

Linux :9/9 groupes, modèle C++ON/OFF, génération MOC et C++ généré ON/OFF passent.
Windows : à exécuter pour ces nouvelles sources. Aucun résultat de la cible
QtCore ne valide gestes GUI, redémarrage, ouverture, édition musicale ou écoute.
Le job lit aussi quatre logs stdout/stderr du précédent runGUI11 ; ils ont été
observés vides et ne permettent pas une attribution exacte de son erreur.

Publication autorisée uniquement dans cadence-studio/windows-build ; commit
avec le marqueur `[cadence-packaging-only]`.
Le workflow inchangé est cadence-library-store-probe.yml. Les artifacts sont
expérimentaux et temporaires14jours, pas le lien de téléchargement du cadeau.
