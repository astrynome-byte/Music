# Inspection DATAONLY du full Windows 2007

Cette proposition ajoute uniquement un workflow de lecture avant activation.
Le producteur est fixé à `43266732201`, job `131352164369`, pilote
`c3421a217c76a1b2cc5d4fab74305d209491d82f`, source originale
`5058d29dad67e6131ee46ee617258ccfed8ba4b0`, arbre
`58d06a1c89e99173b0473587245187df5bc3b3cf`.

Le workflow s'exécute sur Windows2022 avec Python3.12 et seulement
contents:read/actions:read. Il charge les six entrées de l'inspecteur publiées
au commit immuable `8004e8d1ff9d5e0ff8761a482e563624c7427b6d` et vérifie leurs
SHA exacts. Il ne charge aucun target actif et ne fournit aucun ID d'artefact
ou hash binaire à inventer : l'inspecteur observe les trois artefacts réels
après succès du producteur, vérifie leurs ZIP, leurs dix rapports et les
fichiers réels, puis prépare localement les sept assets et leurs SHA.

Les marqueurs `CADENCE_WINDOWS2007_INSPECTION_BEGIN/END` de l'inspecteur
contiennent son reçu complet. Le workflow vérifie ensuite les dix JSON
originaux et source.json, et imprime un candidat ready=false complet sous
`CADENCE_WINDOWS2007_READYFALSE_CANDIDATE_BEGIN/END`, sans tronquer les objets.
Ce candidat est une projection des vrais reçus pour revue, pas un target actif,
une autorisation de publication, un tag ou une URL publique inventée.

L'upload est limité à douze fichiers JSON : les dix rapports originaux,
source.original.json et le reçu d'inspection. Aucun MSI, ZIP de sons/sources,
exécutable, banque ou autre binaire n'est envoyé. Sur échec, les données déjà
présentes sont conservées comme échec ; aucun succès n'est simulé.

Le workflow se déclenche uniquement lorsque son fichier est publié sur la
branche autorisée. Il ne comporte ni workflow_dispatch, ni trigger tag/release,
ni opération d'écriture GitHub. Aucune compilation complète, installation ou
exécution de Cadence n'est effectuée. Les ouvertures MSI sont uniquement des
SELECT de base READONLY0. Aucun compte, activation ou publication n'est ajouté.

La règle relative `cadence-windows-2007-data-inspection.yml -text` est à
fusionner dans `.github/workflows/.gitattributes` sans écraser les règles
existantes. Cette préparation locale a seulement parsé le code ; le vrai
workflow n'a pas été lancé par son auteur.
