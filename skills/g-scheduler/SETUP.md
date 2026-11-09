# g-scheduler setup

g-scheduler reads calendars through Google's [`gws`](https://github.com/googleworkspace/cli) CLI, signed in with an OAuth client from a Google Cloud project. Setup is done once per computer.

**For the agent:** walk the user through this one step at a time. After each step, run the check it names before moving on. If a check fails, look in Troubleshooting below.

## Step 1: Python 3.9+

Check: `python3 --version` (Windows: `python --version`).

- macOS: the built-in `python3` works. If it is missing, run `xcode-select --install`.
- Windows: Windows has no Python of its own. If `python` opens the Microsoft Store or fails, install the Python install manager with `winget install 9NQ7512CXL7T` (or from the Microsoft Store), then open a new terminal. Then run `python -m pip install tzdata`, because Windows also has no time zone data Python can use.
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
2. **Enable two APIs:**
   - Google Calendar API: https://console.cloud.google.com/apis/library/calendar-json.googleapis.com
   - People API: https://console.cloud.google.com/apis/library/people.googleapis.com. This one lets g-scheduler look up colleagues' emails by name. It's optional; without it, the agent finds emails some other way or asks you.
3. **Configure the consent screen** at https://console.cloud.google.com/auth/overview, then click Get started.
   - App name: `g-scheduler`. Support and contact email: yours.
   - **Audience: Internal.** This lets anyone in your Workspace organization use the client, with no Google verification and no "unverified app" warning. If Internal isn't offered (for example, on a personal Gmail account), choose External and add yourself under Audience → Test users.
4. **Create the client** at https://console.cloud.google.com/auth/clients/create. Type: **Desktop app**. Download the JSON.
5. **Move the JSON** to the path above and rename it `client_secret.json`.

To let colleagues skip Option B, share this file with them privately (Option A).

## Step 4: Sign in

Run:

```bash
gws auth login --scopes https://www.googleapis.com/auth/calendar,https://www.googleapis.com/auth/directory.readonly
```

A browser opens on this computer. Sign in with your work account and approve access to your calendars and your organization's directory. It's finished when the page says "You may now close this window." Signing in again replaces the previous sign-in. If you are signing in again to add access, first delete `~/.config/gws/token_cache.json`, or `gws` keeps using the old access token for up to an hour.

Checks (from the skill folder):

- `python3 scripts/gcal.py check` prints your email and time zone.
- `python3 scripts/gcal.py find "<a colleague's name>"` lists matching people with their emails. If it fails with `accessNotConfigured`, the People API isn't enabled in the client's project (Step 3, Option B, item 2). If you got the client file from someone else (Option A), ask them to enable it. Everything except name lookup still works.

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
| `accessNotConfigured` or "API has not been used in project" | Enable the API it names (Calendar, or People for `find`) in the same project as the client (Step 3, Option B, item 2), wait a minute, retry. |
| `find` fails with "insufficient authentication scopes" | Delete `~/.config/gws/token_cache.json`, then sign in again with the command in Step 4. |
| `find` fails with "The G Suite domain admin has disabled external directory sharing" | Your Workspace blocks third-party apps, including g-scheduler, from reading the directory. "External" means apps, not people outside your organization. A Workspace admin can allow it in the Admin console: Directory → Directory settings → Sharing settings → **External Directory Sharing** → "Organization data and authenticated user basic profile fields" ([Google's help page](https://support.google.com/a/answer/6343701)). Until then, everything except name lookup still works; the agent finds emails another way or asks you. |
| Sign-in fails with "Error 400: invalid_request" right after enabling an API | Wait a few minutes and run the sign-in command again. |
| `gws failed: ...` mentioning credentials or token | Sign in again with the command in Step 4. Check with `gws auth status`. |
| `gws is not installed or not on PATH` | Repeat Step 2, then open a new terminal. |
| "Python has no time zone data" | `python -m pip install tzdata` |
| Times for one zone are an hour off | The time zone data is older than a rule change. Update it: `python -m pip install -U tzdata`, or update the OS. |
