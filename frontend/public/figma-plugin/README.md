# VelocityAI Importer — Figma Plugin

This plugin creates real Figma frames from a `*-figma.json` file exported by VelocityAI.

## Installation (one-time)

1. Open Figma Desktop (the plugin API requires the desktop app).
2. Menu → **Plugins → Development → Import plugin from manifest…**
3. Navigate to this folder and select **`manifest.json`**.
4. The plugin appears under **Plugins → Development → VelocityAI Importer**.

## Usage

1. In VelocityAI, run a **Prototype** workflow and wait for it to complete.
2. In the **Files** tab, click **Download Figma Design** — saves a `<name>-figma-export.zip` file.
3. Unzip the file. Inside you'll find your JSON file and this plugin folder.
4. Open Figma, run **Plugins → Development → VelocityAI Importer**.
5. Drop or browse to the JSON file and click **Import to Figma**.

Figma will create one frame per screen on the current page.

## Notes

- The plugin requires **Figma Desktop** (not the browser version) because it
  uses the Figma Plugin API to create nodes directly in your file.
- Layout is approximated from DOM order. You may need to adjust spacing and
  sizes after import.
- SVG icons and images are imported as grey placeholder rectangles — replace
  them with your Figma icon components and actual images.
- The plugin only reads the JSON file you provide. It does not access the
  network or any VelocityAI service.
