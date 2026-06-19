# EmployeurD-MegaGest

EmployeurD-MegaGest est un utilitaire Windows local qui transforme une écriture détaillée EmployeurD au format TXT en fichier `.mnd` destiné à MégaGest.

Il sert à préparer un import comptable de paie, avec des validations visibles avant de créer le fichier final.

## À quoi ça sert

- Lire l'écriture détaillée EmployeurD standard au format TXT.
- Créer un fichier MND prêt à tester dans MégaGest.
- Comparer les totaux débit/crédit du MND avec ceux du fichier source.
- Comparer aussi les totaux avec le rapport SPD640-P CSV, si ce rapport est fourni.
- Produire au besoin un résumé Markdown et un fichier JSON de validation.

Le traitement se fait sur l'ordinateur de l'utilisateur. Aucun fichier de paie n'est envoyé par l'application.

## Utilisation

1. Télécharger l'exécutable depuis les versions officielles publiées sur GitHub.
2. Ouvrir `EmployeurD-MegaGest.exe`.
3. Ajouter l'écriture détaillée EmployeurD au format TXT.
4. Ajouter le rapport SPD640-P au format CSV si vous voulez corroborer les totaux.
5. Cliquer sur `Vérifier la paie`.
6. Si tout est conforme, cliquer sur `Créer le MND`.
7. Tester le fichier MND dans MégaGest hors production avant toute utilisation réelle.

Sans dossier de sortie choisi, l'application utilise le dossier Documents et crée un sous-dossier horodaté.

Les exécutables publics sont publiés seulement après les vérifications de sécurité prévues.

## Aperçu

Le microsite de présentation est disponible dans [docs/index.html](docs/index.html).

Les captures d'écran versionnées sont conservées dans [docs/assets/screenshots](docs/assets/screenshots).

## Données d'exemple

Les fichiers dans [samples](samples) sont synthétiques et peuvent être suivis dans Git. Ils servent aux tests, à la démonstration et à la documentation.

Aucun fichier de paie réel ne doit être ajouté au dépôt, joint à un billet GitHub ou transmis à un service externe.

## Support

Pour un problème ou une amélioration, privilégiez l'ouverture d'un billet GitHub.

Pour un contact direct : services@mathieu.pro

Ne joignez jamais de fichier TXT EmployeurD réel, de rapport SPD réel, de MND réel, de rapport Markdown, de JSON de validation ou de capture contenant des données sensibles.

## Documents utiles

- [Guide rapide](docs/guide_utilisateur.md)
- [Formats TXT et MND](docs/formats.md)
- [Sécurité](SECURITY.md)
- [Mentions légales](docs/mentions_legales.md)

## Licence

Le code est publié sous licence [MIT](LICENSE).

## Mentions légales

EmployeurD, PG Solutions, MégaGest et les autres marques citées appartiennent à leurs propriétaires respectifs. Ce projet n'est pas affilié, approuvé, commandité ni garanti par ces propriétaires.
