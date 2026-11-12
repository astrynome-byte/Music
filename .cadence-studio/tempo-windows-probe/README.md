# TempoMap Windows — deux compilateurs réels

Le full2004 a exécuté35tests et arrêté un échec de compilation du nouveau
harnais tempo sous GNU Windows, avant toute compilation de l'application.
WIN32, UNICODE et _UNICODE manquaient au harnais alors que CMake les fournit
normalement au code Windows amont.

Ce pilote reconstruit la source053 et applique uniquement le correctif approuvé
du test : candidatfcec, arbre0ea. Il respecte CXX et les critères musicaux : le
vrai TempoMap et le helper de transport doivent passer1024propriétés avec
g++, puis les mêmes1024 avec cl, sans skip. Les six sources et l'arbre sont
vérifiés avant et après. Aucun Qt, application ou GUI n'est compilé ou exécuté ;
les deux petits binaires de test le sont réellement sur un runner Windows jetable.
