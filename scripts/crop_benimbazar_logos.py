from PIL import Image
import os

SRC = r'C:\Users\PC\.cursor\projects\d-Dolphin\assets\c__Users_PC_AppData_Roaming_Cursor_User_workspaceStorage_empty-window_images_ChatGPT_Image_15_A_u_2026_17_31_13-2b099580-4f98-40bb-9fab-f33c63e54be8.png'
OUT = r'D:\changex\php-site\assets\branding'
os.makedirs(OUT, exist_ok=True)

regions = {
    'logo-horizontal.png': (20, 68, 338, 322),
    'logo-vertical.png': (343, 68, 661, 322),
    'logo-icon.png': (683, 68, 1001, 322),
    'favicon-512.png': (20, 378, 338, 676),
    'logo-horizontal-transparent.png': (343, 378, 661, 676),
    'logo-vertical-transparent.png': (683, 378, 1001, 676),
}


def key_transparent(im: Image.Image) -> Image.Image:
    im = im.convert('RGBA')
    px = im.load()
    w, h = im.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if r > 210 and g > 210 and b > 210:
                px[x, y] = (r, g, b, 0)
            elif abs(r - g) < 12 and abs(g - b) < 12 and 150 <= r <= 230:
                px[x, y] = (r, g, b, 0)
    bbox = im.getbbox()
    if bbox:
        im = im.crop(bbox)
    return im


for name, box in regions.items():
    raw = Image.open(SRC).crop(box)
    if name == 'favicon-512.png':
        out = raw.convert('RGBA')
    elif 'transparent' in name or name == 'logo-icon.png':
        out = key_transparent(raw)
    else:
        out = raw.convert('RGBA')
        bbox = out.getbbox()
        if bbox:
            out = out.crop(bbox)
    path = os.path.join(OUT, name)
    out.save(path, 'PNG')
    print(name, out.size, os.path.getsize(path))

fav_path = os.path.join(OUT, 'favicon-512.png')
fav = Image.open(fav_path)
if max(fav.size) != 512:
    fav = fav.resize((512, 512), Image.Resampling.LANCZOS)
    fav.save(fav_path, 'PNG')
    print('favicon resized', fav.size)
