# 📣 Better Banners

<img width="6400" height="1600" alt="banner-better-banners" src="https://github.com/user-attachments/assets/6296f5ce-2ec9-4df4-aab4-628585ca7124" />

Makes the banners you already manage in **Admin Panel → Settings → General → Banners** reach your users properly: in every chat, at the top of the page or right above the message input, collapsible and dismissible, updated live and shown in each user's language.

---

## ✨ Features

| Feature | What you get |
|---|---|
| 📍 **Two positions** | Show banners at the top of the chat or right above the message input. |
| 💬 **In every chat** | Open WebUI shows banners only on the new chat screen. Better Banners keeps them visible inside every chat. |
| 🔽 **Collapsible** | One small pill sits at the edge of the banners and shows how many there are. Clicking it collapses all banners into it. Clicking it again brings them back. The choice is remembered, and a new or edited banner expands them again for everyone. |
| ✖️ **Dismissible** | Banners with **Dismissible** turned on get a close button and stay gone for that user. Inside chats, banners without it cannot be closed, only collapsed. |
| ⚡ **Live updates** | Add, edit or remove a banner and every open tab updates within about 2 seconds, without a reload. |
| 🌍 **Translations** | Banner translations you set in the admin panel are shown in each user's language. |
| 🎨 **Sleek design** | Frosted, color-coded cards for Info, Success, Warning and Error that follow light and dark mode. |
| 📝 **Formatting** | Markdown (**bold**, *italic*, `code`, lists, headings, links) or HTML with inline styles, like Open WebUI's own banners. |
| 🤝 **Plays well with others** | Built on the [Shared Assets Protocol](../shared-assets-protocol/), so it runs side by side with other plugins that add code to Open WebUI. |

---

## 📸 Screenshots

<p align="center"><img width="1952" height="580" alt="better-banners-toggle-animation" src="https://github.com/user-attachments/assets/9e60206a-4232-4e3b-9873-f91501f33317" /></p>

| Expanded, at the top | Collapsed into the pill |
|---|---|
| <img width="2800" height="1800" alt="better-banners-toggle-top-light" src="https://github.com/user-attachments/assets/64b49547-caa5-40d1-a82d-ab465902ad9a" /> | <img width="2800" height="1800" alt="better-banners-toggle-top-collapsed-light" src="https://github.com/user-attachments/assets/a69258d9-7b7d-4bdd-b5bc-53228f4812b6" /> |
| **Right above the message input** | **On a phone, expanded and collapsed** |
| <img width="2800" height="1800" alt="better-banners-toggle-bottom-dark" src="https://github.com/user-attachments/assets/2e3a1997-60a0-4f3c-80bb-183ad1e4ab09" /> | <img width="260" alt="better-banners-toggle-phone-top-light" src="https://github.com/user-attachments/assets/7120c83f-6559-42e0-88b7-af054c4a0a49" /> <img width="260" alt="better-banners-toggle-phone-bottom-dark-collapsed" src="https://github.com/user-attachments/assets/6e6b92d4-c4b9-4563-a8e7-3adbc9ccd19e" /> |

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

Your banners now show up in the new style inside every chat. Manage them as before under **Admin Panel → Settings → General → Banners**.

---

## ⚙️ Settings

Open **Admin Panel → Functions → Better Banners → gear icon**.

| Valve | Default | What it does |
|---|---|---|
| **Position** | `top` | `top` shows banners at the top of the chat, `bottom` right above the message input. |
| **Max Height Px** | 160 | How tall a single expanded banner gets before its text scrolls. |
| **Resync Interval Seconds** | 300 | How often each open tab re-reads the banners on its own, in case it missed a live update. 0 turns it off. |

Changed settings reach users on their next page load. With several workers or containers and Redis, every one of them picks up a code change, a settings change or a disable within a second.

---

## 🧭 How it behaves

- **The new chat screen** keeps Open WebUI's own banners, including the Enterprise license notices. Better Banners takes over once a chat is open, with its own collapse and dismiss.
- **New and edited banners** always open expanded. A user can collapse them into the pill, and they stay collapsed until you add or change a banner.
- **Dismissing** uses the same memory as Open WebUI's own banners, so banners a user closed before stay closed, and switching the function off keeps their choices.
- **Language** follows the language each user picked in Open WebUI. When a banner has no translation for it, the main text is shown.

---

## 🧰 Troubleshooting

<details>
<summary><b>Banners still look like the default ones</b></summary>

On the new chat screen this is expected. Open WebUI shows its own banners there. Inside a chat, reload the page. The new style loads with the page, so tabs that were open while you installed the function keep the old look until they reload.
</details>

<details>
<summary><b>An edit took a while to show up</b></summary>

Live updates ride on Open WebUI's WebSocket connection. With `ENABLE_WEBSOCKET_SUPPORT` turned off, or several workers without Redis, a tab catches up at its next resync (5 minutes by default) or when you switch back to it.
</details>

<details>
<summary><b>Can banners use HTML?</b></summary>

Yes, like Open WebUI's own banners. Formatting tags and inline styles are kept, so a banner designed in HTML looks the same. Scripts, event handlers, frames and unsafe links are removed.
</details>

<details>
<summary><b>The banners are still there after I deleted the function</b></summary>

Turn the function off before deleting it. A deleted function cannot tell the server to stop serving its code, so it stays until the next restart.
</details>

---

## ⚠️ Limits

- Banners show in chats. Other pages (Workspace, Admin Panel, Notes) show none.
- The pill and dismiss buttons are labelled in English. The banner text itself follows each user's language.
- With several servers that do not share a data folder, turning the function off takes effect on each of the other servers after its next restart.

---

## 🙏 Credits

Inspired by [Broadcast Toasts](https://openwebui.com/posts/e3b3e715-1312-4b46-8b74-94aef3e681b5) by [G30](https://openwebui.com/u/g30) ([@silentoplayz](https://github.com/silentoplayz) on GitHub).
