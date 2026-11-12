# Mini natif AU15 — correction des dépendances de lien

Ce harnais prépare une seule nouvelle exécution Windows. Le run précédent
43256333055 (pilote 9720c3eb) a échoué au lien ON : deux symboles réels manquaient.
Aucun des 10 groupes ON, des 3 contrôles OFF ou des deux contrôles anciens n’a
été exécuté. Les preuves historiques sont conservées hors de ce payload.

Candidat `0f1b61397d7b00714f135ecc737c48cdc380c930`, arbre `34bd415cc77469c6439e6274c8c8c556391ae7e1`, enfant de
`88f49ea89ba96471fb00abd4e3074488239648aa`. Un seul fichier du candidat change :
le CMake du test autonome ajoute les vraies unités MscReader, stringutils,
ZipReader, XmlStreamReader et pugixml, plus son répertoire d’en-têtes. Les corps
moteur, assertions et six fichiers du contrôle ancien `b02b41f4` sont inchangés.
Les sources pugixml conservent leur licence MIT dans leurs en-têtes.

Le snapshot contient 39 CPP, 180 fichiers candidat et 6 fichiers anciens,
soit 188 membres ZIP avec manifeste et sommes. Les fichiers viennent de
`git show` du candidat figé, jamais du worktree. Tous sont vérifiés avant/après.
Le même générateur de configuration canonique, le SDK Qt 6.10.2, MSVC 17.14 x64,
le SDK Windows 26100, Python 3.12 et zlib 1.3.2 /MD sont exigés. L’action Python
reste après Qt. Le workflow et les assertions de qualification sont inchangés.

La correction passe sous Linux : 39 unités réelles liées sans élimination des
sections ; les 10 groupes comportementaux et la sauvegarde native réussissent.
Cela ne qualifie pas encore Windows. L’exécution Windows devra obtenir 10/10 ON,
3/3 OFF et les deux erreurs anciennes attendues exactement. Aucune application
complète, interface, banque réelle, VST externe, ASIO ou écoute humaine n’est
qualifiée par ce mini. L’indication UI de secours reste un complément séparé.
