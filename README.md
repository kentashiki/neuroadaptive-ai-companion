# Neuroadaptive AI Companion

This repository contains a small Flask-based demo of a neuroadaptive AI companion.
The UI lets you simulate cognitive-state changes and observe how the assistant changes its tone in response.

## What This Demo Does

- Runs a local Flask web app
- Simulates user state with dummy EEG labels
- Switches the assistant tone between `focused` and `distracted`
- Uses the OpenAI API when an API key is configured
- Falls back to a rule-based response mode when no valid API key is available

## Requirements

Before you start, make sure you have:

- Python 3.10 or newer
- `pip`
- An OpenAI API key if you want live LLM responses

## Quick Start

After cloning the repository from GitHub, run the following steps.

### 1. Clone the repository

```bash
git clone <your-repository-url>
cd neuroadaptive-ai-companion
```

### 2. Create and activate a virtual environment

On Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

On macOS or Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Create a `.env` file

Create a file named `.env` in the project root.

Example:

```env
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-4o-mini
```

Notes:

- If `OPENAI_API_KEY` is missing or left as `your_openai_api_key_here`, the app will still run.
- In that case, the assistant uses the built-in rule-based fallback instead of the OpenAI API.

### 5. Start the app

```bash
python app.py
```

### 6. Open the app in your browser

Visit:

```text
http://127.0.0.1:5000
```

## How To Use the Demo

1. Open the web app.
2. Click `Focused` or `Distracted` in the dummy state switch panel.
3. Send a message in the chat box.
4. Observe how the assistant keeps the topic the same but changes tone and style based on the selected state.

## Project Structure

```text
neuroadaptive-ai-companion/
├─ app.py
├─ requirements.txt
├─ agent/
├─ eeg/
├─ models/
├─ static/
└─ templates/
```

## Troubleshooting

### The app starts, but responses do not use OpenAI

Check the following:

- The `.env` file exists in the project root
- `OPENAI_API_KEY` is set correctly
- The API key is active and has access to the selected model

### Port 5000 is already in use

Stop the process using port `5000`, or change the Flask startup code in `app.py` to use a different port.

### PowerShell blocks virtual environment activation

If PowerShell blocks `Activate.ps1`, you can either:

- run `Set-ExecutionPolicy -Scope Process RemoteSigned`
- or activate the environment from Command Prompt instead

## Development Notes

- The app entry point is `app.py`.
- `main.py` has been removed because it duplicated the same startup behavior.
