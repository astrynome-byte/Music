# Correctif de sérialisation du résumé MSI

Le premier lecteur DATAONLY 2006 a lu les données jusqu'à conserver neuf
fichiers dans l'artefact `13960077684` du run `43254541505`. Sa construction du
reçu final échoue avec `TypeError: Object of type bytes is not JSON serializable`.
Le champ SummaryInformation VT_LPSTR renvoyé par `_msi.GetProperty(7)` est un
objet bytes ; les valeurs de `Record.GetString` sont des chaînes Unicode.

Seul `read_only_msi.py` change : le résumé plateforme/langue est décodé en ASCII
strict et ses octets exacts restent disponibles sous `summary_template_raw_hex`.
Le type d'origine figure dans `summary_template_raw_type`. Une valeur non ASCII,
vide, trop grande ou d'un type inattendu provoque un échec explicite. Aucun
convertisseur JSON générique ne masque un autre type inattendu.

L'ouverture de base reste READONLY=0, les SELECT et les constantes de
provenance restent identiques. Aucun exécutable, installation, registre ou
produit enregistré n'est interrogé. Les autres fichiers du lecteur gelé ne
sont pas modifiés par ce lot. Une nouvelle exécution du même workflow DATAONLY
devra authentifier les mêmes trois artefacts originaux ; ce correctif ne
constitue pas lui-même un reçu de lecture réel.

Les cinq vérifications locales utilisent uniquement des retours d'API
synthétiques : elles reproduisent le TypeError original, vérifient la
sérialisation bytes/str et le refus des types/octet non ASCII. Elles n'appellent
pas Windows Installer et ne lisent aucun MSI réel.
Le reproducteur accepte les chemins explicites `--original`, `--fixed` et
`--output`, afin de conserver séparément les deux versions du lecteur.
