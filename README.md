# Archiv

Eine schlanke Dokumentenablage auf Basis von [paperless-ngx](https://github.com/paperless-ngx/paperless-ngx).
Nur das Wesentliche: Dokumente hochladen, per OCR lesbar machen, automatisch mit Tags versehen, suchen.

**Bewusst entfernt:** E-Mail-Import, Workflows, Share-Links, Custom Fields, KI/LLM, Websockets,
Redis, Postgres/MariaDB, MFA/Social-Login und die komplette Angular-Oberfläche.

## Installation mit Portainer

Du brauchst nichts selbst zu bauen: GitHub erstellt das Image bei jedem Push automatisch
(`.github/workflows/image.yml`) und legt es unter `ghcr.io/luckytitan/simplerpaperless:latest` ab.

1. **Einmalig auf GitHub:** Unter *Packages → simplerpaperless → Package settings* die Sichtbarkeit auf **Public** stellen, damit Portainer das Image ohne Login laden kann.
2. **Ordner für Scans anlegen:** `mkdir -p /opt/archiv/consume` auf dem Docker-Host.
3. **Stack anlegen:** In Portainer *Stacks → Add stack → Web editor*, den Inhalt von `docker-compose.portainer.yml` einfügen und **Deploy the stack** wählen.
4. **Öffnen:** `http://<host>:8010`. Beim ersten Aufruf legst du das Administrator-Konto an.

**Aktualisieren:** *Stacks → archiv → Editor → Update the stack* mit aktiviertem **Re-pull image and redeploy**.
Daten und Dokumente bleiben erhalten (Volumes `archiv_data` und `archiv_media`).

Port, Zeitzone oder OCR-Sprache änderst du direkt in der Compose-Datei (`ports:` bzw. `environment:`).

## Start mit Docker Compose (lokaler Build)

```bash
docker compose up -d --build
```

Dann `http://<host>:8010` öffnen. Beim ersten Aufruf legst du das Administrator-Konto an.
Ein Container, **kein Redis, keine extra Datenbank** (SQLite liegt in `./data`).

| Ordner | Inhalt |
| --- | --- |
| `./data` | Datenbank, Suchindex, interne Warteschlange |
| `./media` | deine Dokumente (Originale, durchsuchbare PDFs, Vorschaubilder) |
| `./consume` | Scans hier ablegen, sie werden automatisch importiert |

## Bedienung

- **Hochladen:** Dateien in das Fenster ziehen oder auf **Hochladen** klicken. Neue Dokumente landen im **Posteingang**, bis sie einen Tag haben.
- **Alle Dokumente:** Oben filterst du nach Tag, Korrespondent und Dokumenttyp. Die Filter lassen sich kombinieren und mit **Filter zurücksetzen** wieder löschen. Die Suche durchsucht auch den erkannten Text.
- **Tags, Korrespondenten, Dokumenttypen:** Ein Klick auf den Menüpunkt in der Seitenleiste zeigt rechts alle Einträge. Dort legst du neue an, bearbeitest oder löschst sie mit dem Stift-Symbol. Ein Klick auf einen Eintrag zeigt die zugehörigen Dokumente.
- **Zuordnung:** automatisch lernen aus deinen bisherigen Zuordnungen, bei bestimmten Wörtern oder nur von Hand.
- **Dokument öffnen:** Reiter **Vorschau** und **Inhalt** (der per Texterkennung ausgelesene Text). Rechts änderst du Titel, Korrespondent, Dokumenttyp und Tags.
- **Papierkorb:** Gelöschte Dokumente landen zuerst im Papierkorb (Standard: 30 Tage, einstellbar mit `PAPERLESS_EMPTY_TRASH_DELAY`). Dort kannst du sie wiederherstellen oder endgültig löschen.
- **Einstellungen** (unten links): Darstellung (hell/dunkel, Akzentfarbe per Schieber, Dokumente pro Seite), Texterkennung (OCR, nur Admins), Passwort ändern und – für Admins – die Benutzerverwaltung.

## Einstellungen (optional, als Umgebungsvariablen)

| Variable | Standard |
| --- | --- |
| `PAPERLESS_OCR_LANGUAGE` | `deu+eng` |
| `PAPERLESS_TIME_ZONE` | `Europe/Berlin` |
| `PAPERLESS_URL` | – (bei Reverse-Proxy setzen, z. B. `https://archiv.example.de`) |
| `PAPERLESS_ADMIN_USER` / `PAPERLESS_ADMIN_PASSWORD` | – (legt den ersten Admin ohne Weboberfläche an) |
| `PAPERLESS_TASK_WORKERS` | `1` (gleichzeitige OCR-Jobs) |

## Technik

Ein Container startet drei Prozesse: Webserver (Granian), Hintergrund-Worker mit Zeitplaner (Celery mit
Dateisystem-Broker statt Redis) und den Ordner-Wächter für `./consume`. Fällt einer aus, beendet sich der
Container und Docker startet ihn neu.

Lizenz: GPL-3.0 wie paperless-ngx (siehe `LICENSE`).
