# Qualification de coexistence Windows — préparée, pas exécutée

Cette recette installe une **nouvelle** copie officielle de MuseScore Studio et le véritable MSI Cadence déjà qualifié, sur un runner GitHub hébergé Windows x64 jetable. Elle ne demande aucun compte MuseHub/MuseScore et n'accepte aucun achat, abonnement ou dialogue d'activation. Un tel blocage ferait échouer le test.

## Entrées authentifiées

MuseScore officiel vient exclusivement de la release [musescore/MuseScore v4.7.6](https://github.com/musescore/MuseScore/releases/tag/v4.7.6) : `MuseScore-Studio-4.7.6.261022093-x86_64.msi`, 135020544 octets, SHA-256 `41c9ca34fbf0b720f229ed3b0c4ff923b5d41a8c24ad9262e1fce390cd5c34e5`. Ce hash a été recoupé avec le digest de l'asset GitHub et le [fichier de checksums téléchargé depuis la release](https://github.com/musescore/MuseScore/releases/download/v4.7.6/checksums.sha256.txt). Le SHA de ce fichier est `4ee62d3be3004e7d48d3a1f409fa58b5b57cde825b9374b2d8a690bad8084b80`. Le workflow vérifie de nouveau les octets téléchargés avant toute installation.

Cadence vient de l'artefact `13720861986`, run `42721049351`, avec le MSI SHA-256 `9314306b8520d7480bdb57a270152c6329a8c39bb72e1070c9c14c1b8767a6aa` et l'exécutable SHA-256 `62987537161d89d9d0f2da6b9915b7f421a9718e288d7aa84a6b3f7dacfc0a34`. Cette entrée GitHub demande l'accès au dépôt et expire après la rétention de 14 jours ; elle doit être conservée durablement avant expiration. Le test ne republie aucun MSI officiel ou Cadence.

`releases.lock.json` fixe les sources, tailles et empreintes. L'UpgradeCode officiel n'est pas deviné à partir du fallback CMake : le CI amont injecte une valeur secrète. Le script lit donc le véritable GUID dans le MSI authentifié, vérifie son indépendance de Cadence, puis cherche les produits déjà enregistrés dans cette famille.

## Contrôles et garde-fous

- Garde Windows x64, `GITHUB_ACTIONS=true`, `CI=true`, `RUNNER_ENVIRONMENT=github-hosted` et dossier de sortie neuf sous `RUNNER_TEMP`.
- Refus de toute MuseScore/Cadence déjà enregistrée, famille MSI existante, entrée de désinstallation, processus actif, profil attendu ou UserChoice préexistant. Aucun profil réel n'est écrasé.
- COM Installer en lecture seule, jamais `Win32_Product`. Les helpers COM lisibles sont repris du helper MSI déjà éprouvé ; toute installation/désinstallation appartient à une seule fonction du script principal.
- Installation silencieuse de l'officiel puis Cadence dans deux dossiers neufs, codes 0/3010 observés ; aucun redémarrage automatique. Les versions sont lancées avec PATH limité au bin de leur installation et System32, sans variables SDK.
- Snapshots des valeurs racines `.mscz`/`.mscx` HKCR/HKLM/HKCU, UserChoice et classes officielles/commandes. Après installation puis retrait de Cadence, le défaut officiel doit être inchangé. Les OpenWith Cadence doivent exister et pointer vers son propre programme.
- Snapshots SHA-256 des réglages officiels, données locales et fichiers de documents, avec trois sentinelles possédées par ce seul essai. Les originaux sont vérifiés après installation/exécution de Cadence, puis de nouveau **avant** retrait de l'officiel.
- `finally` retire exclusivement les deux ProductCodes lus avant l'installation, inconnus lors du précontrôle et dont la nouvelle installation a été tentée. Même en erreur, les deux nettoyages sont tentés ; aucun échec ne devient un PASS.

La GUI est séquentielle et optionnelle : aucun test IPC simultané. Avec GUI demandée, les deux helpers doivent réellement observer une fenêtre puis fermer proprement ; un blocage, un kill ou l'absence des profils INI/données attendus fait échouer la qualification. Sans GUI, le rapport distingue les chemins calculés et sentinelles des profils réellement initialisés ; `--long-version` quitte avant le chargement des préférences et ne prouve pas leur création.

## Chemins vérifiés dans les sources

`src/app/main.cpp:120–142` fixe en release les couples org/application `MuseScore`/`MuseScore4` et `CadenceStudio`/`CadenceStudio4`. `src/framework/global/settings.cpp:56–60` force IniFormat sous Windows ; Qt 6.10.2 `qsettings.cpp:1013–1018,1075–1083` place les INI dans RoamingAppData/org/app.ini. Les chemins visés sont donc `%APPDATA%\MuseScore\MuseScore4.ini` et `%APPDATA%\CadenceStudio\CadenceStudio4.ini`.

`globalconfiguration.cpp:103–121` et Qt `qstandardpaths_win.cpp` placent les données dans `%LOCALAPPDATA%\org\app` et les documents dans le dossier Documents Windows connu, suivi du nom d'application. Le script emploie `GetFolderPath(MyDocuments)`, et ne suppose pas un dossier non redirigé. Les chemins distincts sont consignés dans le rapport.

## Exécution et limites

Le workflow proposé `cadence-coexistence.yml` doit être copié par le parent vers `.github/workflows/`, et ce dossier vers `.cadence-studio/coexistence/`. Publier sur la branche autorisée avec le marqueur `[cadence-packaging-only]` pour éviter la longue recompilation complète. La GUI est activée par défaut ; la désactiver explicitement dans workflow_dispatch réduit le contrôle aux associations, sentinelles et CLI. Durée visée environ dix minutes, limite de job vingt minutes, aucune compilation ni installation de SDK.

Le dossier est autonome pour les contrôles : il contient `MsiReadOnly.ps1`, `Run-CleanGuiProbe.ps1` et `Test-GuiLaunch.ps1`. Les deux helpers GUI sont des copies exactes des versions déjà éprouvées, respectivement SHA-256 `8a5f7d237c4ebf452ca347fab7c5dfc612bc7b457036e541cbd5df635902c68d` et `1cc4ea0a980e8f6b2bc5efc20b85561143144388a80583d6b7a3df85041022c6`. Le workflow les appelle dans `.cadence-studio/coexistence/` ; aucun clone `cadence-src` ni helper situé seulement à la racine locale du driver n'est requis.

Conserver les rapports, snapshots, logs msiexec et éventuelles captures avec `if: always()` ; rétention de 14 jours, téléchargement durable nécessaire. Le rapport est aussi imprimé en console pour l'accès par le connecteur GitHub. Les fichiers INI, scores sentinelles et dossiers créés par le test sont laissés au runner jetable ; aucun nettoyage global de profil ou du registre n'est effectué.

Ce jalon ne valide pas l'édition musicale, le fonctionnement simultané/IPC, un profil utilisateur historique, une machine Windows personnelle ou un changement de défaut demandé manuellement par l'utilisateur. Il ne fournit aucun lien de cadeau public et ne clôt pas l'audit des licences. Les tests locaux de préparation portent sur le parse PowerShell/YAML et les refus avant mutation, pas sur une installation Windows de coexistence déjà exécutée.

Les snapshots d'associations utilisent la vue registre 64 bits, correspondant aux deux applications et à Explorer x64. Les clients 32 bits ne sont pas qualifiés ici. Les codes MSI 3010 sont acceptés et conservés dans les rapports, sans prétendre avoir testé un redémarrage Windows.
