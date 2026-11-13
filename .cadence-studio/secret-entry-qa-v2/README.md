# Seconde recette de saisie secrète native — inactive

Ce lot ne lance ni Cadence, ni serveur, ni vraie clé. Il reprend les douze cas
natifs V1 et ses deux saisies de la fixture publique de 43 lettres A, sans changer
`OwnedSecretEntry.h`, ses gardes, son propriétaire de fichier ou ses contraintes
PID/HWND/IsPassword. Les deux helpers existants sont repris par empreintes.

Le run V1 `43337069937`/job`131595813897` a compilé sous MSVC, puis son harnais
est sorti avec le code 3 sans rapport natif : aucun des douze cas n'est qualifié. Le contrôleur
n'a forcé aucun processus et son Job a été drainé. Le pump ancien pouvait sortir
sur un timer étranger ou WM_QUIT puis attendre sans servir les messages UIA.
Le message qui a effectivement déclenché V1 n'a pas été enregistré ; cette
attribution demeure une hypothèse. Le gel et les journaux V1 restent intacts.

V2 attend le **handle réel du worker** avec MsgWaitForMultipleObjectsEx. Il
sert les messages avec PeekMessage, au plus 256 messages par lot, et garde une échéance
de 30 secondes vérifiée entre appels ; le contrôleur borne le processus à 45 secondes
si un appel Windows ne revient pas. Seul le timer de sa propre HWND/id provoque un timeout ;
les autres timers sont dispatchés normalement. WM_QUIT et Finished ne prouvent
jamais la fin du worker. Le thread de test injecte avant le worker un timer
étranger sans HWND et un WM_QUIT : la réussite exige qu'ils aient été consommés
et que les douze cas, le nettoyage et la vraie fin du worker aient réussi.

En échec avec worker actif, le rapport lit seulement des atomiques de phase et
d'index, sans parcourir son vecteur. Après flush JSON, `_Exit(3)` évite de lancer
des destructeurs C++ concurrents. Ce chemin est explicitement un **échec avec
nettoyage non prouvé** ; aucun faux résultat propre n'en est déduit. Les erreurs
initiales de fenêtre/timer/thread produisent aussi un rapport. Aucun contenu,
hash ou chemin de clé, clipboard ou texte saisi n'est journalisé.

Le wrapper conserve les sorties originales et exige douze cas exacts, deux
saisies de 43 caractères (86 événements chacune) et zéro événement sur chaque refus ; il exige en plus le
handle terminé, code0, phase finale, les deux régressions observées, aucun échec
du pump, aucun kill et le Job fermé. Les captures restent absentes.

La nouvelle recette utilise le namespace `secret-entry-qa-v2`, un workflow
séparé à permissions de lecture et une activation distincte. Le modèle de
target reste `ready=false` ; aucun target actif n'est dans le payload. La
racine seule peut publier, puis activer le manifeste exact après revue.

Les vérifications locales portent sur les octets, le YAML, le parsing
PowerShell, les refus de cible et le format des rapports. Elles ne compilent
ni n'exécutent UIA sous Windows. Le prochain run réel doit encore qualifier
la primitive et le pump ; même un succès ne qualifierait pas le dialogue Qt,
l'authentification, un installateur ou une fonction payante de Cadence.

Reproduction des préparations locales :

```sh
python assemble_payload.py
python checks/verify_report_serializer.py
python checks/verify_preparation.py
```

Le test du sérialiseur compile le corps C++ exact du rapport avec des types de
frontière explicites et un conteneur qui interdit tout accès aux résultats du
worker actif. Cinq états produisent du JSON relu et vérifié. Ce test ne lance
ni le pump Win32, ni le fournisseur UIA, ni la saisie de caractères.
