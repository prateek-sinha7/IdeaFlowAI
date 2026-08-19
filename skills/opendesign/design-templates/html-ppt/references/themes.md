# Themes catalog

Every theme is a short CSS file in `assets/themes/` that overrides tokens
defined in `assets/base.css`. Switch themes by changing the `href` of
`<link id="theme-link">` or by pressing **T** if the deck has a
`data-themes="a,b,c"` attribute on `<body>` or `<html>`.

All themes define the same variables: `--bg`, `--bg-soft`, `--surface`,
`--surface-2`, `--border`, `--text-1/2/3`, `--accent`, `--accent-2/3`,
`--good`, `--warn`, `--bad`, `--grad`, `--grad-soft`, `--radius*`, `--shadow*`,
`--font-sans`, `--font-display`.

## Light & calm

| name | description | when to use |
|---|---|---|
| `minimal-white` | Minimalist white, restrained and refined. Inter font, strong text hierarchy, very subtle shadows. | Internal reports, 1:1 technical reviews, serious topics that shouldn't compete with the content |
| `editorial-serif` | Magazine style, Playfair serif + cream background. | Brand storytelling, text-dense long-form talks |
| `soft-pastel` | Soft macaron three-color gradient. | Product launches, consumer-facing content, lighthearted topics |
| `xiaohongshu-white` | White background in the style of Xiaohongshu (RED) social posts, warm-red accent, serif headlines. | Xiaohongshu (RED) image-and-text posts, lifestyle/aesthetic content |
| `solarized-light` | Classic low-glare color scheme. | Workshops and teaching sessions viewed for long periods |
| `catppuccin-latte` | Catppuccin light palette. | Developer- and geek-friendly technical talks |

## Bold & statement

| name | description | when to use |
|---|---|---|
| `sharp-mono` | Pure black and white + Archivo Black + hard shadows. | Manifesto-style content, high-impact visuals |
| `neo-brutalism` | Thick outlines, hard shadows, bright-yellow accent. | Startup pitches, bold and confident tone |
| `bauhaus` | Geometric shapes + primary red/yellow/blue. | Design talks, art-history/product-aesthetics topics |
| `swiss-grid` | Swiss grid + Helvetica feel + 12-column underlay. | Serious typography, design industry |
| `memphis-pop` | Memphis-pop dotted background + bold headline type. | Youthful, trendy, brand collaborations |

## Cool & dark

| name | description | when to use |
|---|---|---|
| `catppuccin-mocha` | Catppuccin dark palette. | Internal developer talks, long viewing sessions |
| `dracula` | Classic Dracula purple/red primary colors. | Code-heavy technical talks |
| `tokyo-night` | Tokyo Night blue-night palette. | Cooler-toned technical talks, infrastructure |
| `nord` | Nordic cool blue-and-white. | Infrastructure, cloud products |
| `gruvbox-dark` | Warm retro dark theme. | Terminal / vim / *nix communities |
| `rose-pine` | Rosé Pine, soft dark palette. | Where design meets development, aesthetics-forward technical content |
| `arctic-cool` | Blue/cyan/slate-gray light palette. | Business analysis, finance, calm and rational tone |

## Warm & vibrant

| name | description | when to use |
|---|---|---|
| `sunset-warm` | Orange / coral / amber three-color gradient. | Lifestyle content, award ceremonies, upbeat and positive tone |

## Effect-heavy

| name | description | when to use |
|---|---|---|
| `glassmorphism` | Frosted glass + multicolor light-blob background. | Apple-style keynotes, product feature showcases |
| `aurora` | Aurora gradient + blur + saturate. | Cover / CTA / closing pages |
| `rainbow-gradient` | White background + flowing rainbow gradient accent. | Cheerful, festive, celebration pages |
| `blueprint` | Engineering blueprint + grid underlay + montage-style type. | System architecture, engineering blueprints |
| `terminal-green` | Green-screen terminal + monospace + glowing text. | CLI / black-hat / retro-punk aesthetics |

## v2 additions

### Light & professional

| name | description | when to use |
|---|---|---|
| `corporate-clean` | Pure white + navy-blue accent + Inter + conservative borders. | Board reports, B2B sales, finance and insurance |
| `pitch-deck-vc` | YC-style white background + blue-purple gradient accent + generous whitespace. | Fundraising pitches, seed rounds, VC meetings |
| `academic-paper` | Paper white + serif body text + black ink + blue links. | Academic reports, research talks, conference papers |
| `japanese-minimal` | Ivory white + vermilion accent + very generous whitespace + Noto Serif. | Brand refreshes, artisan/craft stories, zen-inspired narratives |
| `engineering-whiteprint` | White background + graph-paper grid + navy ink lines + monospace font. | System design, API documentation, architecture whitepapers |

### Bold & editorial

| name | description | when to use |
|---|---|---|
| `magazine-bold` | Cream background + oversized Playfair serif + orange spot color. | Column articles, cover stories, brand magazines |
| `news-broadcast` | White background + red vertical bar + uppercase Oswald + hard shadows. | Breaking news, press releases, data broadcasts |
| `midcentury` | Cream background + mustard/teal/burnt-orange + sharp geometry. | Design history, home-aesthetics content, retro branding |
| `retro-tv` | Warm cream + CRT scanlines + amber-orange accent. | Nostalgic storytelling, 80s/90s-themed topics |

### Effect-heavy / dramatic

| name | description | when to use |
|---|---|---|
| `cyberpunk-neon` | Pure black + neon pink/cyan/yellow + glow effects + JetBrains Mono. | Hacker culture, underground scenes, cyberpunk talks |
| `vaporwave` | Deep purple + pink-cyan-blue gradient + blurred light blooms. | Music, trend-driven art, A E S T H E T I C content |
| `y2k-chrome` | Silver-chrome gradient + rainbow accent + large rounded corners + Space Grotesk. | Y2K nostalgia, fashion brands, Gen-Z audiences |

## How to apply

```html
<link rel="stylesheet" id="theme-link" href="../assets/themes/aurora.css">
```

Or enable `T`-cycling by listing themes on the body:

```html
<body data-themes="minimal-white,aurora,catppuccin-mocha" data-theme-base="../assets/themes/">
```

## How to extend

Copy an existing theme, rename it, and override only the variables you want to
change. Keep each theme under ~200 lines. Prefer adjusting tokens to adding
new selectors.
