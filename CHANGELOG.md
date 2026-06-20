# Journal des changements

Toutes les versions officielles publiées sur GitHub doivent reprendre la section de version correspondante.

## [Non publié]

- Audit de préparation des mises en ligne officielles GitHub.
- Garde locale contre les secrets et fichiers générés suivis par Git.
- Génération des notes de mise en ligne depuis ce journal.
- Licence MIT, microsite GitHub Pages et build Windows reconstruit sans UPX.
- Vérification d'intégrité de la version ouverte par comparaison SHA256 avec la mise en ligne GitHub.
- Mise à jour des références GitHub Actions et des planchers de dépendances de compilation.
- Durcissement de l'audit de publication, de la compilation CI/release et du contrôle VirusTotal.
- Distribution officielle déplacée vers un paquet portable cx_Freeze avec blocage automatique si VirusTotal signale une détection.
- Manifeste JSON de mise en ligne avec empreintes SHA256, statut VirusTotal et statut Authenticode.
- Icône produit financière avec symbole `$` dans l'application, l'exécutable et le microsite.
- Score VirusTotal affiché dans les notes de chaque mise en ligne officielle, avec rapport détaillé joint.

## [0.1.0] - 2026-06-18

- Conversion EmployeurD TXT vers MND MégaGest avec validation stricte.
- Parser/writer MND avec roundtrip obligatoire.
- Rapports Markdown et JSON.
- Rapprochement SPD640-P CSV configurable.
- Interface graphique minimale.
- Packaging Windows préparé en paquet portable.
