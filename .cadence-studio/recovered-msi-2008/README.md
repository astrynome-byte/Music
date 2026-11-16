# Runtime 2008 récupéré du MSI public

Origine nouvelle et explicitement distincte : MSI2008 public, extraction
administrative Windows puis comparaison à l’inventaire authentifié du stage.
Cette recette ne télécharge aucun artefact Actions et ne fabrique aucun reçu
de l’ancien producteur. Le statut historique failed31 est conservé.

Workflow Windows2022/10minutes, uniquement sur la branche autorisée et au
changement de `target.json`. La recette initiale est inactive : root publie
d’abord les helpers puis ajoute séparément la cible prête après revue.
Permissions contents:read, aucun secret transmis, aucune API d’écriture.

Seuls le MSI public, Python3.12 et les actions checkout/upload sont utilisés.
Le MSI est vérifié à120979784octets/SHAa3f934…52a9e, puis lu en mode0 pour
version4.7.6.2008, GUID indépendants, x64;1033 et2712lignes File avant `/a`.
La comparaison exige exactement2712chemins, tailles et SHA, EXE13cd…f6cd,
338fichiers licences/doc et aucune ICU locale. Aucun lancement d’application,
build, SDK, installation du produit ni mode portable n’est demandé.

L’inventaire est le blob public existant `af7d8b2a27c1468281efe849d4e098dac26639da`,
530785octets/SHA7b3b721f…81a4a4, réutilisé dans le nouvel arbre Git sans
dupliquer son contenu dans le payload texte. Les338chemins licences/doc ont
été comparés aux338notices du rapport d’installation original et coïncident.

La sortie est une preuve de récupération du runtime, pas une nouvelle
qualification musicale. Les rapports JSON et le journal admin borné sont
retenus14jours ; le MSI téléchargé et l’image temporaire sont nettoyés après
comparaison. La recette peut ensuite être répétée tant que le MSI public
reste disponible, sans promettre la permanence de cet hébergement.
