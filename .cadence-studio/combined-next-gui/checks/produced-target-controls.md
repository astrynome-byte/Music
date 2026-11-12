Contrôle indépendant Linux, 12 novembre 2026 : **20/20 cas de données passent** avec la vraie définition AST de `Get-NextGuiTarget`. Les fichiers source.json, target.json et les octets de faux patch sont explicitement synthétiques ; le faux patch n’est pas un gzip et n’a jamais été appliqué ou exécuté. Les SHA des fixtures sont réellement calculés. Cela ne valide ni un stage Windows réellement produit, ni ses identifiants distants.

Le premier passage avait trouvé deux coercitions de `schema_version=true` (target et source.json). `produced-target-guard-checks.initial-failing.json` conserve ce constat 18/20. Le responsable du helper a corrigé les types int/long ; `produced-target-guard-checks.json` décrit la relance 20/20, avec le SHA du helper effectivement testé.

`Restore-NextStage.ps1` a été parsé sans erreur et son bloc ZIP comparé aux six restaurateurs existants : mêmes 2 799 octets UTF-8, SHA256 `56d251fdca659f439f18c1197522da9b03009a6eef8f3be244f4fe055d71fb05`. La preuve est dans `restore-zip-source-comparison.json`. Aucune archive n’a été ouverte ni extraite par cette comparaison.

Reproduction :

```sh
XDG_DATA_HOME=/tmp/cadence-produced-target-data \
XDG_CACHE_HOME=/tmp/cadence-produced-target-cache \
XDG_CONFIG_HOME=/tmp/cadence-produced-target-config \
/workspace/toolchains/cadence-pwsh/pwsh -NoLogo -NoProfile \
  -File /workspace/cadence-ci-driver/combined-next-gui/checks/check-produced-target.ps1 \
  -OutputPath /workspace/cadence-ci-driver/combined-next-gui/checks/produced-target-guard-checks.json
```

Aucun programme du produit, COM, MSI, workflow ou job Windows n’a été lancé. Aucun helper ni fichier produit n’a été modifié par ces contrôles.
