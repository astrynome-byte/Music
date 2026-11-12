# Point de reprise après le MSI2006

Source locale `b07fcaf544f494ca9bbab78000c220235d0db731`, arbre `ae4cdc6b70db059ad91a103480aaa7bfe72aa990`.
Ce lot ajoute au gel2006 les cartes d’import VSCO, les notices finales, preuves réelles et documentation. Il ne contient aucun son, exécutable ou installateur. Le correctif des ressources audio absentes est encore séparé et n’y est pas inclus.

Repartir de la source2006 exacte au commit ac9a24933f78f22ea630570910848201baad3d3b (arbre a94a09974229c47e7b90b593a7649c29d6a6d190), reconstruite par le namespace voisin `combined-2006-source` et son Bootstrap. Vérifier le SHA du gzip dans source.json, le décompresser puis appliquer avec `git apply --index --binary`. `git write-tree` doit rendre l’arbre annoncé. Cette reconstruction à partir du gel2006 a été réellement vérifiée dans un index isolé sous Linux ; elle n’est pas une compilation Windows de ce point.

Dernier MSI réellement produit : 2006, source ac9a2493, hors cartes VSCO et notices postérieures. Le ZIP sonore public CC0 1.0.0-exp.1 est indépendant. Voir README.md, STATUS.md, FEATURES.md et docs/DELIVERY.md dans la source reconstruite pour les liens, SHA, résultats et fonctions encore incomplètes. Les contrôles natifs Windows, GUI et écoute restent distincts.

Le code et les modifications Cadence restent GPL-3.0-only ; sons, polices et notices conservent leurs propres licences. Ce point de reprise ne déclare ni distribution finale prête ni couverture payante complète. Il est ajouté à la seule branche Cadence sans modifier main ou Android, les namespaces figés, les workflows ni les releases existantes.
