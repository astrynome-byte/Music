# Mini Windows : installateur VSCO natif, sans application complète

Préparé seulement, sans publication ni exécution Windows de ce lot.
Le candidat isolé est `13c68381fe81f57e09f892db00b014d9c1a09133`, arbre
`dda148ef004e17d038a443315eb4e975b1d9ef5e`, parent `ac9a2493` ; branche locale
`cadence/vsco-manager-candidate`. L’index principal et le worktree ne sont pas
modifiés. Le full 2007 et les installateurs conservés restent indépendants.

Le workflow neuf est `.github/workflows/cadence-vsco-installer-probe.yml`, son
espace de fichiers `.cadence-studio/vsco-installer-probe/`. Il réutilise le kit
et les blocs de preuves du précédent probe `free-sound-bank` : Windows Server
2022 x64 GitHub-hosted jetable, Qt **6.10.2** `qtbase` MSVC2022_64, MSVC
**17.14** x64, Windows SDK **10.0.26100.0**, Python **3.12**, CMake/Ninja.
Le rapport garde les versions réelles, chemins, noyau, empreintes du compilateur,
de QtCore/QtNetwork et des deux exécutables de test.

## Sources et sons

Les **huit** entrées de production/test/catalogue/licences sont extraites par
`git show` du candidat exact. Les **six** entrées du convertisseur sont identiques
à celles du pilote `1fbc211789c7698c4c191fa204ddbb00216209ec`, réellement exécuté
au run Windows **43231480145**. Elles comprennent son Python, son manifeste
source, les deux mappings et les textes CC0/GPL, sans modification de l’algorithme.
Le manifeste épingle ces **14 fichiers**, tailles et SHA-256. Son propre SHA est :

```text
a4e9812807b825d1c4e7023619b807ec090ae8d23e789589de007bacad6ffed6
```

Le workflow reconstruit les SF2 avec ce convertisseur inchangé, qui télécharge
les 43 WAV du commit VSCO `28092772094b2d9f1148d84cea97f4545b8c687d` et vérifie
chaque original avant usage. Les deux banques musicales et le contrôle de gain
sont ensuite rehashés contre les octets déjà qualifiés. Aucun son lourd ne
figure dans Git ou dans le payload.

Pour les 13 régressions préexistantes, la fixture GeneralUser est téléchargée
depuis son URL officielle fixée au commit `684543d5e5efaef08d02be50dcda8d552478fa60`
puis vérifiée : 32 319 396 octets,
`9575028c7a1f589f5770fccc8cff2734566af40cd26ed836944e9a5152688cfe`.
Cette préparation explicite ne constitue pas un téléchargement proposé sur les
nouvelles cartes VSCO et ne change pas leur état : **aucune URL publique des
SF2 Cadence n’est annoncée**.

## Vérification Windows préparée

`Run-VscoInstallerProbe.ps1` refuse une machine qui n’est pas un runner Windows
x64 hébergé, exige un dossier neuf sous `RUNNER_TEMP`, vérifie les sources
**avant et après**, puis configure uniquement les cibles du composant :

- `local_only_collection_tests` : **8 scénarios**, sur les deux vrais SF2.
  Ils vérifient l’URL absente acceptée pour l’import et réellement refusée pour
  le téléchargement avant dossier/progrès, les octets/licences/préréglages,
  les reçus, la reconnaissance persistante, la coexistence, le retrait limité,
  les fichiers erronés, dossiers/contenus existants, verrou, réentrance et
  politique HTTPS conservée.
- `free_collection_installer_tests` : **13 scénarios** sans `--download-real`.
  Ils comprennent l’annulation initiale et en cours de copie, la destruction,
  le redémarrage d’import réentrant, les contenus inconnus, le verrou et les
  reçus/empreintes. La quatorzième variante de téléchargement réel n’est pas
  exécutée dans ce mini.

Les deux processus doivent sortir à zéro, sans timeout, avec exactement
8 et 13 lignes `PASS:` et les résumés Qt **6.10.2** attendus. Les cinq fichiers
préparés, dont les deux banques, la licence et la fixture de régression, sont
vérifiés avant et après. Le manifeste des banques reconstruites reste inchangé.
La copie technique à −18 dB est vérifiée comme produit du convertisseur ;
elle n’est pas installée comme collection musicale.

Les installations de test se font uniquement dans des dossiers temporaires
possédés. Les banques témoins MS Basic et tierces des scénarios sont des
sentinelles de test ; aucun profil musical existant ou banque de l’utilisateur
n’est inspecté ou modifié. Les vrais fichiers SF2 d’entrée restent intacts.

## Preuves et limites

L’artefact de 14 jours retient les JSON/logs et manifestes uniquement, pas les
SF2, WAV ou une application. Les journaux impriment les blocs complets bornés
`CADENCE_FREE_SOUND_EVIDENCE_BEGIN/END`, avec `file`, `file_bytes`,
`printed_bytes`, `tail_only` et `text`, et le résumé
`CADENCE_FREE_INSTALLER_REPORT_BEGIN/END`. Un bloc tronqué est signalé.

Les contrôles locaux de préparation passent : parsing YAML et des trois blocs
PowerShell, manifeste réel des 14 sources, refus d’un fichier source modifié,
refus d’un vrai transcript Qt 6.8.2 comme preuve Qt 6.10.2, comptage exact des
résumés et refus de qualification native sous Linux avant écriture.
Les chaînes réétiquetées pour le parseur de protocole sont **synthétiques** ;
elles ne constituent aucune exécution Windows. Voir
`checks/preparation-checks.json`.

Ce mini ne compile ni ne lance le modèle, le QML ou l’application complète,
ne charge pas un périphérique audio et ne constitue pas une écoute. Même si
les 21 scénarios passent sous Windows, le parcours GUI des nouvelles cartes et
le futur téléchargement public des SF2 resteront à vérifier séparément.

Le responsable publie le payload préparé après revue. Aucun fichier des anciens
espaces CI ou du produit n’est remplacé par cette préparation ; la nouvelle
règle `.gitattributes` maintient les octets exacts des sources et licences.
