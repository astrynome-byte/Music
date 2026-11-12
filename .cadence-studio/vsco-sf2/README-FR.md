Ce dossier prépare deux banques SoundFont natives pour Cadence : une flûte et un violon solo, issus des enregistrements VSCO 2 Community Edition. Les trois SF2 ont été construits et rendus avec une bibliothèque FluidSynth déjà présente sous Linux. La qualification dans Cadence Windows build 2005 reste à exécuter ; aucune interface de gestion de bibliothèque ni écoute humaine n’a été validée.

Les sons et les deux mappings originaux sont sous **CC0-1.0**, reproduit sans conversion dans `VSCO-CC0-LICENSE.txt`. Les outils de ce dossier sont sous **GPL-3.0-only** ; `CODE-GPL-3.0.txt` contient le texte GNU GPL version 3, repris à l’octet près du compagnon QA phase2. Son SHA-256 est `8ceb4b9ee5adedde47b31e975c1d90c73ad27b6b165a1dcd80c7c545eb65b903`. Cette préparation utilise le chargeur SF2 natif : aucun sfizz, plugin VST ou achat de bibliothèque n’est requis pour ces banques.

La source retenue est `sgossner/VSCO-2-CE`, tag `1.1.0`, commit `28092772094b2d9f1148d84cea97f4545b8c687d`. `asset-source-manifest.json` fixe les tailles et identités Git des 46 originaux : 43 WAV, deux mappings et le texte CC0. Le téléchargement du convertisseur porte uniquement sur les 43 WAV, soit 99 522 542 octets ; chaque fichier est contrôlé avant utilisation. Les WAV sont traités un par un sans cache original conservé sur disque.

Avec Python 3.12 et sa bibliothèque standard, la construction se lance vers un dossier qui n’existe pas encore :

```text
python build_vsco_sf2.py --output CHEMIN_NOUVEAU_VERS_LES_BANQUES --download
```

Une copie locale des sources exactes peut aussi être utilisée :

```text
python build_vsco_sf2.py --output CHEMIN_NOUVEAU_VERS_LES_BANQUES --source-root CHEMIN_VERS_VSCO_ORIGINAL
```

Le résultat comprend `banks-manifest.json`, le texte CC0 et ces fichiers :

| Fichier | Préréglage SF2 | Numéro GM affiché à partir de 1 | Tessiture couverte | Taille |
| --- | --- | --- | --- | --- |
| `Cadence-VSCO-Flute.sf2` | Banque 0, programme 73 | 74, flûte | MIDI 60–96 | 16 778 410 octets |
| `Cadence-VSCO-Violin.sf2` | Banque 0, programme 40 | 41, violon | MIDI 55–96 | 74 366 558 octets |
| `Cadence-VSCO-Flute-minus18.sf2` | Banque 0, programme 73 | 74, flûte | MIDI 60–96 | 16 778 410 octets |

Le troisième fichier est le contrôle technique à −18 dB. Les deux premières banques sont celles prévues pour l’essai musical manuel. Le total des trois SF2 est de 107 923 378 octets. Les empreintes exactes sont consignées dans `conversion-contract.json` et dans le manifeste produit par le convertisseur.

Pour un essai manuel ultérieur, placez les deux banques musicales dans le dossier de documents utilisé par Cadence, normalement `Documents/CadenceStudio4/SoundFonts`, ou dans un dossier choisi dans les chemins de banques de sons de l’application. Relancez Cadence, ouvrez une partition de la bonne famille et choisissez le préréglage flûte ou violon de la banque correspondante. Gardez **MS Basic** disponible comme banque généraliste et solution de secours : ce petit ensemble VSCO ne remplace pas une bibliothèque complète. Cette procédure décrit l’installation manuelle envisagée ; son fonctionnement dans la version Windows retenue doit encore être vérifié.

