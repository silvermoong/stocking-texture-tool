"""Where the texture may show: the rough regions minus colours far from the stocking's.

The stocking's colour is the robust centre of Lab chroma over every region; pixels more than Z_MAX robust
deviations away (gold trim, gloves, hair, skin) are dropped. The user refines the edge further in Photoshop.
"""
import cv2
import numpy as np

Z_MAX = 6.0


def lab_of(art_rgb):
    return cv2.cvtColor(art_rgb, cv2.COLOR_RGB2LAB).astype(np.float32)


def stocking_coverage(lab, REG, z_max=Z_MAX, exclude=True):
    """(stock bool mask, alpha float32 0..1) from the art's Lab image and the region map (any value > 0 = inside).
    exclude=False keeps every region pixel whatever its colour (the user turned 颜色排除 off: sheer stockings with
    skin showing through look too warm for the colour test)."""
    inside = REG > 0
    if not inside.any():
        z = np.zeros(inside.shape, np.float32)
        return inside.copy(), z
    if exclude:
        ab = lab[..., 1:][inside]
        med = np.median(ab, 0)
        mad = np.median(np.abs(ab - med), 0) + 1.0
        z = np.sqrt((((lab[..., 1:] - med) / mad) ** 2).sum(-1))
        stock = inside & (z < z_max)
        # single stray pixels the colour test lets through
        stock = cv2.morphologyEx(stock.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)).astype(bool)
    else:
        stock = inside.copy()
    alpha = cv2.GaussianBlur(cv2.erode(stock.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(np.float32),
                             (0, 0), 0.8)
    return stock, alpha
