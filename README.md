# employeurd-coda-megagest

Convertisseur en cours de developpement pour preparer des ecritures de paie EmployeurD en fichier d'import `.mnd` compatible avec le flux attendu par MegaGest.

## Etat du projet

Le format exact du fichier `.mnd` doit etre confirme avec un exemple valide ou une specification d'import COBA. Le convertisseur est donc bati autour d'un mapping configurable plutot que d'un format fige.

## Utilisation locale

```powershell
python convert.py inspect samples/employeurd-example.csv
python convert.py convert samples/employeurd-example.csv outputs/paie.mnd --mapping config/mapping.example.json
```

## Donnees attendues

Le premier format supporte est un fichier CSV ou TXT avec en-tetes. Les fichiers Excel doivent etre exportes en CSV avant conversion.

Champs usuels a mapper:

- date d'ecriture;
- code de journal;
- compte comptable;
- description;
- reference;
- debit;
- credit.

La disposition finale du `.mnd` sera ajustee lorsque le format d'import cible sera confirme.
