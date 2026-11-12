# Publication des seuls sons VSCO CE expérimentaux

Ce namespace distribue deux banques SF2 CC0, leurs notices et les sources GPL
du convertisseur indépendant. Aucun installateur ou binaire Cadence n’est livré.
La cible active `target.json` est volontairement absente ; le modèle porte
`ready=false`, sans approbation ni inventaire complet des workflows.

La qualification musicale utilisée est le run Windows 43231480145 avec Cadence
2005 retenu. Elle couvre des exports CLI et les sauvegardes/réouvertures natives,
pas les écoutes ou l’installation GUI. Les preuves sous `evidence/` et la notice
expliquent ces limites ; les sons restent explicitement expérimentaux.

La recette reconstruit les SF2 depuis les originaux CC0 épinglés, puis prépare
les sept assets déterministes sous RUNNER_TEMP. Les SHA de la cible doivent
correspondre aux octets relus par le responsable, jamais à des fichiers substitués.
`--inspect-only` du validateur retourne toujours `allowed=false` : une inspection
ne constitue aucune autorisation de publier.

Le futur workflow se déclenche uniquement par l’ajout du fichier cible sur
`cadence-studio/windows-build`. Publier d’abord les recettes inactives et auditer
leurs workflows ainsi que main Android. Après revue explicite des assets et
licences, ajouter seulement la cible approuvée dans un commit distinct.
Le publisher crée un nouveau tag au HEAD effectif et une prerelease de sons.
Il n’altère pas main ou un tag/release préexistant.

Un client HTTP indépendant doit ensuite retrouver les sept fichiers publics et
leurs SHA sans compte, cookies ou Authorization. Le message de partage français
n’est écrit qu’après cette vérification réelle. Aucun lien public ou permanence
d’hébergement n’est annoncé dans ce brouillon.
