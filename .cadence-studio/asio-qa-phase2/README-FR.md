# QA ASIO — activation enregistrée puis vrai projet GUI2002

**Phase2 préparée seulement : aucune clé, profil Windows ni application n’a été exécuté par cette préparation.** Elle réutilise des binaires précis déjà produits ; elle ne recompile pas Cadence et ne modifie ni son code ni son installateur. L’endpoint reste un sink silencieux de qualification, sans sortie physique, écoute ou matériel validé.

## Preuve native déjà obtenue, distincte de la phase2

Le [run direct 43212261044](https://github.com/astrynome-byte/Music/actions/runs/43212261044), commit `be392cc7fa98ff8b18c9d679eb55f42f49030f8c`, a réellement compilé puis exécuté le harness Windows x64 MSVC 19.44.35229.0. Ses quatre scénarios sont : 44,1 kHz/callback simple/signal connu ; 48 kHz/TimeInfo/signal connu ; 48 kHz/silence contrôlé ; 44,1 kHz/stop demandé depuis callback puis drain extérieur.

| Matériel réutilisé | Identité mesurée du producteur |
|---|---|
| DLL `CadenceQaClock.dll` | SHA256 `08f570d7df0dfb5f2cafe899c6b6679e48d4e1fa132656e58f4b0113a8709fd2` |
| Harness | SHA256 `adeea91ef5207b7425dfa90b8c412c23ca0d0e4ad9e99138b6dfe4778bcc9665` |
| Sources exactes du tool | ZIP SHA256 `5b9204779f64706191eba6428bb7eff1dc37885aa43e488178f38974a80442aa`, manifeste SHA256 `061c8801a4de0bb0546091226844fa999b81b02a47fdaeab63088c98bdfc98f3` |
| Artefact original | ID `13941567509`, 173 154 octets, digest GitHub `96657947191133d0d213aa684ddd549c228866cd7ddd098386c1b6279e0919e0`, expiration 26 novembre 2026 à 11:48:39 UTC |

Le téléchargement local de l’archive est bloqué par le proxy pour le domaine temporaire fourni par le connecteur. Le lecteur `Read-EndpointEvidence.py`, séparé et sans exécution de DLL, a réellement vérifié via Actions les quatre lignes originales, les quatre JSON arrêtés, les SHA réels et les dix-neuf membres des sources : [run43218548675](https://github.com/astrynome-byte/Music/actions/runs/43218548675), job131183894426, SUCCESS. Les comptes originaux sont 31/36/35/1 callbacks et 7936/9216/8960/256 frames ; les trois signaux connus donnent peak0,5/RMS0,395284708, le silence contrôlé0/0. Il s’agit d’une lecture des preuves du run natif, pas d’une nouvelle exécution du périphérique. Ne pas présenter le lien d’artefact expirant/éventuellement soumis à compte GitHub comme le lien du cadeau.

## Séquence proposée du workflow Windows

1. Télécharger l’artefact natif exact et en vérifier données, DLL/harness et sources avec le lecteur.
2. Télécharger le **stage**2002 du run `43108867145`, artefact `13898607081` (`cadence-combined-system-aac-stage-experimental-2-1`), vérifier tous ses membres et restaurer le ZIP interne SHA `18bdda165ddcdef884949bf84ae398e6ee11619439161d4a1b84404edf307b46`. EXE exigé : `35d8b076cacddb8b37a4f23aeea9899e6ab4ac9214e9a5b1125bbeccf26cf39e`, source0e05/treef95. Le petit artefact de logs du même run n’est pas le stage.
3. Ouvrir seulement la portée des clés QA décrites ci-dessous, puis lancer le harness binaire connu en mode `--registered`. Il passe réellement par `CoCreateInstance`, contrôle l’origine de la vtable dans la DLL attendue et doit refaire ses quatre scénarios avec quatre nouveaux rapports.
4. Créer le profil Cadence neuf par les vraies API KnownFolders, avec sélection explicite `ASIO` / `Cadence QA Clock (silent sink)` et première configuration déjà complétée pour ce test. Aucun test d’onboarding n’est revendiqué.
5. Ouvrir deux copies du même piano CC0 dans la vraie GUI : contrôle MS Basic, puis identité SoundFont absente. Chaque processus dispose de son propre dossier de statistiques sous `RUNNER_TEMP`. Exiger nom du driver et démarrage ASIO dans son log, plus de vrais callbacks dans ses rapports arrêtés.
6. Pour chaque même projet GUI : exporter réellement WAV, demander la sauvegarde native et observer son hook. Vérifier le WAV fini/non muet/non saturé et les fichiers MSCZ après sauvegarde ; le protocole ne remplace pas l’audio par un état « ready » ou un fichier vide.
7. Fermer seulement la fenêtre Qt du PID enfant possédé après le marqueur final, ou arrêter cet arbre possédé au timeout en déclarant l’échec. Drainer les processus avant de quitter l’action, nettoyer les seules clés marquées puis les seuls profils marqués, et relire leur absence.

`Invoke-Phase2.ps1` est le pilote. `cadence-asio-qa-phase2.yml` conserve les résultats réels même lors d’un échec. Une différence d’identité audio après sauvegarde est un échec de conservation à analyser, même si le rendu et les callbacks ont fonctionné ; aucun PASS partiel ne devient un PASS global.

Avant tout lancement, le contrôleur PowerShell rejoint son propre Windows Job anonyme imbriqué. Ses descendants héritent de cette portée sans course entre démarrage et assignation. Le Job refuse le breakaway et conserve `KILL_ON_JOB_CLOSE` jusqu’à une preuve que le seul processus actif restant est ce contrôleur. L’attente du PID Python seul ne constitue pas cette preuve : le pilote vérifie et draine le Job aussi après la fin du parent, avant l’EOF des transcriptions et avant toute suppression. Les contrôles registre et profil refusent leur suppression si ce drainage n’a pas réussi. Une terminaison forcée de descendant interdit le PASS global. La fermeture du Job est la dernière opération susceptible de concerner des processus ; un double-échec natif fermeture/réarmement reste explicitement non confirmé, échoue et exige la sortie du contrôleur. Ce mécanisme reste une préparation à qualifier sur Windows.

## Pourquoi le profil a une exception précise à RUNNER_TEMP

Le CLI retenu ne définit pas `--config-folder`. `Settings` utilise `QSettings` INI UserScope ; Qt6.10.2 obtient les chemins Windows avec `SHGetKnownFolderPath`. Changer seulement `APPDATA`/`LOCALAPPDATA` en environnement ne suffit donc pas. Le mode release gelé met `MUSE_APP_UNSTABLE` à OFF ; le nom d’application est `CadenceStudio4`, organisation `CadenceStudio`.

`profile-source-contract.json` garde les commits/SHA des sources Qt et Cadence effectivement lues. `CadenceProfileScope.py` dérive les chemins depuis les API à chaque opération, vérifie SID/intégrité/identité du job et refuse tout emplacement préexistant ou reparse. **L’unique élargissement de borne concerne trois racines de profil :**

- `KnownFolder(LocalAppData)/CadenceStudio` ;
- `KnownFolder(RoamingAppData)/CadenceStudio` ;
- `KnownFolder(Documents)/CadenceStudio4`.

Ces racines doivent être absentes avant création. Chacune reçoit un marqueur aléatoire immuable lié au record sous `RUNNER_TEMP` et à son identité de fichier. Les fallbacks QSettings d’organisation/machine sont seulement lus pour refuser un état préexistant ; rien dans ProgramData n’est écrit. Aucun profil existant n’est déplacé, sauvegardé puis écrasé, ou « restauré » à partir d’une supposition. DLL, stage, fixtures, partitions copiées, WAV, rapports et statistiques restent strictement sous `RUNNER_TEMP`.

`verify_record` accepte une INI réécrite normalement par Cadence, mais exige toujours les deux clés de sélection audio exactes et les marqueurs. `cleanup_record` peut nettoyer même si le test a altéré la sélection audio ; il exige encore identité/markers/arbre borné sans liens et ne supprime que les trois racines créées. Une interruption entre suppression du marker et rmdir peut laisser une racine que le helper refusera ensuite de supprimer automatiquement ; le job doit le signaler. Le helper ne découvre ni ne tue des processus tiers : le pilote termine d’abord les seuls processus qu’il a créés.

## Registre : portée neuve, vérifiée, nettoyée

Le SDK hôte de Cadence lit HKLM ASIO ; une inscription HKCU seule ne suffit pas. La portée réutilise le helper relu, ne lance pas regsvr32 et n’installe aucun pilote :

- `HKLM\SOFTWARE\ASIO\Cadence QA Clock (silent sink)` ;
- `HKLM\SOFTWARE\Classes\CLSID\{8176CDA0-8AF9-4483-A03D-45EE2F9E864E}` et son seul enfant `InprocServer32`.

Refus des deux clés préexistantes et d’un masquage du même CLSID sous HKCU avant toute mutation. La création native vérifie aussi sa disposition pour refuser une clé apparue après le préflight. Les clés créées portent un owner unique ; valeurs et enfants doivent correspondre exactement avant suppression inverse en `finally`. Un parent ASIO créé par ce run est retiré seulement s’il porte encore sa marque et ne contient plus d’enfants. Un contenu étranger ou un échec de nettoyage fait échouer le job. Aucun service noyau, reboot, test-signing, paiement ou installation chez l’ami.

## Extension de diagnostic et critères musicaux

La version reprise est le `Run-Retention.py` final du dossier `missing-resource-retention-next/run-2/parser-check`, avec URI corrigée `action://extensions/cadence/resource-retention-qa` et décodage strict QDebug puis JSON. Les hooks propres au profil observent six marqueurs portant le même nonce, titre et scoreName dans l’ordre : GUI_PROJECT → RENDER_RETURNED (`rendered=true`) → NATIVE_SAVE_REQUEST → NATIVE_SAVE_WITNESSED → NATIVE_SAVE_RETURNED → SCRIPT_FINISHED.

Le runner adapté ne change ni ce parser ni le mutateur/audio checker repris par SHA. Il ajoute le contrat de profil et les rapports du clock par processus. Les conditions comprennent : WAV vérifié par le vrai checker, score source/EXE/banque MS Basic inchangés, copie de travail réellement changée par sauvegarde, identité de ressource et état opaque conservés. Les métriques du sink sont rapportées séparément de celles du WAV ; elles ne constituent ni une écoute ni une validation de jeu interactif au clavier/MIDI.

## Vérifications et état avant publication

Revue registre indépendante de `qualification_resume` et `library_collections` : refus HKCU, disposition native, propriété et origine de vtable vérifiés sans défaut concret bloquant à la lecture. Une revue supplémentaire a détecté puis fait corriger le défaut de drainage avant cleanup. Helper profil écrit par un agent distinct puis relu indépendamment ; renforcement du type entier de schéma après détection de `True == 1`, corrigé. Douze tests Linux synthétiques du profil, trois contrôles du Job (parseur PowerShell réel, compilation C# sans API Windows, refus Linux) et deux cas du vrai AST de la garde cleanup avec faux objets passent. Ils ne simulent pas une qualification Windows. Les parsers PowerShell/Python et les checks de préparation restent séparés des exécutions natives attendues.

Le payload de phase2 ne doit être publié qu’une fois les pins/manifestes finalisés et relus. Les artefacts peuvent expirer : contrôler les dates et identités avant une reprise. La provenance du vrai full2005 reste prioritaire si son collector devient disponible ; ce test du stage2002 ne le remplace pas.
