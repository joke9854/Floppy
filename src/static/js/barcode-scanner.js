/**
 * Barcode Scanner Module for ISBN-13 decoding from images
 * Uses ZXing library to decode barcodes from uploaded photos
 */

// Barcode scanning functionality using ZXing
async function initBarcodeScanner() {
  // ZXing is loaded from a self-hosted static library in base.html
  if (typeof window.ZXing === 'undefined') {
    console.error('[BARCODE] ZXing library not loaded - make sure the script tag loaded correctly');
    return null;
  }

  try {
    const { BrowserMultiFormatReader, BarcodeFormat, DecodeHintType } = window.ZXing;
    
    const hints = new Map();
    const formats = [
      BarcodeFormat.EAN_13,
      BarcodeFormat.EAN_8,
      BarcodeFormat.UPC_A,
      BarcodeFormat.UPC_E,
    ];
    hints.set(DecodeHintType.POSSIBLE_FORMATS, formats);
    
    hints.set(DecodeHintType.TRY_HARDER, true);
    
    hints.set(DecodeHintType.CHARACTER_SET, 'UTF-8');
    
    const reader = new BrowserMultiFormatReader(hints);
    
    return reader;
  } catch (error) {
    console.error('[BARCODE] Error initializing ZXing reader:', error);
    console.error('[BARCODE] Error stack:', error?.stack);
    return null;
  }
}

/**
 * Validate if a decoded code is a valid ISBN-13
 * ISBN-13 must be 13 digits and typically starts with 978 or 979
 */
function computeIsbn13CheckDigit(isbn12) {
  let sum = 0;
  for (let i = 0; i < isbn12.length; i += 1) {
    const digit = Number.parseInt(isbn12[i], 10);
    if (Number.isNaN(digit)) {
      return null;
    }
    sum += digit * (i % 2 === 0 ? 1 : 3);
  }
  return (10 - (sum % 10)) % 10;
}

/**
 * Compute the ISBN-10 check digit (positions weighted 10..2, remainder mod 11).
 * Returns 10 for a remainder of 10 ('X' in print, but this path only ever
 * sees digit-only input - see normalizeIsbn).
 */
function computeIsbn10CheckDigit(isbn9) {
  let sum = 0;
  for (let i = 0; i < 9; i += 1) {
    const digit = Number.parseInt(isbn9[i], 10);
    if (Number.isNaN(digit)) {
      return null;
    }
    sum += digit * (10 - i);
  }
  return (11 - (sum % 11)) % 11;
}

function normalizeIsbn(code) {
  if (!code) return null;

  const cleaned = code.replace(/\D/g, '');

  if (cleaned.length === 10) {
    const isbn9 = cleaned.slice(0, 9);
    // cleaned is digits-only (\D was stripped above), so an ISBN-10 check
    // digit of 'X' never reaches this branch - only a 0-9 check digit does.
    // A misread digit from a blurry scan can still produce 10 digits, so the
    // check digit is verified here instead of trusted, otherwise a misscan
    // silently turns into a different, wrong-but-valid-looking ISBN-13.
    const providedCheckDigit = Number.parseInt(cleaned[9], 10);
    if (providedCheckDigit !== computeIsbn10CheckDigit(isbn9)) {
      return null;
    }
    const isbn12 = `978${isbn9}`;
    const checkDigit = computeIsbn13CheckDigit(isbn12);
    return checkDigit === null ? null : `${isbn12}${checkDigit}`;
  }

  if (cleaned.length > 13) {
    const candidate = cleaned.slice(0, 13);
    if (candidate.startsWith('978') || candidate.startsWith('979')) {
      return candidate;
    }
    return null;
  }

  if (cleaned.length === 13) {
    if (cleaned.startsWith('978') || cleaned.startsWith('979')) {
      return cleaned;
    }
    return null;
  }

  return null;
}

function loadImageFromUrl(url) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.decoding = 'async';
    img.onload = () => resolve(img);
    img.onerror = (error) => reject(error);
    img.src = url;
  });
}

function createCanvasFromImage(img, maxDimension) {
  const width = img.naturalWidth || img.width;
  const height = img.naturalHeight || img.height;
  const maxSide = Math.max(width, height);
  const scale = maxDimension ? Math.min(1, maxDimension / maxSide) : 1;
  const targetWidth = Math.max(1, Math.round(width * scale));
  const targetHeight = Math.max(1, Math.round(height * scale));
  const canvas = document.createElement('canvas');
  const ctx = canvas.getContext('2d');
  if (!ctx) {
    throw new Error('Canvas context not available');
  }

  canvas.width = targetWidth;
  canvas.height = targetHeight;
  ctx.drawImage(img, 0, 0, targetWidth, targetHeight);
  return canvas;
}

