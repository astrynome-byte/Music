# Ressource absente : rendu puis sauvegarde du même projet GUI

**Préparé ; aucun essai Windows de ce pilote encore exécuté.** Le stage réel2002
est repris sans reconstruction : source0e05d04a, arbre f95b7097…, EXE35d8b076…cf39e,
run43108867145/artifact13898607081. La restauration est la copie exacte du
vérificateur déjà utilisé ; les dix hashes bruts et le ZIP imbriqué sont épinglés.

## Pourquoi ce scénario

Le précédent QA sauvegardait une copie et exportait son audio dans deux projets
CLI distincts. Il ne prouvait pas qu'une identité absente restait stockée après
que le moteur avait appliqué son secours dans le même projet.

Le `-p plugin.qml` historique n'existe pas dans ce tag. `--test-case` force le
mode ConsoleApp, où ProjectModule n'initialise pas les actions de projet. Le
writer de notation utilisé par `api.engraving.writeScore(...,"mscz")` ne stocke
pas les réglages audio du projet : il n'est donc pas utilisé pour ce test.

Les17sources exactes examinées et leurs SHA figurent dans source-audit.json.
Il s'agit des fichiers du commit gelé2002, pas d'une hypothèse tirée de la seule
présence d'une API.

## Parcours réellement préparé

1. Refuser autre OS/architecture, environnement non GitHub-hosted, chemins hors
   RUNNER_TEMP et profils Cadence déjà présents ; vérifier EXE, source, fixture
   CC0 et MS Basic. Ne supprimer aucun profil utilisateur.
2. Créer uniquement le profil Cadence neuf du runner. L'introduction est
   explicitement déjà terminée : **onboarding non testé**. Une conversion CLI
   prépare la base native ; cette opération ne compte pas comme le test GUI.
3. Créer deux sources de test et deux nouvelles copies de résultat : contrôle
   MS Basic et SoundFont délibérément inexistante. Seuls les réglages audio
   sont injectés par le helper déjà qualifié, avec un état opaque synthétique.
4. Installer une extension de notation diagnostique originale dans le profil
   jetable. Deux points d'exécution amont sont configurés :
   `onpost_project_opened` et `onpost_project_saved`. Aucun plugin audio ni son
   payant n'est installé ou retiré.
5. Ouvrir chaque copie par **un seul processus GUI**, sans `-o`. Le hook garde
   le vrai `curScore` sélectionné, vérifie titre, nom de fichier contrôlé et deux portées, puis appelle
   `writeScore(score, fichier.wav, "wav")` : export audio réel du même projet.
   Après retour de ce rendu, `cmd("file-save")` appelle la sauvegarde native du
   projet, qui écrit ses `audiosettings.json`. Le deuxième hook témoigne de la
   fin effective de cette sauvegarde.
6. Exiger dans le nouveau journal, avec nonce unique, les marqueurs GUI, retour
   rendu, demande save, hook post-save, retour save et fin du script **dans cet
   ordre**, avec titre/nom de partition cohérents. Le WAV doit être non muet,
   fini et sans pleine échelle. Le cas absent exige le vrai diagnostic Fluid
   `Not found: <ID>` pendant ce seul processus, avant le retour du rendu et donc avant la sauvegarde.
7. Fermer uniquement l'unique fenêtre Qt Cadence visible, sans propriétaire et
   activable du PID enfant, après le marqueur de fin. Le PID est revérifié avant
   WM_CLOSE. Aucun clavier/souris n'est injecté et l'action globale `quit`
   (toutes instances par défaut) n'est jamais appelée.120s par enfant ; un
   timeout termine seulement son handle Popen et interdit tout PASS global.
8. Lire l'archive réellement sauvegardée ; comparer identité demandée et état
   opaque avec ce qui est désormais enregistré. Exiger hook natif, bytes de la
   copie modifiés et sources/EXE/banque inchangés. Les scripts/manifeste exacts
   du hook et tous les rapports/logs/copies/WAV restent dans l'artefact.

**La copie de résultat est créée avant l'ouverture GUI, puis véritablement
réenregistrée.** Ce n'est pas un Save As vers un chemin inexistant et ce n'est
pas l'export natif de notation. Le rapport l'indique explicitement.

## Portée et limites

C'est un test du **rendu audio puis save natif du même projet GUI**. Il ne
revendique pas de lecture interactive via la sortie physique, d'écoute humaine,
de message d'avertissement GUI ou de restauration d'un véritable plugin. L'état
opaque sert de sonde sérialisée ; sa conservation ne prouve pas la validité de
l'état d'un plugin réel. Son éventuelle perte doit être distinguée de celle de
l'identité de SoundFont.

Si un hook ne peut pas tourner, si l'export GUI est bloqué (périphérique absent,
API indisponible, dialogue…), ou si la fermeture échoue, le pilote garde un
résultat failed_or_blocked et les diagnostics. Ne pas attribuer automatiquement
ce résultat au produit. Si le rendu et la sauvegarde sont réellement prouvés
mais l'identité disparaît, les dictionnaires avant/après permettent de qualifier
le défaut AU15. Aucun changement produit n'est caché dans ce QA.

## Préparation locale

Sept vérifications passées : sources/helpers épinglés, scripts JS parsés,
contrat du vrai script avec API simulée (ordre et refus d'un autre score), garde
native réelle sous Linux avant toute sortie, YAML/permissions et parsing des
blocs PowerShell. Cela ne vaut pas exécution de l'extension ou de l'éditeur.
`preparation-checks.json` garde cette distinction.

Publier seulement ce namespace et cadence-resource-retention.yml sur la branche
Windows autorisée, avec `[cadence-packaging-only]`. Préserver combined-source0e,
main/Android, les lots Learn/Practice et tous les stages/installeurs conservés.
Les artefacts sont temporaires et peuvent exiger un compte ; pas de lien final
de cadeau ni nouvelle application produite par ce pilote.
