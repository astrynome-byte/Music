# Deux pages natives du stage 2005 — préparation de qualification GUI

Ce lot prépare un seul job Windows, sans reconstruire l'application. Le stage
réel 2005 reste celui du run 43207550870, artefact 13943781621, EXE
`d957ffc99497cb01b1f00f82ba1d6e89ef84547708506c6c51423675805e140a`.
Le lecteur 43216765461 a rehashé les 289fichiers originaux, le ZIP et l'EXE ;
`target.json` contient uniquement ces identités réelles. Le test ne remplace
pas ce stage par une source 2006 ou un ancien binaire. L'artefact source expire
le 26 novembre 2026 et n'est pas le lien public du cadeau.

Aucun SDK/MSVC, application, GUI, COM, pare-feu ou réseau Windows n'a été exécuté
par cette préparation Linux. Le nouveau client natif doit encore compiler puis
exercer les pages de la vraie application ; une vérification de syntaxe ou de
métadonnées ne constitue pas ce résultat.

Le job restaure tous les compagnons avec leurs SHA et compile seulement le
client UI Automation, après contrôle des octets natifs UTF8/LF. Le dossier
porte `* -text` pour préserver ces octets au checkout Windows. Le wrapper refuse
un autre processus de partition, un profil Cadence préexistant et un dossier
Exercices préexistant ; il ne modifie ni paramètres ni fichiers MuseScore officiel.
Il marque seulement l'introduction déjà terminée dans le nouveau profil Cadence
jetable. Ce n'est pas un essai du premier lancement ni un profil Windows isolé.

Le parcours prévu privilégie deux pages indépendantes de la bibliothèque dont
l'activation des collections échoue dans 2005 :

1. Collections sonores : observer l'offre facultative GeneralUser GS, son bouton
   `Télécharger 30.8 Mio · GeneralUser GS` sans l'activer, puis la licence 2.0
   dans le vrai champ lisible. Le contenu observé doit identifier GeneralUser
   GS 2.0.3 et la section de licence du travail complet. Aucun achat, compte,
   téléchargement, import ou activation de banque n'est demandé.
2. Apprendre : observer l'onglet Parcours hors ligne et les huit boutons distincts
   des exercices originaux, puis activer seulement `Ouvrir l’exercice : Garder la
   pulsation`, en dernier. Exiger une caption de fenêtre principale Qt possédée,
   changée après l'action et identifiant pulsation ; un texte de carte ne prouve
   jamais l'ouverture dans l'éditeur.

Le client limite la phase sons à 45 secondes et l'ensemble à 140 secondes. Un état
sons bloqué n'empêche pas l'essai du cours lorsque le contexte de fenêtres reste
valide. Chaque geste contrôle PID, rôle, libellé, activation et focus ; aucune
coordonnée ou injection de JSON produit n'est utilisée. Les transitions source
et leurs limites sont décrites dans native/README.md. Le coach reste explicitement
non testé ; aucune écoute ni édition de notes n'est déduite de ce parcours.

Le seul EXE est placé sous une nouvelle règle sortante Block/Any Windows Defender
Firewall. Les profils et services doivent déjà être actifs ; ils ne sont jamais
modifiés. Les quatre fonctions de vérification sont reprises sans changement du
helper offline-qa déjà éprouvé. Le wrapper enregistre l'enforcement actif avant
et après le parcours, retire uniquement son UUID/description, puis vérifie son
absence. Le runner et le transport GitHub restent en ligne ; aucune déconnexion
physique ni couverture d'un programme enfant n'est prétendue.

L'import MusicXML est un projet à enregistrer. Le wrapper prend donc sa capture
éditeur avant un second mode du même client, `--close-exercise true` : vérifier
la caption de la seule copie pulsation, demander sa fermeture, ne sélectionner
que le vrai DontSave possédé si un dialogue apparaît, puis exiger la vraie
sortie 0 du processus. Aucun bouton Save n'est autorisé. Une fermeture non
prouvée, un timeout ou un kill restent bloquants et ne permettent pas de lire
le contenu des exercices comme corroboration réussie.
La chaîne source utilise une vraie fenêtre QQuickView transiente et
ApplicationModal ; sa parenté GW_OWNER et l'état désactivé de la principale
doivent encore être observés sous Windows. Une autre modalité reste bloquante.

Après la sortie 0 confirmée seulement, la corroboration exige un unique nouveau
dossier `Documents/CadenceStudio4/Exercices/pulsation-UUID`, contenant exactement
`pulsation.musicxml` et `LICENSE-CC0.txt`. Les 5101/595 octets et leurs SHA doivent
être identiques aux deux ressources CC0 du commit 961c80b2 ; la copie du score
doit être inscriptible. Le wrapper ne crée jamais ce dossier à la place de
l'application et n'injecte aucun catalogue. Les fonctions de données refusent
les liens symboliques/reparse, identités divergentes, faux booléens, comptes de leçons incomplets et
absence de fermeture. Les tests locaux utilisent des copies sous Temp et des
claims UI synthétiques, jamais une prétendue preuve Windows.

Les preuves futures comprennent rapports natifs/UIA, caption avant/après,
fermeture contrôlée, captures de la fenêtre possédée, logs, identité de la copie,
règle effective et suppression vérifiée. Les JSON imprimés sont bornés ; les
frames/actions peuvent être explicitement projetées, les originaux restent dans
l'artefact. Le succès exige toutes les preuves de pages, copie et fermeture ;
les résultats partiels restent lisibles même lorsque le job échoue. Un succès
ne validerait ni la lecture musicale, ni tous les cours, ni l'écoute, ni le
catalogue commercial MuseScore.com ou les instruments payants.
