# Lecture des fichiers réels de la compilation Windows 2006

Ce lot lit uniquement des données existantes. Il ne lance ni Cadence, ni son
installateur, ni une action MSI. Aucun nouveau test d'installation, de lecture
musicale ou d'interface n'est effectué. Il ne clôt pas l'audit de distribution.

Le producteur fixé est le run `43233124321`, pilote
`5d9cd789149de212c2fe9cf51ea3dddd2d48867c`, tentative 1. La source originale est
`ac9a24933f78f22ea630570910848201baad3d3b`, arbre
`a94a09974229c47e7b90b593a7649c29d6a6d190`. Les identifiants, tailles et SHA-256
des trois artefacts stage/livraison/logs sont des constantes de
`download_originals.py` : `13955301913`, `13955727693`, `13956760224`.

Le workflow proposé fonctionne seulement sur un runner Windows GitHub jetable,
avec `contents: read` et `actions: read`. Ses seules requêtes sont des GET vers
ces ressources fixes. Les redirections HTTPS sont bornées aux domaines GitHub
et Azure attendus ; le jeton API n'est pas transmis aux URL redirigées. Le
lecteur recalcule la taille et le SHA-256 des **ZIP originaux téléchargés**,
avant de lire leurs membres. Une expiration ou une différence provoque un
échec ; aucune archive de remplacement n'est acceptée.

Le lecteur conserve les inventaires et SHA de tous les fichiers du stage et
de la livraison. Il vérifie les listes SHA256SUMS originales, la provenance et
les deux ZIP internes de stage, dont les fichiers doivent être identiques.
Les chemins du conteneur de livraison peuvent avoir le préfixe produit par
l'ancêtre commun d'`upload-artifact` : son unique sous-dossier
`cadence-delivery` est identifié par sa liste SHA256SUMS, sans extraire ses
chemins. Seuls deux ZIP internes et l'unique MSI annoncé sont matérialisés,
sous des noms constants dans un dossier temporaire neuf.

Le MSI doit porter le SHA
`47e93cedd47d76baa7f91542cc937ea1ee3797e45d47d3532b327b90879fe5e9` et le stage
l'EXE `c29d7c8c76b213b79d7390acd65cbabc6fb940f06e3e7f86c0ce60be7e9b9520`.
Sur Windows, Python 3.12 lit le fichier avec `_msi.OpenDatabase` en mode
`MSIDBOPEN_READONLY` (0), puis uniquement des vues SELECT Property et le résumé
du fichier. Le SHA du MSI est vérifié à nouveau ensuite. Aucune interrogation
de `Win32_Product`, des produits enregistrés ou du registre n'est effectuée.
L'appel `view.Execute` exécute une vue SELECT ; il n'exécute pas l'installateur.

Le rapport **déjà produit** `msi-qa/msi-install-report.json` est retrouvé dans
l'archive de logs ou de livraison, conservé octet pour octet et lié au MSI,
à l'EXE installé et au commit CI. Les codes install/uninstall, les indicateurs
de redémarrage et la version sont recopiés tels quels : **3010 reste 3010**,
une valeur absente reste `null`. Le lecteur ne déduit pas un code 0 de la
réussite globale du workflow. L'absence ou l'ambiguïté du rapport bloque la
lecture complète. La version historique est comparée à la Property réellement
lue dans le MSI.

Les seules sorties à archiver sont les reçus JSON, les inventaires de SHA et
les rapports originaux sélectionnés, dans `retained-2006-data-receipts`.
Aucun exécutable, MSI ou ZIP binaire n'est réuploadé. Le workflow a une durée
maximale de 40 minutes ; les reçus sont conservés 14 jours, sans constituer un
lien de téléchargement public de l'application.

Le lecteur 2005 est conservé sans modification, avec son SHA dans
`baseline-reader-sha256.txt`. Les contrôles préparatoires locaux figurent dans
`preparation-checks.json`. L'API `_msi` et les contenus exacts des trois ZIP
doivent encore être lus sur Windows par ce lot : aucune exécution locale de
ces opérations n'est prétendue.
