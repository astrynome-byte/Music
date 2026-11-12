# Recette INACTIVE de préversion Windows 2007

Ce lot propose une publication future et bornée. **Aucun `target.json` actif,
MSI 2007, hash de binaire ou URL publique future n'est fourni.** Le seul modèle
est `target.json.template` : ready=false, review.approved=false, CI/MSI/EXE,
artefacts et assets inconnus restent null. Il est effectivement refusé par
les gardes Python et PowerShell. Aucun workflow ni publication n'a été lancé
pendant cette préparation. Les anciennes recettes, gels, releases et main
Android ne sont pas modifiés.

## Origine fixée, fichiers encore à observer

Producteur attendu : full `43266732201`, job `131352164369`, pilote
`c3421a217c76a1b2cc5d4fab74305d209491d82f`. Source originale
`5058d29dad67e6131ee46ee617258ccfed8ba4b0`, arbre
`58d06a1c89e99173b0473587245187df5bc3b3cf`. Les SHA du gel source.json et
du correctif sont des constantes vérifiées dans la recette. Le commit CI
reconstruit et les identifiants/digests des trois artefacts stage/livraison/logs
devront provenir du vrai run terminé avec succès, run_number7/tentative1.
Une relance ou une autre identité nécessite une nouvelle revue de cette recette.

`acquire_originals.py` n'effectue que des GET des ressources Actions de ce
dépôt. Il exige le job Windows2022 réussi, les IDs/noms/tailles/digests/expirations
réels, télécharge les ZIP originaux, recalcule leurs SHA puis extrait des
chemins bornés sans lien, ADS ou traversée. Il ne transmet pas le jeton aux
redirections CDN. Aucun contenu téléchargé n'est exécuté.

## Préparer les octets avant toute activation

Après le full, un job de préparation Windows en lecture seule, avec
`contents: read`, `actions: read` et le jeton éphémère fourni en `GH_TOKEN`,
peut exécuter cette unique commande. Elle ne demande aucun target, ID d'artefact,
SHA de binaire ou reçu à connaître à l'avance :

```
./Inspect-DeliveryDataOnly.ps1 -WorkDirectory "$env:RUNNER_TEMP/windows2007-inspection" -OutputPath "$env:RUNNER_TEMP/windows2007-inspection-receipt.json"
```

`inspect_delivery.py` commence par lire le run/job fixés. Tant que le full est
en cours ou en échec, il produit seulement un refus DATAONLY, sans inventer les
artefacts. Après réussite, il découvre les trois noms exacts dans la liste
complète du vrai run, enregistre leurs IDs/digests observés, retélécharge et
vérifie les trois ZIP puis retrouve les dix rapports à leurs suffixes connus.
Une absence ou ambiguïté est refusée. Il calcule lui-même les dix reçus
(rôle, chemin, taille, SHA) ainsi que les SHA du MSI et de l'EXE, vérifiés ensuite
contre les données réelles par la préparation.

La commande produit `observed-reports/` (les dix JSON originaux plus source.json),
`assets/` (les sept vrais fichiers publics et leurs sept reçus SHA) et le reçu
d'inspection demandé. Aucun document target.json, tag, draft ou release n'est
créé ; ready et publication_authorized restent false. L'opérateur examine les
octets, sources et notices, puis reprend les valeurs réelles du reçu dans la
future cible approuvée. Le workflow de publication reste séparé et ne sert pas
à découvrir ces valeurs. Aucun workflow d'inspection actif distinct n'est ajouté.

Les dix rapports requis appartiennent obligatoirement aux trois artefacts du
full : Bootstrap, Build, stage-manifest, release-manifest, CLI57, MSI, notices,
collection de sources, politique ICU et résolution des exports système. Chaque
reçu désigne son rôle d'artefact, son chemin exact, sa taille et son SHA réel.
La recette ne réinterprète pas un succès global comme un code MSI0 : elle lit
les vrais codes0/3010, erreurs, identité, installation/désinstallation, CLI et
démarrage/fermeture GUI dans le rapport. Les 57 étapes et leurs sorties/audio
sont vérifiées. Le profil GUI préparé ne valide pas le premier lancement neuf.

L'absence ICU est vérifiée dans les fichiers du stage, dans le rapport
d'installation aux deux phases, et directement dans la table File du MSI,
ouverte READONLY=0 sans action MSI. Le ProductVersion doit être4.7.6.2007 ;
les20 exports système et le Qt6Core exact sont liés aux reçus du full.
Les ZIP de stage et de livraison doivent contenir les mêmes fichiers.

## Sept assets et leurs sources

- MSI exact : copie du fichier réellement testé, sans modification/signature.
- Source application : archive git exacte du full ; son commentaire PAX doit
  identifier le commit CI du même arbre source.
