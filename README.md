# Le Pouletier Intelligence — noyau initial

Agent IA de gestion avicole, conçu pour un accès cloud depuis un téléphone, avec budget initial visé de 0 FCFA.

## Fonctions du prototype
- Assistant conversationnel avec outils métier si une clé Groq est configurée.
- Mode local limité sans clé API.
- Gestion de base des lots, mortalités, stocks, ventes, dépenses et tâches.
- Calcul des besoins d'aliments, du coût de bande et de la synthèse financière.
- Alertes calculées lors de l'ouverture/actualisation de l'application.
- Tests automatisés des calculs et contrôles métier.

## Lancer localement
Python 3.11 recommandé.

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Déployer sur Streamlit Community Cloud
- Dépôt GitHub contenant `app.py`, `requirements.txt`, `agent/` et `tests/`.
- Main file path : `app.py`.
- Ajouter éventuellement `GROQ_API_KEY` dans les paramètres Secrets de Streamlit. Ne jamais enregistrer cette clé dans GitHub.
- `GROQ_MODEL` est facultatif; valeur par défaut dans le code : `llama-3.3-70b-versatile`.

## Exécuter les tests
```bash
pytest -q
```

## Limites importantes
- La base SQLite locale n'est pas garantie persistante sur un hébergement gratuit; connecter une base PostgreSQL hébergée avant d'utiliser ce système comme registre réel.
- Les alertes sont calculées à l'exécution de l'application. Le prototype ne tourne pas en arrière-plan 24/7 et n'envoie pas de SMS/e-mails.
- Les prix, calendriers sanitaires, rendements et règles locales doivent être documentés et validés. Ce prototype n'est pas un substitut à un vétérinaire, à un comptable ou aux autorités compétentes.
- Les actions externes engageantes (paiements, commandes fermes, messages clients) ne sont pas automatisées.
- Une offre gratuite ne garantit ni quotas illimités, ni disponibilité permanente. Vérifier les conditions des services utilisés.

## Structure
```text
app.py
agent/
  __init__.py
  db.py
  tools.py
  orchestrator.py
  system_prompt.md
tests/
  test_tools.py
.streamlit/
  config.toml
requirements.txt
README.md
```

## Sauvegarde et restauration (version 2)

L'onglet **Sauvegarde** permet de télécharger un fichier JSON contenant les lots, stocks, dépenses, ventes, tâches et événements d'alerte, puis de restaurer ce fichier. La restauration remplace les données présentes : télécharger une sauvegarde récente avant toute restauration.

Cette fonction ne transforme pas SQLite en base persistante. Sur un hébergement cloud gratuit, les fichiers locaux peuvent être perdus lors de certains redéploiements ou changements d'environnement. Pour un usage réel, prévoir ensuite une base PostgreSQL distante et des sauvegardes régulières.
