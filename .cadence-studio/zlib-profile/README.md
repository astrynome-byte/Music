# Profil zlib 1.3.2 depuis ses sources

État du **10 novembre 2026** : profil isolé préparé ; archive officielle vérifiée,
compilation statique GCC/Linux et tests réels réussis. Le workflow Windows est
prêt à être ajouté au dépôt pilote, mais **aucune compilation Windows de ce
profil n'est encore attestée**. Aucun fichier de MuseScore/Cadence n'a été modifié.

Le MSI du stage 7 qualifié dans le run `42721049351` utilise toujours le zlib
précompilé historique 1.2.8. Ce profil n'a été ni lié à ce programme, ni incorporé
à ce MSI. Une reconstruction complète de Cadence et de nouveaux essais de fichiers
seront nécessaires pour livrer le remplacement.

## Sources, version et licence vérifiées

- Dépôt officiel : <https://github.com/madler/zlib>.
- Version et archive : <https://github.com/madler/zlib/releases/tag/v1.3.2>,
  `zlib-1.3.2.tar.gz`, **1 502 830 octets**.
- Tag annoté `v1.3.2` : objet `216c70c020aa53f0c40920d155f808b6b59c9acb`,
  commit cible `da607da739fa6047df13e66a2af6b8bec7c2a498`.
- SHA-256 annoncé par l'API GitHub de l'éditeur et recalculé sur les octets reçus :
  `bb329a0a2cd0274d05519d61c667c062e06990d72e125ee2dfa8de64f0119d16`.
- Licence zlib autorisant usage et redistribution, conservée intégralement dans
  `LICENSE.zlib.txt` et dans l'archive source. Les scripts et tests de ce profil
  sont sous GPL v3 ; voir `LICENSE.txt`. Aucune vérification de signature PGP
  n'est revendiquée par ce profil.

`zlib.lock.json` fixe les sources et les options. L'archive de publication
officielle est la référence exacte des octets compilés ; le commit est la
correspondance du tag vérifiée à la source, pas l'affirmation d'un checkout Git.
Le fetcher contrôle SHA-256 et taille avant extraction et refuse un répertoire
de destination existant. Il n'exécute aucun script téléchargé avant cette
vérification et ne modifie pas les sources de l'éditeur.

## Construction native Windows du composant

Dans une console développeur **MSVC x64** et PowerShell 7, avec CMake **3.31.6**,
Ninja **1.11.1** et `dumpbin.exe` disponibles :

```powershell
./Build-Windows.ps1 -WorkPath 'C:\dev\zlib-source-profile-001'
# Variante hors ligne, avec l'archive officielle préalablement téléchargée :
./Build-Windows.ps1 -WorkPath 'C:\dev\zlib-source-profile-002' `
  -SourceArchivePath 'C:\downloads\zlib-1.3.2.tar.gz'
