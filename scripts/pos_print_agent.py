#!/usr/bin/env python3
"""
ServisHub POS Print Agent
=========================
Standalone HTTP server that receives receipt data from the web app
and prints directly to a thermal POS printer via ESC/POS commands.

Usage:
    # USB printer (need Vendor ID and Product ID from System Info):
    python pos_print_agent.py --vendor 0x0483 --product 0x5720

    # Network printer:
    python pos_print_agent.py --network 192.168.1.100

    # Custom port for the HTTP agent:
    python pos_print_agent.py --vendor 0x0483 --product 0x5720 --agent-port 9200

Requirements:
    pip install python-escpos flask flask-cors

Finding Vendor/Product ID:
    macOS:   System Information → USB → Your Printer
    Windows: Device Manager → USB → Properties → Hardware IDs
    Linux:   lsusb
"""

import argparse
import json
import sys
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler

# ---------------------------------------------------------------------------
# Price formatting helper
# ---------------------------------------------------------------------------

def fmt(val):
    """Format number as Serbian price: 1.234,56"""
    if val is None:
        return '0,00'
    try:
        val = float(val)
    except (TypeError, ValueError):
        return '0,00'
    # Format with 2 decimals, then convert to Serbian style
    s = f'{val:,.2f}'
    # Swap , and . for Serbian format
    s = s.replace(',', 'X').replace('.', ',').replace('X', '.')
    return s


# ---------------------------------------------------------------------------
# ESC/POS receipt formatter
# ---------------------------------------------------------------------------

LINE_WIDTH = 42  # characters for 80mm paper

