# Sécurité

L'application travaille localement. Les fichiers de paie ne doivent jamais être publiés dans GitHub, joints à un billet public ou envoyés à un service externe.

## À ne pas publier

- TXT EmployeurD réel;
- rapport SPD réel;
- fichier MND réel;
- rapport Markdown ou JSON issu d'une paie réelle;
- capture contenant des données sensibles;
- fichier `.env`, clé, jeton, certificat ou mot de passe.

## Versions officielles

Téléchargez l'application depuis la page officielle des versions GitHub.

Chaque version publique doit fournir les empreintes SHA256. Le paquet Windows officiel est un ZIP portable accompagné d'un manifeste de mise en ligne et d'un rapport VirusTotal sur l'exécutable public.

Aucun certificat de signature payant n'est utilisé. SmartScreen peut donc afficher un avertissement d'application non reconnue.

La fenêtre `Sécurité` de l'application permet de comparer l'empreinte de la version ouverte avec l'empreinte publiée.

## Signaler un problème

Pour une vulnérabilité, utilisez le signalement privé GitHub lorsque disponible.

Contact direct : services@mathieu.pro
