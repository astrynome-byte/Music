# Essai autonome de l'encodeur AAC Windows

Prototype **0.1.0**, indépendant de Cadence Studio. Il évalue la possibilité de
conserver AAC et, plus tard, la vidéo avec son sans lier FDK-AAC. Il utilise
l'encodeur **AAC-LC du système Windows**, via COM et Media Foundation ; aucun
codec commercial, source FDK ou enregistrement de banque sonore n'est repris.
Le code original du prototype est sous **GPL-3.0-only**, voir [LICENSE.txt](LICENSE.txt).
Les composants du système Windows gardent leurs propres conditions et ne sont
pas inclus dans ce dossier. Aucun paquet multimédia n'est installé automatiquement.

**État : sources et vérificateur préparés. Aucune compilation ni exécution
Media Foundation sous Windows n'a encore été effectuée. Ce prototype n'est
pas intégré à Cadence et ne rétablit pas actuellement son export AAC.**
Le [statut](STATUS.md) distingue précisément les contrôles réalisés.

## Ce que le programme fait

- Accepte PCM16 signé, stéréo entrelacée, à **44 100 ou 48 000 Hz**. L'entrée
  vient d'un fichier PCM brut little endian ou d'une sinusoïde de test générée
  localement : 440 Hz à gauche, 660 Hz à droite, amplitude 0,2.
- Demande AAC-LC **ADTS**, à 96/128/160/192 kbit/s. Le type accepté par le MFT
  est relu ; un refus ne déclenche pas de substitution ni de faux fichier AAC.
- Regroupe les entrées en blocs de 1 024 trames PCM, horodatés en unités de
  100 ns. Le dernier bloc est complété de zéros. Les compteurs réels et ajoutés
  sont conservés dans les métadonnées.
- Récupère les sorties, traite `MF_E_NOTACCEPTING` en réessayant le même bloc,
  puis envoie fin de flux et drain. Samples, buffers, événements, COM et MF
  ont un nettoyage prévu pour les chemins de succès et d'erreur.
- Contrôle la structure ADTS, le profil, la fréquence, les canaux, le nombre
  de trames et la durée avant de conserver le fichier. Il refuse d'écraser
  une sortie existante et supprime sa sortie incomplète en cas d'échec.
- Journalise les timestamps/durées de sortie disponibles. Il ne compense pas
  le délai de l'encodeur et ne promet pas un résultat sans délai initial.

Le comptage accepte entre `ceil(trames_PCM / 1024)` et ce nombre **+4 trames
AAC** pour rendre explicite la tolérance de délai/remplissage du prototype.
Cette limite de test ne constitue pas une mesure de synchronisation musicale.
Les CRC éventuels sont repérés mais pas recalculés. La structure d'un fichier
ne prouve pas que son contenu comprimé se décode correctement.

## Compiler et exécuter sous Windows x64

Prérequis de développement : Windows 10/11 x64 avec ses fonctions multimédias,
Visual Studio 2022 C++ et Windows SDK, CMake ≥3.22, Python 3 pour les tests.
Les tests décodent avec FFmpeg/FFprobe **uniquement s'ils sont déjà sur PATH**.
Aucun Qt, SDK VST, SDK ASIO ou dépôt MuseScore n'est nécessaire.

Dans PowerShell 7 Windows :

```powershell
.\scripts\Run-Probe.ps1 -BuildPath 'C:\dev\mf-aac-build-001' `
  -ResultsPath 'C:\dev\mf-aac-results-001'
```

Choisir des dossiers nouveaux/vides. Le générateur Visual Studio x64 évite
d'exiger un terminal MSVC déjà configuré ; `-Generator Ninja` est prévu pour
un terminal de développement x64. Avec `-RequireDecode`, l'absence de FFmpeg
ou d'un contrôle de signal décodé fait échouer le script.

Le script compile, lance deux tests de 1,25 s (44,1 et 48 kHz), puis rassemble
les journaux et `run.json`. Chaque cas dispose d'un dossier neuf ; relancer
CTest conserve les précédents résultats et utilise de nouvelles sorties.
Un MFT absent, une négociation refusée ou une erreur d'encodage échoue au test.
Ce n'est pas un test « ignoré » présenté comme réussi.

Commandes manuelles équivalentes :

```powershell
cmake -S . -B 'C:\dev\mf-aac-build-001' -G 'Visual Studio 17 2022' -A x64
cmake --build 'C:\dev\mf-aac-build-001' --config Release --parallel 2
ctest --test-dir 'C:\dev\mf-aac-build-001' -C Release --output-on-failure
```

Pour construire seulement l'utilitaire sans Python : ajouter
`-DMF_AAC_PROBE_TESTS=OFF`. Cela ne réalise aucun des tests Python/CTest.
Un fichier propre peut être demandé à l'utilitaire :

```powershell
.\build\Release\cadence-mf-aac-probe.exe --output 'C:\temp\sine.aac' `
  --metadata 'C:\temp\sine.native.json' --rate 48000 --seconds 1.25 --bitrate 128000
.\build\Release\cadence-mf-aac-probe.exe --output 'C:\temp\music.aac' `
  --rate 44100 --bitrate 160000 --pcm 'C:\temp\music.stereo-s16le.pcm'
