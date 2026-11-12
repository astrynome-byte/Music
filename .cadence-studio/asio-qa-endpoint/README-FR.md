# Cadence QA Clock — endpoint ASIO de qualification

**Source non qualifiée : la première compilation Windows du [run 43211237239](https://github.com/astrynome-byte/Music/actions/runs/43211237239) a échoué avant la production de la DLL et l’exécution du harness.** Cause MSVC C2664 : `ASIOTimeStamp` et `ASIOSamples` sont deux structures distinctes dans le SDK exact. Le correctif écrit leurs mots hi/lo par un helper générique sans conversion de pointeur ; sa réexécution Windows reste attendue. Outil séparé de Cadence et de son installateur, destiné uniquement à un runner Windows x64 GitHub-hosted jetable. Il n’émet aucun son physique et ne valide pas une écoute, un matériel ou WASAPI.

Cette DLL COM fournit deux sorties Float32 little-endian, zéro entrée, des blocs de 256 frames et les fréquences 44 100 / 48 000 Hz. Une horloge `steady_clock` déclenche les vrais callbacks ASIO de l’hôte. Les deux moitiés de buffer sont remises à zéro avant chaque callback, puis les échantillons **écrits en sortie par l’hôte** sont agrégés après son retour : blocs/frames, nombre de valeurs finies/non nulles/non finies/écrêtées, pic et RMS. Aucun dump PCM, périphérique d’entrée ou donnée utilisateur n’est conservé. Ces mesures prouvent un chemin de rendu lorsqu’il est exercé ; elles ne sont pas une mesure de latence matérielle.

Le code des méthodes, la factory COM et le cycle de vie sont indépendants. Le sample BSD du SDK a été audité comme référence de contrat ; ses anciens helpers COM Microsoft ne sont pas copiés ni compilés. Seuls `asio.h`, `asiosys.h`, `iasiodrv.h` et leur licence originale proviennent du SDK exact 2.3.4 du 15 octobre 2025 (SHA de l’archive et de chaque fichier dans `asio-interfaces.lock.json`). La voie choisie est GPLv3 ; `LICENSE.txt` contient son texte. Aucune licence propriétaire, logo ou marque de sample n’est nécessaire à cet outil.

Identités QA propres, jamais celles du sample Steinberg :

- CLSID : `{8176CDA0-8AF9-4483-A03D-45EE2F9E864E}`.
- Interface de statistiques arrêtées : `{3D5B7D9F-1F8B-4249-9F1B-97B755EFD01F}`.
- Nom annoncé : `Cadence QA Clock (silent sink)` — aucune sortie physique.

## Cycle de vie et bornes

Le thread possède sa référence COM et une référence au module. Arrêt : événement Windows, fin du callback en cours, agrégation finale et journal borné, terminaison du thread, puis fermeture des handles/libération des buffers. Aucun `TerminateThread`. Un stop demandé depuis le callback signale l’arrêt et renvoie `ASE_InvalidMode` : il ne se joint pas lui-même ; le contrôleur termine ensuite le drain. `DllCanUnloadNow` refuse l’unload tant qu’objets, workers ou verrous de serveur existent. La libération finale du module sur le worker utilise `FreeLibraryAndExitThread` pour éviter un retour dans une DLL déchargée.

Un callback hôte bloqué ne peut pas être libéré de force en toute sécurité. `stop()` attend donc son drain ; **le processus de test externe** possède un délai de 45 s et peut arrêter tout son propre arbre de processus en échec. L’endpoint cesse de demander de nouveaux blocs après cinq minutes, sans prétendre pouvoir interrompre un callback bloqué. Le premier harness ne fait tourner chaque scénario que 60–180 ms. Une métrique JSON inférieure à 4 Kio est écrite par run arrêté, `CREATE_NEW`, sous un dossier existant strictement sous `RUNNER_TEMP`, sans reparse. L’initialisation refuse tout environnement qui n’est pas Windows x64 GitHub-hosted CI.

Le timer de test utilise un timer Windows haute résolution attendu avec l’événement d’arrêt, sans modifier la résolution globale de l’OS ; il comptabilise les blocs en retard et ne fournit aucune précision temps réel garantie dans une VM. Les handles sont fermés après le drain. Cible de cet outil seulement : Windows 10+ / runner Windows Server 2022 x64. Les callbacks doivent traiter les buffers directement (`ASIOTrue`), comme le chemin Cadence2002 audité. La prise en charge d’un autre hôte différant le remplissage n’est pas annoncée.

## Première compilation future, sans registre

Outils de développement du runner : MSVC x64, CMake 3.22+ et Ninja. Aucun SDK audio à télécharger par le job, les trois interfaces exactes sont dans la source. Après revue et publication par le responsable :

```powershell
./Build-And-Test.ps1 -SourcePath $PSScriptRoot `
  -WorkPath (Join-Path $env:RUNNER_TEMP 'cadence-qa-clock')
```

Le workflow préparé `cadence-asio-qa-endpoint.yml` ne construit pas Cadence, n’enregistre aucune classe et ne crée aucune clé. Le script vérifie tous les fichiers du manifeste source, conserve ce manifeste et une copie ZIP des sources/licences exactes à côté des éventuels binaires QA ; les empreintes de la DLL, du harness, du manifeste et du ZIP sont enregistrées. Le harness charge la DLL revue par son chemin explicite, obtient `DllGetClassObject`, crée `IASIO`, alloue deux buffers puis vérifie :

1. 44,1 kHz, callbacks simples, données connues ±0,25/±0,5 ;
2. 48 kHz, callbacks TimeInfo, mêmes mesures connues ;
3. 48 kHz, sortie silencieuse, pic/RMS nuls ;
4. 44,1 kHz, demande de stop depuis un callback, puis drain extérieur.

Chaque scénario vérifie aussi fréquences/blocs non acceptés, double allocation/démarrage refusés, compteurs, arrêt définitif des callbacks, métriques de **sortie**, fichier de rapport et unload final. Ce futur test direct vérifie l’ABI sans dépendre de l’énumération globale du système. Un appel réussi de factory n’est pas encore un test de `CoCreateInstance` par Cadence.

## Portée registre ultérieure et essai Cadence

Étape séparée, **non exécutée par le workflow actuel** : le SDK hôte de Cadence énumère `HKLM\SOFTWARE\ASIO`, puis active la classe via `CoCreateInstance`. HKCU seul n’est donc pas suffisant. `QaRegistryScope.psm1` prépare une fonction `Invoke-QaClockRegistryScope`, encore non exécutée sous Windows. Elle doit être revue avec ces règles :

1. Refuser toute machine hors runner natif x64 jetable et tout DLL/EXE dont les SHA ne sont pas ceux du lot revu ; profil Cadence et stats strictement sous `RUNNER_TEMP`.
2. Refuser des clés préexistantes pour `HKLM\SOFTWARE\ASIO\Cadence QA Clock (silent sink)` et `HKLM\SOFTWARE\Classes\CLSID\{8176CDA0-8AF9-4483-A03D-45EE2F9E864E}`, ainsi qu’un masquage COM du même CLSID sous `HKCU\Software\Classes\CLSID`, sans les modifier ni sauvegarder/écraser leurs valeurs.
3. Créer seulement ces clés, avec un marqueur d’appartenance aléatoire du run, chemin absolu de DLL et `InprocServer32` / `ThreadingModel=Both` ; suivre aussi un éventuel parent ASIO créé par ce run pour ne supprimer que ce parent encore vide.
4. Vérifier leur relecture exacte. Dans un `try`, appeler d’abord un harness `CoCreateInstance`, puis seulement l’EXE Cadence conservé avec SHA vérifié et profil propre sélectionnant explicitement ASIO/ce sink. Aucun changement du code applicatif requis.
5. Dans `finally`, fermer tous les processus QA possédés et attendre le drain ; supprimer seulement les clés dont le marqueur, valeurs et enfants correspondent toujours à cette portée. Refuser la suppression si un contenu étranger est apparu ; exposer l’échec de nettoyage dans la preuve. Relire ensuite leur absence.

Le helper vérifie la disposition native de création pour refuser une clé apparue entre vérification et création, marque seulement ses clés et contrôle récursivement valeurs/enfants avant leur suppression en `finally`. Le bloc d’action fourni par le futur wrapper **doit terminer/drainer ses processus possédés avant de rendre la main** ; ce module ne parcourt ni ne tue les autres processus de la machine. Le harness dispose d’un mode `--registered` supplémentaire exigeant la marque de portée en environnement ; il utilise alors `CoCreateInstance`. Dans les deux modes, il vérifie aussi que la vtable de l’interface créée appartient au module DLL explicitement chargé. Aucun de ces chemins enregistrés n’est exécuté par la première compilation/workflow directe. Leur vraie qualification Windows et le wrapper GUI restent à faire avant le second lot. Le présent incrément ne fournit aucun pilote système, service noyau ou dispositif Windows virtuel, ne demande aucun reboot/test-signing, et n’entre pas dans le MSI du cadeau.

Pour le test GUI ultérieur, la base Cadence2002 offre déjà une factory ASIO et le SDK hôte compilé selon les logs conservés. Les métriques du sink pourront permettre de tester lecture/tempo/boucles et comportement d’une ressource manquante avec le **vrai moteur**. L’activation directe du harness ne prouve pas encore ce parcours applicatif.

## Vérifications locales possibles

```sh
cmake -S . -B /tmp/cadence-qa-clock-metrics -DCADENCE_QA_PORTABLE_METRICS_ONLY=ON
cmake --build /tmp/cadence-qa-clock-metrics
ctest --test-dir /tmp/cadence-qa-clock-metrics --output-on-failure
```

Ce mode compile seulement le vrai agrégateur portable : silence, signal connu, NaN/infinis exclus et comptés, écrêtage. Il ne compile pas la DLL Windows ni ne simule sa validation. Les scripts PowerShell et le YAML peuvent être parsés sous Linux. Les résultats exacts se trouvent dans `checks/` ; un artefact Windows n’est pas annoncé avant sa production réelle.
