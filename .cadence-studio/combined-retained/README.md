# Qualification et empaquetage du stage combiné 2002

**Préparé pour revue ; aucun MSI de cette qualification n'est encore produit.**
Ce parcours conserve les octets de la véritable application compilée dans le
run Windows `43108867145`. Il réemploie le mini-projet CPack/WiX du MSI 7,
les métadonnées et les cinq assets du nouvel arbre source. Il ne recompile
aucun module de Cadence et n'appelle pas `Build.ps1`, `cmake --build`,
`cmake --install` ou `windeployqt`.

## Ancres du programme conservé

- Source originale : `0e05d04acbeee32f1b561f24493d7ef41c322081`.
- Arbre exact : `f95b7097a55dddf9c7f697fc826b95721071231a`.
- Commit CI d'origine : `dbca5382bc029a2a6bb8c8eb761abb2c9294479c`.
- Stage : artifact `13898607081`, build 2002, run 2 / tentative 1, Qt 6.10.2 Release.
- EXE : 79 200 256 octets, SHA-256
  `35d8b076cacddb8b37a4f23aeea9899e6ab4ac9214e9a5b1125bbeccf26cf39e`.
- ZIP du payload : SHA-256
  `18bdda165ddcdef884949bf84ae398e6ee11619439161d4a1b84404edf307b46`.
- ZIP distinct des sources zlib complètes : SHA-256
  `7254e29e7c3aed673cd29d46353aa8ddd758b22b4b1ee41b6d4d194155b740ae`.

Les empreintes RAW des fichiers de provenance et de SHA256SUMS sont ancrées
dans le script, après lecture indépendante `43119684321`. Elles sont vérifiées
avant extraction/exécution. Le payload contient 2631 entrées, 359 771 381 octets
décompressés. Le ZIP des sources zlib reste séparé du répertoire installé.
Le script compare aussi les deux locks à leurs blobs Git LF : seule une
comparaison CRLF→LF en mémoire est permise, sans réécriture ni reserialization.

Le Bootstrap utilisé est celui de `.cadence-studio/combined-source/`, fixé à
cet arbre ; le namespace historique Source24 n'est jamais employé. Un nouveau
Bootstrap peut créer un autre commit CI synthétique. Les métadonnées originales,
son ancien commit dbca et ses chemins historiques sont conservés intacts.
`stage-verification-result.json` documente seulement la nouvelle localisation
de l'EXE pour les essais ; il ne prétend pas être un nouveau résultat Build.ps1.

## Parcours Windows prévu

Le workflow neuf `cadence-combined-retained.yml` utilise un runner Windows 2022
jetable, le SDK/MSVC 2022 x64, CMake 3.31.6, Ninja 1.11.1 et WiX 3.14.1. Il :

1. reconstruit et contrôle l'arbre original, puis télécharge le stage immuable ;
2. compile uniquement le petit client SDK de lecture UIA, pas l'application ;
3. vérifie les records RAW, les deux ZIP, PE AMD64, taille/empreinte EXE,
   version 4.7.6 et révision dbca dans un environnement sans chemins SDK ;
4. réemploie le vrai module CPack pour créer un MSI 4.7.6.2002 ; vérifie que
   tous les fichiers du payload sont inchangés après empaquetage ;
5. réexécute le cas vidéo indisponible en recueillant les nouveaux journaux
   des seuls profils Cadence ; exige 1331, zéro octet vidéo et le marqueur exact ;
6. installe réellement le MSI, vérifie l'EXE installé et son lancement sans SDK,
   observe Home/Intro, ferme proprement puis désinstalle ce seul ProductCode ;
7. observe également le stage conservé, imprime les rapports et retient les
   sources correspondantes, ZIP zlib, recettes et preuves pendant 14 jours.

Le ProductCode attendu est `6BF4BBA1-C7AA-5FCD-B5F2-14B7CF0D240C`, l'UpgradeCode
Cadence reste `319B992F-470A-465B-9A79-6B0CBFC7D6C7`. Aucun produit préexistant
n'est remplacé par cette recette : le test MSI refuse les installations liées
préexistantes et retire uniquement le ProductCode du MSI testé.

## Correction du contrôle vidéo, sans changement du programme

Les cinq AAC musicaux du build 2002 ont réussi : exports réels Qt à 44,1 kHz,
128 kbit/s, chemins accentués/espaces, ADTS et décodage externe comparés aux WAV.
Les 57 contrôles CLI et 35 comparaisons de référence sont aussi passés. La vidéo
négative avait déjà retourné 1331 en 0,875 s avec zéro octet, mais stdout/stderr
étaient vides. `globalmodule.cpp` active le log console uniquement en GUI ou
build debug ; une conversion Release écrit son diagnostic dans le fichier log.

`Test-VideoUnavailable.py` capture uniquement les fichiers nouveaux/modifiés
pendant son invocation dans `LOCALAPPDATA/CadenceStudio/{CadenceStudio4,
CadenceStudio4Development}/logs`. Un ancien marqueur ne peut pas valider un
nouvel essai. Aucun fournisseur, registre ou réglage n'est modifié par la sonde ;
l'application peut écrire normalement dans son propre profil Cadence. Le
marqueur `video_export_ffmpeg_unavailable`, le code 1331 et zéro octet restent
obligatoires. Aucun encodage MP4 ou échec Media Foundation n'en est déduit.

## Observation GUI et limites

`UiReadyProbe.cpp` lit seulement le PID détenu. Le splash seul ne réussit pas :
un contrôle Home/Accueil, Scores/Partitions ou Bibliothèque locale visible et
actif est exigé, ou une vraie introduction native appartenant au même PID et
liée à son propriétaire désactivé. Aucune navigation, saisie ou édition n'est
réalisée. Après lecture, la capture est cadrée sur une fenêtre du PID détenu ;
elle demande encore une inspection visuelle. Le wrapper ferme uniquement ses
fenêtres et exige une sortie 0 sans forçage. Il ne préinitialise pas le guide.

Les vérifications locales concernent la syntaxe et les gardes, la collecte de
logs nouveaux et le rejet des marqueurs anciens, ainsi que la configuration du
vrai module CPack sur Linux (version/GUID/règles d'installation vides). Aucun
MSI, test GUI ou test du nouveau client SDK Windows n'est inféré de ces checks.

La recette n'ajoute pas d'écoute humaine, de contrôle interactif de bibliothèque,
de MP4 avec son ou d'essai Windows 10/11 client. L'audit des licences/DLL et la
signature restent distincts. Les artefacts sont expérimentaux, peuvent demander
un compte GitHub et expirent après 14 jours : ce n'est pas le lien du cadeau.
