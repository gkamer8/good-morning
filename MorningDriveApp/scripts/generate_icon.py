#!/usr/bin/env python3
"""Generate app icon for Morning Drive"""

from PIL import Image, ImageDraw
import os
import math

def create_icon(size):
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

    return img

def main():
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

    # Output directory
    output_dir = '/Users/gkamer/Desktop/claude-project/morning-drive/MorningDriveApp/ios/MorningDriveApp/Images.xcassets/AppIcon.appiconset'
    os.makedirs(output_dir, exist_ok=True)

    for size, filename in sizes:
        print(f"Generating {filename} ({size}x{size})...")
        icon = create_icon(size)
        # Convert to RGB for iOS (no alpha in app icons)
        rgb_icon = Image.new('RGB', icon.size, (30, 27, 75))
        rgb_icon.paste(icon, mask=icon.split()[3] if icon.mode == 'RGBA' else None)
        rgb_icon.save(os.path.join(output_dir, filename), 'PNG')

    print("Done! Icons generated.")

if __name__ == '__main__':
    main()
