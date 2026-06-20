# Contribuer

Les contributions sont les bienvenues, avec une règle simple : aucune donnée de paie réelle ne doit se retrouver dans le dépôt ou dans une demande publique.

## Données d'exemple

Utilisez seulement des données synthétiques dans les fichiers partagés, les captures d'écran et les billets GitHub.

Il est possible de tester l'application localement avec ses propres fichiers, mais ces fichiers doivent rester sur votre poste.

## Avant de proposer un changement

```powershell
python -m unittest discover -s tests
python -m compileall src scripts
python scripts/audit_release_readiness.py --version 0.1.0
```

## À garder en tête

- Le MND ne doit pas être créé si une validation bloquante échoue.
- Le rapport SPD640-P aide à confirmer les totaux, mais il reste optionnel.
- Les textes visibles par les utilisateurs doivent rester courts et naturels.
