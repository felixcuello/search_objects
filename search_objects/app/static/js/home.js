// Upload form of the home page: dropzone, threshold label and the processing state.
(() => {
  const form = document.querySelector("[data-detect-form]");
  if (!form) {
    return;
  }

  const fileInput = form.querySelector("[data-file-input]");
  const dropzone = form.querySelector("[data-dropzone]");
  const pickButton = form.querySelector("[data-pick-file]");
  const submitButton = form.querySelector("[data-submit-upload]");
  const fileName = form.querySelector("[data-file-name]");
  const fileError = form.querySelector("[data-file-error]");
  const uploadGrid = form.querySelector("[data-upload-grid]");
  const processing = form.querySelector("[data-processing]");
  const processingImage = form.querySelector("[data-processing-image]");
  const thresholdInput = document.getElementById("threshold");
  const thresholdValue = document.getElementById("threshold-value");

  let submitting = false;
  let previewUrl = null;

  thresholdInput.addEventListener("input", () => {
    thresholdValue.textContent = Number(thresholdInput.value).toFixed(2);
  });

  function showFileError(message) {
    fileError.textContent = message;
    fileError.hidden = !message;
  }

  // Shows the chosen file and enables the submit button, or explains why it was rejected.
  function acceptFile(file) {
    showFileError("");
    if (!file) {
      return;
    }
    if (!file.type.startsWith("image/")) {
      fileInput.value = "";
      fileName.hidden = true;
      submitButton.hidden = true;
      submitButton.disabled = true;
      showFileError("Ese archivo no es una imagen. Probá con una foto JPG o PNG.");
      return;
    }
    fileName.textContent = file.name;
    fileName.hidden = false;
    pickButton.textContent = "Cambiar foto";
    submitButton.hidden = false;
    submitButton.disabled = false;
  }

  pickButton.addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", () => acceptFile(fileInput.files[0]));

  dropzone.addEventListener("dragover", (event) => {
    event.preventDefault();
    dropzone.classList.add("is-dragging");
  });
  dropzone.addEventListener("dragleave", (event) => {
    if (!dropzone.contains(event.relatedTarget)) {
      dropzone.classList.remove("is-dragging");
    }
  });
  dropzone.addEventListener("drop", (event) => {
    event.preventDefault();
    dropzone.classList.remove("is-dragging");
    const file = event.dataTransfer && event.dataTransfer.files[0];
    if (file) {
      const transfer = new DataTransfer();
      transfer.items.add(file);
      fileInput.files = transfer.files;
      acceptFile(file);
    }
  });

  function showProcessing(previewSrc) {
    processingImage.src = previewSrc;
    uploadGrid.hidden = true;
    processing.hidden = false;
    processing.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }

  function resetProcessing() {
    submitting = false;
    uploadGrid.hidden = false;
    processing.hidden = true;
  }

  form.addEventListener("submit", (event) => {
    if (submitting) {
      event.preventDefault();
      return;
    }
    const sampleButton = event.submitter && event.submitter.name === "sample" ? event.submitter : null;
    if (!sampleButton && !fileInput.files[0]) {
      event.preventDefault();
      showFileError("Debe seleccionar una imagen para continuar.");
      return;
    }
    submitting = true;
    if (sampleButton) {
      // The sample wins on the server, so the chosen file must not be uploaded for nothing.
      fileInput.value = "";
      showProcessing(sampleButton.dataset.previewSrc);
    } else {
      previewUrl = URL.createObjectURL(fileInput.files[0]);
      showProcessing(previewUrl);
    }
  });

  // Coming back with the browser button can restore this page from cache, still "processing".
  window.addEventListener("pageshow", (event) => {
    if (event.persisted) {
      resetProcessing();
    }
  });
})();
