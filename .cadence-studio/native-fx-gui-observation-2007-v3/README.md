# Diagnostic V3 du premier échec UIA — recette inactive

Aucun `target.json` n’est livré. Le modèle séparé reste `ready=false`, tentative3.
La racine relit les octets, publie les sources inactives puis ajoute une cible
distincte si elle décide de lancer l’essai. Aucun lancement Windows, résultat de
mixeur, écoute ou changement du produit n’est établi par cette préparation.

## Sources et exécution prévues

Le stage original2007 reste fixé au run43266732201/artefact13970570430, source
5058d29dad67e6131ee46ee617258ccfed8ba4b0 et EXE SHA256
dcfbf9155c6c972c37966a4b2b0dcd212133c8e31fb397c644dda800ac7122be.
L’endpoint ASIO de test silencieux reste celui du run43212261044/artefact13941567509,
DLL08f570d7df0dfb5f2cafe899c6b6679e48d4e1fa132656e58f4b0113a8709fd2.
Les producteurs sont authentifiés et les artefacts originaux vérifiés avant tout
lancement. Aucun driver noyau, service, programme utilisateur nouveau ou achat.

Les helpers de registre HKLM64, profil KnownFolder, Job, restauration, conversion
CLI et contrôle du clock sont repris octet pour octet de V2. Le profil QA neuf
désactive explicitement la promotion MuseHub et le revérifie après conversion ;
ce réglage ne corrige pas l’application2007. Le vrai CLI crée une copie MSCZ de
notre MusicXML CC0, puis la GUI ouvre uniquement cette copie. Source/copie et EXE
sont contrôlés ; le profil et le registre restent possédés, avec drainage du Job
avant nettoyage. Aucun geste d’édition, sauvegarde, crash ou récupération.

## Instrumentation seule du probe

Deux fichiers changent : `native/ObserveMixer.cpp` et le nouveau
`native/ObservationFailure.h`. Le graphe RuntimeId reste identique. Tout premier
échec de propriété, de navigation du walker ou d’une garde de complétude est
enregistré avec phase, API, HRESULT signé et hexadécimal, origine réelle/synthétique
et RuntimeId déjà vérifié par PID. Aucun texte de contrôle étranger n’est lu.
Les causes sont distinctes par snapshot et la première cause globale survit aux
dumps suivants. Les JSON et stderr portent `first_observation_failure` ; le
wrapper V2 inchangé les imprime avant son `throw`, même si le probe échoue.

La projection incomplète bloque toujours F10. PID, focus, refus de texte/menu/modale,
délai75s,1200identités/3600arêtes et un seul F10 restent inchangés. Aucun retry,
HRESULT ignoré, commande interne ou tolérance nouvelle n’est ajouté. La commande
SDK compile réellement le client et écrit ses empreintes de sources sous Windows.
Le helper portable passe15 assertions et six sorties JSON sous GCC ; cela ne
qualifie ni MSVC ni un provider UIA réel. Une réussite de collecte demande encore
inspection des captures ; elle ne qualifie pas les paramètres FX ou NVDA.

## Historique conservé

- Tentative1, run43335448410/job131590425967 : promotion modale et projection
  cyclique,0geste ; application possédée forcée une fois, sortie−1, pas de clock
  final ; profil/registre nettoyés. Échec GUI, pas de résultat Mixer.
- Tentative2, run43405873102/job131820024692 : copie ouverte, fermeture0,
  callbacks clock valides,0arrêt forcé et nettoyage ; pourtant probe3,0geste,
  projection incomplète. Les12nœuds/12identités ne dépassent aucune borne ; la
  dernière entrée est «Publier». Les HRESULT exacts manquent dans V2 : la cause
  est inconnue. V3 cherche cette cause, sans traiter une limite supposée comme
  un fait et sans requalifier cet échec.

V1 et V2 restent immuables. Le champ `previous_failed_runs` des métadonnées fixe
ces deux origines. Aucun de ces essais n’est une validation du nouveau produit
en cours de compilation, de son installation ou d’une écoute physique.

## Artefact de diagnostic limité

`retention-policy.json` et le workflow énumèrent seulement rapports, journaux,
copie MusicXML/MSCZ, dumps JSON, deux PNG, rapports clock, provenance du DLL et
empreintes de sources. L’arborescence `stage`, les archives d’entrée, DLL/EXE/OBJ
et les dossiers d’installation ne sont pas téléversés. Les fichiers de preuve
gardent leurs octets originaux ; aucun JSON ou PNG n’est tronqué dans l’artefact.
Les journaux affichés restent bornés par les wrappers existants.

Lire d’abord le JSON natif ou `first_failure=` dans stderr après le prochain
essai. Un code transitoire pourra ensuite justifier un retry ciblé et borné, en
gardant l’échec initial et une preuve fraîche avant toute touche ; aucun n’est
proposé avant l’observation réelle. Le cœur de l’application et les fichiers
musicaux d’origine restent inchangés.
