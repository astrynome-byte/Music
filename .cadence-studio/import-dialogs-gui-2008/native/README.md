# Client indépendant UI Automation

UiaProbe.cpp réutilise les primitives Notes6 de PID/poignée, fenêtres possédées,
dumps UIA bornés et timeouts COM. ImportDialogsFlow.inc contient les seules
phases d’import. OwnedKeyboard conserve ses gardes ; le delta autorise une
frappe Alt complète par ouverture, pour la navigation du vrai menu Fichier,
et Home/PgDown pour les indices réels des contrôles WAV. Ces gestes restent
bornés et exigent les observations de focus exactes ; les paires de dumps
avant/après chaque geste conservent leur numéro.
OwnedWaveFileDialog dérive du sélecteur MSCX existant avec uniquement les
extensions/titres d’import fixés ; ses contrôles de chemins locaux et handles
sans reparse, ValuePattern exact puis Open Invoke restent en place.

Les phases ne contiennent aucune URI/actions internes de Cadence. Le pilote
ne charge pas un modèle QML de remplacement et n’injecte aucun résultat OMR.
Aucun Windows SDK n’est installé par l’utilisateur final. Compiler avec
MSVC 2022 /std:c++17 /utf-8 /EHsc et ole32, oleaut32, user32, uuid.
