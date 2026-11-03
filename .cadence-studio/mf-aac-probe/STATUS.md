# État du prototype — 3 novembre 2026

Prototype autonome **0.1.0** dans `/workspace/cadence-mf-aac-probe`. Code original
GPL-3.0-only ; seules les API du SDK Windows et le codec système sont utilisés.
Aucun changement de `/workspace/cadence`, du worktree AAC ou du pilote CI.
Aucun accès GitHub, commit, fusion, exécutable Windows ou publication.

## Préparé

- CMake/MSVC x64 + C++17, sans Qt ou dépendances MuseScore.
- Chargement facultatif MF, COM MTA, PCM16 stéréo 44,1/48 kHz -> AAC-LC ADTS,
  blocs 1 024, timestamps/durées rationnels, retry, drain et cleanup.
- Refus explicites si MF/MFT/ADTS manque ; pas de faux fallback AAC.
- Vérification ADTS native, sorties partielles nettoyées, métadonnées de
  compteurs/temps ; aucune compensation de priming annoncée.
- Tests Windows CTest reproductibles dans des dossiers frais, script
  PowerShell et fragment de job local, sans téléchargement ni publication.
- Validateur Python des trames, durée et signal stéréo connu, décodage
  facultatif avec les outils déjà installés, SHA-256 et rapports distincts.

## Réellement testé

- **16 tests Python PASS** sous Linux : corruptions ADTS et contrôles de
  signal ; vrais AAC générés par **FFmpeg**, puis décodés à 44,1/48 kHz sur
  1,25 s ; rejet d'un flux silencieux. Ces tests qualifient le vérificateur,
  pas le MFT Windows. Les petits en-têtes synthétiques ne sont pas de l'audio.
- Revue indépendante en lecture des appels COM/MF et du cycle de vie ;
  corrections de drapeaux de sortie, métadonnées et répétition CTest.

- Syntaxe des trois fichiers Python et du script PowerShell vérifiée ;
  refus explicite de l'hôte Linux par CMake et PowerShell observé.
- L'orchestrateur renvoie bien un échec, avec rapport non validé, lorsque
  l'exécutable natif manque ; aucune réussite Windows n'est inventée.
- Contrôle des espaces de fin et fins de fichiers effectué.

Versions et portée sont consignées dans
[evidence/local-checks.json](evidence/local-checks.json).

## Non validé et prochaine action

**Aucune compilation C++/MSVC ni exécution Windows du prototype.** Aucune
écoute, comparaison avec FDK, intégration à Cadence ou vidéo avec son validée.
La disponibilité réelle de MF selon les éditions Windows reste à mesurer.

Prochaine action : importer ce petit dossier dans une branche d'essai
autorisée et lancer `scripts/Run-Probe.ps1` sur un runner Windows x64. Conserver
les deux AAC, journaux et rapports, vérifier les HRESULTs éventuels, décoder
les sorties puis écouter avant de concevoir l'adaptateur de production.
Le succès du programme de test ne suffit pas à déclarer AAC livré dans Cadence.
