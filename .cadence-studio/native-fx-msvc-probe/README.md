# Mini qualification Windows des effets natifs

Lot préparé uniquement : aucune publication, modification de l'application ou compilation complète n'est effectuée par ces fichiers.

Les huit fichiers de `source/` sont les nouveaux fichiers exacts extraits du correctif candidat `native-fx.patch`, SHA-256 `3799741259937200e23fd859811c483719e4a18db448a29a61df4504545e71aa`. Le manifeste conserve chaque taille et empreinte. Aucun Qt, SDK VST, instrument externe ou téléchargement de dépendance musicale n'est nécessaire. Les mentions GPL-3.0-only des sources restent présentes.

Le workflow, limité à un push de son propre namespace sur `cadence-studio/windows-build`, utilise `windows-2022`, Visual Studio 2022, la plateforme `x64`, la configuration `Release` et C++17. Il possède uniquement `contents: read`. Il compile les deux cibles existantes `native_fx_dsp_tests` et `native_fx_config_tests`, puis exécute réellement CTest avec leurs deux noms exacts et refuse zéro test. Le rapport ne devient positif que si les deux tests ont été exécutés avec succès. Aucun nouveau test reflétant artificiellement l'implémentation n'est ajouté.

Commande manuelle dans un environnement Windows x64 avec Visual Studio 2022 et CMake déjà installés :

```powershell
./Run-NativeFxMsvc.ps1 -OutputDirectory "$env:TEMP/cadence-native-fx-msvc-nouveau"
```

Le répertoire de sortie doit être inexistant. Les sources sont vérifiées avant compilation. Le runner conserve les commandes et codes de retour, sorties compilateur/CTest, rapport JUnit, empreintes des deux exécutables de test et identités du workflow et du correctif. Le workflow conserve ces preuves pendant quatorze jours, même après échec. Les exécutables sont des tests techniques, pas l'application cadeau ni un installateur.

Vérification locale réellement effectuée sur la nouvelle extraction : CMake/Ninja en Release avec GNU sous Linux, CTest 2/2, 48 contrôles DSP et 71 contrôles du codec réussis. Le vrai moteur PowerShell a parsé le runner et le bloc du workflow ; le YAML et son déclenchement restreint ont également été vérifiés. Les résultats locaux sont conservés hors payload dans `checks/`. Cette compilation Linux et le parsing ne prouvent pas une compilation MSVC : le premier job Windows devra encore s'exécuter.

La portée reste limitée aux noyaux DSP et au codec C++17. Ce job ne valide ni la factory audio intégrée, ni Qt/QML, les dialogues, les projets MSCZ, l'export audio complet, le matériel audio, l'écoute ou l'installateur. Il n'applique et ne modifie pas le correctif applicatif.

Le payload UTF-8 révisé contient quinze fichiers, dont une `.gitattributes` locale qui préserve les octets UTF-8/LF épinglés lors du checkout Windows. Les chemins de `SHA256SUMS` sont relatifs à la racine du dépôt pilote, car le workflow réside sous `.github/workflows/`. Le parent conserve la revue, la publication du workflow et la lecture des résultats Windows.

Le premier essai Windows `43225735271` s’est arrêté avant la compilation : le tri culturel `Sort-Object` ne correspondait pas à l’ordre ordinal de la liste attendue. La conversion de fins de lignes avait aussi changé le manifeste dans le checkout. La révision utilise un tri explicitement ordinal pour les chemins et noms de tests, et interdit la conversion de texte dans le seul dossier du probe. Les huit sources DSP/codec et leurs empreintes restent identiques au candidat.

Douze contrôles de données exécutent les vraies gardes extraites du script avec PowerShell sous Linux : trois cultures, un vrai checkout Git avec `core.autocrlf=true` et `core.eol=crlf`, acceptation des huit fichiers exacts, refus des chemins/casse/doublons/taille/hash modifiés et des tests non exécutés. Le manifeste conserve réellement son SHA-256 `281a00328d1c3587015adbdbb84e882f68939d31305ad35ae4c6982fb15916eb` dans ce checkout. Ces contrôles n’exécutent ni ne contournent le garde Windows, le compilateur MSVC ou la GUI. Les reçus locaux sont dans `checks/retry2-*` ; un nouvel essai Windows reste nécessaire.
