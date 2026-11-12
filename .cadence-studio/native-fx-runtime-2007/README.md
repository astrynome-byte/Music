# Qualification CLI privée des effets natifs dans le vrai binaire 2007

Préparation seulement. `target.json` reste `ready=false` jusqu’à revue racine.
Aucun workflow Windows, build de l’application, MSI, installation, publication
ou téléchargement du stage n’a été lancé par cette préparation.

Le manque de preuve est réel : `docs/evidence/native-fx-windows-msvc` qualifie
le DSP et le codec de paramètres MSVC autonomes ; il exclut explicitement le
mixeur Qt complet, l’application et les projets MSCZ. Les essais locaux du
harnais ne remplacent pas une exécution native. L’enquête sourcée complète
est conservée dans `source-contract-investigation.json`.

Le workflow proposé réutilise exactement le producteur réussi 43266732201,
artefact 13970570430, source 5058d29dad67e6131ee46ee617258ccfed8ba4b0,
EXE SHA256 dcfbf9155c6c972c37966a4b2b0dcd212133c8e31fb397c644dda800ac7122be.
Métadonnées API GET, manifeste original de 3776 octets SHA ba985694…41ad05,
rapport de build, ledger, ZIP intérieur et EXE sont vérifiés avant tout essai.
Le digest du ZIP extérieur reste une métadonnée GitHub, sans prétendre avoir
recalculé ce ZIP ici. Aucun remplacement d’artefact ou d’exécutable n’est permis.

Une fixture MusicXML originale CC0, quatre mesures de do3 pour violoncelle,
utilise MS Basic déjà livré dans le stage exact. Son programme MusicXML 43
doit réellement être importé en GM42. Le contenu CC0 et son origine sont
documentés dans `fixtures/LICENSE.txt`. Les scripts restent GPL-3.0-only.
Ni VST, faux plugin, service, achat ni nouvelle banque ne sont utilisés.

Les identifiants et paramètres viennent des véritables sources C++, dont les
SHA2007/2008 sont relevés dans l’enquête. Le JSON `audiosettings.json` utilise
`type=muse_plugin`, `vendor=Cadence`, `fxChain={"0":…}`, `active`, `chainOrder=0`
et chaque valeur `unitConfiguration` encodée en Base64 selon
`ProjectAudioSettings::unitConfigFromJson`/`unitConfigToJson`. Deux envois
auxiliaires explicites `active=false, signalAmount=0.0` empêchent le défaut de
réverbération ajouté si la liste des sends était vide. Ils restent vérifiés
après sauvegarde. Volume maître constant −24dB, piste0dB, balance0.

Le plan contient 11 cas et 34 commandes réelles : une importation ; référence ;
puis pour chaque emplacement piste/maître EQ contourné, EQ actif plat avec
gain de sortie −6dB, compresseur contourné, compresseur actif ratio1 et makeup
+6dB, compresseur actif seuil−60dB/ratio4/knee0/attaque0,1ms/release10ms/makeup0.
Chaque cas est rendu, sauvegardé par l’application dans un nouveau MSCZ,
rouvert puis rendu à nouveau. La chaîne FX intégrale, identité, configuration,
ordre, activation et gains/sends sont comparés au JSON demandé après save.
Le chemin source est vérifié : `ConverterController::convertFile` charge le
projet et appelle réellement `notationProject->save(out)` pour le suffixe MSCZ ;
`NotationProject` lit/écrit `ProjectAudioSettings`. Le harnais ne fabrique pas
la copie sauvegardée par l’application. Les extraits et SHA exacts de ces deux
fichiers supplémentaires sont joints à l’enquête source.

Les contrôles audio exigent float32 stéréo fini, non muet, pic inférieur0,95 et
même forme temporelle. Le rapport enregistre les SHA PCM/WAV/projets.
Le gain connu exige une erreur relative RMS≤0,3% et résidu normalisé≤0,01% ;
une simple conservation de métadonnées ou une sortie non muette ne suffit pas.
La réduction réelle exige RMS<90% de la référence et aucun accroissement de
valeur absolue à un échantillon (tolérance1e-5 du pic). Les deux analyses sont
faites sur rendus frais et réouverts ; le rendu après save est lui-même comparé
au rendu avant save. Les seuils peuvent faire échouer le futur essai ; aucun
PASS Windows n’est anticipé ni affaibli sur une sortie supposée.

Le helper KnownFolder et le module Job sont copiés sans modification, SHA
respectifs 60b6bb…c27c et e24bb6…4b77. Ils gardent le seed ASIO et la dépendance
initiale Cadence QA Clock. Le script vérifie ce seed exact puis modifie seulement
son INI possédé pour WASAPI et export hors ligne, comme la recette SF2 éprouvée.
Tous les enfants héritent du Job ; son drainage est prouvé avant nettoyage des
trois racines initialement absentes. Un enfant tué de force interdit le PASS.
Les profils existants sont refusés. L’environnement applicatif retire Qt/QML
SDK et variables de secrets. Stage, banque, fixture et projets source restent
hachés avant/après ; aucun MSI ni installation système n’est touché.

Les 13 fichiers production inspectés sont identiques entre 2007 et candidate
49272b75a4107c97130b8a46727af6a8c95d1c9a. Cela ne qualifie pas le binaire 2008.
La preuve future sera CLI sur 2007 ; ni matériel audio, écoute humaine, GUI,
édition en direct, qualité subjective, toutes fréquences de l’EQ ou séparation
acoustique de plusieurs pistes n’en seront déduits. Une seule piste peut
confirmer stockage et chemins piste/maître lus dans le code, pas distinguer
acoustiquement une inversion de routage entre ces deux bus.

Le workflow n’a que permissions `contents:read`/`actions:read`. Le gate Linux
valide les octets puis ignore le job Windows si `ready=false`. Le seul push
déclencheur est le `target.json` de ce namespace, sur la branche CI identifiée.
La recette source et le manifeste sont immuables dans cette proposition ; une
activation revue ne doit changer que `ready` vers `true`. Les diagnostics,
projets et WAV restent artefacts de workflow 14jours, sans release publique.
