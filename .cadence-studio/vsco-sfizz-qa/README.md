# Qualification native SFZ par sfizz VST3 — lot isolé

Ce lot réutilise l'exécutable Cadence Windows 2002 authentifié. Il ne recompile
pas l'application et ne transforme pas encore le gestionnaire SF2/SF3 en
installateur SFZ. Un fichier SFZ seul n'est pas un instrument directement pris
en charge par le moteur Fluid de MuseScore : le lecteur VST3 réel est requis.

1. Restaurer l'artefact original et vérifier tous les fichiers de provenance.
2. Télécharger le petit installateur officiel sfizz 1.2.3 et l'outil officiel
   innoextract 1.9, avec tailles et SHA-256 fixés. **Ne pas lancer l'installateur
   sfizz** : son paramètre `/DIR` ne réoriente pas le dossier VST3 système.
   Extraire ses données vers un nouveau dossier temporaire détenu par cet essai.
   Vérifier les 25 fichiers du bundle et la DLL PE x64 réelle.
3. Lancer `--register-audio-plugin` sur ce bundle isolé, avec profil Cadence neuf.
   Lire le registre effectivement produit ; aucune entrée n'est inventée.
   Arrêter avant les échantillons si ce premier hôte réel échoue.
4. Télécharger seulement 46 fichiers CC0 du commit VSCO fixé : 43 WAV,
   2 définitions SFZ et la licence, 99 534 068 octets au total. Chaque fichier
   est contrôlé par sa taille et son identifiant Git blob SHA-1 source fixé ;
   le SHA-256 effectif est conservé dans le reçu produit pendant le job.
5. Importer l'exercice CC0 original ; utiliser ses véritables IDs de pistes.
   Restaurer l'état v5 du véritable plugin pour flûte et violon, gain maître
   explicite −12 dB, puis exporter trois WAV (dont flûte témoin −18 dB).
6. Exiger le rapport de gains −18 dB, WAV stéréo non silencieux/finis/sans
   pleine échelle, différence flûte/violon et conservation en sauvegarde seule
   de l'identité VST3 et de l'état brut. Les originaux ne doivent pas changer.

Le témoin de gain modifie les 13 gains **de régions** du SFZ flûte CC0. Il
empêche de valider par erreur la sinusoïde par défaut de sfizz lorsque l'état
ou le fichier n'est pas restauré : le seul fait d'obtenir un WAV audible ne
suffit pas. Le sérialiseur a été comparé au véritable store/load sfizz et au
FStreamer du SDK correspondant ; ces vérifications Linux ne remplacent pas
l'essai de chargement du plugin Windows.

Aucun Qt de développement n'est installé par ce workflow ; les processus Cadence
utilisent leur propre dossier bin et System32 dans PATH, avec les variables
QT_/QML_ héritées retirées. Cela ne remplace pas toute la qualification MSI.
Les processus et dossiers sont détenus par ce job GitHub Windows jetable ; aucun
profil existant, plugin système, banque commerciale ou fichier personnel n'est
modifié. Les délais concernent seulement ces processus détenus.

L'artefact contient les rapports, journaux et exports musicaux autorisés, pas
les binaires sfizz ni les WAV bruts des banques. Il expire après 14 jours et
reste un artefact Actions ; ce n'est pas un lien de livraison anonyme du cadeau.
Les fichiers de source `../combined-source/` restent ceux du driver original
2002 et sont exigés par Restore-CombinedStage.ps1.

Restent distincts : interface réelle du gestionnaire de collections, ouverture
de l'éditeur sfizz, ergonomie de sélection des SFZ, sauvegarde après lecture du
même projet GUI, installation/premier lancement MSI, écoute humaine, adéquation
musicale des nuances/articulations et disparition d'un plugin. Aucun de ces
contrôles n'est annoncé comme passé par ce script.

Licences : code de qualification GPL-3.0-only ; exercice et VSCO CC0-1.0 ;
lecteur sfizz sous notices BSD/tiers et conditions GPLv3 de son VST3/SDK.
Ne pas étiqueter tout le bundle BSD : l'audit précis des polices et notices est
conservé dans le dossier research du lot source avant redistribution finale.
