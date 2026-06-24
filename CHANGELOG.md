# Journal des changements

Toutes les versions officielles publiées sur GitHub doivent reprendre la section de version correspondante.

## [Non publié]

## [0.1.3] - 2026-06-24

- Corrige la vérification de signature Windows pour éviter l'interpolation de chemins dans PowerShell lors du contrôle Authenticode.
- Respecte la préférence de vérification de mise à jour au démarrage et ignore les vérifications silencieuses vers un canal personnalisé.
- Publie et vérifie l'empreinte SHA256 du paquet applicatif complet avec le manifeste de mise en ligne.
- Durcit l'audit de mise en ligne pour limiter l'exception de fichiers d'exemple suivis à `.env.example` seulement.
- Ajoute des instructions de première ouverture Windows pour expliquer SmartScreen et l'absence de signature numérique.
- Ajoute le bouton officiel Sponsor GitHub dans l'application, le README et le microsite.
- Raffine les exemples synthétiques, la documentation des échantillons et la présentation publique des téléchargements.

## [0.1.2] - 2026-06-21

- Mise en ligne officielle recentrée sur le ZIP portable, avec garde-fous contre les doublons de release et les assets .exe directs.
- Vérification de version silencieuse au démarrage, journal plus lisible avec lien de mise à jour cliquable, et badge Sécurité OK explicité.
- Microsite public clarifié pour présenter le ZIP portable, les empreintes et le rapport VirusTotal sans surcharger l'utilisateur.
- Environnement de revue simplifié autour de Python 3.12 et d'une commande de validation unique.
## [0.1.1] - 2026-06-21

- Retrait du rapport sécurité Markdown distinct des fichiers joints aux mises en ligne; les informations utiles restent dans les notes, le manifeste JSON et le rapport VirusTotal.
- Vérification de version plus rapide et robuste au premier lancement, même sans dossier local de préférences.
- Fallback léger vers GitHub Releases quand l'API répond lentement ou en 504, avec timeouts courts et messages hors ligne clairs.
- Garde-fous GUI contre les vérifications concurrentes et les réseaux qui répondent trop lentement.

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
