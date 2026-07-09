# Sécurité

L'application travaille localement. Les fichiers de paie ne doivent jamais être publiés dans GitHub, joints à un billet public ou envoyés à un service externe.

## À ne pas publier

- TXT EmployeurD réel;
- PDF grand détail GL réel;
- rapport SPD réel;
- fichier MND réel;
- rapport Markdown ou JSON issu d'une paie réelle;
- capture contenant des données sensibles;
- fichier `.env`, clé, jeton, certificat ou mot de passe.

## Versions officielles

Téléchargez l'application depuis la page officielle des versions GitHub.

Chaque version publique doit fournir les empreintes SHA256. Le paquet Windows officiel est un ZIP portable accompagné d'un manifeste de mise en ligne et d'un rapport VirusTotal sur l'exécutable public seulement.

Aucun certificat de signature payant n'est utilisé. SmartScreen peut donc afficher un avertissement de sécurité ou d'application non reconnue au premier lancement.

Si le fichier provient bien de la page officielle GitHub Releases, ouvrez `Informations complémentaires`, puis choisissez `Exécuter quand même`. Ce message s'affiche parce que l'application n'est pas signée numériquement, pas parce qu'elle transmet des fichiers de paie.

La fenêtre `Sécurité` de l'application permet de comparer l'empreinte de la version ouverte avec l'empreinte publiée.

## Signaler un problème

Pour une vulnérabilité, utilisez le signalement privé GitHub lorsque disponible.

Contact direct : services@mathieu.pro
