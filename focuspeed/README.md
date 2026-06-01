# FocuSpeed

FocuSpeed is a standalone demo UI for an EEG-adaptive audio player. The demo keeps all implementation files inside this directory, including the audio asset under `static/audio/`.

## Run

```powershell
..\.venv\Scripts\python.exe app.py
```

Then open `http://127.0.0.1:5050/`.

The demo API simulates realtime EEG features and maps the current concentration score to the HTML audio element's `playbackRate`.