- Recette ZIP : dossier build-recipe original complet, patch binaire amont et
  release-manifest. source.json et changes.patch.gz correspondent au gel fixé.
- Sources de composants ZIP : tout le dossier corresponding-sources, ses
  archives/notices/locks/manifests, ainsi que les sources zlib préparées, leur
  profil et leur supplément. Les listes SHA et archives originales sont revérifiées.
- Notices ZIP : tous les fichiers de notices du stage avec leurs vrais octets,
  exactement ceux prouvés présents dans l'installation MSI.
- Guide français original : installation et limites expérimentales, sans outil
  de développement requis pour l'utilisateur.
- SHA256SUMS : couvre les six autres fichiers. Son propre SHA reste dans les
  reçus et métadonnées de release.

Les noms sont versionnés et fixes. Les ZIP dérivés ont ordre, date, permissions
et méthode STORED fixes ; ils sont reconstruits de façon déterministe. Les
décisions établies sur Qt, Mesa et les onze composants Microsoft sont conservées :
ce lot n'ouvre pas un nouvel audit juridique. La revue finale porte sur la
correspondance des vrais octets, des sources et des notices finales. L'ancien
champ historique complete_distribution_ready de la collecte de sources ne vaut
pas une nouvelle approbation et n'est pas transformé artificiellement.

## Activation future, distincte de cette proposition

Le workflow écoute exclusivement un push ajoutant
`.cadence-studio/windows-2007-public-download-next/target.json` sur la branche
autorisée. Il n'écoute ni tag/release ni workflow_dispatch. La recette et le
workflow doivent d'abord être présents dans un commit inactif séparé. Le commit
activant ultérieur doit ajouter **seulement** la vraie cible approuvée ; les
scripts vérifient le statut added et son unique chemin via l'API.

La règle d'attributs fournie doit être fusionnée dans
`.github/workflows/.gitattributes` sous la forme relative
`cadence-windows-2007-experimental-public.yml -text`, sans préfixe de dossier
et sans remplacer les autres règles déjà présentes.

Les listes exhaustives de workflows du main audité et du futur HEAD de
publication doivent être relues pour leurs triggers tag/release, avec chaque
blob exact. **Aucune ancienne liste54/55 n'est préremplie ni réputée valable**.
La comparaison utilise le correctif à clés ordinales éprouvé par la release
sons. Le tag nouveau pointe le HEAD déclencheur ; la provenance de l'application
reste séparément fixée au producteur ci-dessus. main doit rester inchangé avant
chaque mutation. Un tag/release/draft existant provoque un refus, sans clobber.

Le publisher reprend sept fonctions de sécurité et le bloc HTTP anonyme octet
pour octet du publisher sons réussi. Il crée un tag neuf, puis une prerelease
draft vide par POST/ID, vérifie le brouillon, envoie les sept fichiers vérifiés
et publie la préversion. Un client neuf sans compte, cookie ou Authorization
retélécharge ensuite **tous** les assets et vérifie tailles/SHA. Le texte à
partager n'est écrit qu'après cette vérification réelle. En cas d'échec final,
le même brouillon créé par cette invocation est remis privé sous les gardes
d'identité/main ; les issues de rollback inconnues restent explicitement dans
le rapport. Aucune ancienne release ou tag n'est supprimé/modifié.

## Portée des annonces

Le guide et la description disent « préversion expérimentale », jamais cadeau
final ni équivalence payante complète. Le seul système testé annoncé est
Windows Server2022CI. Les clients Windows10/11 et écoutes humaines restent
explicitement non validés. Aucun parcours de collections2006 n'est présenté
comme un essai de ce nouvel EXE2007. La lecture, les imports/exports et les
fonctionnalités encore partielles restent décrits dans FEATURES/STATUS/ROADMAP.
Les dépendances de développement restent dans les sources/recette, pas dans
les étapes d'installation de l'ami. L'hébergement GitHub public ne nécessite
pas de compte ; aucune permanence ni absence de suppression future n'est promise.

## Vérification locale de la proposition

Dix groupes unittest de données passent, avec mutations MSI/ICU/notices/CLI,
types bool/string, identité, doublons, chemins Windows, déterminisme ZIP et
découverte DATAONLY. Le refus du producteur en cours se produit après un seul
GET simulé, avant toute découverte d'artefact ; les dix reçus sont mesurés sur
des fichiers de test et une ambiguïté est rejetée.
Ils utilisent des rapports synthétiques explicitement marqués et ne certifient
aucun MSI réel. Quatre fichiers Python ont été parsés ; les trois scripts et
quatre blocs du workflow passent le vrai parseur PowerShell. Le modèle a été
refusé réellement. Les fonctions de transport sensibles et le bloc anonyme
restent identiques à la release sons réussie. Aucun accès réseau, artefact
2007, API MSI réelle, application ou publication n'a été exécuté par ces tests.
