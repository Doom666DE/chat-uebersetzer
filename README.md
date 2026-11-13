# Chat-Übersetzer für Windows

[**Windows-EXE herunterladen**](https://github.com/Doom666DE/chat-uebersetzer/releases/latest/download/Chat-Uebersetzer-win-x64.exe) · [**Einrichtung auf Deutsch**](Ollama-Anleitung.md) · [**English setup guide**](README.en.md) · [Aktueller Release](https://github.com/Doom666DE/chat-uebersetzer/releases/latest)

Übersetze ausgewählte Nachrichten aus Discord Desktop und WhatsApp Desktop auf Deutsch. Schreibe deine Antwort auf Deutsch und übersetze sie vor dem Abschicken ins Englische, Polnische oder Türkische. Die Übersetzung und die Antwortvorschläge laufen mit Ollama auf deinem PC.

## So sieht die App aus

| Nachrichten lesen | Antworten übersetzen | Antworten vorschlagen |
| --- | --- | --- |
| <img src="docs/screenshots/lesen.png" alt="Reiter Lesen mit einer deutschen Übersetzung" width="300"> | <img src="docs/screenshots/antwort-schreiben.png" alt="Deutscher Entwurf und fertige englische Antwort im Reiter Antwort schreiben" width="300"> | <img src="docs/screenshots/antwortvorschlaege.png" alt="Dialog mit drei deutschen Antwortvorschlägen und Übernehmen-Schaltflächen" width="250"> |

Die Screenshots zeigen Beispielnachrichten.

## Download und Einrichtung

1. Lade die [Windows-EXE](https://github.com/Doom666DE/chat-uebersetzer/releases/latest/download/Chat-Uebersetzer-win-x64.exe) herunter und speichere sie in einem Ordner deiner Wahl.
2. Installiere [Ollama für Windows](https://ollama.com/download/windows) und lade das Modell nach der [Schritt-für-Schritt-Anleitung](Ollama-Anleitung.md).
3. Starte **Chat-Uebersetzer-win-x64.exe**, sobald Ollama läuft und das Modell heruntergeladen ist.

Die App ist für **Windows x64** gebaut. Discord und WhatsApp wurden unter Windows 11 getestet. Die EXE bringt Python mit und nutzt die [Microsoft Visual C++ Laufzeit für x64](https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist). Wenn sie auf deinem PC noch fehlt, installiere sie über Microsoft.

Die EXE ist unsigniert. Windows SmartScreen kann den Download oder den Start als unbekannte App kennzeichnen. Die Release-Datei `SHA256SUMS.txt` enthält die Prüfsumme der EXE zur Kontrolle des Downloads. [Microsoft zu SmartScreen](https://learn.microsoft.com/windows/apps/package-and-deploy/smartscreen-reputation)

## Bedienung

- **Oberfläche.** Wähle oben **Deutsch** oder **English**. Die App merkt sich die Auswahl für den nächsten Start.
- **Lesen.** Markiere mit der Maus Text in Discord Desktop oder WhatsApp Desktop. Ein Doppelklick auf den Nachrichtentext versucht, die ganze Nachricht zu erfassen. Die deutsche Übersetzung erscheint im Fenster neben dem Chat.
- **Antwort schreiben.** Schreibe deinen Entwurf auf Deutsch. Wenn du zuvor eine englische, polnische oder türkische Nachricht markiert hast, wählt die App die erkannte Zielsprache aus. Bei uneindeutigem Text bleibt die bisherige Auswahl stehen. Du kannst die Sprache manuell ändern.
- **Antwortvorschläge.** Klicke auf **3 Antworten vorschlagen**, sobald die deutsche Übersetzung der markierten Nachricht fertig ist. Wähle **Kurz und direkt**, **Freundlich** oder **Mit Rückfrage** und bearbeite den übernommenen Entwurf.
- **Abschicken.** Klicke auf **Übersetzen**, prüfe die Fassung und wähle **Antwort kopieren**. Füge sie mit **Strg + V** in Discord oder WhatsApp ein und sende sie dort selbst.

## Lokale Verarbeitung

Die App liest mit Windows UI Automation den Text deiner Auswahl aus dem geöffneten Fenster. Die einzige Verbindung für Übersetzung, Spracherkennung und Antwortvorschläge geht an Ollama auf `127.0.0.1:11434`. Die App benötigt dafür weder Discord- noch WhatsApp-Zugangsdaten. Sie speichert die Texte im Arbeitsspeicher. **Antwort kopieren** schreibt deinen fertigen Text in die Windows-Zwischenablage.

Änderungen an der Oberfläche von Discord oder WhatsApp können die Erfassung beeinflussen. Übersetzungen und Antwortvorschläge können sprachliche oder inhaltliche Fehler enthalten.

## Aus dem Quellcode starten oder bauen

Die folgenden Befehle sind für PowerShell auf Windows x64 gedacht. Installiere zuerst [uv](https://docs.astral.sh/uv/getting-started/installation/), öffne eine neue PowerShell und wechsle in den Ordner mit dieser README.

```powershell
uv venv --managed-python --python 3.14.7
uv pip sync --python .venv\Scripts\python.exe requirements-build.txt
.\.venv\Scripts\python.exe chat_uebersetzer.py
```

Zum Erstellen der Windows-Datei verwende dieselbe Umgebung.

```powershell
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm chat-uebersetzer.spec
```

Die Startdatei liegt danach unter `dist/Chat-Uebersetzer-win-x64.exe`. Der Build erzeugt die Windows-Bedienungshilfe-Schnittstelle auf dem jeweiligen Rechner und enthält die Lizenztexte der mitgelieferten Komponenten.

## Lizenz

Der Projektcode steht unter der [MIT-Lizenz](LICENSE). Die Lizenztexte der mitgelieferten Komponenten stehen unter [third-party](third-party/README.md). Ollama und das [Qwen3-Modell](https://ollama.com/library/qwen3:4b-instruct) werden separat bezogen. Dies ist ein unabhängiges Projekt.
