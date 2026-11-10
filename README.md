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
- Tags links mit **+** anlegen. Tragen sie „Wörter für automatische Zuordnung“ ein, vergibt der
  Klassifikator den Tag automatisch, sobald diese Wörter im Dokument vorkommen.
- Rechtsklick auf einen Tag in der Seitenleiste bearbeitet oder löscht ihn.
- Admins verwalten Benutzer unten links unter **Benutzer**.

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