def format_receipt(p, data):
    """Format and print a receipt using ESC/POS commands."""
    tenant = data.get('tenant', {})
    receipt = data.get('receipt', {})
    items = receipt.get('items', [])
    paper = data.get('paper_size', '80')
    width = 32 if paper == '58' else LINE_WIDTH

    sep = '=' * width
    dash = '-' * width

    # --- Header ---
    p.set(align='center', width=2, height=2)
    p.text((tenant.get('name') or 'ServisHub') + '\n')
    p.set(align='center', width=1, height=1)
    if tenant.get('address'):
        p.text(tenant['address'] + '\n')
    if tenant.get('phone'):
        p.text('Tel: ' + tenant['phone'] + '\n')
    if tenant.get('pib'):
        p.text('PIB: ' + tenant['pib'] + '\n')

    p.text(sep + '\n')

    # --- Non-fiscal banner ---
    fiscal_signed = receipt.get('fiscal_status') == 'signed'
    if not fiscal_signed:
        p.set(align='center', bold=True)
        p.text('OVO NIJE FISKALNI RACUN\n')
        p.set(bold=False)
        p.text(sep + '\n')

    # --- Receipt type ---
    p.set(align='center')
    p.text('Vrsta racuna: Promet\n')
    tx = 'Refundacija' if receipt.get('receipt_type') == 'REFUND' else 'Prodaja'
    p.text(f'Tip transakcije: {tx}\n')
    p.text(sep + '\n')

    # --- Receipt info ---
    p.set(align='left')
    rn = receipt.get('receipt_number', '')
    p.text(f"{'Racun br:':<{width-len(rn)}s}{rn}\n")

    issued = receipt.get('issued_at', '')
    if issued:
        try:
            dt = datetime.fromisoformat(issued.replace('Z', '+00:00'))
            date_str = dt.strftime('%d.%m.%Y. %H:%M:%S')
        except Exception:
            date_str = issued
        p.text(f"{'Datum:':<{width-len(date_str)}s}{date_str}\n")

    if receipt.get('issued_by'):
        name = receipt['issued_by']
        p.text(f"{'Kasir:':<{width-len(name)}s}{name}\n")

    # B2B buyer
    if receipt.get('buyer_pib'):
        p.text(dash + '\n')
        bpib = receipt['buyer_pib']
        p.text(f"{'Kupac PIB:':<{width-len(bpib)}s}{bpib}\n")
        if receipt.get('buyer_name'):
            bn = receipt['buyer_name']
            p.text(f"{'Kupac:':<{width-len(bn)}s}{bn}\n")

    p.text(sep + '\n')

    # --- Items ---
    total_tax = 0.0
    for i, item in enumerate(items):
        name = item.get('item_name', '')
        p.set(align='left', bold=True)
        # Truncate long names
        max_name = width - 4  # "1. " + "/Đ"
        display_name = name[:max_name] if len(name) > max_name else name
        p.text(f"{i+1}. {display_name} /\xc4\x90\n")
        p.set(bold=False)

        qty = item.get('quantity', 1)
        unit = fmt(item.get('unit_price', 0))
        total = fmt(item.get('line_total', 0))
        discount = item.get('discount_pct', 0)

        detail = f"  {qty} x {unit}"
        if discount and float(discount) > 0:
            detail += f" (-{discount}%)"

        pad = width - len(detail) - len(total)
        if pad < 1:
            pad = 1
        p.text(f"{detail}{' ' * pad}{total}\n")

        # Accumulate tax (assuming 20% PDV included in price)
        line_total = float(item.get('line_total', 0))
        total_tax += line_total - (line_total / 1.20)

    p.text(sep + '\n')

    # --- Totals ---
    discount_amount = float(receipt.get('discount_amount', 0))
    if discount_amount > 0:
        sub = fmt(receipt.get('subtotal', 0))
        p.text(f"{'Medjuzbir:':<{width-len(sub)}s}{sub}\n")
        disc = '-' + fmt(discount_amount)
        p.text(f"{'Popust:':<{width-len(disc)}s}{disc}\n")

    p.set(align='center', width=2, height=2)
    total_str = fmt(receipt.get('total_amount', 0))
    p.text(f"UKUPNO: {total_str}\n")
    p.set(width=1, height=1)

    p.text(dash + '\n')

    # --- Payment ---
    p.set(align='left')
    pm = receipt.get('payment_method', 'CASH')
    total_amount = float(receipt.get('total_amount', 0))

    if pm == 'CASH':
        val = fmt(total_amount)
        p.text(f"{'Gotovina:':<{width-len(val)}s}{val}\n")
        cash_recv = receipt.get('cash_received')
        if cash_recv and float(cash_recv) > total_amount:
            rv = fmt(cash_recv)
            p.text(f"{'Primljeno:':<{width-len(rv)}s}{rv}\n")
        cash_change = float(receipt.get('cash_change', 0))
        if cash_change > 0:
            cv = fmt(cash_change)
            p.text(f"{'Povracaj:':<{width-len(cv)}s}{cv}\n")
    elif pm == 'CARD':
        val = fmt(total_amount)
        p.text(f"{'Platna kartica:':<{width-len(val)}s}{val}\n")
    elif pm == 'TRANSFER':
        val = fmt(total_amount)
        p.text(f"{'Prenos na racun:':<{width-len(val)}s}{val}\n")
    elif pm == 'MIXED':
        cash_recv = float(receipt.get('cash_received', 0))
        cash_change = float(receipt.get('cash_change', 0))
        cash_part = cash_recv - cash_change
        if cash_part > 0:
            cv = fmt(cash_part)
            p.text(f"{'Gotovina:':<{width-len(cv)}s}{cv}\n")
        if receipt.get('card_amount'):
            ca = fmt(receipt['card_amount'])
            p.text(f"{'Platna kartica:':<{width-len(ca)}s}{ca}\n")
        if receipt.get('transfer_amount'):
            ta = fmt(receipt['transfer_amount'])
            p.text(f"{'Prenos na racun:':<{width-len(ta)}s}{ta}\n")
        if cash_change > 0:
            chv = fmt(cash_change)
            p.text(f"{'Povracaj:':<{width-len(chv)}s}{chv}\n")

    p.text(sep + '\n')

    # --- Tax table ---
    p.text('Oznaka  Ime     Stopa    Porez\n')
    tax_str = fmt(total_tax)
    p.text(f"\xc4\x90       O-PDV   20.00%   {tax_str}\n")
    p.text(dash + '\n')
    total_tax_str = fmt(total_tax)
    p.text(f"{'Ukupan iznos poreza:':<{width-len(total_tax_str)}s}{total_tax_str}\n")

    p.text(sep + '\n')

    # --- PFR metadata ---
    p.set(align='center')
    if issued:
        try:
            dt = datetime.fromisoformat(issued.replace('Z', '+00:00'))
            p.text(f"PFR vreme: {dt.strftime('%d.%m.%Y. %H:%M:%S')}\n")
        except Exception:
            pass

    # Counter
    num = ''.join(c for c in rn if c.isdigit()) or '1'
    suffix = 'RF' if receipt.get('receipt_type') == 'REFUND' else 'PR'
    p.text(f"PFR brojac: PP/{num}-{suffix}\n")

    # --- Void info ---
    if receipt.get('status') == 'VOIDED' and receipt.get('void_reason'):
        p.text(dash + '\n')
        p.text(f"Razlog storna: {receipt['void_reason']}\n")

    p.text(sep + '\n')

    # --- QR code ---
    qr_data = receipt.get('fiscal_qr_code')
    if qr_data:
        try:
            p.qr(qr_data, ec=1, size=8)
            p.text('\n')
        except Exception:
            pass  # Printer may not support QR

    # --- Footer ---
    p.set(align='center')
    footer = data.get('footer_message', 'Hvala na poseti!')
    p.text(footer + '\n')
    p.text('\n')

    # Cut
    if data.get('auto_cut', True):
        p.cut()


