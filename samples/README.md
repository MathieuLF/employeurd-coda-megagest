# Donnees synthetiques

Ces fichiers sont fictifs et servent seulement aux tests locaux. Ils ne doivent
pas etre remplaces par des fichiers de paie, SPD ou MND reels.

## Scenarios

- `employeurd-balanced.txt`: 20 lignes, un lot, une date, debit et credit de
  `6643.00`.
- `OPD_RP_00001234_SPD640-P_SYNTHETIQUE.CSV`: rapport SPD640-P theorique qui
  couvre des gains, retenues, montants employeur, banque vacances code `305` et
  une banque non retenue par la formule de controle.
- `employeurd-unbalanced.txt`: ecart volontaire de `10.50` cote credit.
- `employeurd-unknown-account.txt`: comptes GL fictifs hors plan connu, mais
  fichier equilibre pour le mode permissif.
- `employeurd-zero-amount.txt`: lignes a montant zero, conservees pour verifier
  la lecture et le rapprochement, mais invalides si `reject_zero_amount_lines`
  est actif.

## Totaux de reference

La formule SPD640-P configuree additionne:

- `TYPE=G / MONTANTS`
- `TYPE=D / MNTS/EMPLOYEUR`
- `TYPE=G / CODE=305 / MNTS BANQUE`

Pour le scenario principal: `6200.00 + 330.75 + 112.25 = 6643.00`.
