#!/usr/bin/env python3
"""
Offline Invoice Scanner - Converts invoice images to XML format
Uses OCR (Tesseract) to extract text from images and parse invoice data
"""

import re
import os
import sys
from datetime import datetime
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom
from pathlib import Path

try:
    from PIL import Image
    import pytesseract
except ImportError:
    print("Error: Required libraries not installed.")
    print("Please run: pip install pillow pytesseract")
    print("Also install Tesseract OCR: brew install tesseract (macOS) or apt-get install tesseract-ocr (Linux)")
    sys.exit(1)


class InvoiceParser:
    """Parse invoice text and extract structured data"""

    def __init__(self, text):
        self.text = text
        self.lines = text.split('\n')

    def extract_invoice_number(self):
        """Extract invoice number (e.g., TRU0408374, VK100389)"""
        patterns = [
            r'Nr[.:\s]+([A-Z]+\d+)',
            r'Invoice[:\s]+([A-Z]+\d+)',
            r'Sąskaita[:\s]+([A-Z]+\d+)',
            r'\b([A-Z]{2,4}\d{5,})\b'
        ]
        for pattern in patterns:
            match = re.search(pattern, self.text, re.IGNORECASE)
            if match:
                return match.group(1)
        return "UNKNOWN"

    def extract_date(self):
        """Extract invoice date"""
        patterns = [
            r'Data[:/\s]+(\d{4}-\d{2}-\d{2})',
            r'Date[:/\s]+(\d{4}-\d{2}-\d{2})',
            r'\b(\d{4}-\d{2}-\d{2})\b',
            r'\b(\d{2}/\d{2}/\d{4})\b',
            r'\b(\d{2}\.\d{2}\.\d{4})\b'
        ]
        for pattern in patterns:
            match = re.search(pattern, self.text)
            if match:
                date_str = match.group(1)
                # Convert to standard format
                if '/' in date_str:
                    date_obj = datetime.strptime(date_str, '%d/%m/%Y')
                    return date_obj.strftime('%Y-%m-%d')
                elif '.' in date_str:
                    date_obj = datetime.strptime(date_str, '%d.%m.%Y')
                    return date_obj.strftime('%Y-%m-%d')
                return date_str
        return datetime.now().strftime('%Y-%m-%d')

    def extract_company(self, keywords):
        """Extract company information based on keywords"""
        company_data = {
            'name': '',
            'code': '',
            'vat': '',
            'address': '',
            'iban': ''
        }

        # Find company section
        section_start = -1
        for i, line in enumerate(self.lines):
            if any(kw.lower() in line.lower() for kw in keywords):
                section_start = i
                break

        if section_start == -1:
            return company_data

        # Look at next 15 lines for company details
        section_lines = self.lines[section_start:section_start+15]
        section = '\n'.join(section_lines)

        # Extract all VAT numbers in section
        vat_matches = re.findall(r'(LT\d{9,12})', section)
        if vat_matches:
            company_data['vat'] = vat_matches[0]

        # Extract all company codes (9 digits)
        code_matches = re.findall(r'\b(\d{9})\b', section)
        if code_matches:
            company_data['code'] = code_matches[0]

        # Extract IBAN (look for longer match)
        iban_match = re.search(r'(LT\d{18,20})', section)
        if iban_match:
            company_data['iban'] = iban_match.group(1)

        # Extract company name (UAB, AB, etc.) - take first occurrence after keyword
        for line in section_lines[1:8]:  # Skip first line (keyword line)
            name_match = re.search(r'(UAB|AB)\s+["\u201c\u201d]?([^"\u201c\u201d\n]{3,40})["\u201c\u201d]?', line, re.IGNORECASE)
            if name_match:
                name_text = name_match.group(2).strip()
                # Clean up common OCR artifacts
                name_text = name_text.split('|')[0].strip()
                name_text = name_text.split('/')[0].strip()
                company_data['name'] = f'{name_match.group(1).upper()} &quot;{name_text}&quot;'
                break

        # Extract address (line with street indicators, but not the keyword "Address:")
        for line in section_lines[1:10]:
            if ('g.' in line or 'pr.' in line) and any(city in line for city in ['Vilnius', 'Kaunas', 'Klaipėda', 'Šiauliai']):
                # Clean address
                addr = line.strip()
                addr = re.sub(r'^.*(?:Address|Adresas)[:/\s]*', '', addr, flags=re.IGNORECASE)
                addr = addr.split('|')[0].strip()
                if len(addr) > 10:  # Valid address should be longer
                    company_data['address'] = addr[:200]  # Limit length
                    break

        return company_data

    def extract_amounts(self):
        """Extract financial amounts (subtotal, VAT, total)"""
        amounts = {
            'subtotal': '0.00',
            'vat': '0.00',
            'total': '0.00',
            'vatpercent': '21.00'
        }

        # Find all amounts with optional space-separated thousands
        # Matches: 3 982,58 or 982,58 or 3982.58
        amount_pattern = r'(\d+(?:\s+\d{3})*[.,]\d{2})'

        # Look for total amount with keywords
        total_patterns = [
            r'(?:Total|Suma|apmok[eė]jimui)[:\s/]*' + amount_pattern + r'\s*EUR',
            r'total[:\s]*' + amount_pattern,
        ]

        total_found = None
        for pattern in total_patterns:
            match = re.search(pattern, self.text, re.IGNORECASE)
            if match:
                amount_str = match.group(1).replace(' ', '').replace(',', '.')
                total_found = float(amount_str)
                break

        # Look for VAT amount
        vat_pattern = r'(?:PVM|VAT)\s*[:/]?\s*\d+\s*%[:\s]*' + amount_pattern
        vat_match = re.search(vat_pattern, self.text, re.IGNORECASE)
        vat_found = None
        if vat_match:
            vat_str = vat_match.group(1).replace(' ', '').replace(',', '.')
            vat_found = float(vat_str)

        # Calculate values
        if total_found:
            amounts['total'] = f"{total_found:.2f}"

            if vat_found:
                amounts['vat'] = f"{vat_found:.2f}"
                amounts['subtotal'] = f"{total_found - vat_found:.2f}"
            else:
                # Assume 21% VAT
                calculated_subtotal = total_found / 1.21
                calculated_vat = total_found - calculated_subtotal
                amounts['subtotal'] = f"{calculated_subtotal:.2f}"
                amounts['vat'] = f"{calculated_vat:.2f}"

        return amounts

    def extract_line_items(self):
        """Extract line items from invoice table"""
        items = []

        # Look for table section (between header and totals)
        in_table = False
        skip_keywords = ['total', 'suma', 'viso', 'pvm', 'vat', 'amount', 'apmok', 'skola', 'overdue', 'payment', 'svoris', 'weight']

        for i, line in enumerate(self.lines):
            line_lower = line.lower()

            # Start table detection after seeing quantity/unit indicators
            if any(indicator in line_lower for indicator in ['kiekis', 'quantity', 'vnt', 'mėn', 'unit']):
                in_table = True
                continue

            # Stop at summary/total section
            if any(keyword in line_lower for keyword in ['iš viso', 'total', 'suma apmok', 'saskaitos']):
                in_table = False

            # Skip lines that are clearly not items
            if any(skip in line_lower for skip in skip_keywords):
                continue

            if in_table and re.search(r'\d+(?:\s+\d{3})*[.,]\d{2}', line):
                # This looks like a line item
                # Extract components
                item = {
                    'code': '',
                    'name': '',
                    'quantity': '1.00',
                    'price': '0.00',
                    'unit': 'vnt'
                }

                # Extract code (usually at start, alphanumeric)
                code_match = re.match(r'^\s*(\w+[-\w]*)', line)
                if code_match:
                    item['code'] = code_match.group(1)

                # Extract amounts (with space-separated thousands)
                amounts = re.findall(r'(\d+(?:\s+\d{3})*[.,]\d{2})', line)
                if amounts:
                    # Last or second-to-last amount is usually the price
                    price_str = amounts[-1] if len(amounts) == 1 else amounts[-2] if len(amounts) > 1 else amounts[-1]
                    item['price'] = price_str.replace(' ', '').replace(',', '.')

                # Extract quantity (usually before price, format: 1,00 or 1.00)
                qty_match = re.search(r'\b(\d+[.,]\d{2})\b', line)
                if qty_match:
                    qty_str = qty_match.group(1).replace(',', '.')
                    if float(qty_str) < 10000:  # Reasonable quantity
                        item['quantity'] = qty_str

                # Extract description (text between code and amounts)
                desc = line
                desc = re.sub(r'^\s*\w+[-\w]*\s*', '', desc)  # Remove code
                desc = re.sub(r'\d+(?:\s+\d{3})*[.,]\d{2}', '', desc)  # Remove amounts
                desc = re.sub(r'\b(?:vnt|mėn|m2|kg)\b', '', desc, flags=re.IGNORECASE)  # Remove units
                desc = desc.strip()
                if len(desc) > 3:
                    item['name'] = desc[:100]
                else:
                    item['name'] = 'Prekė/paslauga'

                # Extract unit
                unit_match = re.search(r'\b(vnt|mėn|m2|m³|kg|val)\b', line, re.IGNORECASE)
                if unit_match:
                    item['unit'] = unit_match.group(1).lower()

                items.append(item)

        # Limit to reasonable number of items (avoid junk)
        items = items[:10]

        # If no valid items found, create one from total
        if not items:
            amounts = self.extract_amounts()
            items.append({
                'code': 'SERVICE',
                'name': 'Paslaugos',
                'quantity': '1.00',
                'price': amounts['subtotal'],
                'unit': 'vnt'
            })

        return items


