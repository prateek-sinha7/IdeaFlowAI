"""Theme and tier helpers for screens/17-theme-and-tiers.feature.md.

**The menu control is labelled "Dark mode" in BOTH states** — it names the
target, not the current theme. Read `data-theme` to know which theme is active;
a test that reads the menu text always sees the same string.

The attribute is ABSENT until something sets it, so every read here normalises
a missing value to "light".
"""

from __future__ import annotations

THEME = "() => document.documentElement.getAttribute('data-theme') || 'light'"
BODY_BG = "() => getComputedStyle(document.body).backgroundColor"

BACKGROUNDS = {"light": "rgb(240, 238, 231)", "dark": "rgb(13, 13, 13)"}

# There are FOUR tiers and they are not a chain. `hexaware` gains prototype over
# basic and LOSES ppt, and UPGRADE_PATH sends it straight to enterprise. Any
# assertion shaped "higher tier ⇒ superset" is wrong about the one tier that
# matters — see D-16.
TIERS = ["basic", "pro", "enterprise", "hexaware"]

PLANS = {"basic": "Basic", "pro": "Pro", "enterprise": "Enterprise"}


def read(page) -> str:
    return page.evaluate(THEME)


def set_theme(page, want: str, open_menu, menu_item) -> None:
    """Toggle until `data-theme` reads `want`. No-op if it already does."""
    if read(page) == want:
        return
    open_menu(page)
    menu_item(page, "Dark mode").click()
    page.wait_for_function(
        f"() => (document.documentElement.getAttribute('data-theme') || 'light') === '{want}'"
    )
    # The menu stays open after the toggle. Left open, the next `open_menu`
    # clicks the trigger again and CLOSES it, and the caller then waits for a
    # menu that just went away.
    page.keyboard.press("Escape")


def unreadable_text(page) -> list[str]:
    """Visible text nodes whose colour matches the background they sit on.

    Walks up for the first ancestor with a non-transparent background, because
    most elements are transparent and comparing against `transparent` would
    flag everything or nothing.
    """
    return page.evaluate(
        """() => {
             const bgOf = el => {
               for (let n = el; n; n = n.parentElement) {
                 const bg = getComputedStyle(n).backgroundColor;
                 if (bg && bg !== 'transparent' && !bg.startsWith('rgba(0, 0, 0, 0)')) return bg;
               }
               return getComputedStyle(document.body).backgroundColor;
             };
             const out = [];
             for (const el of document.querySelectorAll('h1,h2,h3,h4,p,span,button,a,label,td,th')) {
               if (!el.textContent.trim() || el.children.length) continue;
               const r = el.getBoundingClientRect();
               if (r.width < 1 || r.height < 1) continue;
               const s = getComputedStyle(el);
               if (s.visibility === 'hidden' || s.opacity === '0') continue;
               if (s.color === bgOf(el)) out.push(el.textContent.trim().slice(0, 40));
             }
             return [...new Set(out)].slice(0, 10);
           }"""
    )
