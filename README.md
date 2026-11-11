# Archiv

Eine schlanke, selbst gehostete Dokumentenablage. Dokumente hochladen, per Texterkennung lesbar machen,
automatisch sortieren und schnell wiederfinden – ohne Ballast.

Archiv basiert auf [paperless-ngx](https://github.com/paperless-ngx/paperless-ngx), ist aber bewusst auf das
Wesentliche reduziert: eine aufgeräumte Oberfläche für Dokumente, Tags, Korrespondenten und Dokumenttypen.

## Funktionen

- **Hochladen per Drag & Drop** oder über einen Überwachungsordner (z. B. für Scanner)
- **Texterkennung (OCR)** auf Deutsch und Englisch, Volltextsuche im erkannten Text
- **Automatische Sortierung:** Tags, Korrespondenten und Dokumenttypen werden aus deinen bisherigen Zuordnungen gelernt oder über Stichwörter vergeben
- **Posteingang** für Dokumente, die noch keinen Tag haben
- **Filter** nach Tag, Korrespondent und Dokumenttyp
- **Papierkorb** mit Wiederherstellung
- **Mehrere Benutzer**, helles und dunkles Design, einstellbare Akzentfarbe
- **Einfacher Betrieb:** ein Container, **kein Redis, keine extra Datenbank** (SQLite)

Nicht enthalten: E-Mail-Import, Workflows, Freigabelinks, benutzerdefinierte Felder, KI-Funktionen.

## Installation

Du brauchst nur Docker. Lege eine `docker-compose.yml` an:

```yaml
services:
  archiv:
    image: ghcr.io/luckytitan/simplerpaperless:latest
    container_name: archiv
    restart: unless-stopped
    ports:
      - "8010:8000"
    environment:
      PAPERLESS_TIME_ZONE: Europe/Berlin
      PAPERLESS_OCR_LANGUAGE: deu+eng
    volumes:
      - archiv_data:/data
      - archiv_media:/media
      - ./consume:/consume

volumes:
  archiv_data:
  archiv_media:
```

Starte mit `docker compose up -d` und öffne `http://<host>:8010`. Beim ersten Aufruf legst du das
Administrator-Konto an.

Mit **Portainer** fügst du denselben Inhalt unter *Stacks → Add stack → Web editor* ein (statt `./consume`
einen absoluten Pfad wie `/opt/archiv/consume` verwenden). Eine fertige Datei liegt als
[`docker-compose.portainer.yml`](docker-compose.portainer.yml) bei.

**Aktualisieren:** `docker compose pull && docker compose up -d` bzw. in Portainer *Update the stack* mit
*Re-pull image*. Deine Daten bleiben erhalten.

### Speicherorte

| Ort | Inhalt |
| --- | --- |
| `/data` | Datenbank, Suchindex, interne Warteschlange |
| `/media` | Dokumente (Originale, durchsuchbare PDFs, Vorschaubilder) |
| `/consume` | Dateien hier ablegen, sie werden automatisch importiert |

## Bedienung

- **Hochladen:** Dateien ins Fenster ziehen oder auf **Hochladen** klicken. Neue Dokumente liegen im **Posteingang**, bis sie einen Tag haben.
- **Alle Dokumente:** Oben nach Tag, Korrespondent und Dokumenttyp filtern. Die Filter lassen sich kombinieren; die Suche durchsucht auch den erkannten Text.
- **Tags, Korrespondenten, Dokumenttypen:** Ein Klick auf den Menüpunkt zeigt alle Einträge. Dort legst du neue an und bearbeitest oder löschst sie. Ein Klick auf einen Eintrag zeigt die zugehörigen Dokumente.
- **Zuordnung:** automatisch aus deinen bisherigen Zuordnungen lernen, bei bestimmten Wörtern oder nur von Hand.
- **Dokument öffnen:** Reiter **Vorschau** und **Inhalt** (der ausgelesene Text); Titel, Korrespondent, Dokumenttyp und Tags änderst du rechts.
- **Papierkorb:** Gelöschte Dokumente bleiben 30 Tage erhalten und lassen sich wiederherstellen.
- **Einstellungen:** Darstellung (hell/dunkel, Akzentfarbe, Dokumente pro Seite), Texterkennung (nur Admins), Passwort und Benutzerverwaltung (nur Admins).

## Konfiguration (optional)

Umgebungsvariablen im Compose-File:

| Variable | Standard | Bedeutung |
| --- | --- | --- |
| `PAPERLESS_OCR_LANGUAGE` | `deu+eng` | Sprachen der Texterkennung |
| `PAPERLESS_TIME_ZONE` | `Europe/Berlin` | Zeitzone |
| `PAPERLESS_URL` | – | Öffentliche Adresse hinter einem Reverse-Proxy, z. B. `https://archiv.example.de` |
| `PAPERLESS_ADMIN_USER` / `PAPERLESS_ADMIN_PASSWORD` | – | Legt den ersten Admin ohne Einrichtungsseite an |
| `PAPERLESS_TASK_WORKERS` | `1` | Gleichzeitige OCR-Aufträge |
| `PAPERLESS_EMPTY_TRASH_DELAY` | `30` | Tage, bis der Papierkorb automatisch geleert wird |

## Selbst bauen

```bash
git clone https://github.com/LuckyTitan/simplerpaperless.git
cd simplerpaperless
docker compose up -d --build
```

## Technik

Ein Container startet drei Prozesse: Webserver (Granian), Hintergrund-Worker mit Zeitplaner (Celery mit
Dateisystem-Warteschlange statt Redis) und den Ordner-Wächter für `/consume`. Fällt einer aus, beendet sich der
Container und Docker startet ihn neu.

## Lizenz

GPL-3.0 wie paperless-ngx, siehe [`LICENSE`](LICENSE).
