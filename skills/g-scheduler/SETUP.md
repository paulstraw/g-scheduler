# g-scheduler setup

g-scheduler reads calendars through Google's [`gws`](https://github.com/googleworkspace/cli) CLI, signed in with an OAuth client from a Google Cloud project. Setup is done once per computer.

**For the agent:** walk the user through this one step at a time. After each step, run the check it names before moving on. If a check fails, look in Troubleshooting below.

## Step 1: Python 3.9+

Check: `python3 --version` (Windows: `python --version`).

- macOS: the built-in `python3` works. If it is missing, run `xcode-select --install`.
- Windows: install from python.org, then run `python -m pip install tzdata` (Windows has no time zone data of its own).
- Linux: use the distribution's `python3` package.

## Step 2: Install gws

Check: `gws --version`.

- macOS or Linux with Homebrew: `brew install googleworkspace-cli`
- Any platform with Node.js 18+: `npm install -g @googleworkspace/cli`
- Or download a binary from [GitHub Releases](https://github.com/googleworkspace/cli/releases) and put it on your `PATH`.

## Step 3: Get an OAuth client file

The file ends up at `~/.config/gws/client_secret.json` (Windows: `%USERPROFILE%\.config\gws\client_secret.json`). Create the folder if it doesn't exist.

### Option A: your organization already has one

If someone in your Google Workspace organization has set up g-scheduler, ask them for the client file (for example, from a shared password vault) and save it to the path above. Skip to Step 4.

Never commit this file or share it outside your organization.

### Option B: create one (about 10 minutes)

Sign in to the Google Cloud console with your work account.

1. **Create a project** at https://console.cloud.google.com/projectcreate (for example, `g-scheduler`). Make sure it is selected in the top bar afterwards.
2. **Enable the Google Calendar API** at https://console.cloud.google.com/apis/library/calendar-json.googleapis.com.
3. **Configure the consent screen** at https://console.cloud.google.com/auth/overview, then click Get started.
   - App name: `g-scheduler`. Support and contact email: yours.
   - **Audience: Internal.** This lets anyone in your Workspace organization use the client, with no Google verification and no "unverified app" warning. If Internal isn't offered (for example, on a personal Gmail account), choose External and add yourself under Audience → Test users.
4. **Create the client** at https://console.cloud.google.com/auth/clients/create. Type: **Desktop app**. Download the JSON.
5. **Move the JSON** to the path above and rename it `client_secret.json`.

To let colleagues skip Option B, share this file with them privately (Option A).

## Step 4: Sign in

Run `gws auth login -s calendar`. A browser opens on this computer; sign in with your work account and approve Calendar access. It's finished when the page says "You may now close this window."

Check: `python3 scripts/gcal.py check` (from the skill folder). It should print your email and time zone.

## Step 5: Confirm you can read a colleague's working hours

Check: `python3 scripts/gcal.py check colleague@yourcompany.com`, using someone who has set working hours in Google Calendar.

- `"working_hours": "set"`: setup is complete.
- `"working_hours": "not set"`: either they haven't set any, or your organization doesn't expose them. Try one or two more people. g-scheduler still works, but assumes 09:00-17:00 for anyone without readable hours.
- `"error": "notFound"`: the address is wrong, outside your organization, or calendar sharing is off.

## Troubleshooting

| Symptom | Fix |
|---|---|
| "Access blocked" or 403 during sign-in | External audience and you aren't a test user. Add yourself under Audience → Test users, or switch the audience to Internal. |
| "This app is blocked" | Your Workspace admin restricts third-party apps. Ask them to mark the OAuth client as trusted in the Admin console (API controls). |
| `redirect_uri_mismatch` | The client isn't a Desktop app. Create a new Desktop app client and replace the JSON. |
| `accessNotConfigured` or "API has not been used in project" | Enable the Google Calendar API in the same project as the client (Step 3.2), wait a minute, retry. |
| `gws failed: ...` mentioning credentials or token | Run `gws auth login -s calendar` again. Check with `gws auth status`. |
| `gws is not installed or not on PATH` | Repeat Step 2, then open a new terminal. |
| "Python has no time zone data" | `python -m pip install tzdata` |
| Times for one zone are an hour off | The time zone data is older than a rule change. Update it: `python -m pip install -U tzdata`, or update the OS. |
| Sign-in asked for more than Calendar | `gws auth login -s calendar` may also request `cloud-platform`. It's harmless and can be declined if the consent screen offers checkboxes. |
