# fun(d)

fun(d) is a simple website that shows public companies matching interests you pick: Gaming, Travel, Music, or Automobile. You look at one company at a time, press Like or Dislike, and the companies you like show up under Matches.

You do not need to know how to code. Do the steps in order. Each terminal step is one command. Copy the whole line, paste it into the VS Code terminal, and press Enter.

There are two versions of some commands: one for Mac, one for Windows. Run only the line that matches your computer.

## Before you start

Install these three things if you do not already have them. Then quit VS Code completely and open it again.

1. Visual Studio Code: https://code.visualstudio.com/
2. Python 3.11 or newer: https://www.python.org/downloads/
   - On Windows, during install, check the box that says **Add python.exe to PATH**.
3. Node.js 18 or newer (the LTS installer is fine): https://nodejs.org/

You also need Git, which VS Code can use. On a Mac it is included with the Xcode command line tools. On Windows, install Git from https://git-scm.com/download/win if `git` is not already there.

## 1. Download the project

Open VS Code. Open a terminal with **Terminal → New Terminal**.

Mac:

```
git clone https://github.com/001-jwn/fund-app.git
```

Windows:

```
git clone https://github.com/001-jwn/fund-app.git
```

You should see several lines of text, and the last ones should say the clone finished (the word `done` appears). A new folder named `fund-app` is created.

Then go into that folder.

Mac:

```
cd fund-app
```

Windows:

```
cd fund-app
```

The prompt comes back and you do not see an error. You are now inside the project folder.

## 2. Open that folder in VS Code

This step is not a terminal command.

1. In VS Code choose **File → Open Folder**.
2. Choose the `fund-app` folder (the one that contains this README).
3. If VS Code asks you to trust the folder, click trust.
4. Choose **Terminal → New Terminal**.

The new terminal is already inside `fund-app`. Run the rest of the commands there. Do not move the files around.

Check that the terminal is in the right folder.

Mac:

```
ls README.md
```

You should see exactly:

```
README.md
```

Windows:

```
dir README.md
```

You should see a listing that includes `README.md`.

## 3. Check Python

Mac:

```
python3 --version
```

Windows:

```
py --version
```

You should see `Python 3.11` or a higher number, for example `Python 3.12.3`.

If the command is not found, install Python from the link above, quit VS Code, open it again, and open a new terminal.

## 4. Check Node

Mac and Windows use the same command:

```
node --version
```

You should see `v18` or a higher number, for example `v22.23.4`.

If the command is not found, install Node.js from the link above, quit VS Code, open it again, and open a new terminal.

## 5. Create a private Python folder

This makes a folder named `.venv` that holds this project's Python tools. It does not change the rest of your computer.

Mac:

```
python3 -m venv .venv
```

Windows:

```
py -m venv .venv
```

The command finishes and the prompt comes back. You should not see the word `Error`. You can ignore the `.venv` folder.

## 6. Install the backend tools

Mac:

```
.venv/bin/python -m pip install -r backend/requirements.txt
```

Windows:

```
.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

This can take a minute. Wait until the prompt comes back. The last line should start with `Successfully installed`.

## 7. Make your settings file

Mac:

```
cp .env.example .env
```

Windows:

```
copy .env.example .env
```

You should not see an error. On Windows you may see `1 file(s) copied.` A new file named `.env` appears next to this README.

That `.env` file is the only place a Finnhub key goes. Never paste the key into a `.py`, `.js`, or `.jsx` file, and never commit the `.env` file.

## 8. Put your Finnhub key in .env, or leave it blank

This step is not a terminal command.

1. In the left sidebar, click the file named `.env`. If you do not see it, choose **File → Open File** and open `.env` inside the `fund-app` folder.
2. Find this line:

```
FINNHUB_API_KEY=
```

3. Click at the end of that line and paste your key. Do not add a space. Do not add quotes. The line should look like this, with your real key instead of the example:

```
FINNHUB_API_KEY=abc123yourkey
```

4. Leave this line blank:

```
FUN_D_FINNHUB_LIVE=
```

5. Save the file. On Windows press Ctrl+S. On a Mac press Cmd+S.

If you do not have a key yet, leave `FINNHUB_API_KEY=` empty and save the file. The app still runs. Price and news will say `unavailable`. You can add a key later.

A free key is available at https://finnhub.io/register (create an account, then copy the API key from the dashboard). After you save a new key, stop the backend (click that terminal and press Ctrl+C) and start it again with the command in step 9.

## 9. Start the backend

Stay in the `fund-app` folder. Run this in the terminal you already have. You will not get a prompt back. That is expected. The backend is running. Leave this terminal alone.

Mac:

```
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --app-dir backend
```

Windows:

```
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --app-dir backend
```

You should see these lines:

```
fun(d) ready. Loaded 31 companies.
Finnhub: off. Price and news will show as unavailable.
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

If you saved a Finnhub key, the second line is instead:

```
Finnhub: on. Live prices and news will fill in in the background.
```

The first time, prices and news can take a minute or two to show up. You can keep swiping while that happens. Reload the page later and the card you are looking at will update.

