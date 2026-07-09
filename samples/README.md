# Données synthétiques

Ces fichiers sont fictifs et servent seulement aux tests locaux. Ils ne doivent
pas être remplacés par des fichiers de paie, SPD ou MND réels.

## Scénarios

- `employeurd-balanced.txt`: 20 lignes, un lot, une date, débit et crédit de
  `6643.00`.
- `OPD_RP_00001234_SPD640-P_SYNTHETIQUE.CSV`: rapport SPD640-P théorique qui
  couvre des gains, des retenues, des montants employeur, une banque de
  vacances avec le code `305` et une ligne de banque non retenue par la formule
  de contrôle.
- Les tests du grand détail GL génèrent un PDF synthétique temporaire à partir
  des fichiers TXT fictifs. Aucun PDF de paie réel n'est conservé dans le dépôt.
- `employeurd-unbalanced.txt`: écart volontaire de `10.50` du côté du crédit.
- `employeurd-unknown-account.txt`: comptes GL fictifs hors du plan connu, mais
  fichier équilibré pour le mode permissif.
- `employeurd-zero-amount.txt`: lignes à montant zéro, conservées pour vérifier
  la lecture et le rapprochement, mais invalides si `reject_zero_amount_lines`
  est actif.

## Totaux de référence

La formule SPD640-P configurée additionne:

- `TYPE=G / MONTANTS`
- `TYPE=D / MNTS/EMPLOYEUR`
- `TYPE=G / CODE=305 / MNTS BANQUE`

Pour le scénario principal: `6200.00 + 330.75 + 112.25 = 6643.00`.
