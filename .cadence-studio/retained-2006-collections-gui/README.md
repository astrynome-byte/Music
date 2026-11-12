# Un parcours réel de collections sur le stage 2006 authentifié

Cette préparation reprend le harnais collections déjà compilé sous Windows et
crée un namespace indépendant. Aucun ancien target 2005 ou code produit n'est
modifié. Aucun workflow n'est lancé par cette préparation.

Le reçu DATAONLY n2 (run 43256055209 / job 131314481337) a authentifié le stage de
production 43233124321, artefact 13955301913. EXE 80068096 octets, SHA
`c29d7c8c76b213b79d7390acd65cbabc6fb940f06e3e7f86c0ce60be7e9b9520` ;
ZIP interne 148007535 octets, SHA
`b6b6bb9160250282879543b44e1ca8217494285e86c47fb2003f8b24dd93954c`.
Source originale `ac9a24933f78f22ea630570910848201baad3d3b`, arbre
`a94a09974229c47e7b90b593a7649c29d6a6d190`, commit CI
`536d13cf1caba07197deccefc9f880d8a77902e0`.

Les octets du source.json gelé ont été comparés au fichier du lecteur : 635 octets,
SHA `0d6c5944374cfa2b58ee8f81a3912b36585ed263ed79ffb3ff1968f2bd07ca1b`.
Le patch compressé porte le SHA
`cba5d10112b8cd7ce470577e07cc70fb8d1cd849ec412b652c0a6b71bf4e3ce7`.
Le target est lié à ces valeurs et au reçu authentifié copié dans
data-authentication.json (JSON du marqueur analysé/sérialisé, sans prétendre
préserver les octets du fichier de reçu initial). Aucun stage-manifest original
n'est synthétisé : le job lira celui de l'artefact avec ses compagnons et SHA.
Le lecteur n'a lancé aucune application ; il ne constitue pas la preuve GUI.

Le seul parcours prévu ajoute une nouvelle copie du piano natif MSCX CC0,
active les collections, marque le morceau favori, crée Cadence-QA-2006, classe
ce morceau, sélectionne la collection puis ferme proprement. Une seconde
instance du même EXE et du même profil jetable vérifie favori et appartenance,
sélectionne la collection et ouvre cette seule copie dans l'éditeur.

Le client natif, ses deux headers et CollectionFlow sont repris sans modification
du harnais précédent, dont la correction BSTR a déjà compilé. Les noms et
coordonnées de contrôle ont été comparés à la source ac9 : inchangés pour ce
parcours. La nouvelle commande Notes se trouve hors séquence. Un profil neuf
reste en schéma 1 ; Activer les collections monte à 2. Le schéma 3 nécessite une
activation de notes distincte qui n'est jamais demandée ici.

Ce fichier est une partition native, pas un exercice MusicXML importé. Aucun
client CloseExercise, Tab de dialogue ou traitement DontSave problématique 2005
n'est inclus. Aucun parcours de notes, effets, cours ou son n'est ajouté. Le
premier lancement est prérempli comme terminé dans un nouveau profil Cadence
du runner jetable ; ce n'est pas un essai de l'introduction.

Les véritables contrôles UIA, PID, rôles, libellés et focus sont requis avant les
gestes. Le catalogue n'est ni injecté ni lu pendant que l'application tourne.
Sa lecture auxiliaire intervient après sortie effectivement observée ; le succès
exige les observations UIA, source/copie inchangées, métadonnées schéma 2 exacte et
sorties propres 0 des deux instances. Un catalogue correct seul ne valide pas GUI.
Un échec AccessDenied ou une fermeture forcée reste un échec conservé avec logs.

Le job compile seulement le client SDK, restaure le stage retenu et garde les
preuves 14 jours. Le présent lot a seulement subi contrôles locaux de syntaxe,
identité et garde de target sur données ; aucune GUI Windows n'a encore été
exécutée pour 2006. La consultation de partitions, l'édition musicale, l'écoute,
les notes et les effets restent hors validation de ce lot.

L'artefact stage expire le 26 novembre 2026 à 14:57:16 UTC ; ce n'est pas le lien public
du cadeau. Le pipeline conserve des résultats bornés dans son journal et les
originaux dans l'artefact, avec projection explicite des longues frames UIA.
