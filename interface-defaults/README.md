# 🎛️ Interface Defaults

<img width="6400" height="1600" alt="banner-interface-defaults" src="https://github.com/user-attachments/assets/57c46cdc-96a1-4f4e-a451-dacef6d55320" />

Set the **Settings → Interface** defaults for your entire instance from one function's Valves. Only the settings you switch to **Custom** are managed, so you can enforce one option without touching anything else your users have configured. New users are seeded automatically, and two one-shot buttons let you apply your settings to everyone or factory-reset the whole instance.

> [!TIP]
> **🚀 [Jump to Setup](#setup)** — paste, enable, configure. Under a minute, no restart.

<img width="2800" height="940" alt="04-functions-list" src="https://github.com/user-attachments/assets/00b08fb7-c7cc-4ab1-a317-58b504a1e621" />

<img width="2360" height="2480" alt="01-valves-overview" src="https://github.com/user-attachments/assets/78fdbf34-1b0b-44cb-8307-7d5db58af1b2" />

<img width="2360" height="2480" alt="02-valves-quick-actions" src="https://github.com/user-attachments/assets/10e842ad-fc67-4384-ab05-5fd398ceaa9d" />

<img width="2360" height="2480" alt="03-valves-triggers" src="https://github.com/user-attachments/assets/de57c9e2-a267-4a6c-be26-a454964378a6" />

<img width="2800" height="1280" alt="05-quick-actions-live" src="https://github.com/user-attachments/assets/f2407d82-f325-4f77-b777-33ce9ad4e84c" />

<img width="2600" height="2000" alt="06-user-settings-interface" src="https://github.com/user-attachments/assets/b287a5d0-8532-45c1-8f15-6328cf3fc567" />

## ✨ Features

- **You manage only what you set** — a setting left on **Default** in the Valves is never written to anyone, so each user keeps their own choice for it. Flip a setting to **Custom** and it becomes instance policy, even if the value you pick happens to equal Open WebUI's factory value.
- **Automatic seeding of new users** — every account created via signup, OAuth, LDAP, SCIM, or by an admin inherits your Custom settings.
- **Apply to all existing users** — a one-shot button to push your Custom settings to everyone already on the instance, leaving their other settings alone.
- **Full factory reset** — a one-shot button that clears every user's interface settings *and* puts this function's config back to Default.
- **Standardize the text-selection quick actions** — set the floating **Ask/Explain**-style buttons instance-wide from one JSON valve (Translate, Summarize, Fix grammar, whatever fits your users). See [the tutorial below](#setting-the-quick-action-buttons-json).
- **Native Valves UI** — booleans render as toggles, direction as a dropdown, text scale as a number. No custom UI.
- **Nothing outside the Interface settings is ever touched.** Open WebUI keeps a user's whole settings store (system prompt, default model, audio, notification webhook, pinned models) in the same `settings.ui` object as the interface options, so both buttons operate key-by-key and leave the rest alone.

## ✅ How it works

Open WebUI dispatches events in-process to any `Event` function that defines an `event` handler. This plugin reacts to:

- `user.created` → writes your Custom interface settings into the new user's `settings.ui`. Fires for signup, OAuth, LDAP, SCIM and admin-created accounts.
- `function.valves_updated` (its own) → runs the apply / reset when you tick a trigger toggle and **Save**, unticking it first via the model layer (no re-publish, so there is no loop).
- `function.enabled` / `system.startup.completed` (its own) → discards any trigger left ticked without running (saved while disabled, or persisted by a crash before the job started), so it cannot fire unexpectedly on a later save.

Both bulk operations run in the background, so saving returns immediately even on large instances.

Open WebUI stores a function's valves with `exclude_unset`, meaning only the fields you switched to **Custom** are persisted at all. This function reads exactly that set, which is why a setting on **Default** can never overwrite a user's own choice, and why writes merge into a user's existing `settings.ui` rather than replacing it.

> [!NOTE]
> **Apply vs reset.** *Apply* keeps your configured settings (so new users keep getting them) and only writes the ones set to Custom. *Reset* is a true factory reset: it clears every user's interface settings **and** returns this function's own config to Default, so nothing is managed afterwards.

> [!IMPORTANT]
> **`settings.ui` is not just the Interface tab.** Open WebUI's frontend persists its entire settings store under that key, so a user's system prompt, default model, audio/TTS config, notification webhook and pinned models live right next to `chatBubble` and `widescreenMode`. Both buttons read a user's full `settings.ui`, change **only the interface keys this function manages**, and write it back, so everything else is preserved unchanged (it is re-written with the same value, not deleted). A settings save a user makes in the same instant the pass touches their row can be lost, the same lost-update the built-in settings modal already has; it is bounded to that one save and self-heals on their next save.

## Components

| File | Type | Install location |
|------|------|-----------------|
| `event.py` | Event | Admin Panel → Functions |

## Setup

1. Copy the contents of `event.py`, or click **Get** on the Community page.
2. In Open WebUI, go to **Admin Panel → Functions → +** (Import/Create).
3. Paste the code and click **Save**.
4. **Enable** the function.
5. Open its **Valves**. Click a setting from **Default** to **Custom** for each option you want to enforce, and pick its value. Leave everything else on **Default**.
6. *(First install only)* Tick **Apply to all existing users** and **Save** to seed everyone already on the instance.

## Usage

- **New users** — nothing to do; they're seeded automatically on registration.
- **Enforce one option across the instance** — set just that option to **Custom**, tick **Apply to all existing users**, and **Save**. Everyone gets that option; all of their other settings stay exactly as they were.
- **Change a setting later** — edit the Valves, then either leave it (new users get the change automatically) or tick **Apply to all existing users** + **Save** to push it to everyone.
- **Stop managing a setting** — switch it back to **Default**. Existing users keep whatever value they currently have; it is simply no longer enforced.
- **Start over** — tick **Reset all users to factory** + **Save**.

> [!WARNING]
> The two buttons act on **every** user, in chunks, in the background. *Apply* overwrites only your **Custom** settings for all existing users; *Reset* clears the interface settings this function manages instance-wide, even ones you never set. Both untick themselves before the background job starts, so an already-open form may show the toggle as still ticked until you refresh. A trigger ticked while the function is **disabled**, or left ticked by a server crash before the job ran, is discarded on the next enable or startup rather than firing late. If the server restarts **mid-pass** the remainder is not resumed; just tick the button again (repeating is safe, every write is idempotent).

## Setting the quick-action buttons (JSON)

Most valves are a toggle or a number, but one is a small JSON config: **Floating Quick Action Buttons**. These are the buttons Open WebUI pops up when a user **selects text** in a message (out of the box: *Ask* and *Explain*). This valve lets you replace that set instance-wide, so you can give everyone a standard toolbox of one-click prompts.

**How to set it**

1. In the Valves, click **Floating Quick Action Buttons (JSON)** from **Default** to **Custom**.
2. Paste a **JSON array** of button objects (below), then **Save**.
3. Tick **Apply to all existing users** + **Save** to push it to everyone (new users get it automatically).

Leave it on **Default** to keep Open WebUI's built-in Ask/Explain. Invalid JSON is ignored (nothing is pushed, so a typo can't break anyone), and it stays separate from the **Floating Quick Actions** on/off toggle, which decides whether the buttons show at all.

**Each button** is an object with four fields:

| Field | Meaning |
|-------|---------|
| `id` | Unique identifier (any short string, must be unique in the list). |
| `label` | The text on the button. |
| `input` | `true` shows a small input box first, so the user can add their own instruction; `false` runs immediately. |
| `prompt` | What gets sent. Use the placeholders below. |

**Placeholders** you can put in `prompt`:

- `{{SELECTED_CONTENT}}` — the text the user highlighted (with formatting).
- `{{CONTENT}}` — the highlighted text as plain text.
- `{{INPUT_CONTENT}}` — replaced with what the user types in the input box (only meaningful when `input` is `true`).

**Copy-paste starter** (Translate asks for a target language; the rest run on the selection directly):

```json
[
  { "id": "translate", "label": "Translate", "input": true,
    "prompt": "Translate the following into {{INPUT_CONTENT}}:\n\n{{SELECTED_CONTENT}}" },
  { "id": "summarize", "label": "Summarize", "input": false,
    "prompt": "Summarize this clearly and concisely:\n\n{{SELECTED_CONTENT}}" },
  { "id": "grammar", "label": "Fix grammar", "input": false,
    "prompt": "Correct spelling and grammar, keep the meaning and tone:\n\n{{SELECTED_CONTENT}}" },
  { "id": "simplify", "label": "Explain simply", "input": false,
    "prompt": "Explain this in plain language a beginner would understand:\n\n{{SELECTED_CONTENT}}" }
]
```

**Ideas for admins** — pick the ones that fit your users:

- **Language teams:** *Translate* (with `input` for the target language), *Rephrase formally*, *Rephrase casually*.
- **Writing / support:** *Fix grammar*, *Improve writing*, *Make more concise*, *Change tone to friendly*.
- **Analysts / PMs:** *Summarize*, *Extract action items*, *List pros and cons*, *Turn into a checklist*.
- **Engineering:** *Explain this code*, *Find bugs or edge cases*, *Add comments*, *Write a test for this*.
- **Learning / onboarding:** *Explain simply*, *Give an example*, *Define the key terms*.

A good default set is 3–5 buttons: too many and the popup gets crowded. Since a push replaces each user's whole button list, keep the config you apply as the complete set you want everyone to have.
