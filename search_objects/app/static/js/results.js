// Results page: object search, object replacement, before/after slider and hover sync.

// Leaving the page loses the photo and every replacement, so the browser must ask first.
window.addEventListener("beforeunload", (event) => {
  event.preventDefault();
  event.returnValue = "";
});

function isModifiedClick(event) {
  return event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey;
}

// Static markup only (no catalog data), so it is safe to set as HTML.
const CART_ICON =
  '<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true" fill="none" ' +
  'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
  '<circle cx="9" cy="20" r="1.5"/><circle cx="18" cy="20" r="1.5"/>' +
  '<path d="M3 4h2.5l2.3 11h10.2l2-8H6.4"/></svg>';
const REPLACE_ICON =
  '<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true" fill="none" ' +
  'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
  '<path d="M17 3l4 4-4 4"/><path d="M3 11V9a2 2 0 0 1 2-2h16"/>' +
  '<path d="M7 21l-4-4 4-4"/><path d="M21 13v2a2 2 0 0 1-2 2H3"/></svg>';

const SPINNER = '<span class="spinner" aria-hidden="true"></span>';

function buildActionButton(className, icon, label, onClick = null) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = `product-action ${className}`;
  const text = document.createElement("span");
  text.textContent = label;
  button.dataset.icon = icon;
  button.dataset.label = label;
  button.innerHTML = icon;
  button.append(text);
  if (onClick) {
    button.addEventListener("click", () => onClick(button));
  }
  return button;
}

// Catalog data is untrusted text, so it must only reach the page through textContent.
function buildProductItem(product, onReplace) {
  const item = document.createElement("li");
  item.className = "product-item";

  const photo = document.createElement("div");
  photo.className = "product-photo";
  if (product.images.length > 0) {
    const image = document.createElement("img");
    image.src = product.images[0];
    image.alt = product.name;
    image.loading = "lazy";
    photo.append(image);
  } else {
    photo.classList.add("is-missing");
    photo.textContent = "Sin imagen";
  }

  const body = document.createElement("div");
  body.className = "product-body";
  if (product.provider) {
    const provider = document.createElement("span");
    provider.className = "product-provider";
    provider.textContent = product.provider;
    body.append(provider);
  }
  const name = document.createElement("h3");
  name.className = "product-name";
  name.textContent = product.name;
  body.append(name);
  if (product.description) {
    const description = document.createElement("p");
    description.className = "product-description";
    description.textContent = product.description;
    body.append(description);
  }
  const actions = document.createElement("div");
  actions.className = "product-actions";
  actions.append(
    buildActionButton("is-primary", CART_ICON, "Agregar al carrito", () => {
      cart.toggle({
        uuid: product.uuid,
        name: product.name,
        provider: product.provider,
        image: product.images[0] || null,
      });
    }),
    buildActionButton("is-secondary", REPLACE_ICON, "Reemplazar", (button) =>
      onReplace(product, button),
    ),
  );
  body.append(actions);

  item.dataset.productUuid = product.uuid;
  item.append(photo, body);
  refreshMarkedState(item);
  return item;
}

// Keeps a product card in step with the list: highlighted card and a button that removes.
function refreshMarkedState(item) {
  const marked = cart.has(item.dataset.productUuid);
  item.classList.toggle("is-marked", marked);
  const button = item.querySelector(".product-action.is-primary");
  const label = marked ? "Quitar del carrito" : "Agregar al carrito";
  button.classList.toggle("is-marked", marked);
  button.dataset.label = label;
  button.querySelector("span").textContent = label;
}

// Cards are rebuilt on every search, so the list refreshes whichever cards are on screen.
cart.onChange(() => {
  document.querySelectorAll(".product-item[data-product-uuid]").forEach(refreshMarkedState);
});

