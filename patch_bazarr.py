#!/usr/bin/env python3
"""Patch Bazarr config.yaml with targeted replacements."""
import re

config_path = "/config/config/config.yaml"

with open(config_path, "r") as f:
    content = f.read()

changes = []

def replace(old, new, desc):
    global content
    if old in content:
        content = content.replace(old, new)
        changes.append(desc)
    else:
        print(f"  SKIP (not found): {desc}")

# 1. Enable multithreading
replace("  multithreading: false", "  multithreading: true",
        "multithreading: false -> true")

# 2. Bump concurrent jobs
replace("  concurrent_jobs: 1", "  concurrent_jobs: 3",
        "concurrent_jobs: 1 -> 3")

# 3. Shorten adaptive search delay
replace("  adaptive_searching_delay: 3w", "  adaptive_searching_delay: 4d",
        "adaptive_searching_delay: 3w -> 4d")

# 4. Shorten adaptive search delta
replace("  adaptive_searching_delta: 1w", "  adaptive_searching_delta: 2d",
        "adaptive_searching_delta: 1w -> 2d")

# 5. Increase search frequency
replace("  wanted_search_frequency: 6", "  wanted_search_frequency: 3",
        "wanted_search_frequency: 6h -> 3h")
replace("  wanted_search_frequency_movie: 6", "  wanted_search_frequency_movie: 3",
        "wanted_search_frequency_movie: 6h -> 3h")

# 6. Lower series minimum score
replace("  minimum_score: 90", "  minimum_score: 80",
        "minimum_score (series): 90 -> 80")

# 7. Add embeddedsubtitles provider
# Find the enabled_providers list and add embeddedsubtitles if missing
if "embeddedsubtitles" not in content:
    # Add after the last provider in the list
    content = content.replace(
        "  - whisperai\n  external_webhook",
        "  - whisperai\n  - embeddedsubtitles\n  external_webhook"
    )
    changes.append("added embeddedsubtitles provider")

with open(config_path, "w") as f:
    f.write(content)

print("Bazarr config updated:")
for c in changes:
    print(f"  + {c}")
print(f"\nTotal changes: {len(changes)}")
