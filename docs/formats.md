# Formats des fichiers

Cette page résume la structure attendue par l'application.

## TXT EmployeurD

Une ligne contient 77 caractères, sans compter la fin de ligne.

| Positions | Longueur | Contenu |
| --- | ---: | --- |
| 1-8 | 8 | Lot EmployeurD |
| 9 | 1 | Espace |
| 10-20 | 11 | Compte GL EmployeurD |
| 21-69 | 49 | Montant |
| 70-77 | 8 | Date, format `AAAAMMJJ` |

Exemple synthétique :

```text
00001234 50213000140                                          2450.0020260618
```

## MND MégaGest

Une ligne MND produite contient 479 caractères, sans compter la fin de ligne `CRLF`.

| Positions | Longueur | Contenu |
| --- | ---: | --- |
| 1 | 1 | Type, toujours `P` |
| 2-11 | 10 | Compte MND |
| 17-22 | 6 | Période `AAAAMM` |
| 53-62 | 10 | Référence |
| 63-70 | 8 | Date `AAAAMMJJ` |
| 71-120 | 50 | Libellé |
| 236-248 | 13 | Débit |
| 250-262 | 13 | Crédit |
| 264-269 | 6 | Lot MND |
| 274-281 | 8 | Date `AAAAMMJJ` |

Les autres positions sont remplies par des espaces.

## Compte

Par défaut, l'application retire le premier chiffre du compte EmployeurD de 11 chiffres.

```text
50213000140 -> 0213000140
```

## Rapports de contrôle

Le rapport recommandé est le PDF original du grand détail de l'écriture GL, tel que généré par EmployeurD. Un PDF scanné, imprimé à nouveau ou modifié peut empêcher la lecture fiable des lignes.

L'application y lit:

- la date d'écriture;
- les lignes de comptes GL;
- le côté débit ou crédit selon la position dans le PDF;
- les sous-totaux;
- le total compagnie.

Le contrôle compare ensuite les totaux débit/crédit et les montants par compte GL avec le TXT EmployeurD, après conversion du compte source de 11 chiffres vers le compte GL/MND de 10 chiffres.
