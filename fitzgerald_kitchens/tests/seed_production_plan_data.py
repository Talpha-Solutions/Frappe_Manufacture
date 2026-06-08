"""
Seed script: creates test Manifest + Project Unit Configuration data on the
travel.com site so the Production Plan → Projects flow can be exercised.

Usage:
    bench --site travel.com execute \
        fitzgerald_kitchens.tests.seed_production_plan_data.seed
"""

from __future__ import annotations

import frappe


# Items that already have active default BOMs on travel.com
MANIFEST_ITEMS = [
    {"item_code": "KIT-1BED-A-SOCIAL", "qty": 1, "uom": "Nos"},
    {"item_code": "KIT-2BED-A-SOCIAL", "qty": 1, "uom": "Nos"},
]

# Projects to link the test manifest to
TARGET_PROJECTS = ["PROJ-0001"]

PUC_CODE = "TEST-PUC-001"
MANIFEST_CODE = "TEST-MANIFEST-001"


def _ensure_puc() -> str:
    if frappe.db.exists("Project Unit Configuration", PUC_CODE):
        print(f"  [skip] Project Unit Configuration '{PUC_CODE}' already exists")
        return PUC_CODE

    puc = frappe.get_doc(
        {
            "doctype": "Project Unit Configuration",
            "configuration_code": PUC_CODE,
            "configuration_name": "Test 1-Bed Kitchen (Seed)",
            "scope": "Project Template",
        }
    )
    puc.insert(ignore_permissions=True)
    frappe.db.commit()
    print(f"  [created] Project Unit Configuration '{PUC_CODE}'")
    return PUC_CODE


def _ensure_manifest(puc_name: str) -> str:
    if frappe.db.exists("Manifest", MANIFEST_CODE):
        print(f"  [skip] Manifest '{MANIFEST_CODE}' already exists")
        return MANIFEST_CODE

    manifest = frappe.get_doc(
        {
            "doctype": "Manifest",
            "manifest_code": MANIFEST_CODE,
            "scope": "Unit Snapshot",
            "manifest_category": "Kitchen",
            "configuration": puc_name,
            "items": [
                {
                    "item_code": row["item_code"],
                    "qty": row["qty"],
                    "uom": row["uom"],
                    "description": frappe.db.get_value("Item", row["item_code"], "item_name") or row["item_code"],
                }
                for row in MANIFEST_ITEMS
                if frappe.db.exists("Item", row["item_code"])
            ],
        }
    )
    manifest.insert(ignore_permissions=True)
    frappe.db.commit()
    print(f"  [created] Manifest '{MANIFEST_CODE}' with {len(manifest.items)} item(s)")
    return MANIFEST_CODE


def _link_projects(manifest_name: str) -> None:
    for proj in TARGET_PROJECTS:
        if not frappe.db.exists("Project", proj):
            print(f"  [skip] Project '{proj}' not found")
            continue

        current = frappe.db.get_value("Project", proj, "fk_effective_manifest")
        if current:
            print(f"  [skip] Project '{proj}' already has fk_effective_manifest = '{current}'")
            continue

        frappe.db.set_value("Project", proj, "fk_effective_manifest", manifest_name, update_modified=False)
        frappe.db.commit()
        print(f"  [linked] Project '{proj}' → fk_effective_manifest = '{manifest_name}'")


def seed():
    print("\n=== Seeding Production Plan test data on travel.com ===")
    puc = _ensure_puc()
    manifest = _ensure_manifest(puc)
    _link_projects(manifest)
    print("=== Done ===\n")