```

Le dossier doit être neuf ; aucun dossier utilisateur ni dépôt précompilé n'est
nettoyé ou écrasé. Le script configure **Ninja / Release / statique / CRT `/MD`**,
conserve l'API standard sans `Z_PREFIX`, lance la suite CTest amont entière,
installe dans `WorkPath/stage`, puis construit et exécute un consommateur contre
les fichiers installés. Le contrôle `dumpbin` doit constater x64 et le CRT `/MD`,
sans `/MT` ou `/MDd`. Un échec arrête la recette et laisse les logs et le manifeste.
Le workflow fixe `windows-2022`, Visual Studio 2022 / v143, SDK Windows
`10.0.26100.0`, Python 3.12 et `actions/checkout@v6`. La résolution des outils
sélectionne un seul premier exécutable avant d'accéder à `Source`, y compris
lorsque plusieurs installations de CMake sont présentes.

Les sorties principales sont :

- `stage/lib/zs.lib`, `stage/include/zlib.h`, `stage/include/zconf.h` et les fichiers
  CMake installés par zlib ; ces en-têtes et cette bibliothèque vont ensemble.
- `sources/zlib-1.3.2.tar.gz` original et sources extraites inchangées ;
  `source-file-sha256.json` et contrôle d'intégrité après les tests.
- `commands.log`, `commands.json` conservant les arguments exacts (y compris
  les chemins avec espaces), journaux de configuration/construction/tests/installation,
  rapports JUnit CTest et `zlib-profile-manifest.json` avec versions réellement
  observées du compilateur, CMake, Ninja, options et empreintes des artefacts.
- `LICENSE.zlib.txt`, lock et `SHA256SUMS.txt`.
- `profile-recipe/` conserve les scripts, le test de consommation, le correctif
  optionnel non appliqué et les notices du profil exact utilisé.

La suite indépendante vérifie l'égalité de version des en-têtes et de la
bibliothèque, un flux Deflate brut connu (`hello`), le CRC32 de `123456789`,
et les appels Deflate/Inflate bruts utilisés par les archives MSCZ/MXL. Elle
ne constitue pas une validation de l'application de notation.

`windows-zlib-profile.yml` est un workflow court, prêt pour le dépôt
pilote. Placer les fichiers de ce profil sous `.cadence-studio/zlib-profile/`
et le YAML sous `.github/workflows/cadence-zlib-windows.yml`. Il se déclenche
sur un push modifiant ces chemins dans `cadence-studio/windows-build`, ou par
déclenchement manuel lorsqu'il est accessible dans GitHub. Le commit de dépôt
pilote porte le marqueur `[cadence-packaging-only]` pour ne pas relancer la
construction complète. Le job est limité à 20 minutes. Il ne modifie pas le workflow de construction
de Cadence, ne reconstruit pas le stage 7 et ne publie aucun fichier. Ses artefacts
de composant demandent un accès GitHub et expirent après 14 jours.

## Future intégration ciblée, non appliquée

`integration/cadence-zlib-source-prefix.patch` est un correctif optionnel **non
appliqué**. Il remplace uniquement l'import de zlib utilisé par les archives,
lorsque `CADENCE_ZLIB_SOURCE_PREFIX` désigne le préfixe `stage` issu de la recette :

```powershell
# Dans un futur worktree Cadence destiné à qualifier le remplacement :
git apply --check C:\dev\zlib-profile\integration\cadence-zlib-source-prefix.patch
git apply C:\dev\zlib-profile\integration\cadence-zlib-source-prefix.patch
# Ajouter à la configuration de l'application :
# -DCADENCE_ZLIB_SOURCE_PREFIX=C:/dev/zlib-source-profile-001/stage
```

Le correctif garde le comportement historique lorsque le préfixe est vide,
refuse l'option pour `CADENCE_BUILD=OFF`, les configurations Debug et les
générateurs multi-configurations, et vérifie la présence des trois fichiers
ainsi que la version 1.3.2. Il ne mélange pas les en-têtes anciens 1.2.8 avec
`zs.lib`. Aucun renommage ou remplacement de `musescore_prebuild_win_deps` n'est
nécessaire. Ne définir ni `ZLIB_DLL`, ni `ZLIB_WINAPI`, ni `Z_PREFIX`, ni `Z_SOLO`.

L'audit du code n'a trouvé qu'un consommateur direct de cet import :
`framework/global/serialization/internal/zipcontainer.cpp`. Il utilise l'API
publique standard, sans MiniZip. Le module FreeType force `FT_DISABLE_ZLIB` et
utilise une copie interne séparée, dont les fonctions sont `static` : **ce profil
ne remplace pas le zlib 1.3.1 interne de FreeType**. Aucun composant libsndfile
supplémentaire n'est introduit.

Après le test Windows du composant : compiler référence et dérivé avec la même
partition de corpus, sauvegarder/réouvrir MSCZ, importer/exporter MXL, puis
contrôler palettes, espaces de travail et autres ZIP utilisés par Cadence.
Comparer le contenu décompressé et la mise en page : les octets compressés
peuvent changer malgré un contenu identique. Requalifier l'installateur et
conserver sources, commandes, bibliothèques exactes et notices de la version
effectivement distribuée. Les obligations des autres dépendances restent à suivre.

## Preuves locales et limites

`evidence/linux-results.json` et les journaux voisins attestent : GCC 14.2.0,
CMake 3.31.6, **16/16 tests CTest amont**, **1/1 test du consommateur installé**,
et **254 fichiers sources inchangés** après compilation et tests. L'archive
officielle de 1,5 Mo est conservée dans `evidence/`. Les deux tests de garde du
fetcher se lancent sans réseau :

```sh
CADENCE_CMAKE=/chemin/vers/cmake python3 -m unittest discover -s tests -p 'test_*.py' -v
```

Ils vérifient le refus d'une archive altérée avant création des sources et la
conservation d'un répertoire existant. Le répertoire `.local/` contient les
constructions locales seulement et n'est pas un livrable Windows. Aucun exécutable
Windows, aucune version de Cadence liée à zlib 1.3.2 et aucun lien public ne sont
annoncés par les résultats Linux.

`tests/Test-ToolPaths.ps1` charge par AST les vraies fonctions `Native` et
`ToolPath` du script, puis utilise deux commandes CMake homonymes dans des
chemins avec espaces. Il vérifie le choix du premier outil, les arguments,
les erreurs natives et les outils absents, sans exécuter la construction Windows.

Le run Windows `43094504840` a effectivement réussi ces gardes, puis son étape
a échoué avant construction : le test négatif laissait `LASTEXITCODE=9`, propagé
par l'enveloppe PowerShell de GitHub Actions malgré le message PASS. Le test
préserve maintenant l'état de sortie natif de l'appelant dans son `finally`.
Il ne force pas `exit 0`. `tests/test_ci_exit.py` reproduit l'enveloppe Actions
réelle et vérifie aussi qu'une vraie mauvaise sélection d'outil reste fatale.
Ces quatre tests locaux passent ; la compilation Windows du composant doit être
relancée pour qualifier cette correction. Les preuves ciblées sont dans
`evidence/guard-exit-reproduction.json` et `evidence/guard-exit-fix.json`.
