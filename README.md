# LeadCompass

Assistant d'aide à la décision commerciale pour la prospection : recherche et résumé de prospect, score de pertinence, rédaction d'emails (premier contact / relance / réponse) et découverte de nouveaux contacts, branché sur HubSpot.

Le cœur de métier n'est pas codé en dur : un **profil entreprise** (`config/business_profile.yaml`, non versionné) décrit votre produit, votre client cible et votre grille de score. LeadCompass s'adapte à n'importe quelle activité à partir de ce fichier — et peut le générer ou le mettre à jour lui-même à partir de vos documents (voir ci-dessous).

## Fonctionnement

1. Vous cherchez un prospect existant dans HubSpot depuis l'interface.
2. LeadCompass récupère sa fiche + l'historique des échanges (notes, emails) via l'API HubSpot.
3. À la demande, vous générez :
   - un **résumé** du prospect (HubSpot + recherche web),
   - un **score de pertinence** selon votre grille de critères,
   - un **brouillon d'email**, avec une option pour comparer les suggestions de tous les modèles enregistrés.
4. Ce que vous validez est enregistré dans HubSpot : score/classification en propriétés personnalisées, résumé et emails retenus en notes. Rien n'est envoyé ni écrit automatiquement — vous restez dans la boucle.
5. Sur la page **Découverte**, une description libre (« influenceurs LinkedIn sur la data B2B », « festivals de jazz en Bretagne »...) guide une recherche web menée par le modèle sélectionné, qui propose des contacts réels et sourcés (nom, organisation, rôle, email public, source, pertinence). Chaque résultat peut être ajouté à HubSpot en un clic, avec une note retraçant la recherche.

Toutes les tâches IA utilisent le **modèle sélectionné dans le sélecteur en haut de l'application**. Les modèles disponibles y sont ceux enregistrés sur la page **Paramètres** (section « Modèles IA ») : chaque entrée nomme un binaire CLI compatible Claude Code (`claude`, ou un wrapper tel que `claude-zai` pour les modèles GLM de Z.ai) et n'apparaît dans le sélecteur que si le binaire est détecté. Le choix par défaut est mémorisé dans `config/settings.yaml` (non versionné), tout comme la liste des modèles.

## Prérequis

- Python 3.11+
- [Claude Code CLI](https://code.claude.com/docs) installé et connecté (`claude auth login`) — utilisé en mode headless (`claude -p`), sans coût API additionnel si vous avez un abonnement Claude.
- Autres modèles (optionnel) : n'importe quel binaire CLI compatible Claude Code. Exemple pour les modèles GLM de [Z.ai](https://z.ai) : un wrapper `claude-zai` qui exporte `ANTHROPIC_BASE_URL=https://api.z.ai/api/anthropic` et votre clé Z.ai avant d'appeler `claude`. Enregistrez-le ensuite sur la page Paramètres (section « Modèles IA »).
- Une Private App HubSpot avec les scopes :
  - `crm.objects.contacts.read`, `crm.objects.contacts.write`
  - `crm.objects.notes.write` (ou l'équivalent engagements selon votre compte)
  - `sales-email-read` (pour lire le contenu des emails déjà logués)

## Installation

```bash
uv sync                # environnement .venv + dépendances (--extra dev pour ajouter ruff)

cp .env.example .env
# renseignez HUBSPOT_TOKEN dans .env

cp config/business_profile.example.yaml config/business_profile.yaml
# ou laissez ce fichier de côté et remplissez le profil depuis la page Paramètres de l'app
```

## Lancement

```bash
streamlit run app.py
```

Rendez-vous d'abord sur la page **Paramètres** pour renseigner le profil de votre entreprise (produit, client cible, grille de score) avant d'utiliser l'outil sur un vrai prospect.

### Génération automatique du profil depuis vos documents

Plutôt que de remplir le formulaire à la main, la page Paramètres permet de donner un ou plusieurs chemins de dossiers (documentation produit, présentations, site exporté...) : le modèle sélectionné les explore et propose une description de l'entreprise et une grille de score adaptées, que vous relisez et ajustez avant d'enregistrer. Relancer l'analyse plus tard affine le profil existant plutôt que de repartir de zéro.

Cette exploration tourne en lecture seule et confinée : le CLI est lancé avec `--restricted` (pas de Bash, pas d'exécution de code, pas de récupération web) et `--allowedTools Read Glob Grep` limité aux dossiers passés en `--add-dir` — le modèle ne peut rien modifier ni lire en dehors des chemins fournis.

## Architecture

```
leadcompass/
├── config.py                    # chargement du .env et du profil entreprise
├── contact_context.py            # mise en forme du contexte prospect (fiche + historique)
├── hubspot_client.py              # lecture/écriture HubSpot (contacts, engagements, notes, propriétés)
├── llm/
│   ├── base.py                    # interface commune aux backends (generate(system, user) -> str)
│   ├── claude_cli.py               # backend générique : un CLI compatible Claude Code en sous-processus
│   └── registry.py                 # modèles enregistrés, détection des binaires, backend par défaut
└── tasks/
    ├── prompts.py                   # construction des prompts à partir du profil entreprise
    ├── research.py                  # résumé de prospect
    ├── scoring.py                    # score de pertinence
    ├── drafting.py                    # rédaction d'emails, avec comparaison multi-modèles
    ├── discovery.py                   # recherche guidée de nouveaux contacts (prospects, influenceurs...)
    └── profile_generation.py          # génération du profil entreprise depuis des dossiers
tests/                                  # tests unitaires (unittest, sans dépendance réseau)
```

## Développement

```bash
uv sync --extra dev

python -m unittest discover -s tests   # tests unitaires
ruff check .                            # lint
ruff format .                           # formatage
```

Le CI (GitHub Actions) fait tourner ces trois commandes à chaque push/PR.

## Limitations connues

- L'intégration HubSpot (lecture des engagements, création de notes) s'appuie sur les endpoints documentés de l'API v3/v4 ; les tests unitaires mockent les appels HTTP mais n'ont pas pu être vérifiés contre un vrai compte — à valider à la première utilisation, notamment si votre compte utilise des types d'association personnalisés.
- La recherche web (résumés, découverte) ne fonctionne que si le CLI du modèle sélectionné y a accès sans prompt d'autorisation interactif ; vérifiez votre configuration de permissions (`claude config` / réglages de permissions du CLI) si les résultats semblent se limiter aux seules données HubSpot.

## Licence

MIT — voir [LICENSE](LICENSE).
