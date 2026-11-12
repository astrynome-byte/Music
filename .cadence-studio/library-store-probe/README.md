# Windows QtCore : identité du catalogue depuis son répertoire parent

Sources actuelles : commit bc3390c6365eb5a3e25311859898aad62f1efa95,
arbre f99d2d6a3c8fc757772d166e6beedc360102f44f. Les six fichiers exacts sont
copiés depuis les blobs Git, indépendamment des modifications futures du
worktree. Source-manifest.json et SHA256SUMS.txt identifient leurs octets.
Cette cible QtCore ne construit ni ne lance l'application Cadence complète.

## Historique conservé

- 43126537489 : zéro job, publication base64 littérale invalide.
- 43178954921 : six sources vérifiées et qmake6.10.2, échec avant C++ : lookup
  PowerShell de deux chemins CMake concaténé. Select-Object -First 1 corrige
  CMake/Ninja/MSVC et reste dans le pilote.
- 43179668680 : vraie compilation,8/9 ; SHARE_DELETE ne permet pas le
  remplacement Qt FileRenameInfo d'une cible de catalogue ouverte.
- 43184034438 : vrai9/9 sous Windows pour le filtre de métadonnées a07.
  Le backend Qt Windows filtre toutefois certaines notifications fichier par
  taille/date/permissions ; ce succès n'est pas une garantie de tous les cas
  où ces métadonnées seraient restaurées avant son observation.

## Nouvelle qualification à exécuter

Le helper Windows énumère le répertoire parent par
GetFileInformationByHandleEx, avec partage lecture/écriture/DELETE, handle RAII
et buffer borné64×16Kio. Il ajoute volume/id de l'entrée au filtre. Il n'ouvre
aucun flux du catalogue et ne change ni schéma, ni nom du verrou, ni QSaveFile.
Une identité différente déclenche la relecture sur directoryChanged même
lorsque le backend Qt supprime une notification fileChanged à propriétés égales.

Le neuvième groupe exige le refus de l'ancien lecteur sous Windows, puis deux
commits de titres de même taille avec date forcée identique, ID natif différent,
événement fichier OU répertoire significatif, réarmement, favori sauvegardé et
partition inchangée. L'activité des seuls verrous reste filtrée. Les huit autres
groupes de stockage/XML sont conservés.

Linux :9/9 et syntaxe du modèle ON/OFF passent pour les nouvelles sources.
La branche d'énumération Windows n'y est pas exécutée : elle doit compiler et
passer le vrai nouveau job avant qualification. Sur un système de fichiers ne
fournissant pas d'identité, un parent inaccessible ou une limite atteinte,
le repli utilise métadonnées/notifications Qt et le bouton Actualiser ; le cas
externe à métadonnées restaurées n'est alors pas garanti automatiquement.

Aucun résultat QtCore ne valide gestes GUI, redémarrage, ouverture de partition,
édition musicale, écoute ou installation. Les quatre stdout/stderr du précédent
runGUI11 ont été observés vides ; son erreur exacte n'est pas attribuée ici.
Publication réservée à cadence-studio/windows-build avec marqueur
`[cadence-packaging-only]`, sans main Android ni changement des stages1001/2002.
Artifacts temporaires14jours et potentiellement authentifiés, pas lien du cadeau.
