# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

from io import BytesIO

import frappe
from frappe import _


def generate_qr_png_bytes(value: str, *, scale: int = 6, quiet_zone: int = 2) -> bytes:
	"""Return PNG bytes for a QR code encoding ``value``."""
	value = (value or "").strip()
	if not value:
		frappe.throw(_("QR code value is required"))

	try:
		from pyqrcode import create as qrcreate
	except ImportError:
		frappe.throw(_("QR code library is not installed. Contact your system administrator."))

	buffer = BytesIO()
	try:
		qrcreate(value).png(buffer, scale=scale, quiet_zone=quiet_zone)
		return buffer.getvalue()
	finally:
		buffer.close()
