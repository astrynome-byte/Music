# Publisher2008 depuis le stage conservé

Copie privée de la recette existante, adaptée à trois origines explicites : construction réelle, qualification indépendante, puis futur producteur MSI réussi. Le code est préparé pour lire les mesures réelles ; **le MSI réel est produit et installé/testé ; son inspection DATAONLY20rapports reste à effectuer**. `target.json.template` reste `ready=false`, `review.approved=false`, avec producteur MSI2, cinq archives et SHA MSI mesurés ; les reçus intérieurs encore inconnus restent à `null`. Aucun `target.json` actif ni lien futur n’est créé.

La source reste `a2b7abaf045a8f3cb84ec2953d9e0e51b9e78903`, arbre `c5452043983a048ef0aeef085615af903de3f5b0`, CI `95cebb22fe6cbde22919c94f2b480bd14c3eb8de` et EXE SHA256 `13cd4e6d2f408d2e64b187d4c3bff1188ff4192ac7b670d3a12373bbeb37f6cd`. Le run43408309742/job131828068954 reste authentiquement échoué31 après25–30PASS ; son stage et ses logs sont repris sans reconstruire l’application. La QA43421094979/job131870989277, pilote `cc88a26de1fd0966c311aae5a8e5e25b130b6629`, compteur2/tentative1, est observée SUCCESS via API. Le MSI2 réel provient du run43425150320/job131884644607, pilote90d304749a692752a3d5537e82e8f225e94c0737, compteur2/tentative1 :120979784octets, SHA256 `a3f934273e2c2002cc035743974941082245655a7bbe4bc6d2540bb921e52a9e`. Installation/CLI/GUI/fermeture/retrait0,338notices installées vérifiées, ICU local absent et zéro arrêt forcé sont observés dans son vrai producteur. La validation locale de cette recette doit encore authentifier ses20rapports originaux ; aucune écoute, Windows10/11client ou équivalence payante complète n’en découle.

## Cinq archives, trois origines

| Rôle | Producteur | Nom attendu |
| --- | --- | --- |
| stage | construction43408309742 | cadence-combined-system-aac-stage-experimental-12-1 |
| original_logs | construction43408309742 | cadence-combined-system-aac-logs-12-1 |
| qa_logs | QA43421094979 | cadence-retained2008-resume-logs-2-1 |
| delivery | MSI43425150320 réussi | cadence-retained2008-msi-delivery-2-1 |
| msi_logs | MSI43425150320 réussi | cadence-retained2008-msi-logs-2-1 |

Les IDs/digests/tailles/expirations viennent des métadonnées réelles. Le garde du stage original est repris byte-identique ; il exige l’échec31 exact et les étapes25–30, avec leurs noms, puis les étapes aval sautées. Les deux autres runs et jobs Windows2022 doivent réussir. Chaque rôle est relié à son propre run/commit ; les cinq ZIP sont rehashés avant extraction bornée. Les requêtes et redirections GET existantes ne transmettent pas l’Authorization au CDN. Aucun contenu acquis n’est exécuté.

## Rapports et livraison

`inspect_delivery.py::REPORT_SUFFIXES` route explicitement les17 rapports historiques et trois reçus retained : agrégateur QA10gates, empaquetage et wrapper MSI installé avec GUI. Les anciens reçus restent dans les archives de construction, les nouveaux parcours dans qa_logs, les reçus MSI et delivery-bundle-report dans msi_logs. Les chemins `_temp/retained2008-package/` et `_temp/retained2008-installer-qa/` sont ceux confirmés par la recette MSI Unity. Les dix fichiers réellement désignés par l’agrégateur sont retrouvés dans l’archive QA et rehashés ; ses limites et le hook de bibliothèque non qualifié restent explicites.

La préparation vérifie puis **copie les sept fichiers originaux déjà produits** par `bundle_delivery.py` : MSI, source, recette, composants, notices, guide français et SHA256SUMS. Elle ne demande plus l’ancien `-staged.zip` ni un release-manifest inexistant. Le vrai `delivery-bundle-report.json` est utilisé avec son schéma actuel. Aucun réempaquetage ne modifie leurs empreintes.

Les contrôles existants restent utilisés : MSI READONLY=0, archive source PAX au commit CI95, patch/source.json exacts, inventaire intégral du stage, Qt6Core/Qt6Network et ICU, sources de composants, archives correspondantes et notices identiques au stage puis au MSI installé. Le companion composants ajoute les deux originaux zlib et un nouveau `zlib-source-supplement.MEASURED.json`, explicitement dérivé ; aucun original absent n’est inventé. L’installation doit réellement produire le wrapper `passed-retained2008-msi-and-installed-gui` avec sources préservées, fermeture puis retrait du produit exact. Empaquetage seul ou CLI seul ne suffisent pas.

`Publish-ExperimentalWindows.ps1` et son téléchargement anonyme sont intégralement inchangés : contrôles main/workflows, tag neuf, draft propre, sept fichiers, téléchargement sans compte et vérification des SHA. Seuls le validateur, l’acquisition, le routage et les gardes de transport relient les nouvelles origines. Les fonctions communes d’extraction, de receipts, de lecture MSI et les contrôles natifs existants sont conservés.

## Prochaine exécution réelle

1. Relire les pins réels MSI2 et les cinq archives renseignés, puis publier les attentes dans un commit inactif ; ne pas remplacer les métadonnées originales de construction ou QA.
2. Publier la recette inactive revue. Avec son vrai commit, le générateur existant `render_inspection_workflow.py` prépare le même workflow DATAONLY read-only, sans cible. Il exige neuf entrées sources épinglées et conserve20 rapports originaux plus source.json et reçu, sans réuploader les binaires.
3. Exécuter cette inspection Windows et relire ses mesures réelles, les sources/notices et les inventaires main/tag actualisés. Compléter les20 receipts et sept assets de la cible seulement depuis ces résultats.
4. Après revue, root ajoute uniquement target.json dans un commit séparé. La publication et les liens n’existent qu’après les vérifications réelles.

Contrôles locaux : AST Python/PowerShell, imports `--help`, refus réel du modèle incomplet et application du garde inchangé aux métadonnées API originales déjà récupérées. Aucun nouveau simulateur, suite miroir, MSI exécuté, Windows de livraison ou publication testé ici. Les anciens tests de la recette monoproduceur sont conservés comme sources historiques ; aucun succès de cette ancienne fixture n’est revendiqué pour ce nouveau contrat.
