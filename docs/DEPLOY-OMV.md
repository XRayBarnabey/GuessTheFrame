# 🐳 Déploiement sur OMV / Debian 10 avec Docker

Ce guide est adapté à un serveur **OpenMediaVault / Debian 10 (buster)** avec **Docker Engine 25+**, une machine x86_64 et Docker Compose v2.

> GuessTheFrame est léger : un conteneur applicatif (Python/FastAPI + frontend compilé + FFmpeg) et un conteneur PostgreSQL. Une machine x86_64 avec 2 cœurs et 2 Go de RAM suffit ; ton serveur OMV est largement au-dessus.

---

## 1. Vérifier Docker Compose

```bash
docker compose version
```

Tu dois voir une version **v2.x**. Si la commande n'existe pas :

```bash
apt-get update
apt-get install -y curl git
apt-get install -y docker-compose-plugin
```

Si le paquet n'est pas disponible sur ton dépôt Debian 10, installe le binaire Compose v2 :

```bash
mkdir -p /usr/local/lib/docker/cli-plugins
curl -SL https://github.com/docker/compose/releases/download/v2.29.7/docker-compose-linux-x86_64 \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
docker compose version
```

---

## 2. Installer l'application

```bash
mkdir -p /srv/guesstheframe
cd /srv/guesstheframe
git clone https://github.com/XRayBarnabey/GuessTheFrame.git .
```

Si le dossier n'est pas vide :

```bash
cd /srv/guesstheframe
git pull
```

---

## 3. Générer la configuration

```bash
cd /srv/guesstheframe
cp .env.example .env

FERNET=$(openssl rand -base64 32 | tr '+/' '-_')
SETUP=$(openssl rand -hex 32)
PGPASS=$(openssl rand -hex 24)

sed -i "s|^GTF_ENCRYPTION_KEY=.*|GTF_ENCRYPTION_KEY=$FERNET|" .env
sed -i "s|^GTF_SETUP_TOKEN=.*|GTF_SETUP_TOKEN=$SETUP|" .env
sed -i "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$PGPASS|" .env
```

Vérifie ensuite les valeurs importantes :

```bash
nano .env
```

```dotenv
# Accès HTTP direct pour le premier test
GTF_PUBLIC_URL=http://<IP_DU_SERVEUR>:8000
GTF_HTTP_PORT=8000
GTF_SESSION_COOKIE_SECURE=false

# Compte(s) Emby administrateur(s)
GTF_ADMIN_EMBY_USERNAMES=admin

# Préremplissage de l'écran de setup
GTF_EMBY_URL=http://<IP_EMBY>:8096
```

Remplace :

- `<IP_DU_SERVEUR>` par l'IP LAN de la machine OMV ;
- `<IP_EMBY>` par l'IP du serveur Emby.

> **Emby sur la même machine ?** Utilise son IP LAN, par exemple `http://192.168.1.50:8096`, ou `http://host.docker.internal:8096`. N'utilise pas `http://localhost:8096` : dans un conteneur, `localhost` désigne le conteneur lui-même.

Pour connaître le jeton d'installation :

```bash
grep GTF_SETUP_TOKEN .env
```

---

## 4. Démarrer

```bash
cd /srv/guesstheframe
docker compose up -d --build
docker compose ps
docker compose logs -f app
```

Le premier build peut prendre quelques minutes. Le conteneur applicatif inclut **FFmpeg** : aucune installation sur l'hôte n'est nécessaire.

Vérifier la santé :

```bash
curl -fsS http://127.0.0.1:8000/api/health
```

Résultat attendu :

```json
{"status":"ok","app":"GuessTheFrame","version":"1.0.0",...}
```

---

## 5. Configurer l'application

Ouvre :

```text
http://<IP_DU_SERVEUR>:8000/setup
```

Renseigne :

1. l'adresse Emby, par exemple `http://<IP_EMBY>:8096` ;
2. la clé API Emby ;
3. le jeton d'installation affiché par `grep GTF_SETUP_TOKEN .env` ;
4. la vérification TLS si nécessaire.

Puis :

1. **Tester** la connexion ;
2. **Enregistrer** ;
3. se connecter avec un compte Emby ;
4. ouvrir **Administration → Actualiser le catalogue** pour lancer la première synchronisation.

La synchronisation automatique suivante aura lieu **tous les jours à 12:00 (heure de Paris)**.

---

## 6. Passer en HTTPS

En HTTP direct, `GTF_SESSION_COOKIE_SECURE` doit rester à `false`, sinon le navigateur refuse le cookie de session et la connexion boucle.

