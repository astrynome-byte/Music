# Qualification Windows ciblée des notes privées

Préparation uniquement, non publiée et non exécutée sous Windows à ce stade.
Les sept fichiers de production/test sont extraits avec `git show` du commit
`2e1b0987e633bcec0247d03cde8933408fd95f81`, arbre
`df58fc9b447840ab2b4451096f5e12ba18a29455`, branche `cadence/annotations-v3`.
Le parent est `961c80b235d413dc9d123ea8f669ddb7f84ecd09`, source de l'application
2005 ; ce mini ne change ni cette application ni ses paquets conservés.

Le nouveau namespace `.cadence-studio/annotation-store-probe` et le workflow
`.github/workflows/cadence-annotations-store.yml` sont distincts des anciens
probes. Aucun fichier Android, autre namespace, branche main ou release n'est
modifié par cette préparation. Seul root pourra publier le payload préparé.

Le mini compile uniquement le vrai store, son journal de brouillons et les
20 scénarios QtCore du commit annoncé : notes/collections, sauvegarde exacte,
révisions concurrentes, brouillons fermés et récupération globale, surveillance
native et porte XML. Le modèle C++, QML, éditeur, audio et installateur ne sont
ni compilés ni exécutés par ce job. LI05 reste partiel ; aucun parcours GUI ou
lecteur d'écran n'est qualifié par cette cible.

Environnement exigé : runner GitHub jetable Windows Server 2022 x64,
MSVC 17.14 x64, SDK `10.0.26100.0`, Qt `6.10.2` / `win64_msvc2022_64`.
Le workflow restaure/installe uniquement `qtbase`, puis utilise CMake, Ninja
et cl du runner. Le helper impose le manifeste exact et 20 scénarios ; il
vérifie tailles/SHA des sept sources et du manifeste avant puis après le test.
`.gitattributes` conserve leurs octets UTF-8 sans conversion LF/CRLF.

Le rapport conserve noyau/OS, PowerShell/.NET, image du runner, versions et
empreintes du compilateur/Qt, commandes exactes et codes de sortie. Les logs
CMake/Ninja/qmake/CTest, les deux vérifications de sources et le SHA du binaire
de test sont archivés, y compris après un échec. Les artefacts Actions expirent
après 14 jours et peuvent exiger un compte ; ils ne constituent pas un lien de
cadeau public ou un installateur utilisateur.

Contrôles préparatoires réellement effectués sous Linux : YAML lu et périmètre
vérifié, AST PowerShell du helper et de deux blocs du workflow sans erreur,
sept contrôles des vraies fonctions de garde (dont source modifiée, manifeste
modifié et faux transcript rejetés), refus du helper complet sur Linux avant
création d'un dossier de sortie. Les transcripts de garde sont explicitement
synthétiques et ne simulent pas une qualification Windows. Les sept sources
correspondent aussi exactement aux octets du contrôle Linux 20/20 antérieur ;
aucune nouvelle suite musicale ou applicative n'est déduite de ce constat.

Après publication par root : laisser le push du nouveau namespace déclencher
le mini, puis vérifier 20/20, manifeste avant/après, versions, journaux et SHA
du binaire de test. Un succès du mini permet de poursuivre l'intégration et la
recette de la vraie GUI ; il ne remplace pas la compilation complète ni les
contrôles de clavier, récupération en fenêtre réelle ou installation Windows.
