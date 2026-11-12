# Comparaison ordinale de l'inventaire des workflows

La première publication de sons, run `43252202862`, s'est arrêtée avant toute
écriture GitHub. Ce lot corrige exclusivement `Assert-WorkflowInventory` du
publisher ; les gardes, la validation des sept fichiers, le producteur, les
licences et les opérations de publication restent identiques.

L'erreur est reproduite localement avec les fonctions extraites par AST du
script réel et les 54 workflows HEAD + 1 workflow main de l'audit root
`66c164b9`. Les GET sont remplacés par une projection des entrées authentifiées
de cet audit ; aucun accès réseau ni point d'entrée du publisher n'est exécuté.
Le script original passe main mais refuse HEAD : `Sort-Object path` n'obtient
pas le même ordre pour des `OrderedDictionary` et des `PSCustomObject`.
L'index 1 compare ainsi cadence-mf-evidence à cadence-annotations-store alors
que les deux inventaires possèdent exactement les mêmes 54 couples.

Le correctif construit deux dictionnaires `StringComparer.Ordinal`, vérifie
les types, chemins et SHA, refuse les doublons et les nombres hors 1..128,
puis compare chaque clé exacte et son SHA. La liste des clés attendues est
triée ordinalement uniquement pour produire un diagnostic déterministe.
Un chemin absent/renommé, une différence de nombre ou un SHA modifié bloque
toujours la publication, avec un message indiquant la différence.

La reproduction exacte passe désormais main et HEAD. Les 18 contrôles de
données PowerShell passent, dont les ordres inversés et types mixtes sous
en-US/fr-FR/tr-TR et les refus des SHA/chemins/types/doublons/nombres incorrects.
Les rapports `original-reproduction.json`, `fixed-real-inventory.json` et
`ordinal-data-results.json` décrivent seulement ces contrôles locaux.
Les champs `legacy_sorted_first_mismatches` montrent le tri original pour
documenter la cause ; ils ne sont plus utilisés par le comparateur corrigé.

La réparation doit **supprimer la cible active**
`.cadence-studio/vsco-public-download-next/target.json` dans le même commit
que le correctif. Le payload indique cette suppression séparément dans
`delete_paths`. Après revue des octets et des inventaires, seule une nouvelle
addition de la cible dans un commit distinct pourra activer le workflow,
conformément à sa garde existante. Ce lot ne contient aucune cible active et
n'effectue aucune publication. Aucun lien de téléchargement n'est créé.

Le script original, ses sources de sons, les lecteurs 2006 et les fichiers
root d'audit/cible locale restent inchangés.