Pour la production, place l'application derrière un reverse proxy TLS (Nginx Proxy Manager, SWAG, Caddy, Traefik, Nginx…).

Exemple Nginx :

```nginx
server {
    listen 443 ssl http2;
    server_name gtf.example.com;

    ssl_certificate     /etc/letsencrypt/live/gtf.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/gtf.example.com/privkey.pem;

    client_max_body_size 10m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Puis dans `.env` :

```dotenv
GTF_PUBLIC_URL=https://gtf.example.com
GTF_SESSION_COOKIE_SECURE=true
```

Redémarre :

```bash
docker compose up -d
```

---

## 7. Sauvegardes

Les données sont dans des volumes Docker nommés. Repère leurs noms :

```bash
docker volume ls | grep gtf
```

Exemple de sauvegarde :

```bash
mkdir -p /srv/backups/guesstheframe
cd /srv/guesstheframe

# PostgreSQL
docker compose exec -T db pg_dump -U gtf -d gtf \
  | gzip > /srv/backups/guesstheframe/gtf-$(date +%F).sql.gz

# Données applicatives et cache
docker run --rm \
  -v guesstheframe_gtf_data:/data \
  -v /srv/backups/guesstheframe:/backup \
  alpine tar czf /backup/data-$(date +%F).tar.gz -C /data .
```

> Le préfixe `guesstheframe_` dépend du nom du dossier / projet Compose. Vérifie avec `docker volume ls`.

Restauration PostgreSQL :

```bash
gunzip -c /srv/backups/guesstheframe/gtf-2026-01-01.sql.gz \
  | docker compose exec -T db psql -U gtf -d gtf
```

---

## 8. Mettre à jour

```bash
cd /srv/guesstheframe
docker compose exec -T db pg_dump -U gtf -d gtf \
  | gzip > /srv/backups/guesstheframe/gtf-avant-maj-$(date +%F-%H%M).sql.gz

git pull
docker compose build app
docker compose up -d app
docker compose logs -f app
```

Les migrations Alembic sont appliquées automatiquement au démarrage.

---

## 9. Diagnostic rapide

```bash
# État des conteneurs
docker compose ps

# Logs applicatifs
docker compose logs --tail=150 app

# Logs PostgreSQL
docker compose logs --tail=100 db

# Santé de l'API
curl -fsS http://127.0.0.1:8000/api/health

# Espace disque Docker
df -h /var/lib/docker

# Port 8000 déjà utilisé ?
ss -ltnp | grep ':8000' || true
```

Si le port `8000` est occupé, change `GTF_HTTP_PORT=8080` dans `.env` et adapte `GTF_PUBLIC_URL`, puis :

```bash
docker compose up -d
```

---

## 10. Problèmes fréquents

| Problème | Cause / solution |
| --- | --- |
| `docker compose` introuvable | Installer le plugin Compose v2 (section 1). |
| Le build échoue | Relancer `docker compose build --no-cache`. Vérifier l'espace disque. |
| `ENCRYPTION_NOT_CONFIGURED` | `GTF_ENCRYPTION_KEY` est vide ou invalide dans `.env`. Régénérer la clé. |
| `value too long for type character varying(64)` | Mettre à jour l'image : `git pull && docker compose up -d --build`. La migration `8ed256215496` élargit `media_items.poster_tag`. |
| Connexion qui boucle en HTTP | Passer `GTF_SESSION_COOKIE_SECURE=false` pour le test HTTP, ou utiliser HTTPS. |
| Emby injoignable depuis le conteneur | Utiliser l'IP LAN d'Emby ou `host.docker.internal`, jamais `localhost`. |
| Aucune frame | Vérifier les logs `app`, la clé API Emby et l'accès au flux vidéo. |
| Contenu supprimé encore présent | **Administration → Actualiser le catalogue** ou attendre 12:00. |
| Base inaccessible après redémarrage | `docker compose ps` puis `docker compose logs db`. Le healthcheck attend PostgreSQL. |
| `POSTGRES_PASSWORD` avec caractères spéciaux | Utiliser un mot de passe hexadécimal (`openssl rand -hex 24`) pour éviter les problèmes d'URL. |

---

## 11. Commandes utiles

```bash
# Démarrer
docker compose up -d

# Arrêter
docker compose down

# Redémarrer l'application
docker compose restart app

# Voir l'utilisation
docker stats --no-stream

# Purger les logs applicatifs (ils sont limités à 10 Mo × 3)
docker compose logs --tail=0 -f app
```

---

**GuessTheFrame v1.0.0** — bon quiz !
