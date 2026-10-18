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


def get_or_create_provider() -> Provider:
    # The provider row is shared with the seeds, so both must use the same name.
    provider = Provider.query.filter_by(name=PROVIDER_NAME).first()
    if provider is None:
        provider = Provider(name=PROVIDER_NAME)
        db.session.add(provider)
        db.session.flush()
    return provider


def upsert_product(provider: Provider, catalog_product: dict) -> Product:
    """Create or update the local product that matches the catalog SKU for this provider.

    The description is the Spanish category name, so a search by object type finds it.
    """
    product = Product.query.filter_by(provider_id=provider.id, external_sku=catalog_product["sku"]).first()
    if product is None:
        product = Product(provider=provider, external_sku=catalog_product["sku"])
        db.session.add(product)
    product.name = catalog_product["name"]
    product.description = catalog_product["category"]["name"]
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
        catalog_product = find_catalog_product(entry["category_id"], entry["sku"])
        if catalog_product is None:
            summary["missing_skus"].append(entry["sku"])
            continue
        product = upsert_product(provider, catalog_product)
        added, failed = import_images(product, catalog_product)
        db.session.commit()
        summary["products"] += 1
        summary["images"] += added
        summary["failed_images"].extend(failed)
        print(f"{entry['label']}: {product.name} ({added} new photos)")
    return summary
