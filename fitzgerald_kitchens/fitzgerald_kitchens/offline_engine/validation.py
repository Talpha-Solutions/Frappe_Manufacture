# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

import frappe


class OfflineConflict(frappe.ValidationError):
	"""Raised by a consuming app's mutator when a stateful offline mutation
	was based on a stale copy of the document — someone else changed it
	since the client last saw it. A ValidationError subclass so the
	idempotency engine's existing error handling (which already treats
	ValidationError as a permanent, non-retryable Rejected status) picks it
	up with no special casing required there.
	"""

	def __init__(self, message, current_state=None):
		super().__init__(message)
		self.current_state = current_state or {}


def assert_not_stale(doc, based_on_modified):
	"""Compare-and-swap guard for stateful mutations. `based_on_modified` is
	the `modified` timestamp the client had cached for this doc when it
	queued the offline action; if the server's copy has moved on since,
	reject rather than silently overwrite someone else's change.

	Purely additive operations (rows that only ever get appended, never
	transition state) should never call this — they have no "current state"
	to be stale against.
	"""
	if not based_on_modified:
		return
	if str(doc.modified) != str(based_on_modified):
		raise OfflineConflict(
			f"{doc.doctype} {doc.name} was changed by someone else since you last saw it.",
			current_state={"modified": str(doc.modified)},
		)
