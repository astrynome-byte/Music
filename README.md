# Music

Application Android de journal musical personnel, en Kotlin et Jetpack Compose. Cette version reprend le travail local existant ; elle fonctionne sans compte ni API externe.

## Fonctions disponibles

- **Journal** : ajout avec une émotion choisie, suppression, conservation locale et reprise des entrées de la première version. Une copie des données illisibles est conservée avant récupération.
- **Audio** : import par le sélecteur de fichiers Android, accès persistant lorsque le fournisseur l'autorise et lecture avec `MediaPlayer`. La lecture s'arrête lorsque l'application passe en arrière-plan. Un signal de démonstration synthétique de deux secondes est fourni pour essayer le parcours sans fichier externe.
- **Analyse audio réelle** : durée, énergie RMS et taux de passages par zéro des WAV PCM 16 bits, mono ou multicanaux, de 12 Mio maximum. Les autres formats peuvent être lus si Android les prend en charge, mais leur analyse affiche une limite explicite. Ce traitement ne prétend pas identifier les émotions, le tempo ou le genre d'un morceau.
- **Découvrir** : profil des émotions déclarées dans le journal et suggestions de genres par humeur. Le moteur est une règle locale déterministe, sans catalogue de morceaux ni modèle de recommandation distant.
- **YouTube / YouTube Music** : recherche externe, validation et normalisation des liens vidéo et ajout d'un lien au journal. L'ouverture utilise YouTube ou un navigateur installé ; si aucune application n'est disponible, un message est affiché.

## Limites et intégrations externes

Aucun résultat distant n'est inventé. Le mode de repli YouTube repose sur des liens publics : OAuth Google, playlists privées, métadonnées de la Data API et lecteur intégré ne sont pas implémentés. Il n'y a pas de téléchargement de vidéos ou de contournement des restrictions YouTube. Les fonctionnalités locales restent disponibles hors ligne ; les liens externes nécessitent une connexion et une application compatible.

Les émotions sont choisies par l'utilisateur. Les suggestions locales ne sont pas une analyse psychologique. Cette version n'est pas une publication Play Store signée avec une clé de production.

## Compiler et tester

Prérequis : JDK 17 ou 21, Android SDK 35, Build Tools 35.0.0. Gradle 8.13, Android Gradle Plugin 8.9.2 et Kotlin 2.1.20 sont fixés dans le dépôt. Android 8.0 (API 26) est la version minimale.

Ouvrir dans Android Studio ou définir `ANDROID_HOME`. Un `local.properties` ignoré par Git peut aussi contenir `sdk.dir=/chemin/du/sdk`.

```sh
./gradlew assembleDebug testDebugUnitTest lintDebug --no-daemon
```

Les tests couvrent les mesures sur un signal connu, les fichiers non pris en charge, la validation des liens, les recommandations, la migration et la récupération du journal. Les tests Robolectric lancent l'Activity et vérifient les quatre écrans Compose, la conservation du journal après recréation, l'analyse du signal fourni et l'intent d'ouverture YouTube. Ils utilisent un framework Android simulé sur JVM et ne remplacent pas les essais sur appareil, notamment pour le son, les fournisseurs de documents et les applications YouTube réelles.

La première exécution télécharge les dépendances et le framework Android de Robolectric. Le cache des tests utilise le dossier Gradle, accessible en écriture, et les paramètres proxy sont transmis au JVM de test lorsque présents.

- APK : `app/build/outputs/apk/debug/app-debug.apk`
- Tests : `app/build/reports/tests/testDebugUnitTest/index.html`
- Lint : `app/build/reports/lint-results-debug.html`

## Récupérer l'APK sur GitHub

Le workflow **Android** compile, teste et publie l'artefact **Music-debug-apk** sur les push de `main`, des branches `codex/**` et sur les pull requests. Dans l'onglet **Actions**, ouvrir une exécution réussie et télécharger cet artefact, puis extraire `app-debug.apk`. Les artefacts sont conservés 14 jours. La présence du workflow ne prouve pas qu'une exécution GitHub a déjà réussi ; consulter son résultat.

## Vérification sur appareil ou émulateur

```sh
adb devices
adb install -r app/build/outputs/apk/debug/app-debug.apk
adb shell am start -n com.astrynome.music/.MainActivity
```

Parcours à vérifier sur Android réel :

1. Ajouter un morceau dans Journal, fermer puis rouvrir l'application et vérifier sa présence.
2. Ouvrir Audio, lire puis analyser le signal fourni. Importer un WAV et un MP3 depuis un fournisseur de documents, puis relancer l'application et vérifier l'accès au fichier.
3. Passer en arrière-plan pendant un chargement ou une lecture : le son doit s'arrêter.
4. Ouvrir Découvrir, changer l'humeur et vérifier les suggestions et les compteurs.
5. Dans YouTube, chercher un morceau, ouvrir un lien valide et l'ajouter au journal. Un lien invalide doit désactiver l'ouverture.

## Environnement cloud existant

Réutiliser le dépôt `/workspace/Music` ; les tâches cloud sont déjà isolées, aucun worktree supplémentaire n'est nécessaire.

```sh
export JAVA_HOME=/workspace/tooling/jdk
export ANDROID_HOME=/workspace/tooling/android-sdk
export ANDROID_USER_HOME=/workspace/tooling/android-user
export GRADLE_USER_HOME=/workspace/tooling/gradle-home
export JAVA_TOOL_OPTIONS="-Djavax.net.ssl.trustStore=/etc/ssl/certs/java/cacerts"
export PATH="$JAVA_HOME/bin:$ANDROID_HOME/platform-tools:$PATH"
cd /workspace/Music
./gradlew assembleDebug testDebugUnitTest lintDebug --no-daemon
```

Les outils, caches et réglages proxy restent hors du dépôt. Ne pas versionner `local.properties`, les APK, les clés de signature ou des secrets. Aucun secret Google/YouTube n'est requis pour les parcours actuellement implémentés.
