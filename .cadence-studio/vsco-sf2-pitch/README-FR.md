Ce lecteur GPL-3.0-only contrôle la hauteur musicale des WAV Windows déjà produits
par le test VSCO SF2 du run43231480145. Il ne lance aucune application, DLL,
banque de sons ou lecteur audio et n’installe aucune dépendance.

Le workflow séparé vérifie le run et le commit du producteur dans l’API GitHub,
puis récupère uniquement l’artefact13949852671 de21278275octets. Le digest du
ZIP extérieur est conservé comme métadonnée API ; le lecteur ne prétend pas
avoir mesuré le ZIP avant l’extraction par actions/download-artifact.

Les SHA256 des dix WAV et des deux MusicXML sont épinglés d’après les preuves
réelles conservées. Les rendus initiaux et réouverts doivent être identiques.
Le conteneur WAV est contrôlé avant toute lecture des échantillons : RIFF exact,
chunks bornés, fmt/data uniques, stéréo float32 à44100Hz et sept secondes.
Aucun PCM n’est imprimé ; seules des mesures numériques sont conservées.

La détection cherche les périodes entre90 et2000Hz avant de consulter la note
attendue. Elle choisit le canal le plus énergique pour éviter une annulation
stéréo, filtre avant décimation, puis analyse des fenêtres de160ms espacées
de80ms. Les pics NSDF sont interpolés avant sélection. Une mesure spectrale
Hann/Goertzel à f/2 et f/3 refuse les fenêtres ayant une sous-harmonique d’au
moins5% de l’amplitude principale : cela évite certains faux accords d’octave
lorsque le deuxième harmonique domine le fondamental.

Les suites de notes soutenues sont ensuite comparées aux huit notes du XML
réel : C5,D5,E5,G5 répétés pour la flûte ; G4,A4,B4,D5 répétés pour le violon.
Le placement des fenêtres ne suppose pas une tempo de120BPM. Chaque note
nécessite au moins deux fenêtres consécutives utilisables ; la médiane doit
rester à60cents de la hauteur attendue. Les résultats des banques VSCO sont
aussi exprimés en cents par rapport aux deux témoins MS Basic.

Une faible périodicité, des releases superposées ou des groupes supplémentaires
donnent un résultat inconclusif, qui fait échouer le job. Un fondamental sous
le seuil spectral de5% n’est pas exclu. Cette mesure ne remplace pas l’écoute,
ne qualifie pas le timbre, les notes longues, tout le clavier ou l’interface GUI.

Les neuf tests locaux utilisent seulement des signaux synthétiques explicitement
identifiés. Ils couvrent les notes et octaves, le vibrato, les harmoniques,
le silence, NaN, la stéréo en opposition de phase, les bornes WAV, les pins API
et le refus de traversée de chemin. Ils n’analysent aucun WAV Windows réel.

Commande locale des tests :

    python -m unittest discover -s . -p test_pitch_reader.py -v

Publication réservée au parent. Le namespace déployé est
`.cadence-studio/vsco-sf2-pitch/` ; il ne déclenche pas le workflow qui lance
l’application et reconstruit les banques.
