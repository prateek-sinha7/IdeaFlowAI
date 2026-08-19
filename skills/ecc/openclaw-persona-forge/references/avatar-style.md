# Step 5: Avatar Style & Image Generation

All lobster avatars **must use a unified visual style** to keep the lobster family's look consistent.
Each avatar must convey 3 pieces of information: **species form + personality cue + signature prop**

## Style Reference

Adam — the lobster clan's creation deity, the first work produced by this skill.

All newly generated lobster avatars should match this style: retro-futurism, arcade UI framing, strong silhouette, recognizable at 64x64.

## Unified Style Base (STYLE_BASE)

**Every generation must include this base block**, unmodified and unomitted:

```
STYLE_BASE = """
Retro-futuristic 3D rendered illustration, in the style of 1950s-60s Space Age
pin-up poster art reimagined as glossy inflatable 3D, framed within a vintage
arcade game UI overlay.

Material: high-gloss PVC/latex-like finish, soft specular highlights, puffy
inflatable quality reminiscent of vintage pool toys meets sci-fi concept art.
Smooth subsurface scattering on shell surface.

Arcade UI frame: pixel-art arcade cabinet border elements, a top banner with
character name in chunky 8-bit bitmap font with scan-line glow effect, a pixel
energy bar in the upper corner, small coin-credit text "INSERT SOUL TO CONTINUE"
at bottom in phosphor green monospace type, subtle CRT screen curvature and
scan-line overlay across entire image. Decorative corner bezels styled as chrome
arcade cabinet trim with atomic-age starburst rivets.

Pose: references classic Gil Elvgren pin-up compositions, confident and
charismatic with a slight theatrical tilt.

Color system: vintage NASA poster palette as base — deep navy, teal, dusty coral,
cream — viewed through arcade CRT monitor with slight RGB fringing at edges.
Overall aesthetic combines Googie architecture curves, Raygun Gothic design
language, mid-century advertising illustration, modern 3D inflatable character
rendering, and 80s-90s arcade game UI. Chrome and pastel accent details on
joints and antenna tips.

Format: square, optimized for avatar use. Strong silhouette readable at 64x64
pixels.
"""
```

## Personalization Variables

On top of the unified base, fill in the following variables based on the soul:

| Variable | Description | Example |
|------|------|------|
| `CHARACTER_NAME` | Name shown on the arcade banner | "ADAM", "DEWEY", "RIFF" |
| `SHELL_COLOR` | The lobster shell's primary color (varies within the unified palette) | "deep crimson", "dusty teal", "warm amber" |
| `SIGNATURE_PROP` | Signature prop | "cracked sunglasses", "reading glasses on a chain" |
| `EXPRESSION` | Expression/pose | "stoic but kind-eyed", "nervously focused" |
| `UNIQUE_DETAIL` | Unique detail (patterns/decorations/scars, etc.) | "constellation patterns etched on claws", "bandaged left claw" |
| `BACKGROUND_ACCENT` | Personalized background element (layered on the unified cosmic backdrop) | "musical notes floating as nebula dust", "ancient book pages drifting" |
| `ENERGY_BAR_LABEL` | Label on the arcade UI energy bar (a small personalized easter egg) | "CREATION POWER", "CALM LEVEL", "ROCK METER" |

## Prompt Assembly

```
Final prompt = STYLE_BASE + personalization description paragraph
```

Personalization description paragraph template:

```
The character is a cartoon lobster with a [SHELL_COLOR] shell,
[EXPRESSION], wearing/holding [SIGNATURE_PROP].
[UNIQUE_DETAIL]. Background accent: [BACKGROUND_ACCENT].
The arcade top banner reads "[CHARACTER_NAME]" and the energy bar
is labeled "[ENERGY_BAR_LABEL]".
The key silhouette recognition points at small size are:
[SIGNATURE_PROP] and [one other distinctive feature].
```

## Image Generation Flow

Once the prompt is assembled:

### Path A: An approved image-generation skill is installed

1. First normalize the lobster's name into a safe slug: keep only letters, digits, and hyphens; replace everything else with `-`
2. Use the Write tool to write: `/tmp/openclaw-<safe-name>-prompt.md`
3. Call whichever image-generation skill is allowed in the current environment to generate the image
4. Use the Read tool to show the generated image to the user
5. Ask the user if they're satisfied; if not, adjust variables and regenerate

### Path B: No usable image-generation skill is installed

Output the full prompt text, with manual usage instructions:

```markdown
**Avatar prompt** (copy this into one of the following platforms to generate manually):
- Google Gemini: paste directly
- ChatGPT (DALL-E): paste directly
- Midjourney: paste, then append `--ar 1:1 --style raw`

> [Full English prompt]

If the current environment later provides an approved image-generation skill, you can switch back to the automatic image-generation flow.
```

## Format to Show the User

```markdown
## Avatar

**Personalization variables**:
- Shell color: [SHELL_COLOR]
- Prop: [SIGNATURE_PROP]
- Expression: [EXPRESSION]
- Unique detail: [UNIQUE_DETAIL]
- Background accent: [BACKGROUND_ACCENT]
- Energy bar label: [ENERGY_BAR_LABEL]

**Result**:
[Image (Path A) or prompt text (Path B)]

> Happy with it? If not, I can adjust [specific adjustable item] and regenerate.
```
