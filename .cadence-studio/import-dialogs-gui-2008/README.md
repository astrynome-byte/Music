# Pilote GUI des imports OMR et WAV — préparation privée

Aucune application 2008 n’a été exécutée par ce lot. Aucun build, EXE, archive,
identifiant d’artefact ou commit à venir n’est inventé : `target.template.json`
contient des valeurs nulles et le garde de lecture le refuse avant compilation,
profil, clavier ou démarrage de l’application. Ne pas publier ce lot avec ce
modèle comme cible utilisable.

Le pilote dérive de l’UiaProbe/OwnedKeyboard/OwnedFileDialog de Notes6
(`windows-private-notes-gui-2006-6`). Le Job possédé, son drain/fermeture et les
KnownFolders indépendants de Cadence sont ceux des qualifications précédentes,
repris avec leur inventaire. Aucun dossier MuseScore officiel n’est importé.
Il exige un job GUI distinct, dans une nouvelle VM Windows Server 2022 x64
GitHub hébergée jetable avec bureau interactif.
Les outils Python/MSVC/SDK servent uniquement à cette qualification, jamais à
l’installation de l’ami.

## Parcours initial obligatoire

1. Ouvrir le vrai binaire du stage 2008 authentifié, profil Cadence neuf avec
   première configuration préremplie et interface française. Ce n’est pas un
   essai de premier lancement vierge. Le PATH de l’application contient
   uniquement son bin et System32 ; les variables Qt/QML/SDK et jetons sont
   supprimées de son environnement enfant.
2. Depuis **Fichier**, ouvrir **Reconnaître un PDF ou une image…**, observer
   la vraie fenêtre et son contrôle **Choisir le document…**, puis conserver
   le dump UIA et une capture de son HWND possédé exact.
3. Ouvrir le sélecteur de source, vérifier le seul dialogue natif possédé et
   l’annuler avec Échap, sans sélectionner de fichier. Retrouver le contrôle
   source, observer les contrôles de choix Audiveris et de données OCR sans
   les invoquer, puis actionner **Fermer**. Vérifier que le dialogue disparaît et que
   la fenêtre principale est de nouveau active.
4. Répéter le même parcours avec **Transcrire un WAV monodique local…** et
   **Choisir un WAV…**. Observer tempo, grille, seuil et case d’accord sans
   modifier les valeurs ni cocher la case. Aucun moteur Audiveris, navigateur, banque, compte,
   export, MIDI ou fichier de partition n’est lancé dans cette première passe.
5. Fermer proprement le seul processus Cadence créé. Recueillir stdout/stderr
   et les journaux du seul profil neuf ; toute erreur QML recherchée maintient
   l’échec. Exiger clients 0, application 0, aucun kill, Job drainé puis profil
   nettoyé et Job fermé. Garder les preuves même sur échec.

Le menu QML cache Fichier en accessibilité avant sa navigation. Une seule
frappe Alt complète (appui/relâchement, sans chord) par phase d’ouverture active
le mécanisme réel `NavigableAppMenuModel`. Le pilote observe ensuite Fichier
et ne déclenche que l’item exact OMR/WAV, jamais une autre action rencontrée.
Les gestes conservent les contrôles de PID/poignée de processus, fenêtre,
focus/modificateurs et arrêt sur échec d’OwnedKeyboard. Aucun clic par position,
hook global, AttachThreadInput, URI interne ou dispatcher de test.

Le parcours WAV suit les indices réels du dialogue : Choisir et l’accord sont
en colonne -1, les paramètres et Fermer en colonne 0. PgDown rejoint le tempo
depuis Choisir, Home revient au premier contrôle unique avant Bas vers l’accord,
puis PgDown rejoint Fermer. Ces touches de navigation ont les mêmes gardes et
comptent dans la limite de 70 gestes par phase, avec au plus un Home et deux
PgDown par phase. Les noms et rôles attendus sont
revérifiés à chaque étape ; aucun réglage n’est modifié volontairement. Chaque
paire de dumps avant/après geste garde désormais son numéro au lieu d’écraser
la preuve du geste précédent. Le résultat de ce parcours reste à établir sous
Windows.

Les vues modales sont vérifiées avec leur titre exact et une chaîne de
propriétaires vers la fenêtre principale possédée. Elles utilisent leur propre
HWND activé pour les gestes, puisque leur parent principal est désactivé.
Les captures ciblent ce HWND, son titre et son rectangle vérifiés ; elles sont
les pixels originaux du bureau et demandent une revue visuelle ultérieure.
L’UIA de MuseScore peut n’exposer que le contrôle actif : les autres propriétés
et contrôles non exposés ne sont pas déclarés automatiquement validés.

