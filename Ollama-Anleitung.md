# Ollama unter Windows einrichten

Ollama stellt das für den Chat-Übersetzer benötigte Sprachmodell auf deinem PC bereit. Für den ersten Download brauchst du Internet und freien Speicher. Das Modell belegt rund **2,5 GB**. Ollama selbst benötigt zusätzlichen Platz. [Ollama für Windows](https://docs.ollama.com/windows) · [Modellseite](https://ollama.com/library/qwen3:4b-instruct)

## 1. Ollama installieren

1. Öffne die [offizielle Windows-Downloadseite](https://ollama.com/download/windows).
2. Lade **OllamaSetup.exe** herunter und führe die Installation aus.
3. Öffne **Ollama** über das Windows-Startmenü. Ollama läuft danach im Hintergrund und ist gegebenenfalls unter den ausgeblendeten Symbolen neben der Uhr sichtbar.
4. Öffne **PowerShell** über das Startmenü. Verwende ein neu geöffnetes Fenster, damit Windows den installierten Befehl findet.

## 2. Modell herunterladen

Kopiere diese zwei Befehle nacheinander in PowerShell und bestätige jeweils mit **Enter**.

```powershell
ollama --version
ollama pull qwen3:4b-instruct
```

Der erste Befehl zeigt die Ollama-Version an. Warte nach dem zweiten Befehl, bis der Modell-Download abgeschlossen ist. Die App verwendet ein lokales Modell und braucht dafür keinen Ollama-API-Schlüssel.

## 3. Ollama und Modell prüfen

```powershell
ollama list
Invoke-RestMethod http://127.0.0.1:11434/api/version
```

In der Ausgabe von `ollama list` sollte `qwen3:4b-instruct` mit der ID **0edcdef34593** stehen. Der zweite Befehl zeigt die Version des laufenden lokalen Ollama-Dienstes.

Für einen kurzen Test kannst du dem Modell direkt einen einzelnen Satz geben.

```powershell
ollama run qwen3:4b-instruct "Übersetze ins Deutsche: Thank you for your help."
```

## 4. Chat-Übersetzer starten

1. Lade **Chat-Uebersetzer-win-x64.exe** unter **Releases → Assets** herunter und starte sie per Doppelklick.
2. Öffne Discord Desktop oder WhatsApp Desktop und markiere einen Satz, zum Beispiel „Thank you for your help.“
3. Im Reiter **Lesen** erscheint die deutsche Fassung. Beim ersten Auftrag kann die Antwort langsamer kommen, weil Ollama das Modell erst lädt.
4. Für deine eigene Antwort öffnest du **Antwort schreiben**. Dort kannst du die Zielsprache überprüfen, eine deutsche Antwort tippen oder einen Vorschlag übernehmen und die fertige Übersetzung kopieren.

Die heruntergeladene EXE lässt sich optional anhand der veröffentlichten Prüfsumme kontrollieren. Öffne PowerShell im Ordner mit der Datei und vergleiche die angezeigte Zahl mit **SHA256SUMS.txt** aus demselben Release.

```powershell
Get-FileHash -Algorithm SHA256 .\Chat-Uebersetzer-win-x64.exe
```

## Fehler beheben

| Anzeige oder Problem | Was hilft |
| --- | --- |
| PowerShell kennt `ollama` nicht | Schließe PowerShell und öffne es nach der Ollama-Installation neu. |
| Ollama antwortet nicht | Starte Ollama über das Startmenü und prüfe erneut die lokale Version mit dem Befehl oben. |
| Das Modell fehlt | Warte auf den Abschluss von `ollama pull qwen3:4b-instruct` und prüfe `ollama list`. |
| Die Modell-ID stimmt nicht | Diese App-Version prüft die genaue Modellversion. Die auf [der Modellseite](https://ollama.com/library/qwen3:4b-instruct) angezeigte ID sollte **0edcdef34593** sein. Wenn die Modellseite inzwischen eine andere ID zeigt, benötigt diese Kombination eine aktualisierte App-Version. |
| Windows meldet eine fehlende `VCRUNTIME140.dll` oder `MSVCP140.dll` | Installiere das [Microsoft Visual C++ Redistributable für x64](https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist#latest-supported-redistributable-version) und starte die EXE erneut. |
| Die Markierung löst keine Übersetzung aus | Prüfe, ob **Pausieren** angezeigt wird. Falls **Aktivieren** angezeigt wird, klicke darauf. Markiere anschließend den reinen Nachrichtentext in der Desktop-App. |
| Eine Antwort hat die falsche Sprache | Prüfe **Zielsprache** im Reiter **Antwort schreiben** und wähle bei Bedarf die Sprache selbst. |

### Ollama auf lokale Modelle beschränken

Der Chat-Übersetzer verwendet bereits das geprüfte lokale Modell. Wenn du Ollamas Cloud-Funktionen auch für andere Aufrufe auf diesem PC ausschalten möchtest, setze in Windows die Benutzervariable `OLLAMA_NO_CLOUD` auf `1` und beende Ollama über das Symbol neben der Uhr. Starte Ollama danach erneut. [Offizielle Ollama-Anleitung](https://docs.ollama.com/faq#how-do-i-disable-ollamas-cloud-features)
