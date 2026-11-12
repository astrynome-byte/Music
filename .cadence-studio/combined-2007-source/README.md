# Cadence 2007 — recette du prochain candidat Windows

Ce namespace neuf reprend les helpers éprouvés de combined-2006-source, conservé
avec ses sources et résultats. La recette Windows réutilise les scripts du dépôt
pour configurer, compiler, installer et empaqueter. Qt 6.10.2, MSVC 2022 x64 et
SDK 10.0.26100.0 restent sélectionnés. Les 35 sorties de référence et leur
comparateur restent identiques à 2006.

Le workflow garde l’identité cadence-combined-system-aac.yml. Son septième run
doit produire 2000 + run_number = 2007 ; toute autre identité est refusée. Ce
fichier prépare un build, sans annoncer un EXE, un MSI ou un hash source futur.
Les quatre fichiers de gel source.json, changes.patch.gz, handoff.json et
SHA256SUMS.txt sont réservés au gel final coordonné par root. Ils doivent identifier
le vrai code final, ses notices et le patch exact avant toute publication du lot.

La section qualification attend exactement 36 tests Python, 21 scénarios Qt de
stockage, 57 contrôles CLI, 35 sorties stables et 5 exports AAC musicaux décodés
par un outil externe. Ces nombres sont des attentes, pas des résultats 2007.
Les journaux réels doivent établir chaque succès sans skip ni compte différent.
Le cœur et les moteurs amont restent ceux de v4.7.6, au commit fixé dans la
sélection source ; aucun remplacement par une maquette n’est préparé.

La source finale inclut la politique CMake Cadence d’omission du seul forwarder
ICU local connu. Après Build et avant le premier archivage du stage, le workflow
exige l’absence de bin/icuuc.dll, le SHA Qt6Core mesuré, puis les 20 résolutions
statiques d’exports dans les fichiers du SystemDirectory Windows. Les helpers
verify_system_icu.py et required-system-icu.json sont repris sans modification
et ne chargent aucune DLL. Leur profil historique 2005 identifie le même QtCore,
pas le futur EXE 2007. Le SHA du nouvel EXE est calculé sur ses vrais octets.

Les deux rapports ICU sont conservés avec stage et livraison avant les sommes.
Le contrôle MSI demande RequireSystemIcu et le ProductVersion exact 4.7.6.2007 ;
la source finale doit donc inclure le Test-MsiInstall adapté. Le retrait CMake
sera qualifié dans ce full : aucun succès Windows du nouveau hook n’est déjà
annoncé par cette seule préparation. Les interfaces Windows clientes, la compatibilité
OS complète et l’écoute restent distinctes de la simple lecture PE des exports.

Le stage expérimental est retenu avant les autres QA et gardé même si elles
échouent. Notices et sources correspondantes, zlib reconstruit, origine des DLL,
licence GPL exacte, négatif vidéo, contrôles CLI/audio, observation Home/Intro,
MSI réel et désinstallation du seul ProductCode sont conservés. Les notices sont
vérifiées depuis les vrais fichiers source/installés, sans nombre arbitraire.

Le contrôle Home/Intro ne valide pas la complétion du premier lancement. Les
parcours de collections 2006 déjà réussis restent des preuves séparées ; aucun
nouveau parcours GUI de notes ou effets n’est ajouté à cette recette. L’édition
complète, Windows 10/11 client et les écoutes humaines restent à qualifier.

La recette jointe à la livraison portera build-recipe/combined-2007-source.
Les artefacts Actions restent expérimentaux, demandent un accès GitHub et
expirent après 14 jours. Ils ne constituent pas le lien public du cadeau, une
validation globale des licences ou une permanence de téléchargement.
