# Vraie chaîne OMR locale — préparation Windows non exécutée

Le workflow dédié lit uniquement sa branche/son namespace. Aucun tag, release,
message externe ou changement du MSI public2007 n'est effectué. Le moteur et
l'application sont de vrais programmes Windows : aucun faux résultat OMR.

Sur un runnerWindows2022 jetable, le wrapper déjà éprouvé OwnProcessJob reste
byte-identique ; CadenceProfileScope et son contrat de source sont repris
sans modification. Le nouveau travail consiste à télécharger anonymement les
MSI figés de Cadence2007 et Audiveris5.11.0Console, vérifier tailles/SHA et
ProductVersion en READONLY0, produire des images administratives MSI dans
RUNNER_TEMP puis lancer leurs exécutables natifs. Cela ne qualifie pas une
installation normale Audiveris ni le futur dialogue Cadence intégré.

Le modèle de notes basic-classifier.zip doit être présent dans Audiveris.jar
et byte-identique au Gitblob2b7b9260e2c9b3ce939afb243bcd8fbd9fc00b62 de son tag.
Le modèle OCR anglais23.5Mo est téléchargé séparément et vérifié SHA-256,
puis fourni via TESSDATA_PREFIX. Aucune ressource réseau n'est supposée incluse
sans vérification. APPDATA et le cache JavaCPP du processus Audiveris pointent
sur le cas possédé ; le Cadenceprofile est préparé, pas un premier lancement.

Après ces téléchargements, des règles pare-feu sortantes bloquent les vrais
exécutables Cadence/Audiveris/java inclus. Les règles nommées uniquement pour
cette invocation sont vérifiées puis retirées ; le rapport en garde la portée.
Un document MusicXML originalCC0 de huit noires/deux mesures4/4 est rendu par
Cadence en PNG300dpi et PDF. Chaque vraie reconnaissance Audiveris produit un
MXL lu structurellement, comparé aux huit hauteurs/durées/mesures exactes, puis
importé en MSCZ avec Cadence, réouvert en PDF et réexporté en MusicXML, à nouveau
comparé. Toute différence musicale ou commande manquante garde FAIL et ses
sorties ; aucun faux PASS ou rattrapage par une partition connue n'est prévu.

Les notes ne prouvent ni tous les scans, ni les photos difficiles, ni manuscrit,
ni la polyphonie, ni l'OCR français. Aucune écoute/GUI ou Windows10/11 client
n'est déduite. Les originaux, copies et téléchargements sont rehashés ; le Job
doit être drainé/fermé sans descendant forcé et le profil nettoyé pour PASS.
Les JSON MusicXML exacts (base64+SHA bornés) sont imprimés dans le reçu final
pour revue indépendante malgré les limites du connecteur d'artefacts.

Tous les fichiers de ce dossier sont des outils développeur de qualification.
L'utilisateur final installe Cadence, puis Audiveris officiel s'il utilise OMR ;
Java est inclus dans ce dernier MSI. Aucun compilateur/SDK n'est demandé.
Ce dossier n'a été que parsé/contrôlé sous Linux ; la vraie chaîne n'a pas encore
été exécutée ici, elle doit être publiée/lancée par la racine après revue.
