# Client UIA : sons et parcours local, binaire Windows 2005 retenu

Ce lot prépare un test de la vraie application ; il ne modifie pas Cadence et ne
constitue pas un résultat Windows. Il attend le PID créé par le wrapper, dans un
runner Windows jetable avec profil Cadence neuf et copie du stage 2005 épinglée.
Le wrapper reste responsable des empreintes EXE/source, du processus enfant, du
profil, des sauvegardes et de la fermeture après le rapport.

```powershell
cl /nologo /std:c++17 /utf-8 /EHsc /W4 UiaProbe.cpp /Fe:UiaProbe.exe /link ole32.lib oleaut32.lib user32.lib uuid.lib
./UiaProbe.exe --pid 1234 --output C:/owned-runner-temp/tools-uia
```

Le répertoire de sortie doit exister, sans `uia-report.json`. Le client renvoie
0 seulement lorsque tous les contrôles requis sont réellement observés ; 2
signifie bloqué/incomplet, 1 une invocation refusée. Limite globale 140 secondes,
100 gestes maximum, timeout UIA 800/1000 ms. La phase sons a une sous-limite de
45 secondes pour réserver du temps au cours indépendant. Le wrapper doit imposer sa propre
limite finie supérieure et capturer sortie/erreur sans confondre un timeout avec
une réussite.

`UiaProbe.cpp` reprend le toolkit de `combined-next-gui/native/` ; les deux
headers Owned sont identiques octet pour octet, y compris la correction BSTR du
sélecteur natif. Le nouveau scénario est `ToolsFlow.inc`. Le sélecteur de fichiers
n’est jamais appelé par ce scénario. Toutes les touches vont au PID attendu,
avec fenêtre/focus Win32 vérifiés. Chaque transition directionnelle part d’un
libellé sémantique effectivement observé ; F6 sert uniquement à découvrir les
sections possédées. Les éléments ambigus sont refusés. Aucun clic par coordonnée,
champ produit injecté, plugin ou raccourci ouvrant directement un fichier.

## Deux parcours, dans cet ordre

1. **Collections sonores.** Sélectionner l’entrée native du menu Accueil.
   Observer `Télécharger 30.8 Mio · GeneralUser GS` sans l’activer : ce nom prouve
   à la fois l’offre facultative et sa taille affichée. Atteindre le bouton
   `Lire la licence complète · GeneralUser GS`, puis lire la valeur UIA réelle
   du champ de licence. Le texte doit contenir l’identité 2.0.3, la licence 2.0
   et son titre de section. Un label de bouton seul ne prouve pas la lecture de
   la licence. Aucun téléchargement, import, activation, dossier externe,
   désinstallation ou compte n’est demandé.
2. **Apprendre.** Ouvrir la page native et constater l’onglet `Parcours hors
   ligne`. Observer au focus les huit boutons d’exercices distincts, dans
   l’ordre du cours original ; les déplacements révèlent les cartes avec le
   mécanisme de défilement de l’application. Revenir sur le premier, puis
   activer seulement `Ouvrir l’exercice : Garder la pulsation`, en dernier.
   Le client exige un titre de fenêtre principale Qt possédée **changé après
   cette action**, portant `pulsation` (nom du fichier importé) ou `Garder la
   pulsation` (titre de l’œuvre). Le texte d’une carte du cours ne sert jamais
   de preuve d’éditeur. Une modalité ou un titre absent laisse le test bloqué.

Un échec d’observation de la page sons n’empêche pas l’essai du cours tant que
le contexte possédé reste utilisable. Une perte de focus/propriété provoquant
un refus du clavier arrête les gestes, par prudence. Le coach n’est pas exercé
dans ce lot (`coach_tested=false`) ; il reste une qualification séparée.

## Contrat du rapport

`uia-report.json` fournit `schema_version=1`, `pid`, `status`, `sounds_status`,
`lessons_status`, les observations brutes dans `actions` et `keyboard_frames`,
ainsi que les booléens suivants :

- `sounds_navigation_delivered`, `sounds_page_control_observed` ;
- `generaluser_offer_control_observed`, `generaluser_download_size_control_observed`,
  `generaluser_license_control_observed`, `generaluser_license_text_observed` ;
- `lessons_navigation_delivered`, `offline_lessons_tab_observed` ;
- `lesson_open_requested`, `lesson_editor_title_observed`.

`offline_lesson_count_observed` compte les vrais boutons successivement visités,
de 0 à 8. `lesson_editor_title`, `window_caption_before_exercise_open` et
`lesson_editor_window_class` conservent la preuve de fenêtre. La licence lue est
bornée à 8192 caractères ; son extrait conservé à 4096. Les arbres sont bornés à
1200 nœuds/18 niveaux. Les fichiers d’arbre homonymes représentent le dernier
instant de chaque phase ; les frames/actions conservent les transitions.

