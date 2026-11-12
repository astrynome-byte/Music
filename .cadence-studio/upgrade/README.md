# Mise à jour réelle MSI7 → MSI2002

Le MSI2002 complet a été produit et installé/désinstallé dans le run `43123411562`. Cette recette indépendante attend son propre premier run de mise à jour ; aucun succès d’upgrade n’est encore déduit du succès de packaging. Aucun code applicatif n’est modifié et aucune application n’est reconstruite.

La publication du pilote vise exclusivement `.cadence-studio/upgrade/**` et `.github/workflows/cadence-msi-upgrade.yml` sur `cadence-studio/windows-build`. Ce sont les seuls filtres push. `workflow_dispatch` est facultatif, sans remplacement des pins, et sa disponibilité sur une branche non par défaut n’est pas garantie. Le `.gitattributes` local impose LF et préserve les octets MusicXML par `-text`. Les permissions GitHub restent `contents: read` et `actions: read`.

## Six entrées mesurées et identités exactes

Les six valeurs réellement produites sont fixées dans le workflow et `selection.json` :

| Entrée candidat | Valeur réelle |
| --- | --- |
| Run de production terminé | `43123411562` |
| Artifact de livraison | `13902536112` (437542329 octets) |
| Fichier MSI | `CadenceStudio-4.7.6-cadence.2002-x86_64.msi` |
| SHA-256 MSI | `2d0d4b82ced312b22fea36470aec4c2677060135dd6cf8fb43bb25777953673e` |
| SHA-256 EXE | `35d8b076cacddb8b37a4f23aeea9899e6ab4ac9214e9a5b1125bbeccf26cf39e` |
| Version MSI | `4.7.6.2002` |

L’ancienne base est l’artifact `13720861986` du run `42721049351`, contenant `CadenceStudio-4.7.6-cadence.7-x86_64.msi`, SHA-256 `9314306b8520d7480bdb57a270152c6329a8c39bb72e1070c9c14c1b8767a6aa`, exécutable `62987537161d89d9d0f2da6b9915b7f421a9718e288d7aa84a6b3f7dacfc0a34`. Les deux ProductCodes exigés sont respectivement `{842A564D-92B8-5F7F-9626-0A29746ED9F2}` et `{6BF4BBA1-C7AA-5FCD-B5F2-14B7CF0D240C}` ; famille commune `{319B992F-470A-465B-9A79-6B0CBFC7D6C7}`, plateforme `x64;1033` et ProductLanguage réel `1033`.

Les livraisons et leurs rétentions restent celles de GitHub Actions, pas un téléchargement public anonyme. Le digest ZIP annoncé pour la livraison2002 est `0f4ab66afaf8f16035a619234354dc29c580f079e89ced9addbdee81298027f8`, pour MSI7 `b12ff2fa870adfef8bdd605fc5483a8bbbaf81115d0efae60c6011c0a6e1985d`. Le transport `actions/download-artifact` vérifie son téléchargement et consigne son digest. Le nouveau vérificateur travaille sur les fichiers déjà extraits ; il ne prétend pas rehash­er lui-même le ZIP extérieur.

## Authentification avant exécution

Le premier step refuse tout environnement sauf Windows natif x64 GitHub-hosted jetable. Les deux scripts d’action répètent cette garde avant leurs premières écritures ou API. Tous les téléchargements et résultats restent strictement sous `RUNNER_TEMP`, dans des dossiers séparés ; les reparse points sont refusés.

`Verify-UpgradeInputs.ps1` recherche exactement un MSI de chaque nom épinglé. Il vérifie **tous** les membres déclarés dans le SHA256SUMS complet de chaque livraison, exige que chaque fichier réel soit couvert, puis vérifie séparément le SHA256SUMS d’`original-stage`. Il recoupe source originale, arbre, révision CI, build, configuration Release propre, Qt6.10.2, upstream v4.7.6, manifestes et records de réempaquetage sans rebuild. La source MSI7 est `24cce38f0fea7d976382bb09e54d90415c9de6c4`, arbre `65322ea3a3fbb419695a9b226607153b1c698886`, CI `a8f2b2432502ba044c7be1b758b30d7fddaedba3` ; MSI2002 est source `0e05d04acbeee32f1b561f24493d7ef41c322081`, arbre `f95b7097a55dddf9c7f697fc826b95721071231a`, CI `dbca5382bc029a2a6bb8c8eb761abb2c9294479c`.

Les archives source correspondantes et patches doivent être présents et avoir les SHA du manifeste complet de la livraison immuable épinglée ; leurs empreintes observées sont conservées. Pour2002, le lecteur indépendant de livraison a en outre fourni des pins exacts : SHA256SUMS raw `7726e4c15b81983c26d6974fc42645ebb57d0f911ad6807d5e382f94e3cf1971` couvrant37 membres, archive source161844110 octets SHA `7978a9bc6ae863e9a6c828b95e4be37e125d201d880bab5a8d9faa569476ff9b`, patch2834780 octets SHA `d3ee463bc9363b9d1576bd21f82a5c823ceea574fda03e5d28911be30f543c55` et MSI121514164 octets. Ces pins indépendants sont exigés avant toute installation. Aucun arbre Git n’est reconstruit et aucune équivalence indépendante de cet arbre n’est revendiquée. Le stage2002 ajoute les six pins raw originaux connus (manifest, build/result, deux locks, SHA256SUMS), `windows_system_aac=true`, la preuve zlib source et son archive correspondante SHA `7254e29e7c3aed673cd29d46353aa8ddd758b22b4b1ee41b6d4d194155b740ae`.

