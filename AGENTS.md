# Guide de contribution automatisée

## Environnement rapide

- Python 3.12 ou plus récent suffit pour les tests et les revues de code.
- Aucune base de données, aucun serveur et aucune clé secrète ne sont requis pour la validation courante.
- `VT_API_KEY` sert seulement à une publication officielle avec VirusTotal; ne pas l'exiger pour une revue.
- Les fichiers de test dans `samples/` sont synthétiques. Ne jamais ajouter de fichier de paie réel, SPD réel, MND réel ou secret.

```powershell
python -m pip install --upgrade pip
python -m pip install -e .
python scripts/agent_validate.py
```

## Validation utile

- Validation complète courte : `python scripts/agent_validate.py`
- Tests seulement : `python -m unittest discover -s tests`
- Compilation seulement : `python -X pycache_prefix=build/pycache -m compileall src scripts`
- Audit release : `python scripts/audit_release_readiness.py --version <version>`

## Règles de contribution

- Garder les textes utilisateurs courts, naturels et en français.
- Le canal public principal est le ZIP portable `EmployeurD-MegaGest-v*-portable.zip`.
- Ne pas publier de release, créer de tag, pousser sur `main` ou soumettre à VirusTotal sans demande explicite.
- Les noms de branche ne doivent pas contenir `codex`.
- Pour une revue de code, prioriser les bogues, régressions, risques de publication et tests manquants.
