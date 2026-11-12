# Collections GUI — prochaine qualification du stage2005 retenu

Le vrai stage2005 est maintenant produit par le run43207550870 et retenu dans
l'artefact13943781621. Le lecteur indépendant43216765461 a recalculé les SHA des
289fichiers originaux, du ZIP et des79737344octets de l'EXE sans l'exécuter.
`target.json` fixe ces identités réellement mesurées ; `target.json.template`
reste volontairement incomplet. Le helper refuse le template, un ancien2002,
une identité source différente ou un artefact expiré. Le client de collections
et son parcours Windows restent à compiler et exécuter. Publier le workflow
et ce namespace après revue de cette cible réelle.
Le code applicatif et les sources gelées ne sont pas modifiés par ce pilote.

La future cible fixe le run et l'artefact GitHub, l'expiration et son digest
explicitement identifié comme métadonnée GitHub, le numéro2005/cinquième-run5,
l'attempt, les deux commits source original/CI, l'arbre et les SHA de source.json,
du patch, du ZIP de stage et de son EXE. Restore vérifie ces références, tous les
fichiers et sources compagnons de l'artefact avec leur inventaire SHA, puis
réutilise l'extracteur ZIP borné des probes retenus. Il ne charge aucun programme.
Les sources compagnons restent hors du runtime extrait. Aucun ancien EXE n'est
substitué à un stage absent. Le lien artefact GitHub nécessite l'accès GitHub,
expire et n'est pas le téléchargement cadeau public de l'application.

Le workflow compile uniquement le petit client Windows UI Automation, avec le
SDK Microsoft. Il utilise le stage retenu sans Qt développeur et sans recompiler
Cadence. Le wrapper exige le vrai SHA de l'EXE avant chaque démarrage, refuse
les autres processus de partitions et un profil Cadence déjà présent, puis crée
uniquement ses réglages Cadence de test sur un runner Windows jetable. L'intro
est marquée déjà terminée : cette précondition ne teste pas le premier lancement.
Le PATH enfant contient uniquement le runtime et System32, sans kit de compilation.

Le parcours réel prévu est :

1. Observer la bibliothèque et son bouton Ajouter, choisir la seule copie de la
   composition CC0 piano dans la boîte Windows possédée par le PID testé.
2. Observer puis activer « Activer les collections », observer le filtre,
   observer la vraie ligne Ouvrir, ajouter le favori et observer « Retirer des
   favoris » pour le titre exact.
3. Saisir le nom ASCII contrôlé `Cadence-QA-2005` dans le champ Nom de collection,
   vérifier la lecture du texte, activer Créer et observer le filtre sur cette
   nouvelle collection. Revenir à Toutes les partitions car la création sélectionne
   initialement la collection vide.
4. Classer la copie par le vrai menu, choisir le nom exact, filtrer sur cette
   collection, observer à nouveau Ouvrir et « Retirer de cette collection » pour
   le titre exact, sans activer la suppression.
5. Fermer proprement le premier PID avec code0, lire le catalogue schema2 comme corroboration et
   vérifier les SHA inchangés du fichier source CC0 et de sa copie musicale.
6. Relancer le même EXE et profil, observer le favori restauré, sélectionner à
   nouveau la collection par UI car le filtre n'est pas un réglage persistant,
   observer le membre, ouvrir la copie et observer son titre dans l'éditeur.
   Fermer proprement le deuxième PID avec code0 et vérifier les données inchangées.

Les contrôles sont identifiés par PID, rôle et nom accessible exact ; les
`navigation.name` internes ne sont pas supposés être des AutomationId UIA.
Chaque transition source connue vérifie le focus avant et après la touche.
Les motifs UIA sont privilégiés lorsqu'ils existent ; la saisie ASCII Unicode
est bornée et autorisée uniquement dans le champ exact lu vide. Un bridge UIA
qui ne permet pas cette lecture produit un état blocked, jamais un faux succès.
Le code ne dépend pas de l'ancienne séquence Add→Down→Open devenue incorrecte.
Les touches et fermetures sont limitées aux processus et fenêtres possédés ;
aucune entrée n'est envoyée à un autre PID et aucune partition personnelle
n'est passée au programme. Un arrêt forcé, une sortie non nulle, un contrôle
manquant ou des métadonnées seules ne permettent pas de valider le parcours.

Les preuves futures sont les deux rapports natifs, arbres UIA et frames de focus,
captures des fenêtres possédées, journaux de l'application après fermeture,
snapshots du catalogue et SHA des copies. Le titre d'éditeur et les captures
prouvent le chemin d'ouverture ; la revue visuelle du contenu musical, la saisie
de notes, l'écoute et les autres commandes de collections restent distinctes.

La préparation locale comprend20 contrôles PowerShell du vrai lecteur de cible,
10 contrôles du vrai bloc de corroboration montrant notamment que JSON seul ne
valide aucun GUI, et le parsing des scripts et du YAML. Les données de ces
contrôles sont explicitement synthétiques ; aucun COM, MSI, GUI ou lecteur
musical n'est exécuté. Le client natif n'a pas encore été compilé avec le SDK
Windows et le parcours2005 reste à exécuter. Voir `checks/` et la préparation
native pour les détails, sans les interpréter comme une validation Windows.
