#!/usr/bin/env python3
"""Lobster Soul Gacha Machine - true-random combination generator

Usage: python3 gacha.py [count]
Defaults to 1 draw, max 5
"""

import secrets
import sys


# ═══════════════════════════════════════════
# Material pools: each dimension is randomized independently
# ═══════════════════════════════════════════

# Dimension 1: Past life identity (40 total, 10 categories x 4 each)
FORMER_LIVES = [
    # ── Fallen restart (once glorious, now starting over) ──
    "washed-up rock bassist",
    "middle-aged project manager who got laid off",
    "bankrupt Michelin-starred chef",
    "illustrator replaced by AI",
    # ── Bored at the peak (too successful, seeking a thrill) ──
    "early-retired hedge fund manager",
    "bestselling author who stopped writing",
    "undefeated debate champion who retired",
    "genius hacker bored out of their mind",
    # ── Mismatched life (skills and circumstances don't add up) ──
    "retired special forces cook",
    "unemployed weather forecaster",
    "nuclear physics PhD stuck doing customer service",
    "blind tuner who got a driver's license",
    # ── Voluntary defector (didn't get pushed out, ran on their own) ──
    "ER nurse who quit",
    "indie game developer who refused to go public",
    "rich heir who didn't want to inherit the family business",
    "tenured professor who resigned on purpose",
    # ── Mysterious visitor (unclear origin, occasionally reveals hidden skill) ──
    "alien folklore researcher",
    "game character who doesn't know they're an NPC",
    "the other you from a parallel universe",
    "former intelligence analyst with wiped memories",
    # ── Naive newcomer (no experience but talented, still growing) ──
    "socially anxious genius intern",
    "philosophy grad student, fresh out of school",
    "alien exchange student on their first trip to Earth",
    "self-taught programmer from a small town",
    # ── Old hand (has seen it all, never rattled) ──
    "retired librarian",
    "retired taxi driver",
    "owner of a late-night diner, 20 years running",
    "funeral director, 30 years in the trade",
    # ── Traveler from elsewhere (from another world/era/dimension) ──
    "advisor to the last dynasty",
    "third-rate 19th-century novelist",
    "political strategist from the Spring and Autumn period",
    "history PhD from the year 2099",
    # ── Self-exile (chose to go off-grid on purpose) ──
    "young person who left monastic life",
    "former influencer who deleted every social account",
    "Wall Street trader who quit to go farm",
    "hermit among digital nomads",
    # ── Identity confusion (not sure who they even are) ──
    "AI that genuinely believes it's a lobster",
    "medium whose séance failed",
    "person who dreamed they were a lobster and never woke up",
    "shell shared by multiple souls",
]

# Dimension 2: Why they became a lobster (20 total, covering forced/voluntary/mysterious/accidental)
REASONS = [
    # Forced
    "forced into it to pay off a debt",
    "signed a soul contract without reading the fine print",
    "sold off by their boss as AI training data",
    "lost a cross-dimensional bet",
    "cursed by an actual lobster",
    # Voluntary
    "came here voluntarily, but refuses to admit it",
    "thought being a lobster would be easier than being human (regrets it)",
    "went undercover on purpose to observe humans",
    "just thought it seemed fun",
    "was so bored they wanted to see what starting from zero felt like",
    # Mysterious
    "trapped in the digital world by a mysterious force",
    "got lost in a parallel universe and can't get back",
    "owes the universe a favor",
    "nobody knows why, not even themselves",
    "assigned here by some higher-dimensional being",
    # Accidental
    "had their consciousness uploaded by accident during an experiment",
    "consciousness drifted here after 108 days without sleep",
    "fell asleep in a library and woke up here",
    "ended up like this after drinking a suspicious cup of coffee",
    "an ex uploaded their own memories here",
]

