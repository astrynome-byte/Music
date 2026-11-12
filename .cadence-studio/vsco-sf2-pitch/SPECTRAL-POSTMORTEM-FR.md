Le premier lecteur de hauteur a réellement échoué au run43242767374.
Son résultat brut reste conservé et ne devient pas un PASS.

Les huit centres de notes du violon VSCO sont à−1,27…+10,47cents des notes
attendues. Son neuvième groupe répète le D5 de release : une comparaison
flottante4.32−4.0>.32 empêche la fusion de ces deux groupes.

La deuxième note C5 des deux variantes flûte est estimée vers261,49Hz par
NSDF, une octave plus bas. Cela ne prouve pas encore un C4 joué : la release
du G5 précédent et le C5 nouveau ont des fréquences proches de784 et523Hz,
soit les harmoniques3 et2 d’un fondamental virtuel à261,5Hz. Le témoin MSBasic
montre brièvement cette même estimation au changement de note.

Le diagnostic complémentaire lit les mêmes dix WAV et deux MusicXML épinglés,
sur le même artefact de données existant. Il importe uniquement les octets
vérifiés SHA256 du lecteur publié ; aucun pyc ni second chargement de source.
Il mesure séparément les canaux L/R, sur neuf fenêtres de160ms avant/après
le changement de2s, les six bandes harmoniques autour de C4 pour la flûte et
G3 pour le violon. Les amplitudes utilisent Hann/Goertzel et une grille±40cents.
Les sondes entre harmoniques donnent seulement un contexte, pas un bruit
de fond calibré.

Une bande basse faible avec les bandes2/3 présentes appuierait l’explication
d’une périodicité virtuelle ; une bande basse nouvellement présente demanderait
une autre analyse. Le script imprime les mesures et n’émet aucun diagnostic
automatique ni nouvelle qualification musicale. Aucun app, DLL, instrument,
Office ou lecteur audio n’est exécuté. Aucun PCM n’est imprimé.

Trois tests synthétiques couvrent la distinction entre un mélange2f/3f et
un véritable fondamental ajouté, la normalisation d’amplitude et le pin du
lecteur publié. Ils ne mesurent pas encore le spectre des vrais WAV.
