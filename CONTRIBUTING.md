# Contribution

Merci de contribuer avec prudence. Ce projet manipule des écritures de paie, même si les fichiers du dépôt doivent rester fictifs.

## Données réelles

Il est permis de tester l'application localement avec ses propres fichiers, sur son propre poste.

Par contre, il ne faut jamais publier de données réelles :

- dans le dépôt Git;
- dans une demande GitHub;
- dans une demande de fusion;
- dans une capture d'écran;
- dans une mise en ligne GitHub;
- dans un service externe de diagnostic.

Utiliser seulement des données d'exemple synthétiques dans les fichiers partagés.

## Avant une demande de fusion

```powershell
python -m unittest discover -s tests
python -m compileall src scripts
python scripts/audit_release_readiness.py --version 0.1.0
```

## À garder en tête

- Le MND ne doit pas être créé si une validation bloquante échoue.
- Un rapport SPD640-P peut aider à confirmer les totaux, mais il reste optionnel.
- Un autre compte GL n'est pas un problème en soi si l'écriture demeure valide.
- Les textes destinés aux utilisateurs doivent rester courts, clairs et naturels.
