# MSI2008 depuis le stage réellement compilé

Préparation privée, sans publication. Le modèle `package-bindings.template.json`
reste `ready=false` tant que les rapports de reprise ne passent pas. Les pins
déjà mesurés viennent du lecteur DATAONLY43417852349 ; aucun reçu de MSI n'est
inventé. L'application n'est jamais recompilée par ces helpers.

Source originale a2b7abaf045a8f3cb84ec2953d9e0e51b9e78903, arbre
c5452043983a048ef0aeef085615af903de3f5b0, commit CI compilé
95cebb22fe6cbde22919c94f2b480bd14c3eb8de. Les sources sont archivées depuis ce
commit CI restauré exactement, avec le même arbre que la source originale.
EXE SHA256 :13cd4e6d2f408d2e64b187d4c3bff1188ff4192ac7b670d3a12373bbeb37f6cd.

## Entrées et fermeture des vérifications

`Package-Retained2008.ps1` reçoit les chemins explicites du stage restauré, du
checkout source CI95 propre, du source.json original, des quatre métadonnées
originales, de l'inventaire runtime mesuré, du reçu DATAONLY, des pins revus,
des sources de composants et d'une recette de build sélectionnée. L'output
doit être nouveau sous RUNNER_TEMP, distinct de toutes ces entrées.

Les fichiers LF authentifiés sont conservés avec `.gitattributes -text`. Un
nouveau reader Windows peut écrire des CRLF et produire d’autres empreintes :
il ne peut pas réutiliser les pins LF sans nouvelle revue et mesure.

Le reçu DATAONLY peut être une projection du console authentifié si la racine
la sélectionne et la pinne explicitement. Elle doit garder son libellé de
projection ; ce n'est pas une métadonnée du producteur original.

Le rapport de qualification construit par la reprise doit avoir :

```json
{
  "schema_version": 1,
  "ready": true,
  "passed": true,
  "application_recompiled": false,
  "source_ci_commit": "95cebb22fe6cbde22919c94f2b480bd14c3eb8de",
  "source_tree": "c5452043983a048ef0aeef085615af903de3f5b0",
  "executable_sha256": "13cd4e6d2f408d2e64b187d4c3bff1188ff4192ac7b670d3a12373bbeb37f6cd",
  "build_number": 2008,
  "counts": {"cli_checks":57,"reference_outputs":35,"music_aac_cases":5},
  "gates": {
    "native_practice": {"passed":true,"path":"CHEMIN_DU_RAPPORT_REEL","bytes":0,"sha256":"EMPREINTE_REELLE"}
  }
}
```

Cet exemple de structure n'est pas un résultat et ne passe pas les gardes. Les
dix gates exacts sont native_practice, native_omr, native_transcription,
audio_transcription_import, cli57, reference35, aac5, stage_notices, stage_GUI et musical_roundtrip.
La construction de ce rapport est réservée à l’agrégateur revu de la reprise
`qualify_retained_resume.py`, qui valide réellement les dix schémas et critères.
Ce helper ne remplace pas cet agrégateur par une seconde définition des tests :
il exige son succès puis rehashe chaque rapport effectivement validé. Le rapport stage_notices doit aussi passer ses propres contrôles et
chacun de ses fichiers est vérifié dans le stage.

Le contrôle Python relie tous les fichiers runtime au ledger complet mesuré
depuis le ZIP original. Il vérifie les quatre originaux, le PE AMD64, CI95,
les sources des onze composants, les265 notices, leur SHA256SUMS et leur lien
au build original. Il copie les neuf assets WiX depuis leurs **blobs Git
épinglés**, indépendamment des fins de ligne du checkout Windows. Le stage,
les notices et les DLL ne sont jamais modifiés ou redéployés.

## Empaquetage uniquement

Le microprojet CMake est `LANGUAGES NONE`, sans cible ni règle `install()`.
Il réutilise le module et le template WiX d'origine, le GPL RTF et l'icône
originale du même arbre. MUE_PACK_INSTALL_DIR est ON et
CPACK_INSTALL_CMAKE_PROJECTS doit être vide : CPack ne lance ni l'installation
du projet, ni windeployqt, ni une compilation. L'architecture MSI est x64.

Le ProductVersion reste4.7.6.2008, ProductCode
{CA4AC56B-9ED9-568F-9F5A-0D9475D4CC26}, UpgradeCode
{319B992F-470A-465B-9A79-6B0CBFC7D6C7}. Le template conserve l'identité,
les associations Cadence et la coexistence officielle déjà prévues.

