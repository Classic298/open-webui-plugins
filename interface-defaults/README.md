# 🎛️ Interface Defaults

<img width="6400" height="1600" alt="banner-interface-defaults" src="https://github.com/user-attachments/assets/f76ab3d6-8d4b-4872-8ba5-29c8c024d970" />

Open WebUI 0.11.1 added **Admin Panel → Settings → General → Default Interface Settings**, which sets instance-wide defaults for everything in a user's Interface settings. This function is the companion to that page. It adds the two buttons the page does not have, and defaults for the user settings the page does not reach.

> [!IMPORTANT]
> Requires Open WebUI **0.11.1 or newer**. On 0.11.0 and older the native defaults page does not exist and this function has nothing to work with.

> [!IMPORTANT]
> **Upgrading from 1.3.0?** Every valve was renamed in 1.4.0, so your saved valve configuration is dropped on upgrade and the function manages nothing until you set it again. Reconfigure the Valves, then tick **Apply Defaults to All Users**.

<img width="3200" height="2300" alt="4" src="https://github.com/user-attachments/assets/fbd82d66-e637-4e0e-8483-36015d97b20d" />

## ✨ What it adds

- **Apply defaults to all existing users, overwriting them.** The native page only reaches a user for a setting they have never personally changed. Anyone who has ever opened their Interface settings has a stored value for every option, so they inherit nothing. This button writes every setting you configured into every existing user, replacing the choice they made for it. Settings you have not configured are left alone.
- **Reset all users to factory.** Clears every interface setting from every user, including options you never configured, so the instance falls back to Open WebUI's built-ins.
- **Defaults for settings the native page does not cover.** Notifications, keyboard shortcuts, memory, the personal system prompt, and the whole speech/voice block. These are written into the same config row the native page uses, so they behave exactly like the native defaults: applied live, inherited by new accounts, overridable per user.

## ✅ How it works

Open WebUI keeps instance defaults in one config row (`ui.default_interface_settings`) and merges it underneath each user's own `settings.ui` on every read. A user only stores the settings they actually deviate on, so changing a default moves everyone who has not overridden it.

- **The extra valves** are merged into that same row. A valve switched back to **Default** is withdrawn from it again. Nothing else in the row is touched, so what you configure on the native page survives.
- **Apply** merges that row into every user's `settings.ui`, so a personal choice that disagrees with one of your defaults is overwritten. Settings absent from the row are untouched, and a user who already matches is skipped without a write.
- **Reset** removes every interface settings path this function knows about, configured or not.
- Both buttons untick themselves and run in the background, so **Save** returns immediately. A button ticked while the function is disabled, or left ticked by a crash, is discarded on the next enable or startup rather than firing late.

> [!NOTE]
> `settings.ui` holds a user's whole settings store, so their direct connections, tool servers, pinned models and default model live right next to `chatBubble`. Both buttons operate on an explicit list of interface settings paths and leave everything else alone.

## Components

| File | Type | Install location |
|------|------|-----------------|
| `event.py` | Event | Admin Panel → Functions |

## Setup

<img width="3200" height="2300" alt="1" src="https://github.com/user-attachments/assets/81f59169-bef9-42df-b24c-7254130db3ea" />

1. Copy the contents of `event.py`, or click **Get** on the Community page.
2. In Open WebUI, go to **Admin Panel → Functions → +** (Import/Create).
3. Paste the code and click **Save**, then **Enable** the function.
4. Configure your interface defaults on **Admin Panel → Settings → General → Default Interface Settings** as usual.
5. Open this function's **Valves** for anything that page does not cover, and switch it from **Default** to **Custom**.
6. Tick **Apply defaults to all existing users** and **Save** to bring everyone already on the instance onto those defaults.

## Valves

<img width="3200" height="2300" alt="2" src="https://github.com/user-attachments/assets/7e2fd766-b538-4e2a-a3c2-8f26745cb0eb" />

<img width="3200" height="2300" alt="3" src="https://github.com/user-attachments/assets/f3974233-10bc-4e79-be60-1f87729d5ac2" />

| Setting | What it does |
|-------|--------------|
| **Apply Defaults to All Users** | One-shot. Overwrites every existing user with the settings you configured. |
| **Reset All Users to Factory** | One-shot. Clears every interface setting from every user. |
| **Bulk Write Rate** | Users per second for either pass. Lower is gentler on the database, `0` runs flat out. |
| **🔔 Notifications** | |
| Desktop Notifications | Browser notifications for finished responses. Users still grant the browser permission themselves. |
| Notification Sound | Sound with in-app toast notifications. |
| Notification Sound While Tab Focused | Sound even while the tab is in the foreground. Open WebUI has no toggle for this anywhere. |
| **💬 Interaction** | |
| Keyboard Shortcuts | Shortcuts and the hotkey hints shown in the UI. |
| Memory | The memory feature. |
| System Prompt | The personal system prompt every user starts with. |
| **🔊 Speech & Voice** | |
| Hands-Free Voice Calls | Start voice calls in hands-free conversation mode. |
| Auto-Send After Transcription | Send transcribed voice input as soon as recognition finishes. |
| Auto-Read Responses Aloud | Read every response out loud automatically. |
| Speech-to-Text Engine / Language | Recognition engine and language. |
| Text-to-Speech Voice / Speech Playback Speed / Allow Non-Local Voices | Voice, playback rate, and whether non-local browser voices are offered. |
| **✨ Quick Actions** | |
| Quick Action Buttons (JSON) | Text-selection quick action buttons, for pasting a whole set at once. |

> [!WARNING]
> Both buttons act on **every** user, in chunks, in the background. They untick themselves before the pass starts, so an already-open form may show a button as still ticked until you refresh. If the server restarts mid-pass the remainder is not resumed; tick the button again, repeating is safe.

## Setting the quick-action buttons (JSON)

**Floating Quick Action Buttons** are what Open WebUI pops up when a user **selects text** in a message (out of the box: *Ask* and *Explain*). The native defaults page has a visual editor for these. This valve exists so a whole set can be pasted in one go.

Paste a **JSON array** of button objects, then **Save**. Invalid JSON is ignored, so a typo cannot break anyone.

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

A good default set is 3–5 buttons: too many and the popup gets crowded. A push replaces the whole button list, so keep the config you apply as the complete set you want everyone to have.
