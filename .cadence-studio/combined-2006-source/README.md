# Cadence 2006 — préparation des helpers du prochain build Windows

Ce namespace neuf prépare les helpers et le workflow du candidat 2006. Il est
indépendant de `combined-2005-source`, qui reste conservé octet pour octet avec
les namespaces plus anciens. La comparaison stricte garde les mêmes 35 sorties
de référence ; `expected-reference.json` et `compare_reference.py` sont identiques
à ceux de 2005.

La publication doit réunir ces helpers et les quatre métadonnées de source
figées : `source.json`, `changes.patch.gz`, `handoff.json`, `SHA256SUMS.txt`.
Le Bootstrap vérifie le commit, l’arbre et le patch ; un dossier incomplet est
refusé. Aucun exécutable n’est annoncé par cette seule recette. Le commit
d’intégration `7826d590a2027564e490281da44e318491d73580` est un repère des
mini-tests ; le snapshot final et ses notices sont identifiés dans `source.json`.

Le workflow adapté garde son identité `cadence-combined-system-aac.yml`. Le
sixième run doit donner `2000 + run_number = 2006` ; le garde refuse toute autre
identité d’installateur. Le même kit Qt **6.10.2**, MSVC 2022 x64 et SDK
10.0.26100.0 restent sélectionnés. La préparation n’autorise ni ne lance le full :
les mini-qualifications Windows et le gel final relèvent de la coordination
racine. Les notices établies sont intégrées au snapshot. Le build reste expérimental
pendant l’audit des DLL particulières ; tout changement de distribution
ultérieur devra être documenté et requalifié avant publication finale.

La section `qualification` du futur `source.json` devra déclarer exactement :
36 tests Python, 21 scénarios Qt de stockage dans le CTest, 57 contrôles CLI,
35 sorties de référence et 5 exports AAC musicaux avec décodage externe. Ces
valeurs ne sont pas des résultats annoncés. Le helper générique lie les attentes
à l’arbre réellement reconstruit, puis refuse les résumés partiels, les skips et
les comptes différents dans les vrais journaux. Les résultats Linux annoncés
par l’agent racine restent distincts d’un résultat Windows.

Le contrôle GUI `Test-ReadyGui.ps1` observe uniquement un vrai contrôle Home/Intro,
conserve une capture puis ferme ses propres fenêtres. Il ne prépare pas lui-même
le profil ; celui-ci peut déjà contenir un INI issu des vérifications CLI. Son
rapport indique explicitement que l’assistant de premier lancement, le parcours
avec profil réellement neuf et sa complétion **ne sont pas testés**. Les nouveaux
textes de premier lancement du produit ne changent pas cette limite. Un essai
neuf sans INI, premier puis second lancement, français, sons de base et dossier
Scores doit rester une qualification séparée.

Les helpers gardent les gardes existants de GPL exact, notices et sources
correspondantes, zlib reconstruit, origine des DLL, source immuable et fermeture
possédée. Le stage réel est retenu avant QA avec sa provenance expérimentale ;
aucun ancien EXE n’est substitué au candidat. Le négatif vidéo exige exit1331,
zéro octet et un diagnostic frais ; il ne qualifie pas un export vidéo positif.

Les archives originales et notices restent dans `corresponding-sources`.
La recette embarquée sera nommée `build-recipe/combined-2006-source` pour préserver
la provenance de cette version ; aucun ancien namespace n’est réécrit. Les
artefacts GitHub restent expérimentaux, demandent un accès GitHub et expirent
après 14 jours. Leur existence ne constitue pas le lien de téléchargement public
du cadeau ni une qualification de l’installation, de l’édition ou des écoutes.
