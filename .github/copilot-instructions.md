# Guide de revue du dépôt

- Ce dépôt est un utilitaire Python/Tkinter local pour Windows.
- Pour configurer l'environnement de revue : `python -m pip install -e .`.
- Pour valider : `python scripts/agent_validate.py`.
- Les tests de base ne demandent ni base de données, ni serveur, ni secret.
- Ne pas exiger `VT_API_KEY` sauf pour une publication officielle explicitement demandée.
- Ne jamais ajouter de fichier de paie réel, rapport GL réel, MND réel ou secret.
- Garder les textes visibles par les utilisateurs courts, naturels et en français.
- Le canal public principal est le ZIP portable, pas un `.exe` publié seul.
- Ne pas créer de tag, release, push sur `main` ou soumission VirusTotal sans demande explicite.
- Les noms de branche ne doivent pas contenir `codex`.
