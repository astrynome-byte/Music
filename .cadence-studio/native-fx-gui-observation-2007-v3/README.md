# Observation F10 native non modifiante — source inactive, tentative4

Ce lot réutilise le namespace et le workflow V3. Aucun `target.json` actif,
nouveau workflow ou lancement Windows n’est créé ici. Le modèle séparé garde
`ready=false` et demande explicitement `native_f10_readonly=true`. La racine
relit les sources puis décide de son activation. Le mode sans argument du probe
reste strict : une projection UIA incomplète l’empêche toujours d’envoyer F10.

## Pourquoi ce mode distinct

Le diagnostic V3 réel (run43410673015/job131836055313) prouve un E_FAIL
`0x80004005` de `IUIAutomationTreeWalker.GetNextSiblingElement` dans le premier
snapshot. Le PID est bien possédé, aucune identité inconnue et aucune borne ou
cycle n’explique cette erreur. La copie s’ouvre, puis ferme0 ; clock et nettoyages
passent, mais0geste est envoyé. Ce résultat ne prouve pas qu’une touche F10 non
modifiante soit impossible. Il reste un échec d’accessibilité conservé.

Le contrat présent est plus étroit qu’une qualification UIA/NVDA : enregistrer
le graphe brut et sa première erreur, activer une fois le raccourci public F10
sur notre copie, capturer le résultat puis fermer proprement. Il n’annonce ni
complétude d’accessibilité, ni mixeur visible automatiquement, ni paramètres FX.

## Geste et preuves natives

Seul un argument exact `--native-f10-readonly`, transmis après vérification du
booléen de la cible revue, sélectionne ce mode. Sans ce flag, les conditions UIA
strictes demeurent. Aucune autre touche, saisie, Invoke, URI interne, édition,
sauvegarde ou récupération n’est ajoutée ; les helpers communs de clavier et de
clé secrète ne sont pas modifiés.

Le probe conserve le vrai PID/handle vivant, le chemin et le verrou SHA de
l’EXE2007. Après chaque lecture du provider et immédiatement avant l’insertion,
il exige le seul HWND principal possédé, visible, activé et sans modale, le
foreground sur ce HWND et un focus natif de ce PID dont la racine est ce HWND.
`GetGUIThreadInfo` doit confirmer ce focus ; les drapeaux de menu/déplacement et
les modificateurs doivent être absents. Une demande de foreground est bornée150ms,
comme celle déjà permise au helper ; aucun clic ou AttachThreadInput de secours.

Le vrai `SendOwnedKey` reste appelé une seule fois avec VK_F10. Il recontrôle
processus, fenêtre, foreground/focus et modificateurs au plus près de SendInput.
Les2événements doivent être envoyés ; les HWND capturés par ce helper doivent
correspondre au dernier échantillon natif. Tout résultat partiel ou changement
invalide la collecte, sans retry de touche. Les HWND/focus/flags sont consignés.
La fenêtre et le focus ne sont pas prouvés par une assertion HasKeyboardFocus UIA.

PID étranger, RuntimeId inconnu, dépassement du délai75s ou garde de graphe
(1200identités/3600arêtes/profondeur) restent bloquants. La première erreur et
`tree_incomplete=true` ne sont jamais effacés pour franchir la suite. Une erreur
de provider seule ne conditionne pas ce geste non modifiant si les preuves
natives sont réunies. Le statut distinct est
`native-F10-observation-collected-with-partial-UIA`, accompagné de
`UIA_complete=false`, `FX_parameter_qualified=false` et
`Mixer_automatically_qualified=false`. Les captures doivent être relues par la
racine pour constater réellement les canaux/Master ; aucun Mixer PASS automatique.

## Dépendances et fermeture conservées

Source application5058d29dad67e6131ee46ee617258ccfed8ba4b0 et EXE SHA
dcfbf9155c6c972c37966a4b2b0dcd212133c8e31fb397c644dda800ac7122be,
stage du run43266732201/artefact13970570430 ; endpoint silencieux du
run43212261044/artefact13941567509 et sa provenance restent identiques.
Le profil QA neuf règle explicitement la préférence publique de promotionfalse,
revérifiée après conversion CLI. Ce n’est pas une correction de l’application2007.

Copie MusicXML/MSCZ, EXE, captures avant/après, fermeture0, clock fini, absence de
kill, drainage Job et nettoyage KnownFolder/registre restent requis. Les rapports
et la première erreur sont affichés avant tout échec. L’upload reste limité aux
JSON/logs/copies/PNG/clock et provenance, sans stage ni archives ou binaires d’entrée.

## Trois échecs immuables et portée de préparation

1. Run43335448410 : promotion/cycle,0geste, application forcée−1, clock absent.
2. Run43405873102 : copie ouverte/close0/clock valide/0kill, mais projection UIA
   incomplète,0geste ; première API non enregistrée.
3. Run43410673015 : même fermeture propre et0geste ; GetNextSiblingElement E_FAIL
   est désormais prouvé. La tentative4 ne réétiquette aucun de ces résultats.

La préparation locale vérifie les copies/hashs, branches de mode, contrat
non modifiant, statuts des wrappers, métadonnées et parsing PowerShell/YAML.
Le helper de diagnostic reste celui déjà testé15assertions/sixJSON. Aucun essai
Windows de ce nouveau mode, écran du mixeur, NVDA ou écoute n’est revendiqué ici.