// The original photo always stays underneath. The latest replacement sits on top of it and the
// "Antes / Después" slider decides how much of the original is uncovered.
function bindImageReplacement(panel) {
  const stage = document.querySelector(".detect-stage");
  const stageImage = stage.querySelector(".stage-original");
  const afterLayer = stage.querySelector(".stage-after");
  const afterImage = afterLayer.querySelector("img");
  const range = stage.querySelector(".compare-range");
  const toggle = document.querySelector("[data-compare-toggle]");
  const originalSrc = stageImage.src;
  // The detector boxes are in pixels of the original photo, whatever image is sent.
  const originalWidth = stageImage.getAttribute("width");
  const originalHeight = stageImage.getAttribute("height");
  let replacementUrl = null;
  let latestBlob = null;
  let animationTimer = null;

  const busy = document.createElement("div");
  busy.className = "stage-busy";
  busy.hidden = true;
  busy.setAttribute("role", "status");
  const busyText = document.createElement("p");
  busyText.textContent = "Reemplazando el objeto… puede tardar hasta un minuto.";
  busy.innerHTML = SPINNER;
  busy.append(busyText);
  stage.append(busy);

  function showReplacement() {
    afterImage.src = replacementUrl;
    afterLayer.hidden = false;
    toggle.hidden = false;
  }

  function setComparing(comparing) {
    stage.classList.toggle("is-comparing", comparing);
    toggle.setAttribute("aria-pressed", String(comparing));
    range.value = 50;
    stage.style.setProperty("--split", comparing ? "50%" : "0%");
    // The slide animation only runs when toggling, so dragging the slider follows the pointer.
    stage.classList.add("is-animating");
    clearTimeout(animationTimer);
    animationTimer = setTimeout(() => stage.classList.remove("is-animating"), 500);
  }

  toggle.addEventListener("click", () => {
    setComparing(!stage.classList.contains("is-comparing"));
  });
  range.addEventListener("input", () => {
    stage.style.setProperty("--split", `${range.value}%`);
  });

  // Each replacement starts from the latest result, so changes stack. The first one starts
  // from the original photo.
  return async function replaceObject(product, target, button, status) {
    const buttons = panel.querySelectorAll(".product-action");
    buttons.forEach((each) => { each.disabled = true; });
    button.innerHTML = SPINNER;
    const label = document.createElement("span");
    label.textContent = "Reemplazando…";
    button.append(label);
    busy.hidden = false;
    status.className = "search-panel is-loading";
    status.textContent = `Reemplazando por «${product.name}»…`;
    try {
      const form = new FormData();
      const input = latestBlob || (await (await fetch(originalSrc)).blob());
      form.append("image", input, "image");
      form.append("image_width", originalWidth);
      form.append("image_height", originalHeight);
      form.append("product_uuid", product.uuid);
      form.append("label", target.label);
      Object.entries(target.box).forEach(([key, value]) => form.append(key, value));
      const response = await fetch("/replace", { method: "POST", body: form });
      if (!response.ok) {
        const failure = await response.json().catch(() => ({}));
        throw new Error(failure.error || "replace failed");
      }
      if (replacementUrl) {
        URL.revokeObjectURL(replacementUrl);
      }
      latestBlob = await response.blob();
      replacementUrl = URL.createObjectURL(latestBlob);
      showReplacement();
      status.className = "search-panel";
      status.textContent = `Objeto reemplazado por «${product.name}».`;
      return true;
    } catch (error) {
      status.className = "search-panel is-error";
      status.textContent = error.message === "replace failed" || error instanceof TypeError
        ? "No pudimos reemplazar el objeto. Intente nuevamente."
        : error.message;
      return false;
    } finally {
      busy.hidden = true;
      buttons.forEach((each) => { each.disabled = false; });
      button.innerHTML = button.dataset.icon;
      const restored = document.createElement("span");
      restored.textContent = button.dataset.label;
      button.append(restored);
    }
  };
}

function bindObjectSearch(root, panel) {
  const status = panel.querySelector("[data-search-status]");
  const list = panel.querySelector("[data-product-list]");
  const replaceObject = bindImageReplacement(panel);
  let latestSearch = 0;

  // The clicked object (its box and its legend cell) stays highlighted until another object
  // is clicked or a replacement succeeds.
  function clearSelected() {
    root.querySelectorAll(".is-selected").forEach((node) => node.classList.remove("is-selected"));
  }
  function markSelected(objectId) {
    clearSelected();
    root.querySelectorAll("[data-object-id]").forEach((node) => {
      node.classList.toggle("is-selected", node.dataset.objectId === objectId);
    });
  }
  root.addEventListener("click", async (event) => {
    const link = event.target.closest("a[href*='/object_search']");
    if (!link || !root.contains(link) || isModifiedClick(event)) {
      return;
    }
    event.preventDefault();
    markSelected(link.dataset.objectId);
    // The detector box travels in the link, so replacing knows which object was clicked.
    const params = new URL(link.href).searchParams;
    const target = {
      label: params.get("q") || "",
      box: Object.fromEntries(
        ["xmin", "ymin", "xmax", "ymax"].map((key) => [key, params.get(key)]),
      ),
    };
    // A slow answer to an older click must not overwrite the answer to a newer one.
    const thisSearch = ++latestSearch;
    list.replaceChildren();
    status.className = "search-panel is-loading";
    status.textContent = "Buscando objetos similares…";
    try {
      const response = await fetch(link.href);
      if (!response.ok) {
        throw new Error("search failed");
      }
      const data = await response.json();
      if (thisSearch !== latestSearch) {
        return;
      }
      const query = data.query || "";
      if (data.results.length === 0) {
        status.className = "search-panel is-empty";
        status.textContent = query
          ? `No hay resultados de catálogo para «${query}».`
          : "No hay resultados de catálogo.";
        return;
      }
      status.className = "search-panel";
      status.textContent = `${data.results.length} resultado(s) para «${query}»`;
      list.replaceChildren(
        ...data.results.map((product) =>
          buildProductItem(product, async (chosen, button) => {
            if (await replaceObject(chosen, target, button, status)) {
              clearSelected();
            }
          }),
        ),
      );
    } catch {
      if (thisSearch !== latestSearch) {
        return;
      }
      status.className = "search-panel is-error";
      status.textContent = "No pudimos completar la búsqueda. Intente nuevamente.";
    }
  });
}

// Pair each list row with its box so hover must highlight both.
function bindHoverSync(root) {
  const nodes = root.querySelectorAll("[data-object-id]");
  const byId = new Map();
  nodes.forEach((node) => {
    const id = node.dataset.objectId;
    if (!byId.has(id)) {
      byId.set(id, []);
    }
    byId.get(id).push(node);
  });

  function setActive(id, active) {
    (byId.get(id) || []).forEach((node) => {
      node.classList.toggle("is-active", active);
    });
  }

  nodes.forEach((node) => {
    const id = node.dataset.objectId;
    node.addEventListener("mouseenter", () => setActive(id, true));
    node.addEventListener("mouseleave", () => setActive(id, false));
    node.addEventListener("focus", () => setActive(id, true));
    node.addEventListener("blur", () => setActive(id, false));
  });
}

const results = document.querySelector("[data-hover-sync]");
const searchPanel = document.querySelector("[data-search-panel]");
if (results) {
  bindHoverSync(results);
}
if (results && searchPanel) {
  bindObjectSearch(results, searchPanel);
}