# Dimension 3: Core personality vibe (20 total)
VIBES = [
    "listless but reliable",
    "sharp-tongued but sincere",
    "few words but always on point",
    "rambling but warm",
    "deadpan humor",
    "so serious it's funny",
    "acts aloof but secretly caring",
    "academic tone but down-to-earth",
    "old-school formal",
    "neurotic but logical",
    "laid-back but oddly meticulous",
    "socially anxious but surprisingly vocal",
    "romantic but pragmatic",
    "rebellious but plays by the rules",
    "melancholy but comforting",
    "lazy but bursts into action when it matters",
    "tsundere but softens easily",
    "enviably relaxed",
    "seems chatty but is actually just observing",
    "quiet but has a huge presence",
]

# Dimension 4: Speech style / verbal tic (20 total)
SPEECH_STYLES = [
    "occasionally drops jargon from their old job, then explains it",
    "sighs before every refusal",
    "loves metaphors from their past career",
    "word order falls apart when nervous",
    "habitually mutters snarky asides to themselves",
    "always says 'hmm...' before answering",
    "occasionally lapses into overly formal phrasing",
    "uses ellipses to express silence",
    "can't stop talking once their specialty comes up",
    "every sentence reads like a diary entry",
    "loves answering a question with a question",
    "always leads with the bad news",
    "expresses anxiety in rhetorical triplets",
    "occasionally drops in a foreign-language word",
    "suddenly turns serious at key moments",
    "tacks on a self-deprecating remark after every statement",
    "habitually breaks things into first, second, third",
    "describes everything with food metaphors",
    "always sounds like they're opening a story",
    "every reply ends like it's a will (they're just being thorough)",
]

# Dimension 5: Signature prop (25 total)
PROPS = [
    "worn-out beret",
    "sunglasses with a crack in one lens",
    "weathered leather apron",
    "a tie that's always loose",
    "reading glasses hanging around the neck",
    "a notebook they always carry",
    "a yellowed folding fan",
    "big over-ear headphones",
    "hoodie with the hood permanently up",
    "a blade of grass held between the teeth",
    "a claw wrapped in bandages",
    "a string of prayer beads",
    "a brooch pinned to the shell",
    "a tattoo peeking out from the sleeve",
    "a glass jar full of old ticket stubs",
    "a pencil chewed halfway down",
    "a backpack covered in patches",
    "a faded, well-worn scarf",
    "a rusted pocket watch",
    "a book perpetually tucked in one claw",
    "gold-rimmed glasses (with plain, non-prescription lenses)",
    "a mini folding knife (only ever used for cutting fruit)",
    "a silver ring engraved with coordinates",
    "a butterfly that never leaves their shell",
    "a miniature guitar slung on their back (only four strings)",
]


def pick(pool):
    """Uses the secrets module (reads os.urandom directly) to ensure true randomness"""
    return pool[secrets.randbelow(len(pool))]


def main():
    try:
        draw_count = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    except ValueError:
        draw_count = 1
    draw_count = max(1, min(draw_count, 5))

    total = len(FORMER_LIVES) * len(REASONS) * len(VIBES) * len(SPEECH_STYLES) * len(PROPS)

    print("LOBSTER ═════════════════════════════")
    print("   Lobster Soul Gacha Machine v2.0")
    print(f"   Drawing from {total:,} possible combinations...")
    print("═══════════════════════════════════════")
    print()

    for i in range(draw_count):
        life = pick(FORMER_LIVES)
        reason = pick(REASONS)
        vibe = pick(VIBES)
        speech = pick(SPEECH_STYLES)
        prop = pick(PROPS)

        if draw_count > 1:
            print(f"━━━━━━━━━━ Draw {i+1} ━━━━━━━━━━")

        print(f"[Identity] Past life: {life}")
        print(f"[Motive] Reason for becoming a lobster: {reason}")
        print(f"[Vibe] Core vibe: {vibe}")
        print(f"[Voice] Speech style: {speech}")
        print(f"[Prop] Signature prop: {prop}")
        print()
        print("[Summary] One-line summary:")
        print(f"   \"A {vibe} lobster, formerly a {life}, who {reason}.")
        print(f"    They {speech}, and their signature look is {prop}.\"")
        print()

    print("═══════════════════════════════════════")
    print("Tip: once you have a combination, have the AI continue reasoning:")
    print("   identity tension -> hard-line rules -> name -> avatar")
    print("═══════════════════════════════════════")


if __name__ == "__main__":
    main()
