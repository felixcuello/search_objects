# Search Objects

App to find catalog objects from a photo and let the user pick, replace, and buy them.

## Product flow (target)

This is the intended product, not the current implementation.

1. **Upload an image** — The user uploads a photo.
2. **Detect objects** — We detect objects in the image against a known list.
3. **Search our catalog** — We look up those detections in our own database.
4. **Present a board** — Matching catalog objects are shown like a Pinterest board.
5. **Select objects** — The user picks some of them. Later, selected objects may be replaced in the original image using the image-manipulation PoC (`search_objects/poc_image_manipulation/`).
6. **Mark to buy** — The user marks the objects they want to purchase.
7. **Return the list** — We return the list of marked objects.

## Current status

- Flask UI for steps 1–2: upload an image, detect furniture/objects with OWLv2, and show a Spanish list plus an overlay image.
- Image-manipulation proofs of concept live in `search_objects/poc_image_manipulation/`.
- The Gradio detector demo lives in `search_objects/poc_detector/`.
- Steps 3–7 (catalog search, board, selection, replace, buy) are not built yet.
- The first detection downloads the Hugging Face model and can take several minutes, especially on CPU.
