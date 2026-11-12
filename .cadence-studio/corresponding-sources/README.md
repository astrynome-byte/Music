# Sources correspondantes : matériel collecté, pas une approbation globale

Ce lot fournit des matériaux concrets pour la redistribution du dérivé Cadence.
Il ne compile ni n'exécute le code provenant des archives.

La collecte locale réelle du 12 novembre2026 comprend **11 archives originales,
156470661 octets**, toutes vérifiées par taille et SHA-256, et **265 fichiers de
notices/attributions :264 textes originaux byte-identiques et une attribution
MNX nom/version ajoutée**. Les métadonnées Qt
contiennent 103 entrées d'attribution ; chaque `LicenseFile`/`LicenseFiles`
déclaré a été trouvé. `local-source-bundle/` conserve les fichiers réels.

## Versions et périmètre

- Qt6.10.2 : qtbase, qtdeclarative, qtsvg, qt5compat, qtnetworkauth,
  qtshadertools. Les tags annotés officiels v6.10.2 ont été résolus en commits
  fixes, puis les archives à ces commits ont été téléchargées et hashées.
- VST3 SDK3.7.12 build20 et ASIO SDK2.3.4 du2025-10-15 : archives exactes du
  verrou de compilation, conservées intégralement, avec leurs notices propres.
- MNXDOM488aa8757ec602c20ff8cf599a2c6857339d8e93 et ses deux FetchContent
  réellement sélectionnés : nlohmann/json3.12.0 et json-schema-validator2.4.0
  au commit40af3ec39670e768fc3f01f935140af311d71024.
- Le snapshot W3C-MNX utilisé par le CMake est déjà dans l'archive MNXDOM ; ses50
  fichiers JSON sont comparés aux Gitblobs du snapshot d513cf7a… et sont identiques.
  Le footer original publie la W3C CLA : texte exact et attribution MNX1.0draft
  sont joints séparément, sans traiter ces données comme MIT.
  Les sous-modules de test262 et de présentation Doxygen sont explicitement
  suivis comme sources externes non nécessaires aux bibliothèques de ce profil.

`sources.lock.json` contient URL originale, racine d'archive, longueur et SHA.
`binary-source-map.json` associe les102binaires réellement inventoriés du stage
2002 aux modules et garde les origines non établies à part. Cela ne prétend pas
reconstituer le graphe des bibliothèques statiques à partir de seuls noms DLL.

## Licences

Le choix GPLv3 est retenu pour les fichiers Qt et SDK qui l'offrent, dans ce
dérivé GPLv3. Les tiers BSD/MIT et autres textes conservent leurs conditions.
Qt Network Authorization offre ici GPL-3.0-only en voie open source ; le lot ne
présente donc pas tout Qt comme LGPL. Les en-têtes représentatifs lus et leurs
SHA sont consignés dans la carte des binaires ; ce relevé ne remplace pas les
licences différentes de chaque fichier tiers.

Le collecteur copie les textes portant les noms LICENSE/COPYING/COPYRIGHT/
NOTICE/AUTHORS/OFL, les répertoires LICENSES et les fichiers référencés dans
les métadonnées `qt_attribution.json`. Les archives complètes originales
restent jointes. Certains JSON Qt contiennent des contrôles littéraux dans des
chaînes ; leurs octets ne sont pas modifiés, le mode de lecture permissif est
signalé dans le rapport.

## Exécuter et vérifier

Python3.12 et CMake sont des outils du développeur/collecteur, pas des prérequis
chez l'ami. CMake ne sert ici qu'à lire l'archive source7z du SDK VST3.

```sh
python -I collect.py --output /nouveau/dossier/sources
python -I verify_bundle.py --bundle /nouveau/dossier/sources
```

Pour utiliser les archives déjà conservées sans réseau : ajouter `--offline`
et un ou plusieurs `--cache /dossier/des/archives`. Aucun fichier de cache n'est
modifié. Le dossier de sortie doit être neuf. Les archives sont copiées avec
leurs octets d'origine, les textes avec leurs chemins, et `SHA256SUMS.txt`
couvre le contenu complet. Un hash, une longueur, une référence de licence ou
un membre inattendu manquant fait échouer la collecte.

Le workflow proposé ne publie pas de release ; il garde un artefact temporaire
14jours qui peut demander un compte GitHub. Ce n'est pas un lien public final.
Le message de commit doit inclure `[cadence-packaging-only]` pour éviter le
workflow historique de construction complète.

## Origines qui restent à établir concrètement

Les sources officielles Qt6.10.2 sont effectivement fournies. Le numéro de
version seul ne prouve pas les options/patches exacts des DLL binaires du kit.
Le petit `Collect-BinaryOrigins.ps1` relève les indices du kit installé :
qmake-query, mkspecs/qconfig, ABI/configurations CMake et SHA des DLL kit/stage.
Il relève aussi VersionInfo et signatures des DLL ICU, rendu OpenGL logiciel,
DXCompiler/DXIL/D3DCompiler et runtimes Microsoft. Il ne charge aucune DLL ni
l'application ; seul qmake, outil développeur déjà installé, est exécuté.
Le rapport reste de la preuve, pas une déduction automatique de licence.

Le profil garde `complete_distribution_ready=false` tant que ces correspondances
et termes de redistribution ne sont pas clos. L'option réelle
`--require-complete-distribution` refuse le profil avant tout téléchargement ou
écriture : elle ne transforme pas une collecte d'archives réussie en approbation
de livraison du cadeau. Les tests locaux conservent ce refus.

Les tests de collecte sont distincts de la recette Windows, des écoutes et de
l'installation de l'application. Aucun résultat de ce dossier ne valide ces
parcours produit.

## Installer les textes dans un prochain paquet Cadence

`optional-notices-install.patch` propose une extension du module d'installation
Cadence existant. Elle est réservée à `CADENCE_BUILD=ON` et reste inactive sans
chemin de bundle. Avec `CADENCE_CORRESPONDING_SOURCE_BUNDLE` et
`CADENCE_CORRESPONDING_SOURCE_REPORT_SHA256`, elle vérifie le lock connu, le
rapport authentifié, les11archives et les265textes avant de préparer leur
installation. Elle installe267fichiers (textes et deux métadonnées), **aucune
archive source ni outil de développement dans l'application**. Les archives
sources restent des fichiers compagnons de livraison.

L'expérience CMake réelle `project(NONE)` a installé les267fichiers en ON,
zéro en OFF ; chaque texte installé garde son SHA. Les contrôles négatifs
refusent un texte GPLv3 altéré ou un mauvais hash de rapport. Aucun MSI nouveau
n'est déduit de ces essais ; le patch est à intégrer puis tester avec le
prochain vrai paquet. Le dossier installé de59textes de base reste conservé.
