# Candidat Windows combiné — préparation du 11 novembre 2026

**Préparé pour revue par le pilote principal. Aucun build Windows de cette
combinaison, aucune publication et aucun installateur de cadeau annoncés ici.**
Le dossier est indépendant des métadonnées historiques Source24 et Library76.
`source.json` donne le commit et l'arbre exacts à reconstruire ; ce fichier
prévaut sur tout identifiant abrégé dans une discussion de développement.

## Sources et preuves conservées

- MuseScore Studio stable `v4.7.6`, commit
  `96480d58445e3b24b230a3fe7d4725d639aa2eb3`.
- Premier candidat bibliothèque seul `76b51af4` : application Windows 1001,
  huit groupes de stockage, 57 contrôles CLI et 35 comparaisons de référence.
  Le parcours du nouvel onglet reste à qualifier dans la GUI.
- AAC de production `0feb75b7` : dix tests natifs Windows x64 `/MD` et deux
  décodages externes réussis, run `43099012775`. Cette preuve porte sur le
  flux SDK et le helper PCM16, pas l'adaptateur Qt ni une partition exportée.
- Candidat bibliothèque + AAC avant ajouts de livraison :
  `cee591a36e65b7e7576b4651a5687a4ac37004f8`, arbre
  `b79a8eb783815d19e52b35ec662ca0c8742c3334`, conservé dans l'historique.
- zlib source 1.3.2 : composant natif MSVC `/MD`, 13 tests amont et un consommateur
  installé réussis, run 43101767743 / artifact 13891238030. Le lecteur 43104164329
  a vérifié 303 empreintes et 254 sources ; cette preuve ne qualifie pas encore
  l'application reconstruite. Le workflow récupère cet ID exact, reconstruit
  uniquement les fichiers source cachés omis par le transport depuis l'archive
  officielle conservée, puis vérifie le package avant de passer
  `Configure.ps1 -OpenSourceZlibPath`. Les pins sont dans le lock source.
- Le candidat reprend les preuves/documentations main et le nouvel écran de
  démarrage Cadence conditionnel. Son aspect reste à observer sous Windows.

Le helper de transport zlib est copié sans modification du lecteur qualifié ;
le dossier de destination est neuf et aucun fichier existant n'est écrasé.
L'archive source officielle complète reste fournie avec le composant. Le package
préparé complet est archivé en ZIP, avec les sources cachées restaurées ; ce
complément de sources est conservé avec le stage, les journaux et la livraison
expérimentale, sans être ajouté comme dépendance à installer pour l'ami.

Le backend FDK demeure le défaut de compilation. Ce nouveau parcours passe
**explicitement** `Configure.ps1 -UseWindowsSystemAac` ; les formats AAC et
vidéo restent enregistrés. La configuration réelle est vérifiée avant build,
y compris avec les unités Unity habituelles de l'amont, pour exclure FDK et
conserver les autres encodeurs et writers.

## Reconstruction et séparation des parcours

Bootstrap, copié sans changement du parcours déjà exécuté, vérifie le SHA-256
du correctif gzip, clone l'amont fixé, applique le correctif binaire, puis
contrôle l'arbre Git exact. Il consigne le commit CI synthétique distinct du
commit original et conserve `core.autocrlf=false` local au checkout. La
restauration du correctif sur un index Git isolé est également contrôlée lors
de la préparation locale du namespace ; aucun index de travail n'est remplacé.

Le sous-dossier `.gitattributes` force LF pour les textes et conserve le gzip
binaire. `source.json`, `handoff.json` et `SHA256SUMS.txt` identifient les octets
à relire. Les sources/codecs, sons, polices et notices gardent leurs licences
respectives ; l'option MF n'achève pas l'audit de redistribution des autres DLL.

Le workflow vise uniquement ses chemins et la branche de test
`cadence-studio/windows-build` ; son déclenchement manuel reste possible.
L'envoi par le responsable utilise le marqueur
`[cadence-packaging-only]`, qui évite la reconstruction de référence historique.
Aucun workflow existant, fichier Android, ancien correctif source ou ancien
artefact n'est remplacé. La préparation locale n'effectue aucun push.

