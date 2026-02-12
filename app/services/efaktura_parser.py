"""
Parser za srpske eFaktura XML fajlove (UBL 2.1 format).

Podržava DocumentEnvelope wrapper i direktni Invoice element.
"""

import xml.etree.ElementTree as ET
from decimal import Decimal, InvalidOperation


def _find_element(parent, local_name):
    """Find first child element by local name, ignoring namespaces."""
    for elem in parent:
        tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
        if tag == local_name:
            return elem
    return None


def _find_all(parent, local_name):
    """Find all descendant elements by local name, ignoring namespaces."""
    results = []
    for elem in parent.iter():
        tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
        if tag == local_name:
            results.append(elem)
    return results


def _find_deep(parent, local_name):
    """Find first descendant element by local name, ignoring namespaces."""
    for elem in parent.iter():
        tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
        if tag == local_name:
            return elem
    return None


def _text(elem):
    """Get text content of element, or empty string."""
    return (elem.text or '').strip() if elem is not None else ''


def _decimal(elem):
    """Get Decimal value from element text."""
    txt = _text(elem)
    if not txt:
        return Decimal('0')
    try:
        return Decimal(txt)
    except InvalidOperation:
        return Decimal('0')


def parse_efaktura_xml(file_content: bytes) -> dict:
    """
    Parse eFaktura XML and return structured data.

    Supports both:
    - DocumentEnvelope wrapper (standard eFaktura portal format)
    - Direct Invoice element

    Returns dict with supplier info, invoice header, and line items.
    Raises ValueError if XML is invalid or missing required elements.
    """
    # Handle BOM
    if file_content.startswith(b'\xef\xbb\xbf'):
        file_content = file_content[3:]

    try:
        root = ET.fromstring(file_content)
    except ET.ParseError as e:
        raise ValueError(f'Neispravan XML format: {e}')

    # Find Invoice element (may be nested in DocumentEnvelope/DocumentBody)
    root_tag = root.tag.split('}')[-1] if '}' in root.tag else root.tag

    if root_tag == 'Invoice':
        invoice = root
    else:
        invoice = _find_deep(root, 'Invoice')
        if invoice is None:
            raise ValueError('XML ne sadrži Invoice element')

    # Invoice header
    invoice_number = _text(_find_element(invoice, 'ID'))
    issue_date = _text(_find_element(invoice, 'IssueDate'))
    due_date = _text(_find_element(invoice, 'DueDate'))

    if not invoice_number:
        raise ValueError('Faktura nema broj (ID)')
    if not issue_date:
        raise ValueError('Faktura nema datum (IssueDate)')

    # Supplier info
    supplier_party = _find_deep(invoice, 'AccountingSupplierParty')
    supplier_name = ''
    supplier_pib = ''
    if supplier_party:
        reg_name = _find_deep(supplier_party, 'RegistrationName')
        supplier_name = _text(reg_name)
        company_id = _find_deep(supplier_party, 'CompanyID')
        supplier_pib = _text(company_id)

    # eFaktura ID from envelope
    efaktura_id = None
    if root_tag != 'Invoice':
        sales_inv_id = _find_deep(root, 'SalesInvoiceId')
        efaktura_id = _text(sales_inv_id) or None

    # Parse invoice lines
    items = []
    for line in _find_all(invoice, 'InvoiceLine'):
        # Skip the Invoice element itself if iter catches it
        line_tag = line.tag.split('}')[-1] if '}' in line.tag else line.tag
        if line_tag != 'InvoiceLine':
            continue

        quantity_elem = _find_deep(line, 'InvoicedQuantity')
        quantity_text = _text(quantity_elem)
        try:
            quantity = int(Decimal(quantity_text)) if quantity_text else 1
        except (InvalidOperation, ValueError):
            quantity = 1

        line_total = _decimal(_find_deep(line, 'LineExtensionAmount'))

        # Item details
        item_elem = _find_deep(line, 'Item')
        name = ''
        supplier_code = ''
        barcode = ''
        tax_percent = Decimal('20')

        if item_elem:
            name = _text(_find_element(item_elem, 'Name'))

            sellers_id = _find_deep(item_elem, 'SellersItemIdentification')
            if sellers_id:
                supplier_code = _text(_find_element(sellers_id, 'ID'))

            standard_id = _find_deep(item_elem, 'StandardItemIdentification')
            if standard_id:
                barcode = _text(_find_element(standard_id, 'ID'))

            tax_cat = _find_deep(item_elem, 'ClassifiedTaxCategory')
            if tax_cat:
                pct = _find_element(tax_cat, 'Percent')
                if pct is not None and _text(pct):
                    tax_percent = _decimal(pct)

        # Unit price
        price_elem = _find_deep(line, 'Price')
        unit_price = Decimal('0')
        if price_elem:
            unit_price = _decimal(_find_element(price_elem, 'PriceAmount'))

        if not name:
            continue

        items.append({
            'name': name,
            'supplier_code': supplier_code,
            'barcode': barcode,
            'quantity': quantity,
            'unit_price': unit_price,
            'line_total': line_total,
            'tax_percent': tax_percent,
        })

    if not items:
        raise ValueError('Faktura nema stavki (InvoiceLine)')

    # Totals from LegalMonetaryTotal
    monetary = _find_deep(invoice, 'LegalMonetaryTotal')
    total_without_vat = Decimal('0')
    total_with_vat = Decimal('0')
    if monetary:
        total_without_vat = _decimal(_find_deep(monetary, 'TaxExclusiveAmount'))
        total_with_vat = _decimal(_find_deep(monetary, 'TaxInclusiveAmount'))
        if not total_with_vat:
            total_with_vat = _decimal(_find_deep(monetary, 'PayableAmount'))

    return {
        'supplier_name': supplier_name,
        'supplier_pib': supplier_pib,
        'invoice_number': invoice_number,
        'invoice_date': issue_date,
        'due_date': due_date or None,
        'efaktura_id': efaktura_id,
        'items': items,
        'total_without_vat': total_without_vat,
        'total_with_vat': total_with_vat,
    }
