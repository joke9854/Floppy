// The header search form. ZXing (336 KB) and barcode-scanner.js load the first
// time a barcode photo is picked, from the URLs base.html lists in
// window.floppyBarcodeScripts, instead of on every page.
if (!window.__floppySearchFormBound) {
  window.__floppySearchFormBound = true;

  let barcodeScannerLoad = null;

  function loadScript(src) {
    return new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = src;
      script.onload = resolve;
      script.onerror = () => reject(new Error(`Could not load ${src}`));
      document.head.appendChild(script);
    });
  }

  window.floppyLoadBarcodeScanner = function() {
    if (window.barcodeScannerUtils) {
      return Promise.resolve(window.barcodeScannerUtils);
    }
    if (!barcodeScannerLoad) {
      // In order: the helper reads window.ZXing when it runs.
      barcodeScannerLoad = (window.floppyBarcodeScripts || [])
        .reduce((chain, src) => chain.then(() => loadScript(src)), Promise.resolve())
        .then(() => window.barcodeScannerUtils)
        .catch((error) => {
          barcodeScannerLoad = null;
          throw error;
        });
    }
    return barcodeScannerLoad;
  };

  document.addEventListener("alpine:init", () => {
    Alpine.data("searchForm", (config) => ({
      isOpen: false,
      selectedType: { display: config.display, value: config.value },
      mediaTypes: config.mediaTypes,
      barcodeScanning: false,
      barcodeError: null,
      barcodePreview: null,
      explicitSubmitTriggered: false,

      getPlaceholder() {
        return interpolate(
          gettext("Search %(media)s in your library or online..."),
          { media: this.selectedType.display },
          true,
        );
      },

      async handleBarcodeImage(event) {
        const barcodeInput = event && event.target;
        if (!barcodeInput || barcodeInput !== this.$refs.barcodeInput) {
          return;
        }
        const file = barcodeInput.files?.[0];
        if (!file) {
          return;
        }
        this.barcodeScanning = true;
        this.barcodeError = null;
        this.barcodePreview = URL.createObjectURL(file);
        try {
          let scanner;
          try {
            scanner = await window.floppyLoadBarcodeScanner();
          } catch (error) {
            scanner = null;
          }
          if (!scanner) {
            throw new Error(gettext("Barcode scanner utilities not loaded. Please refresh the page."));
          }
          const isbn = await scanner.decodeBarcodeFromFile(file);
          if (!isbn) {
            this.barcodeError = gettext("Could not read barcode from image. Please try again or enter ISBN manually.");
            return;
          }
          let form = this.$root;
          if (!form || form.tagName !== "FORM" || !form.contains(barcodeInput)) {
            form = barcodeInput.closest("form");
          }
          const searchInput = form && form.querySelector("input[name=q]");
          if (!searchInput) {
            console.error("[BARCODE] Search form or its query input is missing");
            return;
          }
          searchInput.value = isbn;
          this.explicitSubmitTriggered = true;
          form.submit();
        } catch (error) {
          console.error("Barcode scan error:", error);
          this.barcodeError = gettext("Error scanning barcode: ") + (error.message || gettext("Please try again."));
        } finally {
          this.barcodeScanning = false;
        }
      },

      clearBarcodeError() {
        this.barcodeError = null;
        this.barcodePreview = null;
        if (this.$refs.barcodeInput) {
          this.$refs.barcodeInput.value = "";
        }
      },

      selectType(type) {
        this.selectedType = type;
        this.isOpen = false;
        const input = this.$refs.searchInput;
        if (input && input.value.trim()) {
          this.$nextTick(() => this.$root.submit());
        }
      },

      handleFormSubmit(event) {
        if (event.currentTarget !== this.$el) {
          return true;
        }
        if (event.submitter && !this.$el.contains(event.submitter)) {
          return true;
        }
        if (this.explicitSubmitTriggered) {
          this.explicitSubmitTriggered = false;
          return true;
        }
        if (event.submitter && event.submitter === this.$refs.searchButton) {
          return true;
        }
        if (!event.submitter) {
          const searchInput = this.$el.querySelector("input[name=q]");
          if (searchInput && document.activeElement === searchInput) {
            return true;
          }
        }
        // Only the search button or Enter in the query field submits.
        event.preventDefault();
        event.stopPropagation();
        return false;
      },

      init() {
        this.explicitSubmitTriggered = false;
      },
    }));
  });
}
