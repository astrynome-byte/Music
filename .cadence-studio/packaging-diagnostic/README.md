# Diagnostic WiX court

Ce fixture compile uniquement un minuscule programme C++ déclarant explicitement son rôle de diagnostic. Il utilise les vrais `version.cmake`, `SetupWindowsPackaging.cmake`, `WIX.template.in` et assets de l'arbre source reconstruit. Les assets copiés sont vérifiés par SHA-256. Le mode est exactement `release`, `MUSE_APP_UNSTABLE=OFF`, `MUSE_APP_IS_PRERELEASE=OFF`, build numérique 4.

Deux expériences consécutives emploient le même payload et le même CPackConfig : la configuration originale, puis la seule suppression du contact vide à l'exécution CPack. Le deuxième cas teste une hypothèse et ne constitue pas un correctif validé avant son exécution Windows. Si un cas échoue, le job échoue après avoir exécuté les deux, et affiche `wix.log`, `.wxs` et `.wxi` en console. L'artefact de traces est téléversé avec `if: always()`, rétention 14 jours ; télécharger une copie durable avant expiration.

Aucun MSI diagnostic n'est téléversé, installé ou lancé. Les MSI temporaires sont supprimés après chaque cas. Aucun résultat de ce fixture ne signifie que l'installateur de Cadence Studio est validé.

Publication par le parent uniquement : déposer ce dossier sous `.cadence-studio/packaging-diagnostic/` et `cadence-packaging-diagnostic.yml` sous `.github/workflows/`. Le commit doit porter `[cadence-packaging-only]`, et le job du workflow complet doit ignorer ce marqueur, comme convenu, afin de ne pas relancer les deux compilations longues.

Vérifications Linux possibles : parse PowerShell/YAML et configuration CMake avec `-ConfigureOnly`. Cela ne compile pas de binaire Windows et n'exécute ni candle ni light.
