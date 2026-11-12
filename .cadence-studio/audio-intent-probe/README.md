# Mini Windows AU15 — backend et writer réels, application complète séparée

Préparation non publiée et **non exécutée sous Windows**. Le responsable doit
relire puis publier le workflow `.github/workflows/cadence-audio-intent-probe.yml`
et son espace neuf `.cadence-studio/audio-intent-probe/`.

Source candidate **`88f49ea89ba96471fb00abd4e3074488239648aa`**, arbre
`4c63daf6fd5d5fd44f9fb6a05f9fec18236b80a9`, parent `b02b41f4` ; branche locale
`cadence/audio-intent-retention-candidate`. Le contrôle utilise les six fichiers
moteur exacts du parent `b02b41f4cbb31f43df073d6cdf5249a18d425a7e`, identiques
à ceux du full 2006. Son writer et ses dépendances inchangées, le test courant
et l’accès ami au constructeur restent ceux du candidat : c’est un contrôle
des anciens chemins moteur, pas une application ancienne reconstruite.

## Snapshots exacts

`source-snapshot.zip.base64` contient seulement du code, ses en-têtes, licences
et métadonnées : **34 CPP, 170 fichiers candidat et six fichiers de contrôle**.
Les 178 membres ZIP comprennent aussi le manifeste et ses sommes. Le snapshot
provient de `git show`, avec SHA Git des blobs et SHA-256. Les classes et les
tests n’ont aucune substitution de framework. Les doubles restent aux feuilles
synthétiseur/plugin/FX, comme dans le test Linux.

- ZIP : **368 456 octets**, SHA-256
  `126959e3b82f29ffe47199bdca682d42b7c4b4e9cc2753f9386c1f4c118b0e47`.
- Transport base64 : **496 394 octets**, SHA-256
  `c3b0610f24f0760e27655d6767d1cdfba3a2616e78e9267850f24ba6eccfe3b5`.
- Manifeste source :
  `26fb0c02cf17d8e065431cc3dc23dc39be3865810b6487894c145ada62bf5b8c`.

`RestoreSnapshot.py` refuse archive différente, membre supplémentaire, lien,
collision de casse, dépassement de taille, mauvais octet/SHA/blob Git ou sortie
existante. Il crée une copie possédée séparée du contrôle ancien et vérifie ses
170 fichiers. Les deux arbres sont contrôlés avant et après les exécutions.
Aucune copie ou configuration n’écrit dans le worktree produit.

Le profil de test est rendu par `configure_file` depuis le **template canonique**
du dépôt, pas un header de framework réécrit. Il active threads/RPC et les
interfaces utilisées ; aucun hôte VST, pilote ASIO ou codec multimédia n’est
compilé. La cible possède seule `CADENCE_BUILD`, pour que le même header ne
puisse pas activer accidentellement le contrôle OFF. Son SHA normalisé LF est
`0a3698bb1600a10760128ef912f9558b1bf6b4201a2cfee221d461f2b13a3358`.
Les **34 prétraitements Linux sur ce snapshot** passent sans emprunt d’en-tête
au worktree principal ; cela ne constitue pas une compilation Windows.

## Étapes natives exigées

Le workflow exige Windows Server 2022 x64 GitHub-hosted jetable,
**MSVC 17.14**, SDK **10.0.26100.0**, Qt **6.10.2** `qtbase` et Python **3.12**.
setup-python se place après Qt et le script vérifie encore la version
effectivement sélectionnée. CMake/Ninja compilent trois petites variantes :

| Variante | Résultat obligatoire |
| --- | --- |
| ON | Sortie 0, exactement **10 groupes** moteur + même instance réelle de réglages + vrai writer natif |
| OFF | Sortie 0, exactement **3 groupes** du comportement de référence |
| Ancien moteur, entrée | Sortie 1 et erreur exacte de remplacement de la demande par le secours |
| Ancien moteur, sauvegarde après traitement | Sortie 1 et erreur exacte `Native writer saved the fallback instead of the original request` |

Les échecs attendus du contrôle ancien sont distingués d’une erreur de
compilation, de chargement, de timeout ou de toute autre assertion. Ces dernières
font échouer le mini. Les sources et les huit fichiers QA épinglés sont revérifiés
après exécution, et les versions/empreintes du compilateur, des DLL Qt, des trois
exécutables et des profils générés sont conservées.

Le vrai `MscWriter` nécessite zlib même en mode Dir. Le workflow reprend le
**composant Windows x64 /MD source zlib 1.3.2 déjà qualifié**, artefact
`13891238030` du run `43101767743` ; son existence a été vérifiée le
12 novembre 2026, expiration annoncée le **25 novembre 2026 à 21:18:34 UTC**.
Les helpers existants `prepare_zlib_package.py` et
`Validate-OpenSourceZlib.ps1`, conservés sans modification, vérifient sources,
licence, manifestes, sommes, architecture/runtime et trois fichiers critiques.
Le paquet préparé n’écrase pas le transport original et est revalidé après
les tests. Aucune bibliothèque de sons n’est téléchargée ou chargée.

## Preuves et limites

Les JSON/logs sont conservés 14 jours ; les blocs
`CADENCE_AUDIO_INTENT_EVIDENCE_BEGIN/END` indiquent nom, taille imprimée,
taille réelle et troncature éventuelle. Le résumé natif utilise
`CADENCE_AUDIO_INTENT_REPORT_BEGIN/END`. Le job n’archive ni application,
installateur, banque, SDK Qt ni exécutable de test comme livraison utilisateur.

Contrôles locaux de préparation réussis : restauration exacte, génération du
profil canonique, refus d’écrasement et de modification du contrôle,
parsing YAML/PowerShell, manifestes réels, refus d’un échec ancien sans rapport,
comptage exact des groupes et refus de qualification native depuis Linux.
Les transcripts Linux servent uniquement à tester le parseur de protocole.
Voir `checks/`, `source-preparation/PREPARATION.json` et sa revue.

Même si ce mini réussit, il ne qualifie pas l’application complète, le mixeur
GUI, un vrai plugin, une vraie banque, une écoute ou la réouverture d’un MSCZ.
Le signal constant des doubles vérifie le chemin de traitement et le niveau
auxiliaire, sans revendiquer de qualité musicale.

**Le signalement UI du secours manque encore.** Les modèles actuels considèrent
les métadonnées valides comme actives et insèrent le choix courant avant la
liste des ressources réellement disponibles ; ce backend ne transforme pas cette
liste en état d’absence. Un complément UI indépendant est prévu. AU15 backend
et AU14 avertissement restent deux couvertures distinctes. Le full 2006 est
immuable ; aucun full 2007 n’est lancé par cette préparation.
