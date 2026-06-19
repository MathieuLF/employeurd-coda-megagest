# Formats de fichiers

Cette page décrit seulement les champs utilisés par l'application.

## TXT EmployeurD

Une ligne contient 77 caractères, sans compter la fin de ligne.

| Position | Longueur | Contenu |
| --- | ---: | --- |
| 1-8 | 8 | Lot EmployeurD |
| 9 | 1 | Espace |
| 10-20 | 11 | Compte GL EmployeurD |
| 21-69 | 49 | Montant, aligné à droite, négatif si crédit |
| 70-77 | 8 | Date d'écriture, format `AAAAMMJJ` |

Exemple synthétique :

```text
00001234 50213000140                                          1000.0020260618
```

## MND MégaGest

Une ligne MND produite contient 479 caractères, sans compter la fin de ligne `CRLF`.

| Position | Longueur | Contenu |
| --- | ---: | --- |
| 1 | 1 | Type, toujours `P` |
| 2-11 | 10 | Compte MND |
| 12-16 | 5 | Espaces |
| 17-22 | 6 | Période, format `AAAAMM` |
| 23-52 | 30 | Espaces |
| 53-62 | 10 | Référence |
| 63-70 | 8 | Date, format `AAAAMMJJ` |
| 71-120 | 50 | Libellé source |
| 121-235 | 115 | Champ auxiliaire |
| 236-248 | 13 | Débit, format `0000000000.00` |
| 249 | 1 | Espace |
| 250-262 | 13 | Crédit, format `0000000000.00` |
| 263 | 1 | Espace |
| 264-269 | 6 | Lot MND |
| 270-273 | 4 | Espaces |
| 274-281 | 8 | Date 2, format `AAAAMMJJ` |
| 282-479 | 198 | Espaces |

## Conversion du compte

Par défaut, l'application retire le premier chiffre du compte EmployeurD de 11 chiffres pour produire le compte MND de 10 chiffres.

Exemple :

```text
50213000140 -> 0213000140
```
