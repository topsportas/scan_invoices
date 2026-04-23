# Offline Invoice Scanner

This program scans invoice images and converts them to XML format for Apskaita5 - **completely offline**, no internet or Claude required!

## Setup (One-time)

### 1. Install Tesseract OCR

**macOS:**
```bash
brew install tesseract
brew install tesseract-lang  # Optional: for better Lithuanian support
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt-get update
sudo apt-get install tesseract-ocr
sudo apt-get install tesseract-ocr-lit  # Optional: Lithuanian language pack
```

**Windows:**
Download installer from: https://github.com/UB-Mannheim/tesseract/wiki

### 2. Install Python packages

```bash
pip install -r requirements.txt
```

Or manually:
```bash
pip install pillow pytesseract
```

## Usage

### Process a single invoice:

```bash
python invoice_scanner.py 202604231957.jpg
```

### Process a single invoice to custom output folder:

```bash
python invoice_scanner.py 202604231957.jpg my_xml_folder
```

### Process all images in a folder:

```bash
python invoice_scanner.py /path/to/invoices/ xml_results
```

### Make it executable (optional):

```bash
chmod +x invoice_scanner.py
./invoice_scanner.py invoice.jpg
```

## How it works

1. **OCR (Optical Character Recognition)** - Tesseract extracts text from the image
2. **Text Parsing** - Regex patterns find invoice numbers, dates, amounts, company details
3. **XML Generation** - Creates XML file in Apskaita5 format
4. **Output** - Saves to `xml_results/` folder (or custom folder you specify)

## Limitations

⚠️ **OCR accuracy depends on:**
- Image quality (clear, high-resolution images work best)
- Text orientation (horizontal text works best)
- Invoice layout consistency

⚠️ **Not as smart as AI:**
- Won't understand context like Claude does
- Might miss data if invoice format is unusual
- May need manual verification/correction

⚠️ **Best practices:**
- Use high-quality scans (300+ DPI)
- Ensure good lighting and contrast
- Keep invoice flat (no crumpled edges)
- Review generated XML before importing

## Advantages

✅ **100% Offline** - No internet needed
✅ **Free** - Open source tools
✅ **Fast** - Processes images in seconds
✅ **Batch Processing** - Handle multiple invoices at once
✅ **Privacy** - Your data never leaves your computer

## Troubleshooting

**"pytesseract not found"**
- Make sure Tesseract OCR is installed (step 1)
- On macOS, may need: `export PATH="/opt/homebrew/bin:$PATH"`

**"No text extracted"**
- Image quality may be too low
- Try scanning at higher resolution
- Check if image is upside down or rotated

**"Poor extraction accuracy"**
- Install Lithuanian language pack for Tesseract
- Enhance image contrast before scanning
- Try preprocessing image (increase contrast, convert to grayscale)

## Improving Accuracy

For better results, you can preprocess images:

```python
# Example: Enhance image before OCR
from PIL import Image, ImageEnhance

img = Image.open('invoice.jpg')
# Increase contrast
enhancer = ImageEnhance.Contrast(img)
img = enhancer.enhance(2)
# Convert to grayscale
img = img.convert('L')
img.save('enhanced_invoice.jpg')
```

Then process the enhanced image with the scanner.
