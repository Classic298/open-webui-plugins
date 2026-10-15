# 🤝 Shared Assets Protocol

A community standard that lets any number of Open WebUI plugins add their own JavaScript and CSS to every page, side by side, without overwriting each other.

| | |
|---|---|
| **Author** | [Classic298](https://github.com/Classic298) |
| **Specced with** | G30 (silentoplayz) |
| **Current version** | `ASSET_IMPL_VERSION = 5` |
| **Reference code** | [`shared_assets.py`](shared_assets.py) |
| **License** | [BSD 3-Clause](../LICENSE) |

---

## What it does

Open WebUI loads two files on every page: `/static/loader.js` and `/static/custom.css`. They are the only way for a plugin to change the look or behaviour of the whole interface, and `loader.js` runs before the app itself starts.

There is only one of each file, though. When two plugins both write their code into `loader.js`, the second one wipes out the first. When one plugin is removed, it can take the other plugin's code with it.

This protocol fixes that. Each plugin hands its piece of code (a "fragment") to a shared list kept in the server's memory. Whenever a browser asks for `loader.js` or `custom.css`, the server puts the file together on the spot: whatever is saved on disk first, then every plugin's fragment in a fixed order. Every plugin gets its place, and nobody overwrites anybody.

## Why use it

- **Plugins work together.** Install a theme plugin, a banner plugin and a sidebar plugin at the same time and all three show up.
- **Load order does not matter.** A plugin that starts later simply adds its fragment. No plugin has to know about the others.
- **Nothing is written to disk.** Your hand-written `loader.js` or `custom.css` stays untouched and is served first.
- **Clean on/off.** A plugin turns its code off by returning an empty fragment. The next page load no longer has it.
- **Browsers stay up to date.** The files are served with a fingerprint (ETag), so a browser gets the new version as soon as anything changes, and a cheap "nothing changed" answer otherwise.
- **The whole community converges on one version.** When several plugins carry different copies of the code, the newest copy runs for everyone.

## How it works

1. Your plugin registers a fragment together with a function that returns the fragment's code (the **producer**). The fragment is stored under your plugin's Open WebUI id (the **key**), which the block reads by itself.
2. The first plugin to register replaces Open WebUI's static route for that file with a shared route. Later plugins find the route already there and only add their fragment.
3. On every request for the file, the shared route reads the file from disk, adds every fragment in order and sends the result.
4. If a plugin ships a newer copy of the protocol code (a higher `ASSET_IMPL_VERSION`), its route replaces the older one. The fragments are kept, so nothing gets lost along the way.

The list lives in the memory of each Open WebUI process. With several containers or workers, each one serves the fragments of the plugins it has loaded.

## How to use it

1. Copy everything in [`shared_assets.py`](shared_assets.py) into your plugin **byte for byte**. Do not reformat it and do not rename anything. Every plugin ships the same copy, and whichever copy runs serves everybody.
2. Pick two marker comments that wrap your code. You do not pick a key: the block uses your plugin's Open WebUI id, and Open WebUI never gives two plugins the same id.
3. Register your fragment from your plugin's event handler, where Open WebUI passes the app as `__app__`:

```python
LOADER_BLOCK_START = "// my-plugin:start"
LOADER_BLOCK_END = "// my-plugin:end"

asset_register(
    __app__,
    LOADER_PATH,            # or CUSTOM_CSS_PATH for CSS
    LOADER_BLOCK_START,
    LOADER_BLOCK_END,
    self._loader_fragment,  # returns the code as a string
    order=0,
)
```

4. Make the producer cheap. It runs on every page load, so build the string once and return the stored copy.
5. To switch your code off, have the producer return `""`.

[Better Banners](../better-banners/) is a complete example.

## The rules

| Rule | Why |
|---|---|
| Keep the copied block byte-identical. | Only one copy serves everyone. A changed copy silently changes the behaviour of every other plugin. |
| Do not set a key yourself. | The block keys your fragment by your plugin's Open WebUI id. Ids are unique, so no plugin can overwrite another's fragment. A clone of your plugin gets its own id and its own fragment, so guard JS that must run only once, for example with a `window` flag. Each plugin has one fragment per file, so keep all of your JS in one fragment and all of your CSS in another. |
| Use `order` to sort. | Lower `order` comes first. In `custom.css` that means later plugins win conflicts; in `loader.js` it means running first. The default is `0`. |
| Keep the producer fast. | It runs for every page load, even when the browser already has the latest file. Return a prepared string, and cache anything slow (file checks, network, locks) so a call costs microseconds. |
| Return `""` to switch off. | There is no way to unregister. Open WebUI tells a plugin when it is being disabled, but a deleted plugin never finds out, so disable a plugin before deleting it or its code stays until the server restarts. |
| Put your code inline. | Loading another file with `<script src>` or `@import` arrives too late, after the app has already started. |
| It covers the main app only. | Pages that a plugin serves on its own do not load these files and need their own code. |

## Optional: update every container instantly

With several Open WebUI containers or workers, a change to your plugin does not reach all of them. Open WebUI keeps each plugin's code in memory per container and does not tell the other containers when something changes:

- **Saving new code:** only the container you saved on loads it right away. Every other container keeps running the old code, and keeps serving the old fragment, until some event happens to fire on it. On a quiet container that can take a long time.
- **Changing valves:** the same. Other containers keep the old settings until their next event.
- **Disabling the plugin:** the other containers never find out. A disabled plugin gets no events there, so its fragment keeps being served until that container restarts.

The optional [`live_reload.py`](live_reload.py) add-on makes all three reach every container within a second. Whenever the plugin loads, is disabled or enabled, or has its valves saved, it tells every other container over Redis. Each one then loads the new code if its copy differs from the database, picks up the new valves and switches the fragment off or on to match. A code update needs no build number. [Better Banners](../better-banners/) uses it.

Without Redis the add-on does nothing extra. It needs Open WebUI 0.11.0 or newer.

The add-on is separate from the protocol itself and does not change `ASSET_IMPL_VERSION`. Everything in it is scoped to your own plugin, so your copy never affects anybody else's. It has its own `RELOAD_IMPL_VERSION` for the Redis listener: raise it by one whenever you change the listener, and running containers swap the old listener for the new one on the next load instead of keeping it until a restart.

1. Copy everything in [`live_reload.py`](live_reload.py) into your event function, above the shared asset block.
2. Put your `asset_register` calls into a function called `register(app)` and let each producer return `""` when `reload_active(app)` is false.
3. Wire it into your event class:

```python
def register(app):
    asset_register(
        app,
        LOADER_PATH,
        LOADER_BLOCK_START,
        LOADER_BLOCK_END,
        lambda: LOADER_FRAGMENT if reload_active(app) else "",
    )


class Event:
    def __init__(self):
        reload_bootstrap()

    async def event(self, event=None, __event_name__=None, __app__=None):
        if __app__ is not None:
            await reload_on_event(__app__, event, __event_name__)
```

## Changing the protocol

Any change to the protocol code has to bump `ASSET_IMPL_VERSION` by one, and the new block replaces the old one here first. Plugins that update their copy then take over the route from older copies automatically. Open an issue or a pull request in this repository to propose a change, so every adopter can follow it.

## Adopters

Using the protocol in your plugin? Open a pull request and add yourself here.

| Author | Repository |
|---|---|
| [Classic298](https://github.com/Classic298) | [Classic298/open-webui-plugins](https://github.com/Classic298/open-webui-plugins) |
| [G30 (silentoplayz)](https://github.com/silentoplayz) | [silentoplayz/theme-designer-pro-presets](https://github.com/silentoplayz/theme-designer-pro-presets) |
