# Sources Cadence pour qualification complète Windows2008

Ce pilote reconstruit exactement l’arbre indiqué dans source.json depuis le tag officiel v4.7.6 ; le patch gzip est déterministe et vérifié par SHA-256. Un index Git isolé a reconstruit le même arbre localement. Les sources comprennent tous les nouveaux modules ; cela ne signifie pas qu’un binaire2008 a déjà été produit ou testé.

Attentes liées à cet arbre :54 tests Python sans saut,21 scénarios historiques de stockage,57 contrôles CLI,35 comparaisons et5 AAC réellement décodés. Les tests supplémentaires natifs (bibliothèque4, MIDI, historique, OMR, transcription et client réseau) ont leurs observations séparées ; leurs branches non applicables ou non exercées sont déclarées. MP4 reste un test négatif du profil. Les sons CC0 sont facultatifs, aucune écoute ou Windows10/11 client n’est inventé.

La branche main Android et les anciens espaces sources ne sont pas remplacés. Ce pilote ne publie pas d’installateur final.

Les cinq fichiers binaires du pilote sont transportés en126 morceaux base64 ASCII. Restore-Binaries.ps1 vérifie chaque morceau puis retrouve exactement leurs tailles et SHA avant Bootstrap. Cette adaptation du transport ne modifie ni l’arbre source application ni les WAV/MIDI. Dix-neuf tests PowerShell locaux ont vérifié restitution exacte, refus de corruption et absence d’écrasement. La compilation Windows reste à exécuter.

Première tentative43319506534 :54 tests exécutés, un échec Windows de nettoyage SQLite dans un test, avant toute compilation. La source candidate49272b75 corrige seulement cette connexion de test depuis8420ff17 ; aucun code de production changé. Le numéro produit2008 est désormais explicite dans source.json, indépendant du compteur Actions. Les125 autres morceaux binaires sont inchangés.

Tentative43322336613 : configuration et tests natifs réussis, compilation MSVC Unity interrompue sur une déclaration MIDI masquée avant le chargement tardif du flag. La source2493b32f ne change que CMakeLists depuis49272b75, pour propager CADENCE_BUILD=1 avant chaque unité, PCH et moc ; OFF reste absent. Le nouvel audit compile_commands/config est requis avant la compilation complète.

Nouvelle tentative après le run43333855453 : aucun EXE/MSI2008 produit. La source ajoute les17 fichiers revus de811d (WAV HTTPS direct, état secret accessible, promotionsMuseHub par défaut désactivées), puis le correctif Unity explicitement commité et indiqué dans handoff.json. Le numéro produit reste2008, séparé du compteurActions. Le gate /Zs /Y- conserve les vrais /FI ; les14 groupes HTTPS ont un contrôle natif distinct avant la compilation complète. Les preuves Linux ne sont jamais transformées en résultat Windows.
