# Préflight de checkout uniquement — aucun build de l'application

Le runfull2003/43200417187 a arrêté le Bootstrap source404 après vérification
correcte de l'arbre, car le worktree Windows était sale. Ce pilote reproduit
exactement ce chemin puis relève au plus50chemins : statut, attributs, EOL,
SHA des blobs index et des octets de travail, sans afficher leur contenu. Il
lit uniquement les clés core de Git pertinentes. Aucun Qt, SDK, compilateur ou
programme de partition n'est lancé.

Le nouveau .gitattributes avait forcé une image PNG existante comme texte.
La phase404 n'est donc jamais remise en checkout avec cette règle. Le candidat
8c33b3c110e7f55d7244fbe8af54511d081a969c est construit dans un autre dépôt
jetable sans checkout, par le petit diff approuvé (attributs corrigés et un
vrai test de copies Git de l'image/licence). Son arbre doit être exactement
1d7f2db8877e9cb127d0891d0d9233c13dd139cf avant la matérialisation des fichiers.
Les attributs sont déjà corrigés lorsque checkout-index est exécuté avec
core.eol=lf. L'index n'est jamais renormalisé. Le PNG doit garder son SHA amont.

Le candidat doit finir propre et passer le vrai test_resource_attributes.py :
un test, deux sous-cas core.autocrlf false/true sur des copies du PNG et de la
licence originale. Cela prépare une prochaine compilation complète2004 ; cela
ne produit et ne qualifie aucun EXE ou installateur.
