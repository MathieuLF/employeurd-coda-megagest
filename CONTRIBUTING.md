# Contribuer

Les contributions sont les bienvenues, avec une règle simple : aucune donnée de paie réelle ne doit se retrouver dans le dépôt ou dans une demande publique.

## Données d'exemple

Utilisez seulement des données synthétiques dans les fichiers partagés, les captures d'écran et les billets GitHub.

Il est possible de tester l'application localement avec ses propres fichiers, mais ces fichiers doivent rester sur votre poste.

## Avant de proposer un changement

```powershell
python -m pip install -e .
python scripts/agent_validate.py
```

Ces commandes ne demandent ni base de données, ni serveur, ni clé secrète. `VT_API_KEY` sert seulement à une publication officielle.

## À garder en tête

- Le MND ne doit pas être créé si une validation bloquante échoue.
- Le PDF original du grand détail GL est le rapport de contrôle attendu.
- Les textes visibles par les utilisateurs doivent rester courts et naturels.