Enfin, le vérificateur ouvre chaque ZIP de stage en lecture seule, contrôle les noms/limites, puis rehashe **les vrais octets** du membre `bin/CadenceStudio4.exe` sans extraction ni lancement (79583744 octets pour7, 79200256 pour2002). `input-verification.json` doit être `passed` et lier exactement les deux chemins MSI ; le script de mise à jour refuse son absence ou toute incohérence.

## Tables Windows Installer et appartenance

Windows Installer compare uniquement les **trois premières composantes** de ProductVersion. Les paquets4.7.6.7 et4.7.6.2002 sont donc égaux pour cette comparaison. Le test exige les quatre composantes exactes de chacun, puis lit réellement les tables `Upgrade` et `InstallExecuteSequence` du MSI2002. Il exige une ligne de la même famille couvrant4.7.6, sans `OnlyDetect=0x002`, avec borne haute égale incluse `VersionMaxInclusive=0x200`, suppression complète (`Remove=NULL` ou `ALL`) et propriété d’action sécurisée. Les flags min inclusive0x100 et langue exclusive0x400 sont interprétés. FindRelatedProducts doit précéder RemoveExistingProducts dans la séquence exécutée. Le texte WiX seul ne suffit pas.

Sources : [ProductVersion Microsoft](https://github.com/MicrosoftDocs/win32/blob/docs/desktop-src/Msi/productversion.md), [Upgrade table](https://github.com/MicrosoftDocs/win32/blob/docs/desktop-src/Msi/upgrade-table.md). La possibilité de downgrade portant sur la quatrième composante reste une limite distincte de Windows Installer, pas une protection qualifiée par ce test ascendant.

## Séquence réelle et préservation

1. Refuser les deux ProductCodes déjà enregistrés, toute famille Cadence existante, tout produit/entrée uninstall Cadence ou MuseScore, processus de partition actif ou profil Cadence/MuseScore préexistant. Aucun produit tiers n’est installé ou retiré.
2. Installer sa propre nouvelle instance du MSI7 dans le dossier de test, vérifier le produit, le SHA EXE et `--long-version`/révision CI `a8f2b24`. Ce flag quitte avant QApplication et initialisation des modules dans les deux sources ; il ne sert pas à initialiser un profil GUI.
3. Créer un INI test avec nonce, une sentinelle de données locales et la copie du piano CC0 original SHA `1b38cc5953cc56426976345411394c24d39e0ff22dbf6c350addcb68c770a3fb` dans les vrais emplacements Windows neufs. Conserver noms, tailles et SHA256 exacts.
4. Installer le MSI2002 sur le même emplacement. Comparer l’inventaire **immédiatement après msiexec, avant tout lancement du nouveau binaire**. Aucune donnée historique n’est fournie, migrée ou simulée.
5. Exiger ancien produit inconnu(-1), nouveau installé, un seul produit Cadence et un seul membre de famille, tous deux exactement le candidat. Vérifier l’EXE installé par SHA puis `--long-version`/révision `dbca538`, avec `PATH=bin installé;System32` et variables SDK/Qt/QML retirées du seul enfant. Comparer à nouveau les fichiers.
6. Dans `finally`, désinstaller seulement les ProductCodes initialement inconnus dont l’installation a été tentée : candidat puis ancien s’il subsiste. Exiger les deux absents, vérifier les MSI/corpus/record immuables et conserver les erreurs. Les profils/sentinelles ne sont pas supprimés ; la destruction du runner jetable suit la CI. Aucun nettoyage global, arrêt de service ou retrait d’un produit préexistant.

Chaque client msiexec possède son PID et une limite180s, stdout Windows Installer étant consigné dans un log `/L*V`. Seul ce client détenu est terminé au dépassement ; la fin de la transaction du service Installer n’est alors pas déduite, et le cleanup peut échouer explicitement. Le processus version a30s, sans terminaison d’arbre. Les codes0/3010 sont conservés, `/norestart REBOOT=ReallySuppress` évite un redémarrage demandé par le pilote ; aucun reboot réel n’est déclaré.

Le rapport, les tables Upgrade, trois inventaires de fichiers, versions, opérations/PID/durées, nettoyage et logs sont imprimés et uploadés même à l’échec. Le job est borné à20min. La réussite ne vaut que pour l’installation/remplacement et la préservation exacte des fichiers de test pendant INSTALL sur Windows Server2022. Aucune migration historique, édition GUI, ouverture de projet par le moteur, écoute ou recette Windows10/11 client n’est déduite.

`PREPARATION.json` consigne la syntaxe PowerShell/YAML, le refus Linux avant écriture et la relecture indépendante. Ces contrôles locaux ne sont pas un résultat Windows. Le parent publie le payload revu, puis le run push réel fournit la qualification.
