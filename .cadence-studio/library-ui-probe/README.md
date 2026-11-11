# Inspection active du véritable onglet Bibliothèque locale

Préparation du 11 novembre 2026, **sans publication ni lancement Windows**.
Le probe n'a pas encore été compilé avec le SDK Windows ; ce sera la première
étape native à vérifier dans ce workflow court. Aucun succès UIA n'est déduit
des tests de compilation/installation antérieurs de l'application.

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
avant chaque action. Aucune coordonnée souris, touche ou séquence aveugle n'est
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