function cropCanvas(sourceCanvas, crop) {
  const canvas = document.createElement('canvas');
  const ctx = canvas.getContext('2d');
  if (!ctx) {
    throw new Error('Canvas context not available');
  }

  const sx = Math.max(0, Math.floor(crop.sx));
  const sy = Math.max(0, Math.floor(crop.sy));
  const sw = Math.max(1, Math.floor(crop.sw));
  const sh = Math.max(1, Math.floor(crop.sh));

  canvas.width = Math.min(sourceCanvas.width, sw);
  canvas.height = Math.min(sourceCanvas.height, sh);
  ctx.drawImage(sourceCanvas, sx, sy, sw, sh, 0, 0, canvas.width, canvas.height);
  return canvas;
}

async function canvasToImage(canvas) {
  if (canvas.toBlob) {
    const blob = await new Promise((resolve, reject) => {
      canvas.toBlob((result) => {
        if (result) {
          resolve(result);
          return;
        }
        reject(new Error('Failed to create image blob'));
      }, 'image/jpeg', 0.9);
    });

    const url = URL.createObjectURL(blob);
    try {
      return await loadImageFromUrl(url);
    } finally {
      URL.revokeObjectURL(url);
    }
  }

  const dataUrl = canvas.toDataURL('image/jpeg', 0.9);
  return loadImageFromUrl(dataUrl);
}

/**
 * Decode barcode from image file
 * @param {File} file - Image file to decode
 * @returns {Promise<string|null>} Decoded ISBN-13 or null if failed
 */
async function decodeBarcodeFromFile(file) {
  try {
    const reader = await initBarcodeScanner();
    if (!reader) {
      console.error('[BARCODE] Failed to initialize barcode reader - reader is null/undefined');
      return null;
    }

    const imageUrl = URL.createObjectURL(file);
    let originalImg;
    try {
      originalImg = await loadImageFromUrl(imageUrl);
    } finally {
      URL.revokeObjectURL(imageUrl);
    }

    const naturalWidth = originalImg.naturalWidth || originalImg.width;
    const naturalHeight = originalImg.naturalHeight || originalImg.height;
    
    const maxDimension = 1600;
    const baseCanvas = createCanvasFromImage(originalImg, maxDimension);
    
    const candidates = [
      { label: 'full', canvas: baseCanvas },
    ];

    const height = baseCanvas.height;
    const width = baseCanvas.width;
    
    if (height >= 200) {
      const bottomHalfY = Math.floor(height * 0.5);
      const bottomHalfCanvas = cropCanvas(baseCanvas, { sx: 0, sy: bottomHalfY, sw: width, sh: height - bottomHalfY });
      candidates.push({
        label: 'bottom-half',
        canvas: bottomHalfCanvas,
      });

      const bottomThirdY = Math.floor(height * 0.65);
      const bottomThirdCanvas = cropCanvas(baseCanvas, { sx: 0, sy: bottomThirdY, sw: width, sh: height - bottomThirdY });
      candidates.push({
        label: 'bottom-third',
        canvas: bottomThirdCanvas,
      });

      const bandHeight = Math.max(1, Math.floor(height * 0.3));
      const bandY = Math.floor((height - bandHeight) / 2);
      const centerBandCanvas = cropCanvas(baseCanvas, { sx: 0, sy: bandY, sw: width, sh: bandHeight });
      candidates.push({
        label: 'center-band',
        canvas: centerBandCanvas,
      });
    }


    for (let i = 0; i < candidates.length; i++) {
      const candidate = candidates[i];
      try {
        const candidateImg = await canvasToImage(candidate.canvas);
        
        const decodeStartTime = performance.now();
        const result = await reader.decodeFromImageElement(candidateImg);
        const decodeTime = performance.now() - decodeStartTime;
        
        if (!result) {
          continue;
        }

        const text = result.getText ? result.getText() : (result.text || result);
        
        const validatedISBN = normalizeIsbn(text);
        
        if (validatedISBN) {
          return validatedISBN;
        } else {
        }
      } catch (error) {
        const errorName = error?.name || 'Error';
        const errorMessage = error?.message || '';
        const errorStack = error?.stack || '';
        
        if (errorName !== 'NotFoundException' && errorName !== 'NoCodeFoundException') {
          console.error('[BARCODE] Unexpected error type (not NotFoundException/NoCodeFoundException):', error);
          console.error('[BARCODE] Full error object:', error);
        }
      }
    }

    return null;
  } catch (error) {
    console.error('[BARCODE] Fatal error in decodeBarcodeFromFile:', error);
    console.error('[BARCODE] Error stack:', error?.stack);
    return null;
  }
}

/**
 * Alternative decode method using ZXing's image decoding
 * This is a fallback if the imageData method doesn't work
 */
async function decodeBarcodeFromImageElement(imgElement) {
  try {
    const reader = await initBarcodeScanner();
    if (!reader) return null;

    const result = await reader.decodeFromImageElement(imgElement);
    
    if (result) {
      return normalizeIsbn(result.getText());
    }
    
    return null;
  } catch (error) {
    console.error('Error decoding from image element:', error);
    return null;
  }
}

// Export for use in Alpine.js
window.barcodeScannerUtils = {
  decodeBarcodeFromFile,
  decodeBarcodeFromImageElement,
  normalizeIsbn,
};
