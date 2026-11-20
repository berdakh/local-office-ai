# Pilot Runbook

## Before install day
- [ ] Office computer specs confirmed (from discovery). Decide: their machine or the appliance.
- [ ] Python 3.11+, uv, Node.js with npm, and Ollama installed.
- [ ] `.env` written with the intended models and location for office data.
- [ ] Online preparation completed on the target machine (model downloads can be several GB).
- [ ] The office's Word letterhead saved as `packs/church/templates/letterhead.docx`, or the generated starter reviewed.
- [ ] A recording with known scripture references selected for the offline test.
- [ ] Synthetic samples loaded so the demo works before their documents are in.

## Install day (90 minutes)
1. Disconnect the pilot computer's internet connection while keeping localhost available.
2. Run `./scripts/install.sh --offline` on Linux/macOS or `./scripts/install.ps1 -Mode Offline` in PowerShell.
3. Start with the launcher and confirm the models and Bible show as installed in Settings.
4. Run a recording through Sermon Studio, check a known reference, and download an edited draft. The command below runs the same operations from the terminal and checks that the stored transcript, embedding, all six drafts, and both export formats are usable.
5. Load their documents into the Library, then run the training below.

```bash
.venv/bin/python scripts/offline_check.py sermon.mp3 --expect-reference "John 3:16"
```

On Windows use `.venv\Scripts\python.exe`. Use the actual reference spoken in
the recording. The check exercises the app through localhost. The network must
already be disconnected or blocked before running it.

## 30-minute training script
- 5 min: what it is, what it never does (nothing leaves this computer, nothing is sent anywhere).
- 10 min: Sermon Studio with last Sunday's recording.
- 5 min: Announcement Hub with this week's real announcements.
- 5 min: Ask the Office with three questions they suggest.
- 5 min: where the files go, how to back up, who to call.

## Weekly check-in (15 minutes, four weeks)
- What did you use it for this week?
- What did it get wrong?
- What did you wish it did?
- Note time saved in their words.

## Exit criteria
See docs/mvp-scope.md, section 5.
