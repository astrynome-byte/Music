# Grand corpus Windows : préparation du smoke CLI

État : le premier [run Windows 43116435813](https://github.com/astrynome-byte/Music/actions/runs/43116435813), au commit pilote `87d60fd44c38ecfbd38bd04b9272053d1db1db33`, a exécuté la version et la sauvegarde MSCZ (codes retour zéro), puis s'est arrêté sur le validateur : celui-ci lisait `score_style.mss`, premier `rootfile` d'un MSCZ MuseScore 4, au lieu du membre `.mscx`. La correction sélectionne exactement le membre de partition déclaré pour chaque format et conserve tous les contrôles de structure ; elle attend une nouvelle exécution Windows. Les exports et les parties ne sont pas encore qualifiés par ce premier essai. Le pilote et le corpus occupent `.cadence-studio/large-qa/` ; le workflow court séparé `../cadence-large-qa.yml` occupe `.github/workflows/cadence-large-qa.yml`. Aucun fichier du projet Cadence principal n'est modifié.

Les mesures Windows du premier essai sont réelles : version 0,148833 s et pic working set 23 572 480 octets ; sauvegarde 4,264579 s et pic 141 504 512 octets, avec 86 requêtes mémoire et requête finale réussie. Elles ne prouvent pas la réussite de la suite interrompue. L'artifact de preuve est `13897479176`, SHA-256 ZIP `172aed44473c49cd7ee36e7cebe2d5a1142f117353a0c079e56dd60ff0365b77`, disponible dans le run lié.

La sélection concrète est le stage réel 1001 conservé dans `astrynome-byte/Music`, run `42793810996`, artifact `13755702885`, source `76b51af495b721776945717a812e1de2394a689a`, arbre `59d63e6f93b3bb7e8e5291cf57f57f9c5d61a06b`. Le SHA-256 exigé pour `bin/CadenceStudio4.exe` est `0aba4ced85a18a781c76c27f0072f2a761f7dee87f73610493887790f38fdb6a`. Le restaurateur déjà qualifié `../library-ui-probe/Restore-LibraryStage.ps1` et sa provenance `../library-source/` restent inchangés et sont nécessaires dans la branche pilote. Ils authentifient le manifeste, le ZIP et ses membres avant toute exécution. La date d'expiration annoncée de l'artifact est le 24 novembre 2026 : son absence bloque le téléchargement sans substitution.

Le candidat de source `0e05d04acbeee32f1b561f24493d7ef41c322081`, compilation `43108867145`, est seulement consigné dans `selection.json`. Ses identifiant d'artifact et SHA exécutable restent `null`. La réussite du smoke 1001 ne dépend pas de ce candidat et ne le qualifie pas. Une future adaptation devra disposer de son vrai stage terminé et de sa provenance authentifiée avant de mettre les pins à jour.

## Source et séquence réelles

`upstream_run_exports.py` est la copie exacte du harness `test/cadence/run_exports.py`, SHA-256 `f701874e7a37b8d3148f0bb99477b60b96865e804ed238372d75c06598027d82`. Le nouveau pilote importe ses fonctions `validate_fixtures` et `inspect_output`, et reprend ses commandes réelles en les entourant de mesures Windows et de contrôles supplémentaires. Le manifeste fourni sélectionne uniquement `large`. Le MusicXML original CC0 contient 16 parties de 256 mesures ; il est copié à l'identique, SHA-256 `9086e86d9f59334c4aa691ea3b30b63c1d04676e96aa58993fc53178e3ec500d`. La licence originale est conservée dans `fixtures/LICENSE.txt`. Le `.gitattributes` local impose LF aux textes, notamment au harness dont le hash est épinglé, et `-text` aux MusicXML pour préserver exactement leurs octets lors du checkout Windows, indépendamment de `core.autocrlf` et des attributs parents.

Après contrôle Windows natif x64 GitHub-hosted, vérification du record de restauration, des digests et du corpus, le pilote crée exclusivement de nouveaux résultats sous `RUNNER_TEMP`. Cadence reçoit une copie `large-input.musicxml` et les sorties natives générées ; le corpus source n'est jamais passé à Cadence ni réécrit. Le digest source et celui de la copie sont aussi vérifiés en fin de suite.

La séquence attendue comporte 22 contrôles, plus la commande `--long-version` vérifiant 4.7.6 :

1. Importer la copie par `--test-mode -o saved.mscz large-input.musicxml` et vérifier ZIP/CRC, conteneur, XML natif, 16 parties et 256 mesures sur chacune des 16 portées.
2. Rouvrir le MSCZ par `--test-mode -o reopened.mscx saved.mscz`, puis contrôler sa structure native.
3. Exporter PDF, MIDI et MXL par trois vrais jobs `--test-mode --sound-profile "MuseScore Basic" -j <format>-job.json`, chaque job utilisant `saved.mscz` comme entrée. Contrôler les en-têtes, la fin PDF, les chunks/tracks/end-of-track MIDI et le XML MusicXML complet dans le MXL. Les contrôles ZIP vérifient aussi les CRC.
4. Appeler `--score-parts -o native-parts.json saved.mscz` seulement après la sauvegarde native réussie. L'import MusicXML direct avec `--score-parts` ne fait pas partie de cette séquence. Exiger exactement 16 `parts` et 16 `partsBin`, décoder les vraies données base64 MSCZ et contrôler chaque ZIP et score natif monovoix instrumentale à une portée de 256 mesures.
5. Rouvrir chacun des 16 MSCZ de parties par `-o part-NN.pdf part-NN.mscz`, avec contrôle réel du PDF produit et code retour zéro.

Un échec de version ou de sauvegarde native interdit les commandes dépendantes. Un échec d'extraction ou de validation des parties interdit leurs réouvertures. Les autres échecs sont conservés dans le rapport. Il n'existe aucun test factice d'un exécutable Linux ou de commandes simulées.

## Ressources et preuves

Chaque processus Cadence reçoit uniquement `stage/bin;System32` dans son `PATH`, des répertoires `TEMP/TMP` de sortie et un environnement débarrassé des variables usuelles SDK, Qt/QML, proxy et credentials CI. Python 3.12 x64 utilise uniquement la bibliothèque standard ; aucun SDK, Qt ni dépendance Python ne sont installés pour Cadence.

La durée réelle `elapsed_seconds` est mesurée par `time.perf_counter()` juste avant la création et jusqu'à l'observation de fin du processus. Le polling peut retarder cette observation d'environ 50 ms, auxquels s'ajoutent les délais d'ordonnancement du système. La validation des fichiers est exclue de cette durée ; `stage_elapsed_seconds` conserve aussi la durée totale de l'étape. Une commande non lancée conserve une durée de processus `null`. Le pic mémoire réel est fourni en octets par `GetProcessMemoryInfo`, champ Windows `PROCESS_MEMORY_COUNTERS.PeakWorkingSetSize`, sur le handle CPython `Popen` du seul enfant détenu. Les interrogations ont lieu toutes les 50 ms et après la fin. Ce champ est le maximum historique du working set calculé par Windows jusqu'à l'interrogation réussie, pas un maximum de working sets instantanés échantillonnés. Le rapport conserve le nombre d'interrogations, leur dernière date relative, les erreurs et le succès de l'interrogation finale. Si celle-ci échoue, la couverture s'arrête à la dernière interrogation réussie et peut manquer la fin ; aucun pic n'est extrapolé. Une API absente bloque avant lancement, et un processus sans mesure disponible empêche la réussite de la suite.

Ces observations ne sont pas un objectif de performance, ne mesurent ni private bytes, ni mémoire totale de la machine, ni descendants, ni GPU, et ne peuvent pas être comparées automatiquement à la mesure Linux antérieure. Les processus principaux ont une limite individuelle de 180 s, la version 30 s, chaque PDF de partie 60 s ; le budget global de 17 min réduit les limites restantes pour laisser l'upload dans le job de 20 min. Un dépassement arrête uniquement l'enfant créé par ce pilote ; aucune recherche par nom, suppression d'un autre processus ou terminaison d'arbre n'est effectuée.

Les preuves comprennent `large-qa-report.json` UTF-8 sans BOM, `SHA256SUMS.txt`, les arguments exacts, PID, codes retour, timeouts, durées, pics mémoire et couverture, stdout/stderr distincts pour chaque commande, jobs JSON, MSCZ/MSCX/PDF/MIDI/MXL et 16 MSCZ/PDF de parties. Le rapport est également imprimé entre les marqueurs `CADENCE_LARGE_QA_REPORT_BEGIN/END`. L'upload est exécuté même en cas d'échec ou de blocage. Une restauration ou un téléchargement empêchés laissent leurs propres logs et aucun résultat applicatif n'est inventé.

La réussite exige 22 contrôles réellement exécutés et validés, la version, les mesures disponibles et l'intégrité de l'exécutable et des entrées. Les contrôles de fichiers ne prouvent ni mise en page correcte, ni fidélité musicale, ni gestes d'édition, ni lecture interactive, ni écoute. Aucun résultat GUI ou audio n'est revendiqué.

## Dépôt et invocation

Le payload préparé `../large-qa-payload.json` contient seulement les fichiers du namespace `.cadence-studio/large-qa/**` et `.github/workflows/cadence-large-qa.yml`. La variante `../large-qa-base64-payload.json` fournit les mêmes octets en base64 avec leurs SHA-256. Le push doit viser exclusivement ces chemins sur `cadence-studio/windows-build` ; ils sont les deux filtres stricts du workflow. `workflow_dispatch` est facultatif : sa disponibilité n'est pas garantie tant que GitHub ne reconnaît pas ce workflow sur une branche non par défaut. Les seules permissions GitHub sont `contents: read` et `actions: read`.

```powershell
& "$env:GITHUB_WORKSPACE/driver/.cadence-studio/large-qa/Run-LargeQa.ps1" `
  -StagePath "$env:RUNNER_TEMP/large-stage" `
  -RestorationRecordPath "$env:RUNNER_TEMP/large-qa-results/stage-restoration.json" `
  -OutputDirectory "$env:RUNNER_TEMP/large-qa-results/smoke"
```

`preparation-checks.json` décrit uniquement les contrôles locaux Python/PowerShell/YAML/UTF-8, les hashes du corpus et du harness, et le refus Linux avant écriture. Aucun push, téléchargement d'artifact ou lancement Windows n'est effectué par cette préparation.