La conversion conserve les canaux stéréo, les zones de notes, les couches de vélocité et l’accordage fin présent dans les mappings. Elle convertit les enregistrements entiers 24/32 bits en PCM16 par conservation des bits de poids fort, sans dithering. Les gains positifs sont ramenés sous une marge commune de 12 dB pour la flûte et 21 dB pour le violon ; leurs différences relatives sont conservées.

Les enveloppes utilisent une attaque fixe de 0,001 seconde et une relâche de 0,7 seconde pour la flûte ou 0,8 seconde pour le violon. Le comportement SFZ `ampeg_dynamic` n’est pas reproduit ; la réponse de vélocité SoundFont reste active. Aucun des 43 WAV ne contient de boucle `smpl` : aucune boucle n’a été inventée et une note tenue finit lorsque l’enregistrement atteint sa fin. Aucun legato, staccato, sustain perpétuel ou équivalence sonore avec sfizz n’est annoncé.

Les gains ciblent précisément le moteur FluidSynth de Cadence : son facteur `EMU_ATTENUATION_FACTOR = 0.4` conduit à **25 unités brutes de `initialAttenuation` par dB**, avec un décalage de 450 pour le contrôle à −18 dB. Cette compensation n’est pas un réglage universel pour les autres lecteurs SF2. Le contrat de conversion conserve la référence au source FluidSynth 2.3.3 retenu et cette limite de portabilité.

Les observations réelles sous Linux sont dans `checks/actual-linux-fluid-longnotes.json` : les trois banques se chargent, leurs deux canaux produisent un signal non muet, et le contrôle mesure −17,9999999995 dB avec FluidSynth 2.4.4 existant. Les essais de notes tenues pendant 20 secondes constatent la fin des échantillons ; les essais de note-off après une seconde constatent une relâche revenue au silence après deux secondes. Aucun pilote audio ni dépendance système supplémentaire n’a été installé. Les tests synthétiques vérifient séparément les formats, les chemins, les identités de ressources, les mesures WAV et le refus de lancer la qualification Windows sur Linux.

Le workflow `cadence-vsco-sf2-qa.yml` prépare une qualification future sur un runner Windows x64 GitHub-hosted jetable. Il télécharge l’artefact exact `13943781621` du run `43207550870`, vérifie le ZIP `4707aea7e6f0f63361ced55edfff7c7cf591f15463f9219263bfac4de3f96f9b` puis l’exécutable build 2005 `d957ffc99497cb01b1f00f82ba1d6e89ef84547708506c6c51423675805e140a`, sans reconstruire ni installer l’application.

Cette qualification doit passer cinq cas : MS Basic flûte, flûte VSCO, flûte VSCO à −18 dB, MS Basic violon et violon VSCO. Chaque cas exige un WAV non muet, un enregistrement natif conservant la ressource sélectionnée et un nouveau rendu du projet rechargé. Le contrôle de gain est exigé avant et après rechargement. Les processus appartiennent à un Job Windows ; leur drainage doit être prouvé avant suppression des trois racines de profil Cadence initialement absentes et marquées. Les banques, copies de partitions, WAV et stage restent sous `RUNNER_TEMP`. Le workflow ne qualifie pas une sauvegarde GUI après lecture interactive, du matériel audio ou une nouvelle intégration de bibliothèque.

Le payload de publication contient seulement les sources, licences, mappings et contrôles. `real-banks/`, les WAV originaux, les caches Python et les payloads de publication eux-mêmes sont exclus. Le manifeste lie les chemins, tailles et SHA-256 aux octets préparés ; les mappings SFZ et le texte CC0 restent intacts. La règle locale `.gitattributes` désactive les conversions de fin de ligne dans ce dossier.

La règle compagnon `workflow-gitattributes.txt` correspond à la création ciblée de `.github/workflows/.gitattributes` avec `cadence-vsco-sf2-qa.yml -text`. Ce fichier distant a été constaté absent lors de la préparation. Au moment de publier, le responsable doit relire son état : s’il existe désormais, il doit fusionner cette ligne en préservant les autres règles, puis régénérer les empreintes et le payload. Cette préparation n’autorise aucun écrasement d’attributs existants ni publication automatique.
