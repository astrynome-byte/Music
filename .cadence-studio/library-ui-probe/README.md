# Inspection active du véritable onglet Bibliothèque locale

Correction préparée le 11 novembre 2026, **pas encore exécutée**. La probe
initiale a réellement compilé avec MSVC/SDK puis inspecté le stage dans le
run [43101086728](https://github.com/astrynome-byte/Music/actions/runs/43101086728).
Son résultat reste bloqué : trois arbres vides, aucune action, captures avant
et après identiques montrant uniquement l'écran de démarrage 800 × 380.
Le nettoyage a fermé proprement le processus (exit0, aucun arrêt forcé).
Les preuves ont été relues, sans réexécuter l'application, par le run
[43102505362](https://github.com/astrynome-byte/Music/actions/runs/43102505362).

Le lanceur attendait seulement le premier HWND visible ; la probe demandait
immédiatement l'onglet puis abandonnait si celui-ci était absent. La correction
attend désormais les contrôles sémantiques exacts Accueil/Partitions/Bibliothèque
et réessaie leur apparition sous la même limite globale de 55 secondes.
Les snapshots ajoutent HWND, titre, propriétaire, état et HRESULT de
`ElementFromHandle` afin de documenter un éventuel bridge inaccessible. Aucun
rôle ni nom de contrôle n'est élargi. L'onglet, les favoris et l'ouverture de
partitions restent **non validés** jusqu'à un nouveau résultat Windows réel.

## Application observée et restauration

Le workflow récupère uniquement l'artifact GitHub Actions13755702885 du
run42793810996 dans `astrynome-byte/Music`, avec le jeton court du workflow et
la permission `actions:read`. Cet artifact contient le **vrai stage1001** de
Cadence, source76b51af495b721776945717a812e1de2394a689a et arbre
59d63e6f93b3bb7e8e5291cf57f57f9c5d61a06b. Il n'y a ni installation de Qt de
développement ni reconstruction ou remplacement de l'application.

Le restaurateur impose archive/version/source/build et enregistre le manifeste
original, le résultat de build, les SHA-256 de l'archive interne et de l'exécutable.
Les checksums, cohérence des métadonnées, chemins ZIP et absence de traversée
ou de reparse point sont contrôlés avant lancement dans un dossier neuf du
runner. Le SHA externe de l'artifact connu est427ed2f9726dfd62c5c5c26b4942725f4b711a6a02f335cffe04802ba35c8166 ;
`actions/download-artifact` authentifie le téléchargement ciblé. Le restaurateur
ne prétend pas avoir rehashé un ZIP externe qu'il ne reçoit pas sous cette forme.

## Opérations prévues, strictement bornées

Le workflow Windows2022 compile **seulement le client UI Automation** C++17
avec MSVC2022/SDK10.0.26100.0. Il n'utilise pas d'assemblies .NET UIAutomation.
Le lanceur démarre lui-même l'exécutable restauré, retient son objet Process/PID,
assainit les chemins SDK de son environnement et refuse les applications de
partition déjà présentes. Il est limité à un runner Windows hébergé jetable
avec bureau interactif ; un profil personnel n'est pas réinitialisé.

Le client natif active COM UIA et exige `IUIAutomation2` pour ses délais
connexion800ms/transaction1000ms. Il inventorie uniquement les fenêtres du PID
lancé puis leurs contrôles, avec nom, type, AutomationId, PID et état. Les dumps
ont au plus1200nœuds et18niveaux ; une limite globale55secondes et un watchdog
de processus90secondes empêchent une inspection indéfinie. Les limites atteintes
restent visibles dans les rapports.

Avant la navigation, le seul dialogue fermé est **Introduction**, reconnu par
son titre, son propriétaire modal et le PID, revérifiés avant `WM_CLOSE`. Aucun
autre dialogue n'est accepté ou fermé pour poursuivre l'action. Si un autre
modal bloque la fenêtre, son arbre/capture restent une preuve de blocage.

Les seules actions sémantiques possibles sont les noms exacts Accueil/Home,
Partitions/Scores et Bibliothèque locale/Local library, via `SelectionItem`,
`Invoke` ou l'action par défaut `LegacyIAccessible` du bridge Qt. Un contrôle
ambigu, non visible, non activé ou attribué à un autre PID n'est pas invoqué.
La propriété du processus et de sa fenêtre principale est revérifiée immédiatement
avant chaque action. Aucune coordonnée souris ni séquence aveugle n'est
injectée. Les captures lisent les pixels du rectangle d'une fenêtre propriétaire,
sans simuler de clic.

Le succès de cette première étape exige l'action sémantique sur Bibliothèque
et l'observation de son bouton **Ajouter des partitions…** visible et activé
dans le même PID. Un retour d'Invoke seul ne suffit pas. Aucun fichier n'est
ajouté/ouvert/modifié, et favoris/réouverture ne sont pas encore testés.

Dans tous les cas, le lanceur demande ensuite la fermeture des seules fenêtres
du processus qu'il a créé, puis consigne sortie propre ou nettoyage forcé. Un
blocage UIA produit un rapport `blocked_*` et exit2 ; un nettoyage forcé ou une
erreur fait échouer le contrôle. Un workflow vert ne doit donc pas masquer un
onglet qui n'a pas été observé.

## Fichiers et résultats

Publier après revue uniquement ce namespace vers `.cadence-studio/library-ui-probe/`
et `../cadence-library-ui-probe.yml` vers `.github/workflows/cadence-library-ui-probe.yml`.
Utiliser le message `[cadence-packaging-only] Prepare retained local-library UIA probe`
pour éviter l'ancien workflow complet. Les autres sources, workflows, métadonnées
de compilation et branches restent inchangés par cette préparation.

Les rapports `stage-restoration.json`, `library-ui-report.json`, `uia-report.json`,
arbres `tree-*.json`, captures avant/après, sorties de l'application et log de
compilation sont retenus14jours. Les captures exigent une inspection humaine.
Il ne s'agit pas d'une release publique ni d'un lien de cadeau destiné à l'ami.

## Précondition du prochain essai : profil Cadence neuf après introduction

Le correctif d'attente a compilé et exécuté dans le run
[43103724152](https://github.com/astrynome-byte/Music/actions/runs/43103724152).
Il a observé la navigation réelle (Accueil), puis la fermeture de l'Introduction
a ouvert sa confirmation d'annulation. Le résultat est resté bloqué, avec
nettoyage propre : ni bibliothèque ni favoris n'ont été validés.

La préparation actuelle ajoute une **précondition de qualification après
introduction** : sur le seul runner Windows hébergé jetable, refuser tout
répertoire Cadence préexistant puis créer exclusivement
`%APPDATA%/CadenceStudio/CadenceStudio4.ini` avec
`application/hasCompletedFirstLaunchSetup=true`. Le dossier local Cadence doit
également être absent. L'INI est créé avec `CreateNew`, et son chemin, contenu
annoncé et SHA sont enregistrés. Aucun profil MuseScore n'est touché. Cette
précondition ne valide pas l'assistant du premier lancement et ne modifie pas
le produit1001. Ce nouvel essai de bibliothèque reste à exécuter.

## Navigation clavier préparée après le résultat du profil neuf

Le run [43105216308](https://github.com/astrynome-byte/Music/actions/runs/43105216308)
a réellement appliqué la précondition sans Introduction. Sa capture montre
l'accueil complet et l'onglet Bibliothèque locale, mais son arbre UIA ne contient
que les douze nœuds de fenêtre/barre principale. Le seul résultat d'action est
Accueil déjà sélectionné ; le test est resté bloqué, avec fermeture propre.

La préparation actuelle conserve le bridge et ajoute des gestes de navigation
issus de `src/app/configs/data/shortcuts.xml` (F6, Tab, flèches et Return).
Avant chaque touche, la fenêtre active ET le focus Win32 doivent appartenir
au processus lancé encore vivant ; une touche modificatrice déjà enfoncée
interdit l'envoi. Chaque geste conserve un arbre avant/après et des cadres
bornés dans le rapport. Au plus douze étapes, six F6, deux Tab et deux flèches
droites sont permises, sous le même délai global55s. Tab n'est utilisé que
depuis le champ de recherche identifié, les flèches depuis les onglets connus.
Return exige que l'élément UIA au focus soit exactement celui de Bibliothèque
locale. Le succès exige toujours l'observation de son bouton Ajouter ; un
envoi de touche seul ne vaut pas validation. Cette version reste à compiler
et à exécuter sur Windows, sans reconstruction de l'application1001.

Le run [43108867149](https://github.com/astrynome-byte/Music/actions/runs/43108867149)
a depuis compilé le client et envoyé six F6 avec `input_count=2`, `error=0`,
foreground et focus du PID détenu. `UIAutomation.GetFocusedElement` a observé
successivement Accueil, Mes comptes puis **Panneau Partitions, Rechercher les
partitions récentes**. Le prédicat de recherche attendait un nom différent,
donc il a continué F6 au lieu de Tab. Le résultat est resté bloqué et l'app
s'est fermée proprement.

La préparation actuelle normalise exclusivement les préfixes de panneaux
connus du code/traductions amont et reconnaît le vrai nom de recherche. Elle
utilise aussi l'élément focalisé UIA, qui fonctionne malgré l'arbre partiel,
pour vérifier l'onglet avant Return puis le bouton Ajouter après Tab.
Le rapport distingue explicitement ce canal d'observation de l'arbre global.
Elle reste à compiler et exécuter sur Windows. Aucun fichier n'est ajouté par
cette seule étape ; favoris, recherche de contenu et redémarrage restent à faire.
