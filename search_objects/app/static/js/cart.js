// Marked products list ("carrito"): header badge, bottom bar, drawer and toast.
// The list lives in memory only, so it is lost when the page is left (the page already warns).
const cart = (() => {
  const items = new Map();
  const listeners = [];
  const drawer = document.querySelector("[data-cart-drawer]");
  const bar = document.querySelector("[data-cart-bar]");
  const list = document.querySelector("[data-cart-list]");
  const empty = document.querySelector("[data-cart-empty]");
  const toast = document.querySelector("[data-toast]");
  const toastText = document.querySelector("[data-toast-text]");
  let lastFocused = null;
  let toastTimer = null;

  function countLabel() {
    const count = items.size;
    if (count === 0) {
      return "Todavía no elegiste productos";
    }
    return `${count} ${count === 1 ? "producto seleccionado" : "productos seleccionados"}`;
  }

  // Catalog data is untrusted text, so it must only reach the page through textContent.
  function buildCartRow(product) {
    const row = document.createElement("li");
    row.className = "cart-row";

    const photo = document.createElement("div");
    photo.className = "cart-row-photo";
    if (product.image) {
      const image = document.createElement("img");
      image.src = product.image;
      image.alt = "";
      photo.append(image);
    }

    const body = document.createElement("div");
    body.className = "cart-row-body";
    const top = document.createElement("div");
    top.className = "cart-row-top";
    const provider = document.createElement("span");
    provider.className = "product-provider";
    provider.textContent = product.provider || "";
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "cart-row-remove";
    remove.textContent = "Quitar";
    remove.addEventListener("click", () => toggle(product));
    top.append(provider, remove);
    const name = document.createElement("div");
    name.className = "cart-row-name";
    name.textContent = product.name;
    body.append(top, name);

    row.append(photo, body);
    return row;
  }

  function render() {
    const label = countLabel();
    document.querySelectorAll("[data-cart-count]").forEach((node) => {
      node.textContent = String(items.size);
    });
    document.querySelectorAll("[data-cart-label]").forEach((node) => {
      node.textContent = label;
    });
    bar.hidden = items.size === 0;
    empty.hidden = items.size > 0;
    list.replaceChildren(...[...items.values()].map(buildCartRow));
    listeners.forEach((listener) => listener());
  }

  function showToast(message) {
    toastText.textContent = message;
    toast.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { toast.hidden = true; }, 2400);
  }

  // Adds the product, or removes it when it is already marked. Returns true when it is marked.
  function toggle(product) {
    const marked = !items.has(product.uuid);
    if (marked) {
      items.set(product.uuid, product);
      showToast(`${product.name} se agregó a tu carrito`);
    } else {
      items.delete(product.uuid);
      showToast("Quitamos el producto de tu carrito");
    }
    render();
    return marked;
  }

  function open() {
    lastFocused = document.activeElement;
    drawer.hidden = false;
    drawer.querySelector(".cart-close").focus();
  }

  function close() {
    drawer.hidden = true;
    if (lastFocused) {
      lastFocused.focus();
    }
  }

  document.querySelectorAll("[data-cart-open]").forEach((node) => node.addEventListener("click", open));
  drawer.querySelectorAll("[data-cart-close]").forEach((node) => node.addEventListener("click", close));
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !drawer.hidden) {
      close();
    }
  });

  render();
  return {
    has: (uuid) => items.has(uuid),
    toggle,
    onChange: (listener) => listeners.push(listener),
  };
})();
