# Réempaqueter le véritable stage Windows conservé du run 7

Ce mini-projet ne crée aucun exécutable et ne recompile pas Cadence. Il utilise
le véritable module CPack/WiX et ses cinq assets, copiés et vérifiés par SHA-256,
pour empaqueter exclusivement les fichiers de l'archive de stage déjà produite.
Il ne remplace pas une livraison finale ni l'audit des licences transitives.

```powershell
./retained-stage/Package-RetainedStage.ps1 `
  -SourcePath "$env:RUNNER_TEMP/cadence-src" `
  -BootstrapResultPath "$env:RUNNER_TEMP/cadence-bootstrap.json" `
  -StageArtifactPath "$env:RUNNER_TEMP/downloaded-stage-run7" `
  -OutputPath "$env:RUNNER_TEMP/retained-delivery"
```

Entrée : contenu **complet et non modifié** de l'artefact Cadence run 7, avec
ZIP, `SHA256SUMS.txt`, `stage-manifest.json`, `cadence-build.json`,
`cadence-build-result.json`, lock et autres fichiers originaux. Ne pas passer
l'artefact de référence. Le dépôt source doit être propre et présenter l'arbre
exact `65322ea3a3fbb419695a9b226607153b1c698886`, correspondant au commit original
`24cce38f0fea7d976382bb09e54d90415c9de6c4`. Le commit synthétique créé par un
nouveau Bootstrap peut différer de celui du stage ; leurs arbres doivent être
identiques. Le résultat Bootstrap courant est obligatoire.

L'empaquetage réel est limité à un runner GitHub hébergé Windows x64 jetable,
PowerShell 7, MSVC/C++ et Ninja pour la configuration du mini-projet, CMake et
WiX 3 pour CPack. Il n'appelle ni `cmake --build`, ni `cmake --install`, ni
`windeployqt` : Qt et les redistribuables doivent déjà être présents dans le
stage conservé. Aucune dépendance du payload n'est complétée silencieusement.

Tous les contrôles d'identité source, de manifeste, d'archive et de checksum
précèdent la création de la sortie et l'extraction. Les chemins ZIP dangereux
ou dupliqués sont refusés. Après extraction, l'empreinte de l'exécutable est
comparée aux enregistrements d'origine avant toute exécution. Le contrôle natif
vérifie PE AMD64 et `--long-version` dans un environnement sans chemins de SDK.
Cette commande affiche la version **4.7.6 et la révision source**, pas le numéro
numérique de compilation. Le numéro **7** est vérifié dans les enregistrements
archivés et conservé comme version MSI `4.7.6.7`. Sources et payload sont vérifiés
inchangés après l'opération ; aucune validation d'édition ou d'écoute n'est déduite.

La sortie comprend le MSI expérimental, les sources du véritable arbre via
`git archive`, un correctif binaire depuis l'amont, les notices minimales, le
lock, les hashes des assets et du stage, les logs et le manifeste de provenance.
`EXPERIMENTAL.md` explique en français la version, l'absence de recompilation et
les qualifications encore distinctes de la livraison finale. Les intermédiaires
`_CPack_Packages` restent sur disque pour le diagnostic, mais sont exclus de
`SHA256SUMS.txt` et des livrables à téléverser.
`original-stage/` conserve les fichiers d'entrée, octet pour octet, y compris
leurs enregistrements et l'archive. `stage-verification-result.json` est une
**projection documentée du résultat de compilation original**, dont seul le
chemin de l'exécutable est relocalisé : ce n'est pas un nouveau résultat Build.ps1.
Elle conserve le commit et le SHA-256 du payload d'origine et peut être passée
à `Test-MsiInstall.ps1 -StageBuildResultPath ...`. Le manifeste distingue ce
commit de celui du Bootstrap utilisé pour le nouvel empaquetage.

`-VerifyOnly` réalise seulement le précontrôle en lecture, aussi sur Linux ; il
ne crée aucun dossier de sortie. `-ConfigureOnly` autorise en plus extraction,
vérification des fichiers et génération CMake sur Linux, mais n'exécute aucun
fichier du stage et ne produit aucun MSI. Ce mode ne valide pas Windows.
Dans les deux modes, `RUNNER_TEMP` et une sortie neuve située strictement sous
ce dossier restent requis. Ne pas définir de variables Windows factices pour
faire passer un test Linux pour une validation native.

Les SHA-256 détectent une corruption après téléchargement ; l'authenticité du
jeu de fichiers repose aussi sur la sélection explicite de l'artefact du run 7
dans le workflow, et ne constitue pas une signature indépendante. Aucun upload,
aucune publication et aucune installation ne sont déclenchés par ce script.

Les identifiants du run retenu sont aussi ancrés dans le script : ancien commit
CI `a8f2b2432502ba044c7be1b758b30d7fddaedba3`, SHA-256 de l'archive
`ff8c5f050bb61e1e8de77ca1b3161a226095efbcd7c03d31ac09f2557d3cf1ed`, SHA-256 de
l'exécutable `62987537161d89d9d0f2da6b9915b7f421a9718e288d7aa84a6b3f7dacfc0a34`.
Le script refuse un autre jeu de fichiers, même si son checksum auto-déclaré
serait cohérent.

Contrôles locaux exécutés sur Linux : parse PowerShell réussi ; archive altérée
et mauvais arbre source rejetés avant création de sortie ; configuration CMake
du vrai module réussie, version `4.7.6.7`, stage installé directement et aucune
cible applicative créée. Ces tests ne constituent ni une compilation Windows,
ni un essai du stage, ni un MSI produit. Le premier emploi réel reste à exécuter
sur le runner Windows et doit être inspecté avant toute distribution.