The company list loads by itself. You do not run a separate command for that.

## 10. Install the website tools

Open a second terminal: **Terminal → New Terminal**. It also starts in the `fund-app` folder. Do not type in the first terminal. That one is busy.

Mac and Windows use the same command:

```
npm install --prefix frontend
```

This can take a minute. Wait until the prompt comes back. You may see a note about funding or vulnerabilities. You can ignore that.

## 11. Start the website

In that same second terminal:

```
npm run dev --prefix frontend
```

You should see lines like these:

```
> fund-frontend@0.1.0 dev
> vite

  VITE v5.4.21  ready in 149 ms

  ➜  Local:   http://127.0.0.1:5173/
```

The number of milliseconds can be different. The important line is `Local:   http://127.0.0.1:5173/`. Leave this terminal open too.

## 12. Check the backend in the browser

Open this address in your web browser:

http://127.0.0.1:8000/health

You should see:

```
{"status":"ok","finnhub":"off"}
```

If you added a key and restarted the backend, `finnhub` is `"on"` instead of `"off"`.

## 13. Try the app

Open this address:

http://127.0.0.1:5173/

1. You should see the heading **fun(d)** and four choices: Gaming, Travel, Music, Automobile.
2. Click **Gaming** so its box is checked. You can check more than one.
3. Click **Start**.
4. One company card appears. Near the top, a yellow box says **Why you're seeing this**. The sentence under it starts with `You picked Gaming`.
5. The card also shows the company name, a short ticker symbol, a plain-language description, a latest-quarter summary, and the date that quarter ended. Price says `Price: unavailable` and news says `Latest news: unavailable` until a Finnhub key is working. There is no holder count on the card.
6. Click **Like**.
7. Click **Matches** at the top.
8. The company you liked is listed there, with the same yellow **Why you're seeing this** line.

Click **Dislike** on a card you want to skip. That company does not go into Matches, and it does not come back.

Click **Start over** if you want to pick different interests. That starts a new session in this browser.

## Stop the app

1. Click the backend terminal (the one from step 9) and press Ctrl+C.
2. Click the website terminal (the one from step 11) and press Ctrl+C.

The prompts come back. The app is stopped. Your likes stay in the local database until you delete the `backend` folder's database file. Starting the backend again keeps them.

## If something goes wrong

- `python3` or `py` is not found: install Python, quit VS Code, and open a new terminal.
- `node` is not found: install Node.js, quit VS Code, and open a new terminal.
- `Address already in use`: the app is already running, or an old copy is still running. Press Ctrl+C in the old terminal and run the start command again.
- The website says it cannot reach the app server: the backend terminal is not running. Repeat step 9 and leave that terminal open.
- Price and news stay `unavailable`: `.env` has no key, the key was not saved, or the backend was not restarted after you saved `.env`.
- You see companies that do not match what you picked: click **Start over** and pick the interests again. A card's why line always matches one interest you picked.

## Running for the iPhone app

Do this only on a Mac, and only when the fun(d) app in Expo Go on an iPhone should use this backend. The iPhone and the Mac have to be on the same Wi-Fi. The website steps above stay the same, including the `127.0.0.1` command in step 9.

1. Get the Mac's Wi-Fi address. In a terminal, run:

```
ipconfig getifaddr en0
```

You should see a number like `192.168.1.42`. That is the Mac's IP. Use that number wherever a step says `<Mac-IP>`.

2. Start the backend so the iPhone can reach it. If the backend from step 9 is still running, click that terminal and press Ctrl+C. Then, from the `fund-app` folder, run:

```
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --app-dir backend
```

That is `uvicorn app.main:app --host 0.0.0.0 --port 8000`. Leave this terminal open. You should see `Uvicorn running on http://0.0.0.0:8000`.

The macOS firewall will ask to allow incoming connections for Python. Click Allow.

3. On the iPhone, open Safari and go to `http://<Mac-IP>:8000/health`.

If the address was `192.168.1.42`, open `http://192.168.1.42:8000/health`.

You should see:

```
{"status":"ok",...}
```

The `finnhub` value is `"on"` or `"off"`.

4. Point the Expo app at this backend. The full backend URL is:

```
http://<Mac-IP>:8000
```

The Expo app reads that URL from `EXPO_PUBLIC_API_URL` in `mobile/.env`. For example:

```
EXPO_PUBLIC_API_URL=http://192.168.1.42:8000
```

Expo Go on the iPhone will ask for Local Network permission. Tap Allow.

Anything named `EXPO_PUBLIC_*` gets built into the app, so `mobile/.env` must hold only the server URL and never the Finnhub key. The Finnhub key stays in the `.env` file next to this README.

## Optional: run the automated checks

You can skip this. It is for checking that the app's rules still hold. Use a new terminal in the `fund-app` folder, after step 6. Do not stop the backend if it is already running. This check uses its own temporary database.

Mac:

```
.venv/bin/python -m pytest -q --rootdir=backend backend/tests
```

Windows:

```
.venv\Scripts\python.exe -m pytest -q --rootdir=backend backend/tests
```

The last line should include `27 passed`.
