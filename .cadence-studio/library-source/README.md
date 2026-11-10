# Candidate Windows de bibliothèque — préparation du 10 novembre 2026

**Prêt à relire, pas envoyé, pas exécuté.** Ce dossier est indépendant du
`source.json` et du correctif du pilote principal, qui restent fixés au stage7.
Aucun exécutable ou installateur de la nouvelle bibliothèque n'est annoncé.

## Sources exactes

| Étape | Identifiant |
| --- | --- |
| Référence MuseScore stable | `v4.7.6` / `96480d58445e3b24b230a3fe7d4725d639aa2eb3` |
| Ancien Cadence compilé, stage7 conservé | `24cce38f0fea7d976382bb09e54d90415c9de6c4` |
| Premier incrément de bibliothèque C++/QML | `24e63cc311ce9f55385b5c57a5dd26297388d289` |
| Candidate QA, helpers et documentation actualisés | `76b51af495b721776945717a812e1de2394a689a` |
| Arbre exact de la candidate QA | `59d63e6f93b3bb7e8e5291cf57f57f9c5d61a06b` |
| SHA-256 du correctif gzip candidat | `2b208e6d9ff98e7375c6518bc2222133b35a5619d80131d1a87b220d144f0e6f` |

Le correctif gzip de242866octets provient de `git diff --binary --full-index`
entre l'amont fixé et la candidate QA, compressé avec horodatage gzip0. Sa
décompression et son application sur un index Git isolé de l'amont ont restitué
exactement l'arbre annoncé. Le checkout de travail est propre. Cela ne remplace
pas l'exécution Windows de Bootstrap ou du compilateur.

Bootstrap est copié dans ce sous-dossier pour rendre ce parcours indépendant
du bootstrap et des métadonnées du pilote principal. Il contrôle l'amont, le
SHA-256 gzip, l'application du correctif et l'arbre exact, puis consigne le
commit CI synthétique distinct du commit d'origine. La normalisation locale
`core.autocrlf=false` maintient les octets des sources reconstruits.

## Fichiers locaux à utiliser après revue

| Fichier préparé | Chemin prévu dans le dépôt pilote |
| --- | --- |
| `../cadence-library-windows.yml` | `.github/workflows/cadence-library-windows.yml` |
| `Bootstrap.ps1` | `.cadence-studio/library-source/Bootstrap.ps1` |
| `changes.patch.gz` | `.cadence-studio/library-source/changes.patch.gz` |
| `source.json` | `.cadence-studio/library-source/source.json` |
| `compare_reference.py` | `.cadence-studio/library-source/compare_reference.py` |
| `expected-reference.json` | `.cadence-studio/library-source/expected-reference.json` |
| `README.md`, `handoff.json`, `SHA256SUMS.txt` | Même sous-dossier `.cadence-studio/library-source/` |

Ne pas remplacer `.cadence-studio/source.json`, le correctif du pilote complet,
son workflow ou les sources du projet Android. Le workflow candidat se limite
à la branche `cadence-studio/windows-build` et aux changements de ses propres
chemins ; un déclenchement manuel reste également déclaré. Un push de ces
chemins pourrait déclencher ce nouveau workflow et d'autres workflows du dépôt
selon leurs règles : la préparation locale n'effectue pas ce push.

Pour cet envoi, utiliser le message de commit
**`[cadence-packaging-only] Prepare isolated local-library Windows candidate`**.
Le garde-fou déjà présent dans l'ancien workflow complet reconnaît ce marqueur
et évite sa reconstruction amont inutile. Le nouveau workflow de bibliothèque
ne l'exclut pas ; il est déclenché par ses propres chemins. Aucun changement de
l'ancien workflow n'est nécessaire. Les éventuels workflows Android restent
soumis à leurs règles existantes et ne sont pas modifiés ici.

## Parcours préparé : application complète, sans reconstruction de référence

Le workflow compte20étapes. Il garde Qt6.10.2, MSVC2022 x64, SDK10.0.26100.0,
CMake3.31.6, Ninja1.11.1, WiX3.14.1 et les dépendances du lock. Une seule
application complète est reconstruite : Cadence avec la bibliothèque. La
référence déjà construite est réutilisée par ses35sorties de comparaison.

- Corpus et douze tests Python, contrôles PowerShell et Doctor.
- Petit exécutable de **tests du stockage de production**, en complément de
  l'application complète : huit groupes, `/utf-8`, QtCore du même kit, CTest
  verbeux et journaux. Les restrictions de permissions Unix ne valident pas les ACL Windows.
- `Configure.ps1` puis le vrai `Build.ps1`, numéro de build
  `1000 + GITHUB_RUN_NUMBER`, stage neuf et provenance contrôlée.
- ZIP expérimental du stage avec SHA-256 **archivé avant les recettes**.
- Les57contrôles CLI de tous les formats du parcours, audit sémantique MusicXML,
  puis comparaison stricte de35sorties au run41740259712, dont les références
  étaient identiques octet par octet entre l'amont et Cadence.
- GUI du stage sans chemins SDK, véritable `Package.ps1`, puis installation,
  CLI isolée, GUI installée facultative et désinstallation du ProductCode exact.
- Artefacts et journaux retenus14jours, expérimentaux, potentiellement soumis
  à une connexion GitHub. Aucune release publique n'est créée.

Le comparateur recalcule les empreintes des fichiers candidats, vérifie aussi
leur cohérence avec leur propre rapport et refuse d'écraser une preuve existante.
Une différence bloque le parcours pour inspection ; elle ne constitue pas
automatiquement un défaut musical. PDF et conteneurs ZIP sont hors des35sorties
car leurs octets différaient dans le précédent run. Les résultats de tous les
autres exports restent disponibles par leur rapport séparé.

## Contrôles locaux obtenus

Douze tests Python réussis après copie des helpers. Onze scripts PowerShell
analysés et tests de wrappers réussis sous Linux. Schéma YAML, clés uniques,
ordonnancement et20étapes contrôlés ; treize commandes PowerShell du workflow
et Bootstrap analysés. Cinq essais synthétiques du comparateur passent : égalité,
altération malgré un rapport inchangé, différence de référence, fichier absent
et refus de remplacer un résultat. Ce ne sont pas35comparaisons d'une nouvelle
application réellement compilée.

Les helpers intégrés ont déjà observé une fermeture propre du **binaire ancien**
dans le run42721049351 ; installation/CLI/désinstallation du MSI de ce même
binaire ont réussi. La candidate bibliothèque reste **non qualifiée sous Windows**,
et sa recette d'ajout/recherche/favoris/relocalisation reste à exécuter dans la
nouvelle vue. `handoff.json` garde les limites et identifiants sans annoncer un
build ou une URL de téléchargement inexistants.
