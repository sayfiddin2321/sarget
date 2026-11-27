async function waitForReceiptImages() {
  const card = document.getElementById('receiptCard');
  if (document.fonts) await document.fonts.ready;
  await Promise.all(Array.from(card.querySelectorAll('img')).map(async image => {
    if (image.decode) {
      await image.decode();
    } else if (!image.complete) {
      await new Promise((resolve, reject) => {
        image.addEventListener('load', resolve, { once: true });
        image.addEventListener('error', reject, { once: true });
      });
    }
    if (!image.naturalWidth) throw new Error('Chek rasmi yuklanmadi');
  }));
  // Allow the decoded images to paint before print or PNG capture starts.
  await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
}

function sizeReceiptPage() {
  const card = document.getElementById('receiptCard');
  const paperWidth = document.documentElement.dataset.receiptPaper === '58' ? 58 : 80;
  // Mobile previews can be narrower than paper. Measure an off-screen copy at
  // the actual printable width, using the same typography and spacing as print.
  const copy = card.cloneNode(true);
  copy.setAttribute('aria-hidden', 'true');
  Object.assign(copy.style, {
    position: 'absolute', left: '-10000px', top: '0',
    width: 'var(--receipt-content-width)', maxWidth: 'none',
    height: 'auto', minHeight: '0', margin: '0', boxShadow: 'none'
  });
  // Print media's max-width: 100% must not clamp this absolute copy to a
  // narrow viewport when beforeprint runs on a phone.
  copy.style.setProperty('max-width', 'none', 'important');
  card.parentElement.appendChild(copy);
  let heightMm;
  try {
    // Half a millimetre allows for printer/browser rounding without a blank page.
    heightMm = Math.ceil((copy.getBoundingClientRect().height * 25.4 / 96 + 0.5) * 10) / 10;
  } finally {
    copy.remove();
  }
  let pageStyle = document.getElementById('receiptPageSize');
  if (!pageStyle) {
    pageStyle = document.createElement('style');
    pageStyle.id = 'receiptPageSize';
    document.head.appendChild(pageStyle);
  }
  // CSS page size cannot combine a length with "auto"; supply two lengths.
  pageStyle.textContent = `@media print { @page { size: ${paperWidth}mm ${heightMm}mm; margin: 0mm !important; } }`;
}

const receiptPaperSelect = document.getElementById('receiptPaperWidth');
const receiptPaperStorageKey = 'sargetcrm_receipt_paper_width';

function applyReceiptPaperWidth(value) {
  const width = value === '58' ? '58' : '80';
  document.documentElement.dataset.receiptPaper = width;
  receiptPaperSelect.value = width;
  sizeReceiptPage();
}

let savedReceiptPaperWidth = '80';
try {
  savedReceiptPaperWidth = localStorage.getItem(receiptPaperStorageKey);
} catch (error) {
  // The selector and printing still work when browser storage is unavailable.
}
applyReceiptPaperWidth(savedReceiptPaperWidth);
receiptPaperSelect.addEventListener('change', () => {
  applyReceiptPaperWidth(receiptPaperSelect.value);
  try {
    localStorage.setItem(receiptPaperStorageKey, receiptPaperSelect.value);
  } catch (error) {
    // Keep the selected width for this page even if it cannot be persisted.
  }
});
// Prepare native menu printing as soon as the embedded QR, logo and fonts load.
waitForReceiptImages().then(sizeReceiptPage).catch(error => console.warn('Receipt images:', error));

async function printReceipt() {
  const button = document.getElementById('btnPrintReceipt');
  if (button.disabled) return;
  button.disabled = true;
  receiptPaperSelect.disabled = true;
  try {
    await waitForReceiptImages();
    sizeReceiptPage();
    window.print();
  } catch (error) {
    console.error('Receipt print error:', error);
    alert("Chek rasmlari yuklanmadi. Sahifani yangilab qayta urinib ko'ring.");
  } finally {
    button.disabled = false;
    receiptPaperSelect.disabled = false;
  }
}

// Native menu printing also gets the measured roll length. Ctrl/Cmd+P waits for images.
window.addEventListener('beforeprint', sizeReceiptPage);
document.addEventListener('keydown', event => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'p') {
    event.preventDefault();
    printReceipt();
  }
});

async function downloadReceiptImage() {
  const card = document.getElementById('receiptCard');
  const button = document.getElementById('btnDownloadImage');
  const originalText = button.innerHTML;
  button.textContent = 'Tayyorlanmoqda...';
  button.disabled = true;
  try {
    await waitForReceiptImages();
    const canvas = await html2canvas(card, {
      scale: 2.5,
      useCORS: true,
      backgroundColor: '#ffffff',
      logging: false
    });
    const link = document.createElement('a');
    link.download = `chek_${card.querySelector('.chk-val').textContent.trim()}.png`;
    link.href = canvas.toDataURL('image/png');
    link.click();
  } catch (error) {
    console.error('Receipt capture error:', error);
    alert("Chek rasmini saqlab bo'lmadi. Sahifani yangilab qayta urinib ko'ring.");
  } finally {
    button.innerHTML = originalText;
    button.disabled = false;
  }
}
