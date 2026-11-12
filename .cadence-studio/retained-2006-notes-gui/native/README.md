# Préparation du client UIA annotations

Dérivé du client collections réellement exécuté avec succès2006. `OwnedKeyboard.h` et `OwnedFileDialog.h` sont byte-identiques ; `CollectionFlow.inc` est la version TextPattern prioritaire ayant réussi. `UiaProbe.cpp` conserve le code commun de découverte et ses plafonds, ajoute seulement le préfixe connu du panneau Notes et sélectionne `NotesFlow.inc`. Les anciens parcours collections sont des fonctions non appelées, aucun favori/collection ne sera activé.

CLI : `UiaProbe.exe --pid <owned> --output <new-directory> --fixture-root <controlled-directory> --add-fixture <controlled-piano.mscx> --expected-title "Piano : voix, accords et triolets" --note-text Cadence-QA-PrivateNote-2006`. Au redémarrage, seul `--add-fixture` devient `--verify-fixture`. Aucun autre texte n’est accepté.

Un seul texte ASCII borné, après preuve UIA du champ vide ; TextPattern prioritaire et ValuePattern seulement en secours. Les boutons Enregistrer et Notes sont exacts. La case de compatibilité n’est déclenchée que si son nom/PID/rôle CheckBox/focus sont exacts. Le bouton d’activation doit ensuite être enabled, propriété liée à la case cochée. La note sauvegardée est corroborée par le bouton Supprimer devenu enabled (observation/focus seulement, jamais invocation) et le texte réel. Au restart, seul le choix exact de la note QA est accepté. La note reste affichée pour la capture et la fermeture propre par le lanceur ; aucun fichier musical n’est ouvert.

Plafonds hérités :140s/phase,100 gestes,35F6,25Tab,15Right,20Down,10Left,20Return ; source-known Down/Right/Escape uniquement depuis un focus relu. Pas de lecture/écriture du JSON produit par le client. Pas de parcours de dialogue musical, Save/Cancel, compte ou achat.

Cette préparation n’a pas été compilée avec le SDK Windows ni exécutée contre l’application. Le premier essai réel doit établir les nouveaux contrôles CheckBox/TextInputArea/sélection, et tout écart bloque sans relance automatique.
