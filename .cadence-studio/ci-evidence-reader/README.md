# Lecture des preuves CI existantes

Ce lecteur prépare uniquement le diagnostic des exécutions du 11 novembre 2026. Il ne lance ni application, ni codec, ni compilation, ni nouvelle sonde système. Aucun résultat réel n’a encore été obtenu par ce lecteur au moment de sa préparation.

- Coexistence : run `43094504811`, job `130779790459`, artefact `13890845538` nommé `cadence-coexistence-qa-1-1` ; son rapport original est conservé avec son empreinte SHA-256.
- Zlib : journal du job `130779749675`, run `43094504840`, lu par `gh api repos/astrynome-byte/Music/actions/jobs/130779749675/logs` avec les permissions ordinaires `actions: read` du dépôt propriétaire. Aucun accès à un hébergement File Service ni contournement de destination n’est utilisé.

Le workflow télécharge l’artefact existant avec l’action officielle, puis récupère le journal existant avec GitHub CLI. `GH_TOKEN` est fourni seulement à cette étape et n’est jamais imprimé. En cas d’indisponibilité des journaux, le lecteur produit quand même un résumé explicitement incomplet.

`inspect.py` se lance avec `python -I` pour éviter qu’un fichier nommé `inspect.py` masque le module standard homonyme. Il lit les seuls fichiers `coex*.json` (16 au maximum, 256 Ko chacun), affiche leur JSON intégral entre sentinelles et conserve les octets d’origine identifiés par SHA-256, sans les réécrire. Les rapports sont des preuves de l’exécution précédente, pas des tests rejoués. Il vérifie la cohérence des champs de préservation/désinstallation d’un statut `passed`, sans en déduire une validation musicale ou humaine.

Le journal zlib est détecté comme texte ou ZIP (`PK`), lu en mémoire sans extraction sur disque, avec limites de taille/nombre d’entrées et de sortie. Au maximum 100 lignes de contexte sont retenues autour des marqueurs Traceback/ERROR/exception. Les jetons reconnaissables, en-têtes d’autorisation et paramètres d’URL sont masqués dans ces extraits. Aucun contenu audio n’est lu ou encodé en base64.

Le lecteur produit `summary.json` et un output GitHub Actions `summary` sur une seule ligne ASCII, limité à 180 caractères : statut observé de coexistence et premier message d’exception zlib trouvé. L’étape suivante s’appelle `Observed: ...` grâce à cet output ; son nom reste accessible via l’API des étapes du job même si la lecture des logs échoue. Les artefacts de synthèse expirent après 14 jours et leur accès reste soumis à GitHub ; ce n’est pas une livraison produit.

Le succès de ce workflow signifie seulement que le diagnostic a été écrit. Les statuts des anciens jobs restent distincts. Les contrôles locaux de préparation utilisent uniquement des rapports/journaux synthétiques, notamment texte et ZIP ; ils ne valident pas les deux exécutions Windows.
