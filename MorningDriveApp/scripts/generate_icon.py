#!/usr/bin/env python3
"""Generate app icon for Morning Drive"""

from PIL import Image, ImageDraw, ImageFont
import os
import math
import sys

def create_icon(size, dev_mode=False):
    """Create a sunrise/morning themed icon"""
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Background gradient (deep purple to orange sunrise)
    for y in range(size):
        ratio = y / size
        # Gradient from deep indigo at top to warm orange at bottom
        r = int(30 + (255 - 30) * ratio)
        g = int(27 + (140 - 27) * ratio)
        b = int(75 + (50 - 75) * ratio)
        draw.line([(0, y), (size, y)], fill=(r, g, b, 255))

    # Sun (golden circle near bottom)
    sun_radius = int(size * 0.25)
    sun_center_x = size // 2
    sun_center_y = int(size * 0.65)

    # Sun glow
    for i in range(20, 0, -1):
        glow_radius = sun_radius + i * 3
        alpha = int(100 - i * 4)
        glow_color = (255, 200, 100, alpha)
        draw.ellipse([
            sun_center_x - glow_radius,
            sun_center_y - glow_radius,
            sun_center_x + glow_radius,
            sun_center_y + glow_radius
        ], fill=glow_color)

    # Main sun
    draw.ellipse([
        sun_center_x - sun_radius,
        sun_center_y - sun_radius,
        sun_center_x + sun_radius,
        sun_center_y + sun_radius
    ], fill=(255, 210, 100, 255))

    # Sun highlight
    highlight_radius = int(sun_radius * 0.7)
    draw.ellipse([
        sun_center_x - highlight_radius,
        sun_center_y - highlight_radius - int(sun_radius * 0.1),
        sun_center_x + highlight_radius,
        sun_center_y + highlight_radius - int(sun_radius * 0.1)
    ], fill=(255, 240, 180, 255))

    # Road/highway (perspective lines)
    road_color = (40, 40, 60, 200)
    road_width_bottom = int(size * 0.4)
    road_width_top = int(size * 0.05)

    # Road trapezoid
    road_points = [
        (size // 2 - road_width_bottom // 2, size),  # bottom left
        (size // 2 + road_width_bottom // 2, size),  # bottom right
        (size // 2 + road_width_top // 2, int(size * 0.55)),  # top right
        (size // 2 - road_width_top // 2, int(size * 0.55)),  # top left
    ]
    draw.polygon(road_points, fill=road_color)

    # Road center line (dashed)
    line_color = (255, 220, 100, 255)
    num_dashes = 5
    for i in range(num_dashes):
        t_start = i / num_dashes
        t_end = (i + 0.5) / num_dashes

        y_start = size - (size - int(size * 0.55)) * t_start
        y_end = size - (size - int(size * 0.55)) * t_end

        line_width_start = 4 * (1 - t_start) + 1
        line_width_end = 4 * (1 - t_end) + 1

        draw.line(
            [(size // 2, y_start), (size // 2, y_end)],
            fill=line_color,
            width=max(1, int((line_width_start + line_width_end) / 2))
        )

    # Radio waves emanating from sun (representing audio/broadcast)
    wave_color = (255, 255, 255, 60)
    for i in range(3):
        wave_radius = sun_radius + int(size * 0.12) * (i + 1)
        arc_width = 2
        # Draw partial arc above sun
        bbox = [
            sun_center_x - wave_radius,
            sun_center_y - wave_radius,
            sun_center_x + wave_radius,
            sun_center_y + wave_radius
        ]
        draw.arc(bbox, 200, 340, fill=(255, 255, 255, 100 - i * 25), width=arc_width)

    # Add DEV banner for development builds
    if dev_mode:
        banner_height = int(size * 0.18)
        banner_width = int(size * 0.7)

        # Draw diagonal banner background at top-right corner
        banner_color = (220, 50, 50, 255)  # Red banner

        # Create banner as diagonal strip
        points = [
            (size - banner_width, 0),
            (size, 0),
            (size, banner_height),
            (size - banner_width + banner_height, 0),
        ]

        # Simple horizontal banner at top
        draw.rectangle(
            [(0, 0), (size, banner_height)],
            fill=banner_color
        )

        # Add DEV text
        font_size = int(banner_height * 0.65)
        font = None

        # Try different font paths
        font_paths = [
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
            "/Library/Fonts/Arial.ttf",
        ]
        for font_path in font_paths:
            try:
                font = ImageFont.truetype(font_path, font_size)
                break
            except:
                continue

        text = "DEV"

        if font:
            text_bbox = draw.textbbox((0, 0), text, font=font)
            text_width = text_bbox[2] - text_bbox[0]
            text_height = text_bbox[3] - text_bbox[1]
        else:
            # Fallback: estimate text size
            text_width = int(font_size * 2)
            text_height = int(font_size * 0.8)

        text_x = (size - text_width) // 2
        text_y = (banner_height - text_height) // 2 - int(banner_height * 0.15)

        draw.text((text_x, text_y), text, fill=(255, 255, 255, 255), font=font)

    return img

def generate_icons(output_dir, dev_mode=False):
    """Generate all icon sizes for an icon set"""
    # iOS icon sizes needed
    sizes = [
        (1024, 'AppIcon-1024.png'),  # App Store
        (180, 'AppIcon-60@3x.png'),   # iPhone @3x
        (120, 'AppIcon-60@2x.png'),   # iPhone @2x
        (167, 'AppIcon-83.5@2x.png'), # iPad Pro
        (152, 'AppIcon-76@2x.png'),   # iPad
        (80, 'AppIcon-40@2x.png'),    # Spotlight @2x
        (120, 'AppIcon-40@3x.png'),   # Spotlight @3x
        (58, 'AppIcon-29@2x.png'),    # Settings @2x
        (87, 'AppIcon-29@3x.png'),    # Settings @3x
    ]

    os.makedirs(output_dir, exist_ok=True)
    mode_label = "DEV " if dev_mode else ""

    for size, filename in sizes:
        print(f"Generating {mode_label}{filename} ({size}x{size})...")
        icon = create_icon(size, dev_mode=dev_mode)
        # Convert to RGB for iOS (no alpha in app icons)
        rgb_icon = Image.new('RGB', icon.size, (30, 27, 75))
        rgb_icon.paste(icon, mask=icon.split()[3] if icon.mode == 'RGBA' else None)
        rgb_icon.save(os.path.join(output_dir, filename), 'PNG')


def main():
    # Get script directory to determine project root
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)  # MorningDriveApp
    assets_dir = os.path.join(project_root, 'ios', 'MorningDriveApp', 'Images.xcassets')

    # Parse arguments
    generate_dev = '--dev' in sys.argv or '--all' in sys.argv
    generate_prod = '--prod' in sys.argv or '--all' in sys.argv or len(sys.argv) == 1

    if generate_prod:
        print("=== Generating Production Icons ===")
        output_dir = os.path.join(assets_dir, 'AppIcon.appiconset')
        generate_icons(output_dir, dev_mode=False)
        print()

    if generate_dev:
        print("=== Generating Development Icons ===")
        output_dir = os.path.join(assets_dir, 'AppIcon-Dev.appiconset')
        generate_icons(output_dir, dev_mode=True)
        print()

    print("Done! Icons generated.")


if __name__ == '__main__':
    main()
