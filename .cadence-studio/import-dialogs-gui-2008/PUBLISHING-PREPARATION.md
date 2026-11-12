# Assemblage privé, sans publication par cet agent

Le workflow complet est `cadence-import-dialogs-gui-2008.yml`. Il se place à
`.github/workflows/cadence-import-dialogs-gui-2008.yml` ; les autres fichiers du
payload se placent sous `.cadence-studio/import-dialogs-gui-2008/`. Conserver
l’arbre existant du driver comme `base_tree` : ce lot dépend du vrai dossier
`.cadence-studio/combined-2008-source`, déjà présent dans le driver producteur.
La présence de `.gitattributes` avec `* -text` dans le helper est nécessaire
pour préserver les SHA des scripts, du C++ et des données sous Windows.

`payload-utf8.json` contient un objet `files` de la forme
`{"chemin/relatif":"contenu UTF-8"}`. Ce n’est pas un tableau de tree elements.
La transformation inspectable, sans réseau ni modification de dépôt, est :

```sh
python3 prepare-tree-elements.py --payload payload-utf8.json --output /tmp/cadence-import-gui-tree-elements.json
```

Le résultat contient `tree_elements`, tableau d’objets `{path, mode: "100644",
type: "blob", content}`. La racine pourra transmettre ce tableau au champ
`tree_elements` du create_tree avec le `base_tree` existant ; si le schéma du
connecteur exige du texte JSON, sérialiser ce seul tableau. Elle est seule à
créer branche/commit et à publier ou déclencher le workflow. Le convertisseur
refuse un payload contenant `target.json` pour éviter de présenter un modèle
comme cible prête à exécuter. Ajouter ultérieurement la vraie cible examinée
comme tree element distinct, au même emplacement du helper.

## Passage au vrai stage produit

Le run **43319506534** a échoué avant compilation ; aucun stage n’a été produit
et le lecteur l’exclut explicitement. Sa preuve d’échec reste enregistrée dans
`producer-context.json`. La source corrigée ne change que le test SQLite et
est figée à `49272b75a4107c97130b8a46727af6a8c95d1c9a` / arbre
`fae79e265b3a21431388cd432a853228ffd7676b`, patch compressé
`c7654d9a8fa18adf9bcce0b6198c1ef907a2e5886a19339a08ed8ccb80f7b70d`.
Le producteur courant connu est le run **43322336613**, job **131545929459**,
driver `d685753476a30b8dc29e1fab979bb355263a4fd6`, compteur Actions10,
tentative1. Le contexte porte `reviewed-launched-producer`. Les identités du
stage, de l’artefact et de l’EXE restent inconnues et nulles.
Les échecs des compteurs8 et9 restent enregistrés avec leurs identités
respectives `43319506534` et `43321209033`. Le lecteur exige le seul
producteur courant du contexte et ne remplace jamais sa cible par un ancien run.
Le BuildNumber reste explicitement2008 et ne se déduit plus de run_number.
`target.json` n’existe pas et tous ses champs de produits futurs restent nulls.
La recette reste bloquée à son premier contrôle tant que le nouveau producteur
et son vrai stage n’ont pas été examinés.

Une fois le véritable artefact stage uploadé, la racine doit relever son
identifiant, son nom, run_number/run_attempt, expiration et digest GitHub,
puis les SHA et octets réellement mesurés du ZIP intérieur, de l’EXE et des
quatre compagnons originaux (`SHA256SUMS.txt`, `stage-manifest.json`,
`cadence-build.json`, `cadence-build-result.json`). Remplir `artifact_files`
comme map nom→`{bytes,sha256}` à partir de ces mesures externes examinées.
Remplir également les identités source/CI et les SHA source.json/patch du
véritable stage. Ne jamais fabriquer un manifeste, reprendre un SHA2006/2007,
ou marquer une cible pending comme `reviewed-produced-stage`.

Le déclencheur `push` est strict : branche `cadence-studio/windows-build` et
seul chemin `.cadence-studio/import-dialogs-gui-2008/target.json`.
`workflow_dispatch` reste disponible dans le YAML, mais le connecteur actuel
ne permet pas de l’invoquer. La première publication comprend uniquement la
recette, le contexte et les helpers, avec `.gitattributes` sous le namespace ;
aucun `target.json`, donc aucun essai déclenché. La racine activera l’essai
par un commit distinct ajoutant la vraie cible lorsque l’artefact existe.
Le workflow n’attend pas la
fin des exports, de l’installation MSI ou des autres QA du producteur :
l’artefact original uploadé et la cible complète examinée suffisent. Il ne
déclare aucune réussite de ces autres qualifications.

## Contrôles et chemins de la nouvelle VM

Le premier contrôle exige la vraie cible et son metadata avant toute
restauration, SDK ou profil. Le checkout a transporté le patch source en
morceaux base64 : le workflow vérifie le script/manifest d’origine, restaure
les cinq entrées binaires source comme données, puis effectue le contrôle
complet source.json/patch avant téléchargement du stage. Cette étape ne
reconstruit pas l’application et ne touche aucun profil.

`actions/download-artifact@v4` sélectionne exclusivement l’ID et le run
examinés. Le script de restauration compare d’abord les quatre compagnons
aux SHA/octets externes, vérifie tout l’inventaire SHA original puis les
manifestes, le ZIP intérieur et l’EXE. L’extraction garde les contrôles
anti-traversée/reparse et les plafonds de Notes6. Le digest du conteneur
extérieur est conservé comme métadonnée GitHub : le script ne prétend pas
recalculer les octets bruts de ce conteneur après extraction par l’action.

Tout le stage, le client compilé et les preuves restent sous RUNNER_TEMP.
Aucun Qt n’est installé et aucune application n’est recompilée. MSVC/SDK ne
compilent que le client UIA indépendant. Le lanceur réduit le PATH de
l’application à son bin et System32 et retire les variables Qt/QML/SDK et
jetons avant démarrage. La première passe reste sans `-AnalyzeFixture`.
Les rapports originaux, dumps numérotés, captures, journaux QML, reçu de
restauration et compile.log sont uploadés avec `if: always()`.

La qualification GUI et la revue visuelle restent à effectuer. Le lecteur de
preuves et les contrôles statiques ne valident pas l’interface.