## Recette préparée

Qt 6.10.2, MSVC 2022 x64, SDK 10.0.26100, CMake 3.31.6, Ninja 1.11.1 et
WiX 3.14.1 restent ceux du parcours existant. Numéro distinct :
`2000 + GITHUB_RUN_NUMBER`, avec refus au-delà de la plage MSI 16 bits.

1. Corpus, 30 tests Python/C++ portables, scripts et prérequis ; les contrôles
   C++ portables utilisent le compilateur GNU du runner, distinct du vrai build
   applicatif MSVC. Aucun test MSVC du flux natif n'est inféré de ces contrôles.
2. Huit groupes du stockage/XML de production avec QtCore/MSVC, puis vrais
   `Configure.ps1` et `Build.ps1`, profil MF explicite et graphe sans FDK.
3. Stage complet, source, provenance et SHA-256 conservés **avant** les recettes
   CLI, GUI et MSI pour permettre le diagnostic d'une étape ultérieure.
4. 57 contrôles CLI des formats existants, audit musical MusicXML et comparaison
   stricte des 35 sorties stables au corpus Windows de référence conservé.
5. Cinq véritables exports AAC de l'application sur des copies MSCZ vérifiées,
   chemins avec espaces et accents, puis décodage externe et contrôle ADTS,
   fréquence, durée, niveaux RMS et valeurs finies face aux WAV du même candidat.
   Les fichiers d'exemple sont originaux CC0 ; aucun contenu commercial ajouté.
6. Essai CLI négatif sans encodeur FFmpeg partagé chargé : erreur writer4, remappée par le converter au statut CLI1331, et
   diagnostic explicite requis, sans crash ni faux succès. Aucun encodage MP4 déduit.
7. Observation de l'ouverture/fermeture GUI, vrai MSI, installation, CLI installée,
   observation du lancement installé et désinstallation du ProductCode exact.

FFmpeg est uniquement un outil de contrôle du runner ; il ne remplace pas le
backend AAC de l'application et n'est pas ajouté à son installateur. Le
vérificateur refuse d'annoncer une recette applicative Windows sur Linux et
conserve un rapport d'échec explicite. Les contrôles synthétiques des checkers
sont décrits séparément dans `handoff.json` ; ils ne qualifient pas l'application.

## Limites encore présentes

Le contrôle musical AAC utilise initialement le débit 128 kbit/s et la fréquence
par défaut réellement produite, sans rééchantillonnage implicite. Les niveaux
et durées tolérés ne prouvent ni identité du signal ni lecture sans délai.
Les mesures globales ne valident pas encore l'équilibre de chaque canal.
Les autres débits, réglages du dialogue, annulation, erreurs d'écriture,
absence de MF, longues partitions et écoutes restent à qualifier.

La commande `--score-video` existe, mais l'encodeur vidéo charge cinq DLL
partagées FFmpeg (`avutil`, `avcodec`, `avformat`, `swscale`, `swresample`)
d'un fournisseur Windows enregistré ou d'une préférence de l'application.
Le loader actuel prend en charge FFmpeg 4 à 8. L'exécutable FFmpeg de contrôle
seul, notamment sa version 9, ne fournit pas ces DLL : aucun test MP4 avec son
n'est annoncé avant préparation d'un fournisseur partagé autorisé et fixé.
Les retours du muxeur, la piste AAC, les durées et la synchronisation devront
être contrôlés sur le vrai MP4.

Le nouvel onglet bibliothèque demande une recette interactive distincte ; la
fermeture GUI générique ne la remplace pas. Windows 10/11 client, impression,
accessibilité, contrôles visuels et audit final des notices/DLL restent requis.
Les artefacts expérimentaux expirent après 14 jours et peuvent nécessiter un
compte GitHub : ils ne sont pas le lien public du cadeau.
