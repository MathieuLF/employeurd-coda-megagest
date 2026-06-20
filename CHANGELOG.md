# Journal des changements

Toutes les versions officielles publiées sur GitHub doivent reprendre la section de version correspondante.

## [Non publié]

- Retrait du rapport sécurité Markdown distinct des fichiers joints aux mises en ligne; les informations utiles restent dans les notes, le manifeste JSON et le rapport VirusTotal.

## [0.1.0] - 2026-06-20

- Conversion EmployeurD TXT vers MND MégaGest avec validation stricte.
- Parser/writer MND avec roundtrip obligatoire.
- Rapports Markdown et JSON.
- Rapprochement SPD640-P CSV configurable.
- Interface Windows modernisée pour le choix des fichiers, la vérification et la génération du MND.
- Journal de conversion avec résumé de validation, résumé de génération et messages lisibles.
- Rapports Markdown et JSON optionnels, avec les résultats toujours visibles dans l'application.
- Sorties créées dans un dossier horodaté, avec nommage basé sur l'écriture de paie.
- Vérification des totaux du MND avec les données source et le rapport SPD640-P lorsqu'il est fourni.
- Microsite public, README simplifié, guide utilisateur, formats, support, sécurité et mentions légales.
- Licence MIT.
- Vérification d'intégrité de la version ouverte par comparaison SHA256 avec GitHub Releases.
- Paquet Windows portable généré avec cx_Freeze.
- Icône produit financière pour l'application, l'exécutable et le microsite.
- Workflows GitHub pour les tests, CodeQL, Dependabot et la préparation des mises en ligne.
- Manifeste JSON de mise en ligne avec empreintes SHA256, statut VirusTotal et statut Authenticode.
- Rapport VirusTotal joint à chaque mise en ligne officielle.
- Audit local pour bloquer les secrets, fichiers générés, certificats, outputs et dossiers privés suivis par erreur.
