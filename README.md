# LeadCompass

Assistant d'aide à la décision commerciale pour la prospection : recherche et résumé de prospect, score de pertinence, et rédaction d'emails (premier contact / relance / réponse), branché sur HubSpot.

Le cœur de métier n'est pas codé en dur : un **profil entreprise** (`config/business_profile.yaml`, non versionné) décrit votre produit, votre client cible et votre grille de score. LeadCompass s'adapte à n'importe quelle activité à partir de ce fichier.

## Fonctionnement

1. Vous cherchez un prospect existant dans HubSpot depuis l'interface.
2. LeadCompass récupère sa fiche + l'historique des échanges (notes, emails) via l'API HubSpot.
3. À la demande, vous générez :
   - un **résumé** du prospect (HubSpot + recherche web, via Claude),
   - un **score de pertinence** selon votre grille de critères (via Claude),
   - un **brouillon d'email**, avec une option pour comparer les suggestions de plusieurs modèles (Claude et GLM).
4. Ce que vous validez est enregistré dans HubSpot : score/classification en propriétés personnalisées, résumé et emails retenus en notes. Rien n'est envoyé ni écrit automatiquement — vous restez dans la boucle.

## Prérequis

- Python 3.11+
- [Claude Code CLI](https://code.claude.com/docs) installé et connecté (`claude auth login`) — utilisé en mode headless (`claude -p`), sans coût API additionnel si vous avez un abonnement Claude.
- Un compte [Z.ai](https://z.ai) avec une clé API (backend GLM, utilisé uniquement pour la comparaison lors de la rédaction).
- Une Private App HubSpot avec les scopes :
  - `crm.objects.contacts.read`, `crm.objects.contacts.write`
  - `crm.objects.notes.write` (ou l'équivalent engagements selon votre compte)
  - `sales-email-read` (pour lire le contenu des emails déjà logués)

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# renseignez HUBSPOT_TOKEN et ZAI_API_KEY dans .env

cp config/business_profile.example.yaml config/business_profile.yaml
# ou laissez ce fichier de côté et remplissez le profil depuis la page Paramètres de l'app
```

## Lancement

```bash
streamlit run app.py
```

Rendez-vous d'abord sur la page **Paramètres** pour renseigner le profil de votre entreprise (produit, client cible, grille de score) avant d'utiliser l'outil sur un vrai prospect.

## Architecture

```
leadcompass/
├── config.py           # chargement du .env et du profil entreprise
├── hubspot_client.py    # lecture/écriture HubSpot (contacts, engagements, notes, propriétés)
├── llm/
│   ├── base.py          # interface commune aux backends (generate(system, user) -> str)
│   ├── claude_cli.py     # backend Claude via le CLI en sous-processus
│   └── glm.py            # backend GLM via le SDK anthropic pointé sur l'endpoint Z.ai
└── tasks/
    ├── prompts.py         # construction des prompts à partir du profil entreprise
    ├── research.py        # résumé de prospect
    ├── scoring.py          # score de pertinence
    └── drafting.py          # rédaction d'emails, avec comparaison multi-modèles
```

## Limitations connues

- L'intégration HubSpot (lecture des engagements, création de notes) s'appuie sur les endpoints documentés de l'API v3/v4 mais n'a pas encore été testée contre un vrai compte — à valider/ajuster à la première utilisation, notamment si votre compte utilise des types d'association personnalisés.
- Le backend Claude ne dispose de recherche web que si le CLI y a accès sans prompt d'autorisation interactif ; vérifiez votre configuration de permissions (`claude config` / réglages de permissions du CLI) si les résumés semblent se limiter aux seules données HubSpot.
- Pas de suite de tests pour l'instant.

## Licence

MIT — voir [LICENSE](LICENSE).
