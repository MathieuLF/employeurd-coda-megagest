# Données synthétiques

Ces fichiers sont fictifs et servent seulement aux tests locaux. Ils ne doivent
pas être remplacés par des fichiers de paie, PDF GL ou MND réels.

## Scénarios

- `employeurd-balanced.txt`: 20 lignes, un lot, une date, débit et crédit de
  `6643.00`.
- Les tests du grand détail GL génèrent un PDF synthétique temporaire à partir
  des fichiers TXT fictifs. Aucun PDF de paie réel n'est conservé dans le dépôt.
- `employeurd-unbalanced.txt`: écart volontaire de `10.50` du côté du crédit.
- `employeurd-unknown-account.txt`: comptes GL fictifs hors du plan connu, mais
  fichier équilibré pour le mode permissif.
- `employeurd-zero-amount.txt`: lignes à montant zéro, conservées pour vérifier
  la lecture et le rapprochement, mais invalides si `reject_zero_amount_lines`
  est actif.

## Totaux de référence

Pour le scénario principal: débit `6643.00` et crédit `6643.00`.
