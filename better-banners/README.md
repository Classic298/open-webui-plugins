# 📣 Better Banners

<img width="6400" height="1600" alt="banner-better-banners" src="https://github.com/user-attachments/assets/6296f5ce-2ec9-4df4-aab4-628585ca7124" />

Makes the banners you already manage in **Admin Panel → Settings → General → Banners** reach your users properly: in every chat, at the top of the page or right above the message input, collapsible and dismissible, updated live and shown in each user's language.

---

## ✨ Features

| Feature | What you get |
|---|---|
| 📍 **Two positions** | Show banners at the top of the chat or right above the message input. |
| 💬 **In every chat** | Open WebUI only shows banners on the new chat screen. Here they stay visible in every chat (or only on new chats, if you prefer). |
| 🔽 **Collapsible** | One click collapses all banners into a small pill that shows how many there are. Clicking the pill brings them back. The choice is remembered, and a new or edited banner expands them again for everyone. |
| ✖️ **Dismissible** | Banners with **Dismissible** turned on get a close button and stay gone for that user. Banners without it cannot be closed, only collapsed. |
| ⚡ **Live updates** | Add, edit or remove a banner and every open tab updates within about 2 seconds, without a reload. |
| 🌍 **Translations** | Banner translations you set in the admin panel are shown in each user's language. |
| 🎨 **Sleek design** | Frosted, color-coded cards for Info, Success, Warning and Error that follow light and dark mode. |
| 📝 **Formatting** | A small set of Markdown in the banner text: **bold**, *italic*, `code`, lists, headings and links. |
| 🤝 **Plays well with others** | Built on the [Shared Assets Protocol](../shared-assets-protocol/), so it runs side by side with other plugins that add code to Open WebUI. |

---

## 📸 Screenshots

| At the top of the chat | Right above the message input |
|---|---|
| <img width="2800" height="1800" alt="better-banners-top-light" src="https://github.com/user-attachments/assets/74f21bbc-26ef-4d30-93db-8f50db00c9ad" /> | <img width="2800" height="1800" alt="better-banners-bottom-dark" src="https://github.com/user-attachments/assets/a9ca576d-fe5b-408a-9812-6afb4c5e41bd" /> |
| **Collapsed into the pill, at the top** | **Collapsed into the pill, above the input** |
| <img width="2800" height="1800" alt="better-banners-pill-top-light" src="https://github.com/user-attachments/assets/63d7aa03-8c1b-4dae-9ccc-2be9ad9a40ce" /> | <img width="2800" height="1800" alt="better-banners-pill-bottom-dark" src="https://github.com/user-attachments/assets/9083ff5c-2aa3-4e87-8917-7bfd9dbceed7" /> |
| **In each user's language** | |
| <img width="2800" height="1800" alt="better-banners-i18n-de" src="https://github.com/user-attachments/assets/e529aaf1-62f3-4b1e-9544-616c87efa6c7" /> | |

---

## 📦 Components

| File | Type | Install location |
|------|------|-----------------|
| `event.py` | Event | Admin Panel → Functions |

---

## 🚀 Setup

1. Copy the contents of `event.py`
2. In Open WebUI: **Admin Panel → Functions → + New Function**
3. Paste, **Save**, and switch the function **on**
4. Reload the page once

Your banners now show up in the new style. Manage them as before under **Admin Panel → Settings → General → Banners**.

---

## ⚙️ Settings

Open **Admin Panel → Functions → Better Banners → gear icon**.

| Valve | Default | What it does |
|---|---|---|
| **Position** | `top` | `top` shows banners at the top of the chat, `bottom` right above the message input. |
| **New Chat Only** | Off | On shows banners only on the new chat screen, like Open WebUI does on its own. |
| **Max Height Px** | 160 | How tall a single expanded banner gets before its text scrolls. |
| **Resync Interval Seconds** | 300 | How often each open tab re-reads the banners on its own, in case it missed a live update. 0 turns it off. |

Changed settings reach users on their next page load. With several workers, each worker picks them up the next time it handles any event.

---

## 🧭 How it behaves

- **New and edited banners** always open expanded. A user can collapse them into the pill, and they stay collapsed until you add or change a banner.
- **Dismissing** uses the same memory as Open WebUI's own banners, so banners a user closed before stay closed, and switching the function off keeps their choices.
- **Language** follows the language each user picked in Open WebUI. When a banner has no translation for it, the main text is shown.

---

## 🧰 Troubleshooting

<details>
<summary><b>Banners still look like the default ones</b></summary>

Reload the page. The new style loads with the page, so tabs that were open while you installed the function keep the old look until they reload.
</details>

<details>
<summary><b>An edit took a while to show up</b></summary>

Live updates ride on Open WebUI's WebSocket connection. With `ENABLE_WEBSOCKET_SUPPORT` turned off, or several workers without Redis, a tab catches up at its next resync (5 minutes by default) or when you switch back to it.
</details>

<details>
<summary><b>HTML in a banner shows up as text</b></summary>

Banner text supports Markdown formatting. HTML is shown as plain text on purpose.
</details>

<details>
<summary><b>The banners are still there after I deleted the function</b></summary>

Turn the function off before deleting it. A deleted function cannot tell the server to stop serving its code, so it stays until the next restart.
</details>

---

## ⚠️ Limits

- Banners show in chats. Other pages (Workspace, Admin Panel, Notes) show none.
- On Enterprise instances, the "Trial License" and "Exceeded the number of seats" notices share the spot of the built-in banners, so they are hidden too while the function is on.
- The collapse, expand and dismiss buttons are labelled in English. The banner text itself follows each user's language.
- With several servers that do not share a data folder, turning the function off takes effect on each of the other servers after its next restart.

---

## 🙏 Credits

Inspired by [Broadcast Toasts](https://openwebui.com/posts/e3b3e715-1312-4b46-8b74-94aef3e681b5) by [G30](https://openwebui.com/u/g30) ([@silentoplayz](https://github.com/silentoplayz) on GitHub).
