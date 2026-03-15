"""
Download free icon fonts into this directory.
Run once:  python src/assets/download_icons.py

Fonts downloaded
────────────────
MaterialIcons-Regular.ttf   — Google Material Icons (Apache 2.0)
  https://github.com/google/material-design-icons

Usage in pygame
───────────────
    icon_font = pygame.font.Font("src/assets/MaterialIcons-Regular.ttf", 24)
    surf = icon_font.render("\ue5cc", True, WHITE)   # navigate_next  ▶
"""
import pathlib
import urllib.request

ASSETS = pathlib.Path(__file__).parent

FONTS = {
    "MaterialIcons-Regular.ttf": (
        "https://github.com/google/material-design-icons/raw/master/font/"
        "MaterialIcons-Regular.ttf"
    ),
}


def main():
    for filename, url in FONTS.items():
        dest = ASSETS / filename
        if dest.exists():
            print(f"  already exists: {filename}")
            continue
        print(f"  downloading {filename} …", end=" ", flush=True)
        urllib.request.urlretrieve(url, dest)
        print(f"done  ({dest.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
