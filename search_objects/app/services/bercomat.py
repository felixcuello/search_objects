import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from app.extensions import db
from app.models import Image, Product, Provider
from app.seeds import PROVIDER_NAME
from app.services.storage import upload_image

BASE_URL = os.environ.get("BERCOMAT_BASE_URL", "https://catalogo.familiabercomat.com").rstrip("/")
PRODUCTS_FILE = Path(__file__).resolve().parent.parent / "data" / "bercomat_products.json"
PAGE_SIZE = 100
REQUEST_TIMEOUT_SECONDS = 30
USER_AGENT = "SearchObjectsImporter/1.0"
MAX_PHOTOS_TO_PROBE = 10
# Some products are only listed for certain postal codes. 3400 is the code in the client's links.
POSTAL_CODE = os.environ.get("BERCOMAT_POSTAL_CODE", "3400")


def _http_get(path: str) -> tuple[bytes, str]:
    """GET a path of the Bercomat catalog and return the body and its content type."""
    request = urllib.request.Request(f"{BASE_URL}{path}", headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        return response.read(), response.headers.get_content_type()


def find_catalog_product(category_id: int, sku: str) -> dict | None:
    """Page through a category of the catalog API until the SKU is found, or return None.

    The list endpoint is used (not /api/products/<sku>) because it returns every photo of the
    product, while the detail endpoint can return only the first one.
    """
    page = 1
    while True:
        body, _ = _http_get(f"/api/products?categoryId={category_id}&limit={PAGE_SIZE}&page={page}")
        payload = json.loads(body)
        for product in payload["data"]:
            if product["sku"] == sku:
                return product
        if page >= payload["pagination"]["pages"]:
            return None
        page += 1


def _get_json_or_none(path: str) -> dict | None:
    # A 404 means the catalog does not know the path, any other error must stop the import.
    try:
        body, _ = _http_get(path)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise
    return json.loads(body)


def _photo_exists(photo_path: str) -> bool:
    # HEAD request, so probing for photos does not download them.
    request = urllib.request.Request(
        f"{BASE_URL}{photo_path}", method="HEAD", headers={"User-Agent": USER_AGENT}
    )
    try:
        urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS).close()
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return False
        raise
    return True


def find_catalog_product_by_detail(sku: str) -> dict | None:
    """Fetch one product from /api/products/<sku>, or return None when the catalog has no such SKU.

    Used for products that are in no category (they cannot be found by listing a category).
    """
    payload = _get_json_or_none(f"/api/products/{sku}")
    return payload["product"] if payload else None


def find_catalog_product_by_suggestion(sku: str) -> dict | None:
    """Build a product from the catalog search suggestions, or return None when there is none.

    Some products are only visible there, and only for the POSTAL_CODE. The suggestion has no
    photos, so they are discovered by probing the numbered photo paths the catalog uses
    (<sku>_000_001.jpg, _002, ...).
    """
    payload = _get_json_or_none(f"/api/catalog/suggest?q={sku}&limit=5&cp={POSTAL_CODE}")
    suggestion = next((item for item in (payload or {}).get("suggestions", []) if item["sku"] == sku), None)
    if suggestion is None:
        return None
    photos = []
    for number in range(1, MAX_PHOTOS_TO_PROBE + 1):
        photo_path = f"/images/products/{sku}_000_{number:03d}.jpg"
        if not _photo_exists(photo_path):
            break
        photos.append(photo_path)
    return {
        "sku": sku,
        "name": suggestion["name"],
        "category": {"name": suggestion.get("categoria4") or suggestion["category"]},
        "images": photos,
    }


def resolve_catalog_product(entry: dict) -> dict | None:
    """Find a curated entry in the catalog, trying the most complete source first.

    1. The category listing (entry has category_id): returns every photo of the product.
    2. The product detail endpoint.
    3. The search suggestions.
    """
    sku = entry["sku"]
    product = None
    if entry.get("category_id"):
        product = find_catalog_product(entry["category_id"], sku)
    return product or find_catalog_product_by_detail(sku) or find_catalog_product_by_suggestion(sku)


def get_or_create_provider() -> Provider:
    # The provider row is shared with the seeds, so both must use the same name.
    provider = Provider.query.filter_by(name=PROVIDER_NAME).first()
    if provider is None:
        provider = Provider(name=PROVIDER_NAME)
        db.session.add(provider)
        db.session.flush()
    return provider


def upsert_product(
    provider: Provider,
    catalog_product: dict,
    replace_prompt: str | None = None,
    description: str | None = None,
) -> Product:
    """Create or update the local product that matches the catalog SKU for this provider.

    The description is the given one, or else the Spanish category name, so a search by object
    type finds it. The replace_prompt is only written when given, so an existing prompt is
    never erased.
    """
    product = Product.query.filter_by(provider_id=provider.id, external_sku=catalog_product["sku"]).first()
    if product is None:
        product = Product(provider=provider, external_sku=catalog_product["sku"])
        db.session.add(product)
    product.name = catalog_product["name"]
    category = catalog_product.get("category")
    product.description = description or (category["name"] if category else None)
    if replace_prompt is not None:
        product.replace_prompt = replace_prompt
    db.session.flush()
    return product


def import_images(product: Product, catalog_product: dict) -> tuple[int, list[str]]:
    """Download the product photos into the bucket and register the new ones in the images table.

    Photos already registered for the product are skipped. Returns the number of photos added
    and the list of photo paths that could not be downloaded.
    """
    known_keys = {image.uri for image in product.images}
    added = 0
    failed = []
    for photo_path in catalog_product.get("images") or []:
        key = f"bercomat/{product.external_sku}/{photo_path.rsplit('/', 1)[-1]}"
        if key in known_keys:
            continue
        try:
            data, content_type = _http_get(photo_path)
        except urllib.error.URLError:
            failed.append(photo_path)
            continue
        upload_image(key, data, content_type)
        db.session.add(Image(product=product, uri=key))
        added += 1
    return added, failed


def import_bercomat_products() -> dict:
    """Import the curated Bercomat products with their photos and return a summary.

    The curated list lives in bercomat_products.json. It is safe to re-run: products are matched by
    SKU and photos already imported are skipped.
    """
    curated = json.loads(PRODUCTS_FILE.read_text())
    provider = get_or_create_provider()
    summary = {"products": 0, "images": 0, "missing_skus": [], "failed_images": []}
    for entry in curated:
        catalog_product = resolve_catalog_product(entry)
        if catalog_product is None:
            summary["missing_skus"].append(entry["sku"])
            continue
        product = upsert_product(
            provider, catalog_product, entry.get("replace_prompt"), entry.get("description")
        )
        added, failed = import_images(product, catalog_product)
        db.session.commit()
        summary["products"] += 1
        summary["images"] += added
        summary["failed_images"].extend(failed)
        print(f"{entry['label']}: {product.name} ({added} new photos)")
    return summary