```

Les chemins `build` sont à adapter au dossier réellement compilé. Pour un
fichier PCM personnel, les tests de fréquence 440/660 Hz ne s'appliquent pas :
le vérificateur de signal est destiné à la sinusoïde du test, pas à une musique.

## Résultats et interprétation

Un succès natif indique **structure ADTS contrôlée**, pas décodage ou écoute.
Les tests Python produisent des statuts distincts :

- `passed_with_decode` : structure et signal décodé vérifiés. Les deux voies
  doivent contenir les fréquences attendues, avec une durée/niveau cohérent,
  sans valeurs non finies ni crête au-delà de la marge fixée pour ce signal.
- `passed_structure_only` : le MFT a réussi et la structure est conforme,
  mais le décodeur facultatif manque ; le payload reste à décoder.
- `failed` : aucune validation annoncée ; consulter les journaux et erreurs.

`run.json`, les `case.json`, `native.json`, `validation.json`, AAC et journaux
sont les éléments à conserver pour le futur essai Windows. Les fichiers AAC
et le binaire testés sont identifiés par SHA-256 dans les rapports Python.
La comparaison temporelle ne supprime pas les trames de délai d'encodage et
ne valide pas encore une boucle musicale ou le muxage MP4.

## Windows N/KN et Server

Le programme charge `mfplat.dll` depuis System32 à l'exécution, sans lien
statique vers cette DLL. Son absence peut ainsi produire un diagnostic de
l'utilitaire. `MFStartup` ou l'activation de `CLSID_AACMFTEncoder` peuvent
également échouer si les fonctions multimédias ne sont pas présentes/utilisables.
Le HRESULT est conservé dans le message. Les éditions N/KN et certaines
configurations Server exigent des composants Windows facultatifs ; ce
prototype ne les installe pas et n'affirme pas savoir les réparer.

La version/architecture du système sont enregistrées par le script. Un succès
sur un runner ne qualifie pas toutes les éditions Windows. Les essais avec MF
absent, codec non enregistré, destination non inscriptible et interruption
restent à réaliser sur de vrais systèmes Windows.

## Réutilisation future dans Cadence

La classe de cet essai peut servir à préparer un backend d'`AbstractAudioEncoder`,
après validation. Il reste notamment à assurer le thread COM adéquat, la
conversion du flux du moteur vers PCM16, la gestion des fréquences proposées,
annulation/progression, messages français et découverte des capacités.
L'absence du backend doit laisser les autres exports et la lecture utilisables.

La vidéo avec son doit être testée avec le muxeur existant sur le **vrai AAC
produit**, avec mesure du décalage et de la durée ; aucune compatibilité MP4
n'est annoncée ici. Le profil AAC OFF préparé dans un autre worktree reste
intact. La future intégration ne devra pas transformer une demande AAC/MP4
avec son en un autre format ou une vidéo muette sans accord explicite.

Le [fragment CI](ci/windows-job.yml) est un modèle local pour un job court après
intégration autorisée des sources dans une branche de test. Aucun workflow
n'a été envoyé à GitHub et aucun binaire n'est publié par cet essai.

## Références techniques Microsoft

Les API ont été vérifiées sur les sources officielles ; le code du prototype
est une implémentation indépendante, pas une copie de leurs exemples.

- [AAC Encoder](https://learn.microsoft.com/en-us/windows/win32/medfound/aac-encoder) : formats d'entrée/sortie et payload ADTS.
- [ProcessInput](https://learn.microsoft.com/en-us/windows/win32/api/mftransform/nf-mftransform-imftransform-processinput) et [ProcessOutput](https://learn.microsoft.com/en-us/windows/win32/api/mftransform/nf-mftransform-imftransform-processoutput) : alimentation, récupération, samples et événements.
- [Basic MFT Processing Model](https://learn.microsoft.com/en-us/windows/win32/medfound/basic-mft-processing-model) : messages et drain.
- [Output stream info](https://learn.microsoft.com/en-us/windows/win32/api/mftransform/ns-mftransform-mft_output_stream_info) et [aligned buffer](https://learn.microsoft.com/en-us/windows/win32/api/mfapi/nf-mfapi-mfcreatealignedmemorybuffer) : allocation et alignement.
- [MFStartup](https://learn.microsoft.com/en-us/windows/win32/api/mfapi/nf-mfapi-mfstartup) et [CoInitializeEx](https://learn.microsoft.com/en-us/windows/win32/api/combaseapi/nf-combaseapi-coinitializeex) : durée de vie de MF et COM.

L'option ADTS directe est volontaire : si elle est refusée, le prototype échoue
sans fabriquer de faux en-têtes. Une voie brute + [ADTS media sink](https://learn.microsoft.com/en-us/windows/win32/api/mfidl/nf-mfidl-mfcreateadtsmediasink)
pourrait être évaluée séparément si un cas réel l'exige.
