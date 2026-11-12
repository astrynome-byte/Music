# Qualification d'une vraie collection sonore optionnelle

Préparation, pas encore exécutée sous Windows. Le pilote ne reconstruit pas
l'application : il conserve le stage2002 réel et compile uniquement le nouveau
composant QtCore/Network de gestion des collections avec ses propres tests.
Il n'installe aucun plugin, service, abonnement ou son commercial.

Le SoundFont GeneralUser GS est téléchargé depuis son dépôt officiel à un commit
fixé, puis sa taille32319396 et son SHA2569575028c… sont vérifiés. La licence
v2.0 autorise logiciels, redistribution et production musicale ; elle expose
une incertitude historique sur l'origine de certains anciens échantillons.
C'est une option distincte, pas un remplacement silencieux de MS Basic. Le
catalogue de développement garde aussi l'écart2.0.3/BETA des métadonnées.

Le premier contrôle compile les véritables fichiers de production proposés et
exige14 scénarios : import/relecture/retrait, intégrité/refus des collisions et
données modifiées, verrou réel, annulation/destruction/réentrance, et un vrai
transfert HTTPS par QNetworkAccessManager avec vérification puis commit. Les13
scénarios sans réseau passent déjà sous Linux ; le14e est demandé explicitement
par le pilote. Le réseau n'est jamais utilisé silencieusement par le test local.

Le second contrôle exige un profil Cadence neuf et un dossier Documents/Cadence
absent, résolu par l'API Windows. Il y copie uniquement sa propre banque, avec un
nom de ressource versionné `Cadence-GeneralUser-GS-2.0.3` pour éviter les collisions
avec une banque installée par l'utilisateur. Cinq partitions CC0 sont converties
en copies natives, rendues avec MS Basic puis la vraie alternative, et leurs
identités de ressources sont sauvegardées dans de nouveaux MSCZ. Il exige un
chargement positif de la banque au synthétiseur, aucune résolution de secours
pour la ressource demandée, tous les échantillons WAV finis/non silencieux/sans
saturation et tous les fichiers d'entrée inchangés. Les niveaux et différences
de timbre numériques sont rapportés sans déclarer une équivalence esthétique.

Ce contrôle n'exécute pas l'interface QML du nouveau gestionnaire, ne valide pas
l'écoute humaine ni la sauvegarde du même projet après lecture. La CLI ouvre un
nouveau projet pour chaque sortie. L'intégration et le parcours UI seront testés
avec une future compilation complète contenant le patch, sans attribuer leur
réussite au binaire2002 déjà conservé.

Aucune publication de cadeau ; artifacts Actions temporaires14jours, compte
GitHub possible. Ne pas changer le main Android. Publier uniquement le namespace
free-sound-qa et son workflow sur la branche Windows autorisée, avec le marqueur
[ cadence-packaging-only ] sans espaces dans le commit.
