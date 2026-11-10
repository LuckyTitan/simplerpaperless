# Archiv

Eine schlanke Dokumentenablage auf Basis von [paperless-ngx](https://github.com/paperless-ngx/paperless-ngx).
Nur das Wesentliche: Dokumente hochladen, per OCR lesbar machen, automatisch mit Tags versehen, suchen.

**Bewusst entfernt:** E-Mail-Import, Workflows, Share-Links, Custom Fields, KI/LLM, Websockets,
Redis, Postgres/MariaDB, MFA/Social-Login und die komplette Angular-Oberfläche.

## Start

```bash
docker compose up -d --build
```

Dann `http://<host>:8000` öffnen. Beim ersten Aufruf legst du das Administrator-Konto an.
Ein Container, **kein Redis, keine extra Datenbank** (SQLite liegt in `./data`).

| Ordner | Inhalt |
| --- | --- |
| `./data` | Datenbank, Suchindex, interne Warteschlange |
| `./media` | deine Dokumente (Originale, durchsuchbare PDFs, Vorschaubilder) |
| `./consume` | Scans hier ablegen, sie werden automatisch importiert |

## Bedienung

- Dateien in das Fenster ziehen oder auf **Hochladen** klicken.
- Tags links mit **+** anlegen.
- Neben Tags gibt es **Korrespondenten** (z. B. Stadtwerke) und **Dokumenttypen** (z. B. Rechnung). Sie lassen sich in der Seitenleiste anlegen, filtern und über das Stift-Symbol bearbeiten oder löschen.
- Zuordnung: automatisch lernen aus deinen bisherigen Zuordnungen, bei bestimmten Wörtern oder nur von Hand.
- **Papierkorb:** Gelöschte Dokumente landen zuerst im Papierkorb (Standard: 30 Tage, einstellbar mit `PAPERLESS_EMPTY_TRASH_DELAY`). Dort kannst du sie wiederherstellen oder endgültig löschen.
- **Einstellungen** (unten links): Darstellung (hell/dunkel, Dokumente pro Seite), Texterkennung (OCR, nur Admins), Passwort ändern und – für Admins – die Benutzerverwaltung.

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