`bank_download_or_install_requested`, `account_or_purchase_action_requested`,
`coach_tested`, `musical_editing_tested`, `audio_playback_tested` et
`copy_files_verified_by_native_client` restent faux. La réussite native est
`passed_ui_controls_only`, et non une validation générale du produit.

## Corroboration requise après fermeture

Le bouton appelle le vrai `LearnPageModel::openLessonExercise()`, qui crée une
copie neuve avant de dispatcher l’action native `file-open`. Le wrapper doit
comparer les dossiers avant/après dans le vrai KnownFolder Documents :

`Documents/CadenceStudio4/Exercices/pulsation-<UUID>/pulsation.musicxml`

Un seul répertoire UUID neuf est attendu, contenant également
`LICENSE-CC0.txt`. Comparer les deux fichiers aux ressources du commit retenu
961, vérifier qu’aucun préexistant n’a été modifié et que l’exercice est
inscriptible. Le client ne fabrique ni répertoire ni partition et n’utilise pas
le chemin de cette copie pour ouvrir l’éditeur. Sans cette corroboration,
l’observation du titre reste une preuve UI limitée et aucune copie ne doit être
annoncée comme vérifiée. Un code 2 après création doit également être inspecté :
il peut signifier que la copie existe mais que l’éditeur n’a pas été observé.

Le wrapper doit conserver le stage original immuable et ne pas traiter ce
parcours avec Introduction éventuellement fermée/INI préparé comme un test du
premier lancement complet. Hors ligne signifie que ce parcours local ne demande
pas le réseau ; un runner connecté ne prouve pas à lui seul l’absence de trafic.

## Fermeture contrôlée de l’exercice importé

MusicXML est marqué modifié par le lecteur existant ; un simple WM_CLOSE peut
donc demander de sauvegarder la conversion. Après avoir capturé le vrai éditeur,
le wrapper lance le même client dans un **autre dossier de sortie neuf** :

```powershell
./UiaProbe.exe --pid 1234 --output C:/owned-runner-temp/close-uia --close-exercise true
```

Ce mode n’exécute pas les deux pages. Il exige la fenêtre principale Qt/QWindow
possédée, visible et activée, avec le titre `pulsation` ou `Garder la pulsation`,
puis lui poste un seul WM_CLOSE. Si le processus sort directement avec exit0,
aucune action de dialogue n’est inventée. Sinon, il ne peut agir que sur une
unique modalité possédée par cette fenêtre désormais désactivée, et son unique
bouton exact `Ne pas enregistrer`, `Don’t save` ou `Don't save` de type Button.
L’élément doit appartenir à l’arbre de cette modalité, avec PID et nom relus.
Le choix est livré par Invoke, ou par SetFocus + Return après comparaison du
focus UIA, avec la modalité au premier plan ; le garde clavier Owned inchangé
reçoit cette fenêtre activée, jamais la principale désactivée. Aucun Tab,
Enregistrer, Annuler, parcours inconnu ou arrêt forcé de l’application.

`close-report.json` contient `schema_version=1`, `pid`, `status`,
`close_requested`, `discard_control_observed`, `discard_delivered`,
`app_exit_observed`, `exit_code` (entier ou null), `initial_caption` et
`initial_window_class`. Il ajoute `owned_modal_observed`, le nom du bouton et la
méthode, ainsi que les observations brutes. Le code 0 et le statut
`closed_owned_exercise_exit0` exigent l’observation du vrai handle processus
terminé avec exit0, et, si une modalité a été observée, la livraison du bouton
exact. Une modalité inconnue reste bloquée même si elle disparaît ensuite.
La limite native est de 25 secondes ; le wrapper peut imposer 45 secondes puis
considérer tout fallback forcé comme un échec. Le wrapper vérifie également
l’ExitCode de son propre objet Process avant la corroboration des octets. Ce
mode ne sauvegarde pas l’exercice : XML et licence sont contrôlés après sortie.

Cette adaptation est préparée pour résoudre le blocage de fermeture du parcours
déjà demandé. Aucun SDK, COM, clic, dialogue ou test Windows de ce mode n’a été
exécuté localement ; sa compilation et son comportement restent à qualifier.

## Préparation réellement vérifiée

Les dix-neuf fichiers UI/ressources utilisés pour les libellés ont été relus depuis
`961c80b235d413dc9d123ea8f669ddb7f84ecd09` et comparés octet pour octet au
checkout de lecture ; leurs empreintes sont dans `source-ui-audit.json`. Les
headers Owned sont comparés à leurs originaux et les constantes du cours, du
SF2 et de sa licence ont été vérifiées contre ces données. Aucun SDK Windows
n’est disponible localement : ni compilation MSVC de ce nouveau client, ni
exécution UIA, ni ouverture Windows, ni écoute n’est revendiquée ici.
