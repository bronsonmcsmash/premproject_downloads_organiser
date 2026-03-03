"""
icon.py — Programmatic tray icon generation for Project Organizer.

Generates a folder-style icon as a PIL Image (for pystray) and optionally
saves it as an .ico file (for winotify toast notifications).

No external image files are required — everything is drawn at runtime.
"""

from pathlib import Path

from PIL import Image, ImageDraw


# ---------------------------------------------------------------------------
# Icon colours  (Material Design blue palette)
# ---------------------------------------------------------------------------

_FOLDER_BODY = (52, 152, 219)    # #3498db — vibrant blue
_FOLDER_TAB  = (41, 128, 185)    # #2980b9 — darker blue for the tab bump
_ARROW_FILL  = (255, 255, 255, 230)  # semi-transparent white download arrow


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def create_tray_icon(size: int = 64) -> Image.Image:
    """
    Generate a coloured folder icon as a PIL RGBA Image.

    The icon shows a simple folder shape with a downward arrow to indicate
    the "import / organise files" purpose of the app.

    Args:
        size: Width and height of the square image in pixels.

    Returns:
        A PIL Image in RGBA mode suitable for use with pystray.
    """
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    p = max(2, size // 8)          # outer padding
    tab_h = max(2, size // 6)      # height of the folder tab bump
    tab_w = size // 3              # width of the folder tab bump

    # Folder body (large rectangle)
    draw.rounded_rectangle(
        [p, p + tab_h, size - p, size - p],
        radius=max(1, size // 12),
        fill=_FOLDER_BODY,
    )

    # Folder tab (top-left raised rectangle, slightly darker)
    draw.rounded_rectangle(
        [p, p, p + tab_w, p + tab_h + max(1, size // 16)],
        radius=max(1, size // 16),
        fill=_FOLDER_TAB,
    )

    # Downward-pointing arrow (indicating "receive / import")
    cx = size // 2
    cy = size // 2 + size // 10
    aw = max(3, size // 5)         # half-width of arrow head
    ah = max(3, size // 6)         # height of arrow head
    stem_w = max(2, size // 10)    # stem width
    stem_h = max(2, size // 8)     # stem height

    # Stem
    draw.rectangle(
        [cx - stem_w, cy - stem_h - ah // 2,
         cx + stem_w, cy - ah // 2],
        fill=_ARROW_FILL,
    )
    # Head
    draw.polygon(
        [(cx - aw, cy - ah // 2),
         (cx + aw, cy - ah // 2),
         (cx,      cy + ah // 2)],
        fill=_ARROW_FILL,
    )

    return img


def save_icon_ico(dest_path: Path, size: int = 64) -> None:
    """
    Save the tray icon as a multi-size .ico file for use in toast notifications.

    Creates the parent directory if it does not exist.

    Args:
        dest_path: Full path where the .ico file should be written.
        size:      Base render size (the .ico will include 16, 32, and 48 px variants).
    """
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    base = create_tray_icon(size=max(size, 64))

    # Build multiple sizes for the .ico container
    sizes = [16, 32, 48]
    variants = [base.resize((s, s), Image.LANCZOS) for s in sizes]

    # PIL saves multi-size .ico when passed a list via append_images
    variants[0].save(
        str(dest_path),
        format="ICO",
        sizes=[(s, s) for s in sizes],
        append_images=variants[1:],
    )
