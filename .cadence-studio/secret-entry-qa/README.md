# Qualification Windows native de la saisie secrète — inactive

La recette ne lance ni Cadence2008, ni serveur, ni vraie clé. Elle compile seulement
un petit harnais Windows natif et la primitive destinée à une future QA du champ
secret. Le contenu tapé est la fixture synthétique publique43 lettres A ; aucun
clipboard ou argument contenant une clé. Les12cas natifs restent à exécuter sous
Windows ; parsing et revue statique locaux ne prouvent pas leur réussite.

Deux nouvelles sources représentent environ22Ko. OwnedKeyboard et OwnProcessJob
sont repris du namespace import-dialogs-gui-2008 déjà publié, vérifiés par octets/SHA,
sans duplication ou changement. Les API standard Windows/SDK26100 et MSVC2022
suffisent ; aucune dépendance Qt, système audio, DLL commerciale ou outil ami.

Les cas contrôlent : entréeLF, mauvaisPID,champ nonmasqué,champ nonvide,mauvaislabel,
longueur courte/tropgrande,alphabet incorrect,entréeCRLF,chemin extérieur refusé,
répertoire refusé et hardlink refusé. Les deux entrées doivent produire86inputs
et43bullets ; chaque refus doit conserver0input. Fichier temporaire propriétaire,
reparse/identité finale,PID/HWND/focus/IsPassword,label exact et absence de modificateurs
sont exigés. Le harnais natif borne son temps et nettoie uniquement ses fichiers.
Le lanceur exige fin0,aucun kill et Job drainé/fermé, puis garde le JSONstdout original.
Aucune capture, valeur, hash de clé ou texte entré n’est journalisé.

Target.template reste ready=false/manifestnull et aucun target.json n’existe.
Le workflow push écoute uniquement l’ajout du vrai target dans ce namespace,
sur cadence-studio/windows-build. La racine seule relit les sources/manifestes,
publie la recette inactive, puis ajoute un target distinct avec ready=true,
helper_manifest_sha256 réellement calculé, synthetic_only=true et les trois
flags real_token_used/Cadence_application_executed/server_started=false.

Le résultat, même réussi, qualifiera la primitive sur une fenêtre Edit synthétique.
Il ne qualifiera pas le dialogue Qt, l’authentification du client, une bibliothèque,
un installateur, le matériel ou les fonctions payantes. La source2008 connue masque
visuellement et textuellement la clé mais ne transmet pas encore passwordEdit via
MUAccessible ; la garde stricte pourrait donc y refuser toute saisie. Un patch
produit post2008 séparé est à préparer et vérifier, sans modifier ce test pour le contourner.

assemble_payload.py régénère uniquement les sources privées,manifest et8tree_elements,
aucun réseau ni mutation GitHub. Les commandes réelles Windows sont dans le workflow.
