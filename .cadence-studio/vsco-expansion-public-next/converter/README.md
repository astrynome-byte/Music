# Collections VSCO CE natives SF2

Outil développeur GPL-3.0-only ; les données audio et mappings sources sont
CC0-1.0. L’utilisateur final charge les fichiers SF2 dans Cadence et n’a besoin
ni de Python, ni de sfizz, ni d’un autre plugin. Ce dossier ne constitue pas
une prise en charge SFZ dans l’application.

## Produire les trois collections supplémentaires

Python3.12, bibliothèque standard uniquement pour convertir :

```sh
python tools/audio/vsco_sf2/build_collections.py --list
python tools/audio/vsco_sf2/build_collections.py --collection cello-ensemble --collection trumpet-vibrato --collection contrabass-vibrato --download --output /nouveau/dossier/banques
```

Le dossier de sortie doit être nouveau. `--source-root` remplace `--download`
pour employer les fichiers originaux déjà présents. Le commit source est fixé à
28092772094b2d9f1148d84cea97f4545b8c687d (VSCO CE1.1.0). Chaque WAV est vérifié
par taille et SHA Gitblob, gardé en mémoire, converti puis libéré ; aucun cache
WAV n’est créé. Le manifeste des trois profils est lui-même verrouillé par SHA.
Les banques de flûte/violon1.0.0 déjà publiées ne sont ni écrasées ni modifiées.

`build_vsco_sf2.py` conserve aussi son ancienne commande pour reproduire les
deux mappings flûte/violon. Ses nouveaux paramètres optionnels autorisent
uniquement les métadonnées de groupe exactes du profil et un nom de preset
court. La séquence1/1 est statique, group_label informatif ; une vraie séquence
round-robin ou tout autre opcode inconnu est refusé. Les anciens appels ont
les mêmes défauts et le même binaire SF2 golden de contrôle.

## Instruments et limites musicales

- Violoncelles **ensemble**, programme GM42 (43 affiché), MIDI36–77, plusieurs
  couches de vélocité, attaque0,001s et relâche0,8s. Ce n’est pas un violoncelle solo.
- Trompette vibrato, GM56 (57 affiché), MIDI52–84, deux couches, attaque0,001s,
  relâche0,5s. Aucune alternance round-robin n’est inventée pour sa séquence1/1.
- Contrebasse vibrato, GM43 (44 affiché), MIDI24–60, deux couches, attaque0,001s,
  relâche0,8s.

Une articulation tenue par collection ; pas de legato ou staccato enregistré.
La stéréo et les zones du mapping sont préservées. PCM24/32 devient PCM16 par
troncature sans dithering. Les gains sont normalisés par un même headroom de
banque, conservant les gains relatifs ; les générateurs ciblent le facteur
d’atténuation EMU0,4 du FluidSynth embarqué dans Cadence. Le comportement d’un
autre lecteur peut différer. ampeg_dynamic vivant n’est pas reproduit ; la
réponse de vélocité SoundFont reste active. Aucune boucle nouvelle n’est créée.
Les75 WAV sélectionnés ne contiennent aucune boucle smpl : une note très longue
finit avec l’enregistrement. Un résultat musical identique aux banques ou
lecteurs commerciaux n’est pas annoncé.

Les sources et notices originales VSCO demandent des crédits : Versilian
Studios/Sam Gossner et Ivy Audio/Simon Dalzell. Les textes originaux CC0 et
README sont conservés et recopiés dans la sortie.

## Vérifier

```sh
python -m unittest discover -s test/cadence -p test_vsco_sf2_collections.py -v
python -m unittest discover -s tools/audio/vsco_sf2/checks -p test_converter.py -v
python tools/audio/vsco_sf2/qualify_linux.py --banks /dossier/banques --output /nouveau/dossier/mesures
```

La conversion et les11 contrôles de format/provenance utilisent la bibliothèque
standard. Le dernier diagnostic est Linux seulement, demande NumPy et une
bibliothèque FluidSynth déjà installée, ne crée aucun pilote audio et ne lance
ni Cadence ni un périphérique. Il mesure trois vélocités, la tenue20s, le
relâchement et des bandes spectrales descriptives ; un harmonique fort n’est
pas arbitrairement nommé erreur d’octave. Le gain4,8 suit la constante source
de Cadence. Des WAV de12s sont produits pour une écoute séparée, jamais prétendue
faite par ce diagnostic. Windows/Cadence réel, sauvegarde/réouverture, gestionnaire
GUI, écoute humaine et matériel restent des qualifications distinctes.

Ces trois banques sont actuellement des sorties construites et vérifiées ; le
statut de publication et d’intégration du gestionnaire se trouve dans STATUS.md
et FEATURES.md du projet. Aucun lien de téléchargement public n’est inventé.