def ocr_image(image_path):
    """Extract text from image using OCR"""
    try:
        image = Image.open(image_path)

        # Configure Tesseract for Lithuanian language
        # If Lithuanian language pack is not installed, falls back to English
        custom_config = r'--oem 3 --psm 6'

        # Try Lithuanian first, then fallback to English
        try:
            text = pytesseract.image_to_string(image, lang='lit', config=custom_config)
        except:
            text = pytesseract.image_to_string(image, lang='eng', config=custom_config)

        return text
    except Exception as e:
        print(f"Error processing image: {e}")
        return ""


def create_xml(invoice_data, filename):
    """Create XML document in Apskaita5 format"""

    # Create root element
    documents = Element('documents')
    documents.set('xmlns:xsi', 'http://www.w3.org/2001/XMLSchema-instance')

    document = SubElement(documents, 'document')

    # Add document fields
    SubElement(document, 'optype').text = 'pirkimas'
    SubElement(document, 'id').text = invoice_data['invoice_number']
    SubElement(document, 'docnum').text = invoice_data['invoice_number'].lstrip('ABCDEFGHIJKLMNOPQRSTUVWXYZ')
    SubElement(document, 'docser').text = ''.join([c for c in invoice_data['invoice_number'] if c.isalpha()])
    SubElement(document, 'date').text = invoice_data['date']
    SubElement(document, 'operationdate').text = invoice_data['date']
    SubElement(document, 'duedate').text = invoice_data['date']
    SubElement(document, 'subtotal').text = invoice_data['amounts']['subtotal']
    SubElement(document, 'vat').text = invoice_data['amounts']['vat']
    SubElement(document, 'total').text = invoice_data['amounts']['total']
    SubElement(document, 'currency').text = 'EUR'
    SubElement(document, 'currencyrate').text = '1'
    SubElement(document, 'url').text = ''
    SubElement(document, 'filename').text = filename
    SubElement(document, 'report2isaf').text = 'true'
    SubElement(document, 'separatevat').text = 'false'

    # Seller information
    seller = invoice_data['seller']
    SubElement(document, 'sellerid').text = seller['code']
    SubElement(document, 'sellercode').text = seller['code']
    SubElement(document, 'sellervat').text = seller['vat']
    SubElement(document, 'sellername').text = seller['name']
    SubElement(document, 'selleraddress').text = seller['address']
    SubElement(document, 'sellerisperson').text = 'false'
    SubElement(document, 'sellercountry').text = 'lt'
    SubElement(document, 'selleriban').text = seller['iban']

    # Buyer information
    buyer = invoice_data['buyer']
    SubElement(document, 'buyerid').text = buyer['code']
    SubElement(document, 'buyercode').text = buyer['code']
    SubElement(document, 'buyervat').text = buyer['vat']
    SubElement(document, 'buyername').text = buyer['name']
    SubElement(document, 'buyeraddress').text = buyer['address']
    SubElement(document, 'buyerisperson').text = 'false'
    SubElement(document, 'buyercountry').text = 'lt'

    SubElement(document, 'hasreceipt').text = 'false'

    # Line items
    for idx, item in enumerate(invoice_data['items']):
        line = SubElement(document, 'line')
        SubElement(line, 'lineid').text = str(idx)
        SubElement(line, 'price').text = item['price']
        SubElement(line, 'subtotal').text = item['price']

        # Calculate VAT for line item
        price_float = float(item['price'])
        quantity = float(item['quantity'])
        subtotal = price_float * quantity
        vat_amount = subtotal * 0.21
        total = subtotal + vat_amount

        SubElement(line, 'vat').text = f"{vat_amount:.2f}"
        SubElement(line, 'vatpercent').text = '21.00'
        SubElement(line, 'total').text = f"{total:.2f}"
        SubElement(line, 'code').text = item['code']
        SubElement(line, 'name').text = item['name']
        SubElement(line, 'unit').text = item['unit']
        SubElement(line, 'quantity').text = item['quantity']
        SubElement(line, 'vatclass').text = 'PVM1'
        SubElement(line, 'warehouse').text = ''
        SubElement(line, 'object').text = ''

    # Convert to pretty XML string without newline at end
    rough_string = tostring(documents, encoding='utf-8')
    reparsed = minidom.parseString(rough_string)
    xml_string = reparsed.toprettyxml(indent="  ", encoding='utf-8').decode('utf-8')

    # Remove XML declaration and clean up
    xml_lines = xml_string.split('\n')[1:]  # Remove <?xml...?> line
    xml_string = '\n'.join(xml_lines).rstrip('\n')

    return xml_string


