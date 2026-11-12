# Client natif de qualification GUI collections

Client de test Windows ; aucune modification de l’application. `UiaProbe.cpp` et `OwnedKeyboard.h` sont dérivés du probe bibliothèque existant ; `OwnedFileDialog.h` reste identique octet pour octet. `CollectionFlow.inc` ajoute les opérations UI réelles. Compiler le client avec le même MSVC/SDK que le probe précédent, par exemple :

```powershell
cl /std:c++17 /EHsc /utf-8 /W4 UiaProbe.cpp /link ole32.lib oleaut32.lib user32.lib uiautomationcore.lib
```

Arguments par paires : `--pid`, `--output` (dossier existant), `--fixture-root`, `--expected-title`, `--collection-name Cadence-QA-2005`, et exactement un des modes `--add-fixture <copie.mscz|mscx>` / `--verify-fixture <même-copie>`. Le nom contrôlé comporte au plus 64 caractères ASCII, lettres/chiffres/tiret, préfixe `Cadence-QA-`. Le wrapper crée seul les copies CC0, vérifie l’identité de l’exécutable/profil et conserve les captures. Il doit laisser au moins 150 secondes au client (deadline interne : 140 secondes), puis fermer seulement son processus possédé.

Premier lancement : le client ajoute la vraie copie par le dialogue natif possédé, rétablit la navigation F6 après ce dialogue, observe puis active « Activer les collections » du catalogue v1 neuf, constate le filtre, ajoute le favori, crée la collection par le champ réel, observe sa sélection automatique, revient à Toutes les partitions, classe le morceau avec le menu réel, puis refiltre. Il exige le bouton Ouvrir attendu et le contrôle « Retirer de cette collection <titre> » sans activer ce dernier. Il ne réécrit aucun JSON du catalogue.

Relance : le client observe « Retirer des favoris <titre> », sélectionne à nouveau la collection enregistrée dans le filtre, exige le même morceau et le contrôle de retrait de cette collection, puis ouvre le morceau. Il attend le vrai titre de fenêtre éditeur correspondant au nom de la copie ou au titre connu. Cette preuve de titre n’est pas une validation du contenu musical : la capture de l’éditeur reste à inspecter.

Chaque touche suit un contrôle du libellé, du rôle, de la visibilité, de l’activation et du PID UIA. Les contrôles exposés sont recherchés par libellé exact unique puis SetFocus ; sinon les transitions de navigation connues sont observées individuellement. Les IDs `navigation.name` QML ne sont pas assimilés aux AutomationId. Le menu n’accepte que les deux choix attendus du catalogue neuf : Toutes les partitions et le nom QA. Toute divergence est bloquante. Après une reconstruction du modèle, le client redécouvre les contrôles. Aucun clic par coordonnées ni raccourci Quit global n’est utilisé.

Le champ « Nom de collection » doit être vide et lisible par ValuePattern ou TextPattern. Le client essaie ValuePattern ; si le texte reste exactement vide, il peut saisir le seul nom ASCII contrôlé avec KEYEVENTF_UNICODE. Il relit ensuite le texte complet. L’absence de lecture ou un texte inattendu bloque. Avant SendInput, le handle du processus actif et son PID, le premier plan, le focus Win32 et l’absence de modificateur sont revérifiés. L’insertion n’est pas atomiquement adressée à un PID ; un changement détecté ou une insertion partielle arrête la séquence, sans compensation aveugle.

Les cinq champs JSON sont :

- `collections_enabled_observed` : vrai filtre ComboBox observé (sur relance : filtre de la collection).
- `collection_created_control_observed` : nouveau nom observé dans le filtre après l’action Créer ; première phase seulement.
- `collection_member_control_observed` : morceau visible dans la collection ET contrôle de retrait de membership observé.
- `collection_filter_observed` : collection filtrée et bouton Ouvrir du morceau observés.
- `collection_restored_control_observed` : membership effectivement observé après relance.

Le code de sortie 0 exige **tous** les contrôles de la phase : ajout/favori/activation/création/membership/filtre, ou favori restauré/membership restauré/filtre/ouverture/titre éditeur. Un catalogue valide seul ne peut pas satisfaire ces contrôles. `uia-report.json` conserve les actions, focus, HRESULT, arbres bornés et limites. Le wrapper peut corroborer ensuite le catalogue réel fermé, sans substituer cela aux opérations GUI.

Vérifications de préparation Linux : copie inchangée du sélecteur de fichier ; contrôle des inclusions/fichiers/contrats de rapport et garde des arguments. **Aucun SDK Windows disponible localement : ce nouveau client n’est pas encore compilé ni exécuté sous Windows.** Le premier run peut révéler un rôle UIA non exposé ou une limitation du menu currentIndex=-1 ; il doit alors rester bloqué. Aucune installation, édition de notes, écoute, évaluation MIDI/microphone ni validation sonore n’est revendiquée.
