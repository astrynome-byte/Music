# Pilote de compilation Windows de Cadence Studio

Ce pilote est destiné uniquement à la branche `cadence-studio/windows-build` du dépôt `astrynome-byte/Music`. Le dépôt existant, ses fichiers Android et sa branche principale ne sont pas remplacés. Le pilote ajoute un workflow Cadence et un dossier `.cadence-studio/` sur la branche dédiée. Des workflows déjà présents dans le dépôt peuvent aussi réagir au push selon leurs propres déclencheurs ; ce pilote ne les modifie pas.

## Fichiers à publier sur la branche dédiée

| Fichier local préparé | Chemin dans le dépôt pilote |
| --- | --- |
| `cadence-windows.yml` | `.github/workflows/cadence-windows.yml` |
| `Bootstrap.ps1` | `.cadence-studio/Bootstrap.ps1` |
| `README-CI.md` | `.cadence-studio/README-CI.md` |
| correctif Git binaire compressé | `.cadence-studio/changes.patch.gz` |
| métadonnées de la même version | `.cadence-studio/source.json` |

Les deux derniers fichiers doivent être générés après le commit local final du projet Cadence ; ne pas employer un commit ou un arbre fictif. Le workflow conserve les fichiers du dépôt pilote et clone le code officiel dans un second répertoire du runner. Les opérations GitHub sont réalisées séparément ; la préparation de ces fichiers n'effectue aucun push ni lancement de job.

## Format de `source.json`

```json
{
  "schema_version": 1,
  "upstream": {
    "repository": "https://github.com/musescore/MuseScore.git",
    "tag": "v4.7.6",
    "commit": "96480d58445e3b24b230a3fe7d4725d639aa2eb3"
  },
  "source": {
    "commit": "IDENTIFIANT_COMPLET_DU_COMMIT_CADENCE",
    "tree": "IDENTIFIANT_COMPLET_DE_SON_ARBRE_GIT"
  },
  "patch": {
    "file": "changes.patch.gz",
    "sha256": "SHA256_DES_OCTETS_COMPRESSES"
  }
}
```

Le correctif est le résultat binaire de `git diff --binary --full-index <commit-amont> <commit-cadence>`, compressé en gzip. Le SHA-256 porte sur le fichier **compressé**, pas sur son texte décompressé. `source.tree` provient de `git rev-parse <commit-cadence>^{tree}`. Le commit amont et son tag sont fixés et vérifiés par Bootstrap, sans consulter automatiquement la branche de développement.

## Déroulement

1. Le push sur **la seule branche** `cadence-studio/windows-build` déclenche le workflow. `workflow_dispatch` est aussi déclaré ; sa disponibilité dans l'interface dépend de la configuration GitHub et de la présence du workflow sur la branche par défaut. Un nouveau push sur la branche reste le déclencheur initial.
2. Checkout du dépôt pilote dans `driver/`. `Bootstrap.ps1` vérifie le hash gzip, clone le dépôt officiel au tag fixé dans `cadence-src/`, vérifie le commit, applique le correctif à l'index et compare l'arbre Git exact. Il refuse de remplacer un répertoire source existant et n'exécute aucun contenu de l'archive comme script.
3. Bootstrap crée un commit **local au runner** avec auteur Cadence CI, via options `git -c` et sans modifier la configuration globale. Son identifiant diffère du commit local d'origine ; son arbre doit être strictement identique. `cadence-bootstrap.json` conserve les deux identifiants et les empreintes. Aucun commit n'est poussé depuis le runner.
4. Installation des outils et dépendances déclarés ; compilation native x64 de la référence, essais d'exports, compilation Cadence, essais d'exports, puis MSI expérimental. Les SDK locaux VST et ASIO sont identiques pour les deux variantes.
5. Conservation des journaux, de la provenance et des artefacts pendant **14 jours** dans GitHub Actions. Aucun certificat Windows ni identifiant de publication n'est utilisé. Les permissions du job sont `contents: read`.

Les `run` de construction travaillent dans `cadence-src/`, pas dans le projet Android du pilote. Le premier bootstrap travaille explicitement à la racine du workspace. L'exécutable de référence est dans `$RUNNER_TEMP/stage-reference/bin/MuseScore4.exe` ; celui de Cadence dans `$RUNNER_TEMP/stage-cadence/bin/CadenceStudio4.exe`.

## Ce qui reste à vérifier

La présence du workflow ne signifie pas que Windows a compilé l'application. Relever la véritable exécution, ses journaux et son résultat. Un MSI produit reste expérimental tant que son installation, le premier lancement, les essais visuels, les écoutes et l'audit des sources correspondantes des dépendances ne sont pas achevés. La reconstitution Git et les contrôles syntaxiques réalisés sous Linux ne valident pas le fonctionnement Windows.

Les artefacts Actions nécessitent généralement un accès GitHub et expirent ; ils ne constituent pas le lien public final du cadeau. Une fois la recette passée, publier les fichiers sur un hébergement explicitement accessible à l'ami, vérifier un téléchargement anonyme et fournir SHA-256, sources et notices. Des minutes de calcul peuvent être décomptées au compte selon son offre GitHub.
