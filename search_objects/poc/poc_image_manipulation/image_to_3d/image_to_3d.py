import base64
import math
from pathlib import Path

import numpy as np
import trimesh
from openai import OpenAI
from PIL import Image
from skimage.measure import marching_cubes

client = OpenAI()

PRODUCT_IMAGE = "table.jpg"
PRODUCT_HEIGHT_METERS = 0.75  # Real height of the product, used to scale the final mesh.
GRID_SIZE = 128  # Voxels per axis used for the silhouette carving.
WHITE_BACKGROUND_THRESHOLD = 235  # A pixel with any channel below this is part of the object.

# Axes of the model: X = width (left to right), Y = depth (front to back), Z = height (up).
# The isometric view is only a reference image, it is not used to carve the mesh.
VIEW_PROMPTS = {
    "front": "the FRONT elevation: the camera is level with the product at its mid height, "
    "looking straight at the front face. The image shows only width and height, "
    "the product is not rotated and not tilted at all",
    "side": "the RIGHT SIDE elevation: the camera is level with the product at its mid height, "
    "looking straight at its right face, so the front of the product points to the LEFT of the "
    "image. The image shows only depth and height, the product is not rotated and not tilted "
    "at all",
    "top": "the TOP plan view: the camera is straight above the product looking straight down, "
    "so the front of the product is at the BOTTOM of the image. The image shows only width and "
    "depth, the product is not tilted at all",
    "isometric": "an ISOMETRIC view: orthographic camera elevated 35 degrees above the "
    "horizontal and rotated 45 degrees from the front towards the right, so the front, right "
    "and top faces are all visible with equal foreshortening",
}

PROMPT_TEMPLATE = """
Image 1: product photograph.

Task:
Render this exact product as {view}.
Treat the main face visible in the photograph as the front of the product.

Projection:
- strict orthographic projection, as if the camera were infinitely far away
- parallel edges of the product stay parallel, there is no perspective and no vanishing point
- the product keeps the exact proportions of the real object in the photograph
- the product is centered, fully visible, nothing cropped, with a small margin around it

Background and silhouette (the image is converted into a silhouette, so this is critical):
- pure flat white background (#FFFFFF) everywhere outside the product
- no floor, no horizon, no ground contact shadow, no cast shadow, no reflection, no props
- crisp hard edges, no outline, no glow, no halo
- openings through the product (between legs, handles, arms, cables, loops) show the plain
  white background through them, exactly as they would look from that camera

Appearance:
- keep the same product design: shape, materials, parts, color, and proportions
- flat, even, diffuse lighting, no highlights, no gradients from light, same colors in every view
- do not redesign the product, do not add, remove, or move any part
"""


def generate_view(view_name: str, view_description: str) -> Path:
    # Asks the image model for one orthographic view of the product. Reuses the file if it exists.
    view_path = Path(f"view_{view_name}.png")
    if view_path.exists():
        print(f"Reusing '{view_path}' (delete it to generate it again).")
        return view_path

    with open(PRODUCT_IMAGE, "rb") as product_file:
        response = client.images.edit(
            model="gpt-image-2.5-sunburst",
            image=[product_file],
            prompt=PROMPT_TEMPLATE.format(view=view_description),
            n=1,
            size="1024x1024",
            quality="high",
            output_format="png",
        )
    view_path.write_bytes(base64.b64decode(response.data[0].b64_json))
    print(f"Generated '{view_path}'.")
    return view_path


def load_cropped_view(view_path: Path) -> tuple[np.ndarray, np.ndarray]:
    # Returns the RGB crop of the object and its boolean silhouette, cropped to the object bounds.
    rgb = np.asarray(Image.open(view_path).convert("RGB"))
    silhouette = rgb.min(axis=2) < WHITE_BACKGROUND_THRESHOLD
    rows, cols = np.where(silhouette)
    row_slice = slice(rows.min(), rows.max() + 1)
    col_slice = slice(cols.min(), cols.max() + 1)
    return rgb[row_slice, col_slice], silhouette[row_slice, col_slice]


def resample_mask(mask: np.ndarray, columns: int, rows: int) -> np.ndarray:
    # Stretches a silhouette to a fixed grid so the three views share the same object bounds.
    resized = Image.fromarray((mask * 255).astype(np.uint8)).resize((columns, rows), Image.BILINEAR)
    return np.asarray(resized) > 127