## Deuxième passe facultative, seulement si la première est stable

Relancer le même lot avec `-AnalyzeFixture`. Après la première passe, il ouvre
à nouveau WAV, sélectionne par le vrai sélecteur natif l’unique copie locale
CC0, observe les réglages tempo/grille/bruit sans les changer, coche l’accord
sur la conversion approximative, puis actionne **Analyser**. Il attend que le
contrôle **Enregistrer le MIDI et ouvrir…** devienne disponible : ce contrôle
est lié au brouillon réel produit par le moteur. Il conserve une capture,
puis ferme le dialogue en abandonnant ce seul brouillon. Aucun MIDI n’est
sauvegardé et aucun son n’est écouté dans cette passe. L’annulation d’un calcul
en cours, trop bref sur ce fichier pour être déterministe, reste à qualifier.

L’entrée est un enregistrement original synthétique mono PCM16 16 kHz de
2,1 secondes : trois notes Mi4/Sol4/La4 avec silences, aucune banque commerciale.
Ses 67 244 octets sont fixés sous forme compressée/base64 et décodés avec taille,
SHA et format WAV vérifiés. L’original/copie est rehashé après l’essai.
Observer un brouillon n’établit pas l’exactitude musicale des notes reconnues :
la comparaison MIDI détaillée relève du harnais Windows du moteur audio.

## Préparation de la vraie cible

Une fois seulement le stage 2008 produit, remplir un `target.json` à partir des
preuves réelles : run/artefact/tentative, source originale et CI/arbre,
SHA de source.json et patch compressé, archive et EXE/tailles/SHA mesurés.
Le statut doit devenir `reviewed-produced-stage`. Le lecteur compare aussi les
sources gelées et exige le commit final déjà observé
`49272b75a4107c97130b8a46727af6a8c95d1c9a` / arbre
`fae79e265b3a21431388cd432a853228ffd7676b`, avec le patch compressé
`c7654d9a8fa18adf9bcce0b6198c1ef907a2e5886a19339a08ed8ccb80f7b70d`.
Ces identités source connues ne sont
pas une preuve de production du stage. Aucun champ ne doit être copié d’un
ancien build 2006/2007.

Réutiliser l’architecture de restauration Notes6 sur ce **vrai** artefact,
avec contrôle du manifeste original, des compagnons et de l’archive, avant
exécution. Son reçu doit conserver les mêmes champs de provenance et porter
`retained-actual2008-stage-restored-and-sha256-verified`, build2008 et le vrai
chemin restauré. Le lanceur exige ce reçu et ses liens à la cible/source/EXE.
Ce lot n’invente ni archive ni manifeste de stage pour contourner cette étape.

Le workflow complet privé `cadence-import-dialogs-gui-2008.yml` inclut désormais
le checkout, les gardes de vraie cible, l’authentification de la source
transportée, le téléchargement de l’artefact original, sa restauration,
le SDK du seul client indépendant puis le lanceur. Son déclencheur push vise
exclusivement `target.json` sur `cadence-studio/windows-build` ; le payload
initial ne contient pas ce fichier et ne déclenche donc aucun essai. Le
workflow ne dépend pas de la fin des exports/MSI du producteur. Le fragment reste
une référence des commandes du client et suppose la restauration déjà faite.
Le premier lancement doit rester sans `-AnalyzeFixture` ; conserver
`import-dialogs-gui-results/**`, les captures et le compile.log sur échec aussi,
via le pas upload-artifact présent dans le fragment. Le lecteur de preuves optionnel
imprime les deux premières PNG originales, avec taille et SHA vérifiés, ainsi
que le rapport resérialisé ; la lecture seule ne valide aucune interface.
La branche, publication et lancement appartiennent à la racine après revue.
La conversion du dict `files` en `tree_elements`, les chemins de publication
et les champs mesurés à remplir sont décrits dans `PUBLISHING-PREPARATION.md`.

Ce lot a seulement des contrôles statiques Linux/PowerShell et une vérification
réelle du fichier WAV. Le client C++ Windows n’est ni compilé ni exécuté ici.
Les erreurs d’accès/menu/nom UIA restent des échecs avec dumps, sans variation
silencieuse ni nouvelle tentative automatique.