Sept assets sont créés dans `deliverables/` : MSI, source exacte.tar.gz,
recette.zip, sources des composants.zip, notices.zip, courte notice française
et SHA256SUMS.txt. Les archives et outils de développement restent hors du
MSI ; le destinataire n'installe que le programme. Les sources/recettes sont
fournies séparément conformément aux licences. Aucune archive portable n'est
annoncée. Le source.tar.gz porte le commentaire Git CI95, vérifié à la lecture.

Une seconde vérification conserve les comparaisons du stage, du checkout et
des composants, même après un échec de WiX. Les processus enfants sont bornés
et le Job propre est drainé avant fermeture. Les rapports distinguent
empaquetage, exécution MSI et publication ; aucun faux PASS d'installation.

## Installation réelle à suivre

Le wrapper `installer-test/Test-Retained2008Installer.ps1` appelle le helper
MSI d'origine byte-identique et ajoute les pins de2008. Voir son README :
`-RequireGui` impose le vrai parcours installé, les notices, fermeture0 puis
retrait du seul produit exact. Sans GUI, le statut est limité au CLI. Cette
préparation Linux n'a produit ou installé aucun MSI et n'a lancé aucun EXE.

Le packaging n'a besoin ni de Qt SDK ni de MSVC : Python3.12, Git, CMake/CPack
et WiX3 sont des outils **CI seulement**. La recette installateur SDK/probe
reste distincte du runtime livré. Le premier lancement Windows10/11 client,
le matériel et l'écoute ne sont jamais déduits d'un empaquetage.

## Recette du job MSI autonome

`cadence-retained2008-msi.prepared.yml` reconstruit uniquement le checkout
source et restaure exactement le stage du producteur12, puis authentifie le
succès réel du job QA43421094979/131870989277 par API et SHA du ZIP. Il ne
rejoue aucun des tests déjà qualifiés. Aucun SDK Qt n'est installé. MSVC/SDK
n'est activé qu'après l'empaquetage, pour compiler le petit observateur UIA.
Le wrapper MSI impose ensuite `-RequireGui` avant l'upload des sept fichiers.

Les fichiers `target.template.json`, `qa-artifact.selection.template.json` et
`package-bindings.template.json` restent inactifs. L'activation de la racine
autorise l'acquisition du vrai ZIP QA épinglé et le travail qui en dépend ;
elle n'affirme aucun succès MSI. Le SHA du rapport brut reste null dans les
modèles : le lecteur le mesure seulement après authentification du ZIP entier,
vérifie ses dix rapports puis émet séparément
`retained-package-bindings.MEASURED.json` avec ready=true. L'original du modèle
reste ready=false. Ces nouveaux bindings sont la seule entrée du packaging.
Le reçu LF connu choisi par cette recette est conservé sous son nom explicite
`known-evidence/dataonly-console-receipt.projection.json`, SHA256
6ea5c0b57d9fd56dd98bbef3018e237077817778af8cfbdaa71a9682d3c2a839.
Ce fichier est une projection authentifiée du console DATAONLY, et garde ce
statut. Le nouvel inventaire Windows n'est pas substitué à l'inventaire LF.

`Restore-QualifiedQaEvidence.py` extrait seulement les dix JSON épinglés du
ZIP QA authentifié. `-QualificationEvidenceRoot` résout leurs anciens chemins
absolus via un index de relocation : le rapport agrégé et les JSON d'origine
ne sont jamais réécrits. Chaque JSON est encore vérifié contre le SHA brut du
rapport agrégé, lui-même épinglé. Les rapports MSI incluent cet index et les
preuves originales. L'upload Actions reste un artefact de travail expirant
après14jours ; aucun lien public pour le cadeau n'est créé par ce job.

Les sources des composants incluent aussi les deux compagnons zlib originaux
du stage, indépendants des onze archives du collecteur : l'archive complète
Cadence-zlib-1.3.2-corresponding-source.zip et son profil verrouillé. Leur SHA
est repris de la mesure du ledger original ; ils ne sont pas déployés dans
le programme destiné au musicien. Un nouveau reçu
`zlib-source-supplement.MEASURED.json`, explicitement dérivé de ces deux
originaux, accompagne les sources ; aucun supplément absent du stage
historique n'est présenté comme un original.