def print_test_page(p, data=None):
    """Print a simple test page."""
    p.set(align='center', width=2, height=2)
    p.text('TEST STAMPE\n')
    p.set(width=1, height=1)
    p.text('=' * LINE_WIDTH + '\n')
    p.text(f"Datum: {datetime.now().strftime('%d.%m.%Y. %H:%M:%S')}\n")
    p.text(f"Agent: ServisHub POS Print Agent\n")
    if data and data.get('company_name'):
        p.text(f"Firma: {data['company_name']}\n")
    p.text('=' * LINE_WIDTH + '\n')
    p.text('Stampac radi ispravno!\n')
    p.text('\n\n')
    p.cut()


# ---------------------------------------------------------------------------
# HTTP Server (no Flask dependency - stdlib only for simpler deployment)
# ---------------------------------------------------------------------------

printer_instance = None
printer_config = {}


class PrintAgentHandler(BaseHTTPRequestHandler):
    """HTTP request handler for print agent."""

    def _cors_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        # Chrome Private Network Access (HTTPS → localhost)
        self.send_header('Access-Control-Allow-Private-Network', 'true')

    def _json_response(self, status, data):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self._cors_headers()
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    def _clean_path(self):
        """Strip query string and trailing slash for clean matching."""
        path = self.path.split('?')[0].split('#')[0].rstrip('/')
        return path or '/'

    def do_GET(self):
        path = self._clean_path()
        if path == '/status' or path == '':
            self._json_response(200, {
                'status': 'ok',
                'printer_type': printer_config.get('type', 'unknown'),
                'vendor_id': printer_config.get('vendor', ''),
                'product_id': printer_config.get('product', ''),
                'network_host': printer_config.get('host', ''),
                'agent_version': '1.0.0',
            })
        else:
            self._json_response(404, {'error': 'Not found', 'path': path})

    def do_POST(self):
        path = self._clean_path()
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length) if content_length > 0 else b'{}'

        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self._json_response(400, {'error': 'Invalid JSON'})
            return

        if path == '/print':
            self._handle_print(data)
        elif path == '/test':
            self._handle_test(data)
        else:
            self._json_response(404, {'error': 'Not found', 'path': path})

    def _handle_print(self, data):
        global printer_instance
        try:
            p = get_printer()
            format_receipt(p, data)
            self._json_response(200, {'success': True, 'message': 'Receipt printed'})
        except Exception as e:
            print(f"[ERROR] Print failed: {e}", file=sys.stderr)
            self._json_response(500, {'success': False, 'error': str(e)})

    def _handle_test(self, data):
        global printer_instance
        try:
            p = get_printer()
            print_test_page(p, data)
            self._json_response(200, {'success': True, 'message': 'Test page printed'})
        except Exception as e:
            print(f"[ERROR] Test print failed: {e}", file=sys.stderr)
            self._json_response(500, {'success': False, 'error': str(e)})

    def log_message(self, format, *args):
        """Custom log format."""
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {self.command} {self.path} → {args[0]}")