def process_invoice(image_path, output_dir='xml_results'):
    """Process an invoice image and create XML file"""

    print(f"Processing: {image_path}")

    # Extract text from image
    print("  → Running OCR...")
    text = ocr_image(image_path)

    if not text:
        print("  ✗ No text extracted from image")
        return None

    print(f"  → Extracted {len(text)} characters")

    # Parse invoice data
    print("  → Parsing invoice data...")
    parser = InvoiceParser(text)

    invoice_data = {
        'invoice_number': parser.extract_invoice_number(),
        'date': parser.extract_date(),
        'seller': parser.extract_company(['Pardavėjas', 'Seller', 'From']),
        'buyer': parser.extract_company(['Pirkėjas', 'Buyer', 'To']),
        'amounts': parser.extract_amounts(),
        'items': parser.extract_line_items()
    }

    print(f"  → Invoice #: {invoice_data['invoice_number']}")
    print(f"  → Date: {invoice_data['date']}")
    print(f"  → Total: {invoice_data['amounts']['total']} EUR")

    # Create XML
    print("  → Generating XML...")
    filename = os.path.basename(image_path)
    xml_content = create_xml(invoice_data, filename)

    # Save XML file
    os.makedirs(output_dir, exist_ok=True)
    xml_filename = Path(filename).stem + '.xml'
    xml_path = os.path.join(output_dir, xml_filename)

    with open(xml_path, 'w', encoding='utf-8') as f:
        f.write(xml_content)

    print(f"  ✓ Saved to: {xml_path}\n")

    return xml_path


def main():
    """Main entry point"""

    if len(sys.argv) < 2:
        print("Usage: python invoice_scanner.py <image_file> [output_dir]")
        print("Example: python invoice_scanner.py invoice.jpg xml_results")
        sys.exit(1)

    image_path = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else 'xml_results'

    if not os.path.exists(image_path):
        print(f"Error: Image file not found: {image_path}")
        sys.exit(1)

    # Process single image or directory
    if os.path.isdir(image_path):
        print(f"Processing all images in: {image_path}\n")
        image_files = [f for f in os.listdir(image_path)
                      if f.lower().endswith(('.jpg', '.jpeg', '.png', '.tiff', '.bmp'))]

        for img_file in image_files:
            full_path = os.path.join(image_path, img_file)
            try:
                process_invoice(full_path, output_dir)
            except Exception as e:
                print(f"  ✗ Error: {e}\n")
    else:
        process_invoice(image_path, output_dir)

    print("Done!")


if __name__ == '__main__':
    main()
