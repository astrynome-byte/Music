# Qualification courte du stream AAC de production

Préparation locale seulement, sans envoi GitHub. Ce dossier contient des
**blobs Git exacts** de `0feb75b7abc54c4b239fd7313b90ba0fa020d930`, arbre
`1744f82e9a05de784f9ea6bb6a185d418ce4eb0b`, dans `source/` avec leurs chemins
d'origine. Il ne remplace pas les classes de production par un autre prototype.
`source-manifest.json` donne taille, SHA-256 et identifiant du blob pour chaque
source. Le validateur externe est la copie inchangée de `verify_adts.py` du
prototype Windows validé ; son origine et son empreinte sont séparées.

Le CMake original `test/cadence/system_aac_native/CMakeLists.txt` est utilisé
comme sous-projet. La recette extérieure remplace uniquement son choix de CRT
statique par **/MD**, pour correspondre au runtime de l'application. Elle
vérifie Windows x64/MSVC, compile Release et exporte la commande du vrai
`windowsaacstream.cpp`. Les sources du codec et du test ne sont pas modifiées.

Dix essais sont prévus :

- Deux encodages par la vraie classe `WindowsAacStream`, à 44,1/48 kHz, depuis
  des flottants convertis par le vrai helper PCM16 et poussés par blocs de
  137 trames. La classe effectue accumulation 1024, padding et drain.
- Six cas C++ du helper PCM16, extraits du `HARNESS` Git original : rails,
  arrondis, clipping, nonfinis, null/empty et limites de formats, dont 64 bits.
- Deux cas du vrai contrat `AbstractAudioEncoder` et `Ret` : drain sans nouvel
  octet réussi et erreur tardive remontée. Progress/chemin/format/logging sont
  des données minimales de test, sans Qt ; ce n'est pas le test de l'adaptateur
  `WindowsAacEncoder`, des entrées-sorties du moteur ou de sa GUI.

Après ces tests, FFmpeg **décode seulement** les deux AAC produits par MF.
Le validateur contrôle durée, fréquences 440/660 Hz, niveaux, absence de
saturation et valeurs non finies. Il exige `passed_with_decode`, relève taille
et SHA-256, et imprime les petits rapports entre balises
`CADENCE_SYSTEM_AAC_REPORT_BEGIN/END`. Aucun octet audio en base64 n'est imprimé.
Les commandes de compilation sont vérifiées pour /MD, MSVC Release et pointeur
64 bits. Une absence de MF/MFT ou d'un outil est un échec explicite.

Le workflow n'installe ni Qt, application, banque sonore ou composant Windows.
FFmpeg est un outil de test du runner, installé par Chocolatey seulement s'il
manque. Aucun pare-feu, rôle Server, fonctionnalité OS ou redémarrage n'est
modifié. Les artefacts de sources/recette, petits AAC, logs et rapports restent
14 jours. Aucun exécutable d'application ni codec commercial n'est livré.

**Limites :** avant exécution réelle du job, cette recette ne valide aucun
encodage Windows supplémentaire. Un succès qualifie le stream et le contrat
isolé, pas l'adaptateur Qt, le moteur complet, les partitions musicales, MP4,
la compensation du délai, le gapless, les autres débits ou une écoute humaine.
La prochaine étape sera la compilation complète sous l'option système, puis
les comparaisons de partitions et la qualification image/son.

Le code neuf est GPL-3.0-only. Les sources reprises gardent leurs mentions et
`source/LICENSE.txt`. Aucun binaire du codec Windows ou SDK n'est inclus.

Le workflow possède ses propres filtres de chemins. Pour ne pas lancer le
fullbuild sur le même push, le pilote principal utilise le marqueur déjà
reconnu `[cadence-packaging-only]`. Cette préparation n'a modifié aucun autre
workflow, le namespace des sources de référence, de bibliothèque ou de probe.