def carve_voxels(front_mask, side_mask, top_mask) -> np.ndarray:
    # Keeps a voxel only if it falls inside the silhouette of all three views (visual hull).
    n = GRID_SIZE
    front = resample_mask(front_mask, n, n)  # rows = Z (top to bottom), columns = X
    side = resample_mask(side_mask, n, n)  # rows = Z (top to bottom), columns = Y
    top = resample_mask(top_mask, n, n)  # rows = Y (back to front), columns = X
    front_xz = front[::-1].T  # [x, z]
    side_yz = side[::-1].T  # [y, z]
    top_xy = top[::-1].T  # [x, y]
    return front_xz[:, None, :] & side_yz[None, :, :] & top_xy[:, :, None]


def build_mesh(voxels, width, depth, height) -> trimesh.Trimesh:
    # Converts the voxels into a smooth mesh in meters, with the origin at the bottom center.
    n = GRID_SIZE
    padded = np.pad(voxels.astype(np.float32), 1)
    vertices, faces, _, _ = marching_cubes(
        padded, level=0.5, spacing=(width / n, depth / n, height / n)
    )
    vertices -= np.array([width / n, depth / n, height / n])  # Undo the padding offset.
    vertices[:, 0] -= width / 2
    vertices[:, 1] -= depth / 2
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=True)
    return trimesh.smoothing.filter_taubin(mesh, iterations=10)


def paint_mesh(mesh, front_rgb, side_rgb, top_rgb, width, depth, height) -> None:
    # Colors each vertex from the view that faces it most, using its position as pixel coordinate.
    bounds_min = mesh.bounds[0]
    u = (mesh.vertices[:, 0] - bounds_min[0]) / width  # 0..1 along X
    v = (mesh.vertices[:, 1] - bounds_min[1]) / depth  # 0..1 along Y
    w = (mesh.vertices[:, 2] - bounds_min[2]) / height  # 0..1 along Z

    def sample(image, horizontal, vertical_from_bottom):
        rows, cols = image.shape[:2]
        col_index = np.clip((horizontal * (cols - 1)).astype(int), 0, cols - 1)
        row_index = np.clip(((1 - vertical_from_bottom) * (rows - 1)).astype(int), 0, rows - 1)
        return image[row_index, col_index]

    normals = np.abs(mesh.vertex_normals)
    dominant_axis = normals.argmax(axis=1)  # 0 = X (side view), 1 = Y (front), 2 = Z (top)
    colors = np.empty((len(mesh.vertices), 3), dtype=np.uint8)
    for axis, image, horizontal, vertical in (
        (0, side_rgb, v, w),
        (1, front_rgb, u, w),
        (2, top_rgb, u, v),
    ):
        selected = dominant_axis == axis
        colors[selected] = sample(image, horizontal[selected], vertical[selected])
    mesh.visual.vertex_colors = colors


def to_y_up(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    # GLB and most render tools use Y as up, so rotate the Z-up mesh by -90 degrees around X.
    mesh.apply_transform(trimesh.transformations.rotation_matrix(-math.pi / 2, [1, 0, 0]))
    return mesh


views = {name: generate_view(name, description) for name, description in VIEW_PROMPTS.items()}
front_rgb, front_mask = load_cropped_view(views["front"])
side_rgb, side_mask = load_cropped_view(views["side"])
top_rgb, top_mask = load_cropped_view(views["top"])

# Width and depth come from the aspect ratio of each silhouette relative to the real height.
height = PRODUCT_HEIGHT_METERS
width = height * front_mask.shape[1] / front_mask.shape[0]
depth = height * side_mask.shape[1] / side_mask.shape[0]

voxels = carve_voxels(front_mask, side_mask, top_mask)
if not voxels.any():
    raise SystemExit("The three views do not overlap, nothing to carve. Check the view_*.png files.")

mesh = build_mesh(voxels, width, depth, height)
paint_mesh(mesh, front_rgb, side_rgb, top_rgb, width, depth, height)
mesh = to_y_up(mesh)

mesh.export("model.glb")
mesh.export("model.obj")
print(f"Success! 'model.glb' and 'model.obj' written ({width:.2f} x {depth:.2f} x {height:.2f} m).")
