# Première ouverture de Cadence Studio 2008 sans INI

Préparation inactive pour le stage réel issu de la source `a2b7abaf045a8f3cb84ec2953d9e0e51b9e78903`.
Le producteur `43408309742`, job `131828068954`, a compilé et conservé le stage
(étapes 25 à 30 réussies), puis échoué au harnais MIDI de l’étape 31. Les
qualifications suivantes et le MSI restent à faire. Ce contrôle GUI ne change
pas cet état et refuse les anciennes tentatives sans exécutable.

Le lecteur DATAONLY existant est repris sans changement. Le garde vérifie de
nouveau le producteur exact et le restaurateur vérifie les archives, les quatre
compagnons originaux et les 2 712 fichiers du runtime avant tout lancement.
La mesure d’inventaire est comparée après sérialisation JSON canonique LF ; les
archives et compagnons originaux restent comparés octet pour octet.

Le profil jetable utilise les helpers existants. L’adaptateur appelle leur
prepare puis verify, et supprime uniquement le seul INI qu’ils viennent de
créer, après vérification de son contenu, de son chemin final et de son
identité native FileIdInfo128 sur le même handle. Les trois racines portent
leurs marqueurs d’appartenance. Aucun réglage utilisateur préexistant n’est
remplacé ni supprimé. Le profil est revérifié sans INI avant lancement.

L’EXE démarre avec zéro argument, sans document, banque, plugin ni seed ASIO.
Le probe SDK Home/Intro existant observe l’application et une capture de sa
fenêtre est conservée. Une Introduction exactement reconnue peut recevoir un
WM_CLOSE, puis la fenêtre principale possédée. Une boîte inconnue n’est pas
choisie. Le Job est drainé avant le nettoyage du seul profil créé. Une
terminaison forcée, un échec ou un nettoyage incomplet interdit la réussite.

Les défauts source sont le français, la première configuration non terminée
et les promotions MuseHub désactivées. Ils ne sont pas encore une preuve de
leur résultat visuel Windows. L’absence éventuelle de périphérique WASAPI sur
CI reste une limite réelle ; aucun INI ASIO ne la masque. La fermeture précoce
de l’assistant peut écrire son flag interne de fin : le rapport ne prétend
pas avoir parcouru ni qualifié toute sa configuration. Aucune écoute, absence
totale de réseau, édition, lecture musicale ou validation MSI n’est déduite.

Le target fourni est un modèle `ready: false` ; aucun target actif n’est
inclus. Root seul publie et active la recette. Les contrôles locaux portent
sur les pins, les formats et les refus de contexte. L’exécution Windows et la
relecture des captures doivent être rapportées séparément.
