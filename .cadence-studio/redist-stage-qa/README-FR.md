# Vérification ICU sur une copie du stage2005

Préparation source seulement, à exécuter sur un runner Windows x64 GitHub jetable.
Aucune omission n’est qualifiée avant les résultats réels. L’application et les
DLL graphiques actuelles restent intactes ; aucun moteur ni banque n’est changé.

Le job restaure l’artefact2005 exact avec les helpers de restauration déjà repris,
contrôle le QtCore et le forwarder locaux mesurés dans le vrai relevé PE, puis lit
seulement `icuuc.dll` et `icu.dll` du vrai `Environment.SystemDirectory`. Les vingt
imports nommés de QtCore doivent aboutir à des exports x64 exécutables, y compris
les chaînes de forwarders. Les fichiers système ne sont ni chargés par le lecteur
ni copiés/modifiés. Leurs hardlinks Windows légitimes sont acceptés en lecture.

Une copie complète du stage est vérifiée avant changement. Le seul fichier omis
dans cette copie est `bin/icuuc.dll`, après cette preuve positive. Tous les autres
fichiers, notamment DXC/DXIL/D3DCompiler47 et le secours Mesa, gardent leurs SHA.

Le vrai exécutable de la copie est lancé avec `--long-version`. Les modules de ce
seul PID sont observés : ICUuc et ICU doivent venir de System32, QtCore de la copie.
Le programme existant de corpus est réutilisé à l’octet près : ses57 contrôles
d’import, sauvegarde/réouverture, exports et parties séparées sont exécutés sur la
référence puis sur la copie. Les35 sorties déterministes doivent avoir les mêmes
empreintes. Le contrôle WAV existant mesure silence, nonfinis et rails ; aucune
écoute, édition GUI ou vérification d’un autre Windows n’est revendiquée.

Le profil neuf réutilise le helper KnownFolders déjà qualifié ; ses trois racines
Cadence doivent être absentes et marquées. Cette exception de profil à RUNNER_TEMP
est identique au test antérieur. Le seed audio ASIO du helper est d’abord vérifié,
puis seul le fichier INI possédé est ajusté en WASAPI/périphérique par défaut,
comme dans la qualification native SF2 déjà exécutée. Aucun endpoint QA, aucune
clé ASIO/COM et aucun périphérique ne sont installés. Le contrôle vise ICU.

Le contrôleur rejoint son Windows Job avant les enfants ; tous les descendants
sont drainés avant la suppression des seules racines de profil possédées. La
fermeture du Job est la dernière opération native, suivie seulement du rapport et
de la sortie. Toute terminaison forcée ou erreur de cleanup interdit le PASS.

Les fichiers de référence et de la copie sont rehachés après les essais ; les deux
ICU système doivent garder leurs SHA. Aucune archive ni aucun installateur de
l’application n’est produit ou publié par ce job. Un résultat positif établira
la qualification sur le runner décrit, à reporter honnêtement pour Windows10/11.

Sources des outils sous GPLv3 ; cinq compositions originales inchangées sousCC0.
Le fixture de stress volumineux appartient à une qualification distincte ; il est
exclu du petit manifeste de corpus ici, sans altérer les cinq compositions testées.