def get_printer():
    """Get or create printer connection."""
    global printer_instance
    ptype = printer_config.get('type')

    if ptype == 'usb':
        from escpos.printer import Usb
        vendor = printer_config['vendor']
        product = printer_config['product']
        # Reconnect each time for reliability
        return Usb(vendor, product)
    elif ptype == 'network':
        from escpos.printer import Network
        return Network(printer_config['host'], port=printer_config.get('port', 9100))
    else:
        raise RuntimeError('No printer configured')


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    global printer_config

    parser = argparse.ArgumentParser(
        description='ServisHub POS Print Agent - ESC/POS thermal printer bridge',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  USB printer:      python pos_print_agent.py --vendor 0x0483 --product 0x5720
  Network printer:  python pos_print_agent.py --network 192.168.1.100
  Custom agent port: python pos_print_agent.py --vendor 0x0483 --product 0x5720 --agent-port 9200
        """
    )
    parser.add_argument('--vendor', type=lambda x: int(x, 0),
                        help='USB Vendor ID (hex, e.g. 0x0483)')
    parser.add_argument('--product', type=lambda x: int(x, 0),
                        help='USB Product ID (hex, e.g. 0x5720)')
    parser.add_argument('--network', type=str,
                        help='Network printer IP address')
    parser.add_argument('--printer-port', type=int, default=9100,
                        help='Network printer port (default: 9100)')
    parser.add_argument('--agent-port', type=int, default=9100,
                        help='HTTP agent port (default: 9100)')

    args = parser.parse_args()

    if args.network:
        printer_config = {
            'type': 'network',
            'host': args.network,
            'port': args.printer_port,
        }
        print(f"Printer: Network {args.network}:{args.printer_port}")
    elif args.vendor and args.product:
        printer_config = {
            'type': 'usb',
            'vendor': args.vendor,
            'product': args.product,
        }
        print(f"Printer: USB vendor=0x{args.vendor:04x} product=0x{args.product:04x}")
    else:
        print("ERROR: Specify --vendor + --product (USB) or --network (LAN)")
        print("Run with --help for usage examples")
        sys.exit(1)

    # Test printer connection
    try:
        p = get_printer()
        print("Printer connection: OK")
    except Exception as e:
        print(f"WARNING: Printer not available: {e}")
        print("Agent will start anyway - printer may become available later")

    # Start HTTP server
    port = args.agent_port
    # If USB printer uses default 9100, use 9101 for agent
    if printer_config['type'] == 'network' and port == args.printer_port:
        port = 9101
        print(f"Agent port changed to {port} (avoiding conflict with printer port)")

    server = HTTPServer(('127.0.0.1', port), PrintAgentHandler)
    print(f"\nServisHub POS Print Agent running on http://localhost:{port}")
    print(f"  GET  /status  - Health check")
    print(f"  POST /print   - Print receipt")
    print(f"  POST /test    - Test print")
    print(f"\nPress Ctrl+C to stop\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping agent...")
        server.server_close()


if __name__ == '__main__':
    main()
