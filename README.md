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
- MySQL is connected via Flask-SQLAlchemy and Flask-Migrate.
- There are no catalog tables yet.
- Steps 3–7 (catalog search, board, selection, replace, buy) are not built yet.
- The first detection downloads the Hugging Face model and can take several minutes, especially on CPU.

## Database

Flask uses Flask-SQLAlchemy (ORM) and Flask-Migrate / Alembic (migrations), with PyMySQL against the Compose `db` service.

If you come from Rails:

```
Rails                         Flask
-------------------------     --------------------------------
ActiveRecord                  Flask-SQLAlchemy
db/migrate                    search_objects/migrations/
rails db:migrate              make db-upgrade
rails db:rollback             docker compose run --rm web flask db downgrade
rails g migration             make db-migrate MSG='create whatever'
```

Commands:

```
make db-ping      # SELECT 1 against MySQL
make db-upgrade   # apply migrations (flask db upgrade)
make db-migrate   # autogenerate from models: make db-migrate MSG='create products'
```

Add a model under `search_objects/app/models/`, then `make db-migrate MSG='...'` and `make db-upgrade`.
`flask db migrate` diffs models against the database, like schema changes followed by `db:migrate`.

## Storage (Silo / S3)

Images live in a Silo bucket (MinIO-compatible, `pgsty/silo`).
The `silo-init` service creates the bucket on `docker compose up`.
Anyone can read an object by URL, but only the app key can write.
The `images.uri` column stores the object key, and `storage.public_url(key)` builds the URL from `S3_PUBLIC_URL`.
The admin console is at http://localhost:9001 (log in with `S3_ROOT_USER` / `S3_ROOT_PASSWORD`).

### Import the Bercomat catalog

`make db-import-bercomat` imports the products listed in `search_objects/app/data/bercomat_products.json`.
Each entry has the detector label, the category id and the SKU of a product in the Bercomat catalog.
The command reads the catalog's JSON API, downloads every photo of each product into the bucket, and registers them in `images`.
Products are matched by provider and SKU (`products.external_sku`), so it is safe to re-run.
The catalog URL can be overridden with the `BERCOMAT_BASE_URL` environment variable.

### Replace an object in the photo

Clicking "Reemplazar" on a search result sends the original photo, the product and the detector box to `POST /replace`.
The server sends the original photo and the first photo of the product to the OpenAI image edit API.
The prompt is the general prompt in `app/services/replacement.py`, plus the position of the box in the image, plus `products.replace_prompt`.
The `replace_prompt` of each Bercomat product is written by `make db-import-bercomat` from `app/data/bercomat_products.json`.
The image model can be changed with the `OPENAI_IMAGE_MODEL` environment variable.
The result is not saved, and every replacement starts from the original photo.

### List products

```python
from app.models import Product
[(p.id, p.name) for p in Product.query.order_by(Product.id).all()]
```

Or print one per line:

```python
for p in Product.query.order_by(Product.id).all(): print(p.id, p.name)

```

Add a blank line (Enter) after the `for` line to run it.

### Create an image from scratch (and get its UUID)

Run `docker compose run --rm web flask seed` first so the products exist.
Then open `docker compose run --rm web flask shell`, list the products to find the `product_id`, and paste the snippet below.
It draws an image with Pillow, uploads it to Silo and inserts the `images` row.
Any format Pillow can write works (PNG, JPEG, JPG, TIFF, WEBP, GIF, BMP, ...).
The function has no blank lines inside it on purpose, so it pastes into the REPL.

```python
import io
import uuid

from PIL import Image as PilImage, ImageDraw

from app.extensions import db
from app.models import Image, Product
from app.services import storage

# Pillow format names; "JPG" is accepted as an alias of "JPEG".
FORMAT_ALIASES = {"JPG": "JPEG", "TIF": "TIFF"}


def create_image(product, fmt="PNG", size=(400, 300), color=(200, 80, 60)):
    """Draw a solid image, upload it to Silo and store its row. Returns the Image."""
    fmt = FORMAT_ALIASES.get(fmt.upper(), fmt.upper())
    pil = PilImage.new("RGB", size, color)
    ImageDraw.Draw(pil).text((10, 10), f"{product.name} ({fmt})", fill="white")
    buffer = io.BytesIO()
    pil.save(buffer, format=fmt)
    image = Image(product_id=product.id, uuid=str(uuid.uuid4()), uri="pending")
    image.uri = f"products/{product.uuid}/{image.uuid}.{fmt.lower()}"
    content_type = PilImage.MIME[fmt]
    storage.upload_image(image.uri, buffer.getvalue(), content_type)
    db.session.add(image)
    db.session.commit()
    return image

product_id = 2  # an id from the product list
product = db.session.get(Product, product_id)
image = create_image(product, "PNG")  # also "JPEG", "JPG", "TIFF", "WEBP", "GIF", "BMP"
image.uuid, storage.public_url(image.uri)
```

The last line returns the image UUID and its public URL, for example:

```
('5e3e0017-2ec7-4b3c-b93e-003e32727a7c', 'http://localhost:9000/search-objects/products/<product uuid>/5e3e0017-2ec7-4b3c-b93e-003e32727a7c.png')
```

### Upload an existing image file

Put the file in `search_objects/.tmp/`.
Only `search_objects/` is mounted into the container, so the file is visible there as `/app/.tmp/<name>`.
The `.tmp/` folder is in `.gitignore`, so the file is not committed.
Do not copy files into the Silo data volume by hand: Silo has its own on-disk format, so the file must be uploaded through the S3 API.

Paste this in the same `flask shell` session, after the snippet above (it reuses its imports).
The format and content type are read from the file itself.

```python
def create_image_from_file(product, path):
    """Upload an existing image file to Silo and store its row. Returns the Image."""
    with PilImage.open(path) as pil:
        fmt = pil.format
    with open(path, "rb") as file:
        data = file.read()
    image = Image(product_id=product.id, uuid=str(uuid.uuid4()), uri="pending")
    image.uri = f"products/{product.uuid}/{image.uuid}.{fmt.lower()}"
    storage.upload_image(image.uri, data, PilImage.MIME[fmt])
    db.session.add(image)
    db.session.commit()
    return image

product_id = 2  # an id from the product list
product = db.session.get(Product, product_id)
image = create_image_from_file(product, "/app/.tmp/photo.webp")
image.uuid, storage.public_url(image.uri)
```

The upload runs before the database insert, so a row is never created for a missing file.
You can delete the local copy afterwards.
