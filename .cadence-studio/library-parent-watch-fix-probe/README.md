# Candidat parent-only Windows : store21 et comparaison concurrente

Préparation non publiée, aucun Windows candidat exécuté à ce stade.
Source candidate exacte `391107f9d42518db272420d3f80215ff1e4ba389`, arbre
`ef85a87bbf4c5aad0f2add1a379ff5aaf1f3008b`. Les sept fichiers de production/test
sont aussi identiques à ceux de la source principale intégrée `7826d590`.

Le précédent run 43224732775 sur le store 2005 a observé 368 refus AccessDenied
avec fichier+parent et zéro refus sur 4 000 écritures parent seul ainsi que
4 000 sans watcher. Temp était sur C: NTFS, lookup ACL NTFS désactivé ; pas
d'appel Windows précis attribué. La preuve complète et immuable de ces
12 000 mutations est conservée dans le dossier frère
`library-watch-mode-stress-next/windows-run-43224732775`.

Ce nouveau mini utilise le backend candidat commun aux trois modes afin de
ne faire varier que la stratégie de surveillance. Le contrôle historique est
le **helper exact du commit2005 961c80b2**, conservé sous `control/` sans changer
ses octets. Trois noms de fonctions inline sont renommés au préprocesseur pour
coexister avec le candidat ; la stratégie ancienne et son fichier original
restent inchangés. Le mode parent-only Windows appelle maintenant le **vrai
watchLocalCatalog candidat**, plutôt qu'une simple reproduction dans le test.

Avant le stress, le job compile et lance les **21 scénarios du vrai store
candidat**, dont le nouveau writer processus128 et les remplacements à taille
et date égales. Sous Windows ces contrôles exigent zéro inscription/événement
fichier et vérifient notification, lecture finale et préservation des scores.
Le repli fichier est conservé sur les autres plateformes, où le stamp n'inclut
pas le FileID Windows. Une modification externe en place du catalogue peut ne
pas notifier le parent Windows ; Actualiser reste le repli. Tous les commits
des instances Cadence restent atomiques et notifient le parent.

La comparaison concurrente conserve les mêmes six phases et budgets que le
premier diagnostic : aucun watcher, ancien fichier+parent, véritable helper
candidat ; deux ordres inversés, 2 000 mutations demandées par phase. Si Temp
est partout clair, six phases dans des enfants neufs du LocalAppData Known
Folder sont ajoutées, hors des profils Cadence. Volume, droits et attributs
sont relevés avant toute transaction. Les callbacks n'ouvrent pas le contenu
du catalogue ; validation après fin du worker et destruction du watcher.

Le job requiert Qt 6.10.2, MSVC 17.14 x64 et SDK 26100. Les dix entrées de
compilation, le manifeste et le contrôle961 sont vérifiés avant/après ;
commandes, logs, versions et empreintes sont conservés. Toute erreur de commit
du mode candidat fait échouer le mini. Une expérience sans erreur du contrôle
ancien reste un résultat borné, pas une preuve d'absence de la course initiale.

Contrôles locaux : les octets du store/test21 sont ceux du Linux21 déjà réussi,
non répété inutilement ; adaptateur de stress compilé et exécuté sous Linux,
sans conclusion Windows. AST PowerShell, YAML et gardes du vrai helper passent.
Le helper ne prend pas un résultat Linux pour une mesure Windows. Aucun
lancement de l'application, QML, panneau, écoute ou installation n'est effectué
par ce mini. Le succès Windows éventuel sera nécessaire avant un build2006 et
sa vraie recette GUI ; il ne suffira pas à qualifier l'ensemble.
