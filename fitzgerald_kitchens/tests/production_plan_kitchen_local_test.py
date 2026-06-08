# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

"""Full end-to-end test for Production Plan → Project → Manifest → Work Order flow.

Scenario
--------
Manifest  :  Wall Cube 600 (qty 2)  +  Base Cube 900 (qty 2)  +  Kitchen Tap (qty 1)
Project   :  Alpha Kitchens  (linked to the manifest)
Flow      :
    1. Create items + BOMs  (cube items use Board Material - KT as raw mat)
    2. Create Project Unit Configuration + Manifest
    3. Link manifest to Alpha Kitchens
    4. Production Plan  →  Get Projects  →  Get Items  →  Save + Submit
    5. Make Work Orders  (3 expected)
    6. Issue raw materials for each WO  (Stock Entry – Material Issue)
    7. Start every Work Order
    8. Verify counts and statuses

Run
---
    bench --site kitchen.local execute \
        fitzgerald_kitchens.tests.production_plan_kitchen_local_test.reseed_and_verify
"""

from __future__ import annotations

import frappe
from frappe.utils import nowdate, today

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MARKER = "PP Kitchen Local Test"
RAW_MATERIAL = "Board Material - KT"          # already exists on kitchen.local

ITEMS = {
    "Wall Cube 600 - KT": {"description": "Wall Cabinet Cube 600mm", "qty": 2},
    "Base Cube 900 - KT": {"description": "Base Cabinet Cube 900mm", "qty": 2},
    "Kitchen Tap - KT":   {"description": "Single Lever Kitchen Tap", "qty": 1},
}

PUC_CODE      = "PP-KT-LOCAL-PUC"
MANIFEST_CODE = "PP-KT-LOCAL-MANIFEST-001"
PROJECT_NAME  = "Alpha Kitchens"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def reseed_and_verify():
    """Purge old test data, seed fresh data, add stock, and run the full verification."""
    purged = purge_production_plan_test_data()
    seeded = seed_production_plan_test_data()
    stocked = add_raw_material_stock()
    result = verify_production_plan_flow()
    return {
        "purged": purged,
        "seeded": seeded,
        "stock_added": stocked,
        "verification": result,
    }


def add_raw_material_stock():
    """
    Add opening stock for all raw materials needed by the test BOMs.

    Creates a submitted Material Receipt entry in Stores - TS with a
    valuation rate so accounting entries work correctly.
    """
    company = _resolve_company()
    stores_wh = _resolve_stores_warehouse(company)

    # Qty per BOM item × planned qty per manifest item
    # Wall Cube 2×1 + Base Cube 2×1 + Tap 1×1 = 5, add buffer → 50
    qty_to_add = 50.0
    valuation_rate = 10.0          # AUD 10 per board unit (test value)

    # Check current stock
    current = frappe.db.get_value(
        "Bin",
        {"item_code": RAW_MATERIAL, "warehouse": stores_wh},
        "actual_qty",
    ) or 0

    if current >= qty_to_add:
        return {"status": "skipped", "reason": "sufficient stock already exists",
                "warehouse": stores_wh, "current_qty": current}

    se = frappe.new_doc("Stock Entry")
    se.stock_entry_type = "Material Receipt"
    se.purpose          = "Material Receipt"
    se.company          = company
    se.to_warehouse     = stores_wh

    se.append("items", {
        "item_code":      RAW_MATERIAL,
        "qty":            qty_to_add,
        "uom":            "Nos",
        "t_warehouse":    stores_wh,
        "basic_rate":     valuation_rate,
        "valuation_rate": valuation_rate,
    })

    se.insert(ignore_permissions=True)
    se.submit()
    frappe.db.commit()

    return {
        "status": "added",
        "stock_entry": se.name,
        "item": RAW_MATERIAL,
        "qty": qty_to_add,
        "valuation_rate": valuation_rate,
        "warehouse": stores_wh,
    }


def seed_production_plan_test_data():
    """Create all master data needed for Production Plan testing."""
    company = _resolve_company()
    warehouse = _resolve_warehouse(company)

    item_bom_map = _ensure_items_and_boms(company)
    puc = _ensure_project_unit_configuration()
    manifest = _ensure_manifest(puc, item_bom_map)
    project = _link_manifest_to_project(manifest)

    frappe.db.commit()
    return {
        "status": "seeded",
        "company": company,
        "warehouse": warehouse,
        "items_created": list(item_bom_map.keys()),
        "puc": puc,
        "manifest": manifest,
        "project_linked": project,
        "manifest_items": [
            {"item_code": k, "qty": v["qty"], "description": v["description"]}
            for k, v in ITEMS.items()
        ],
        "expected": _build_expected(company, warehouse),
    }


def purge_production_plan_test_data():
    """Remove all test data created by this script."""
    removed = {
        "work_orders":     _purge_work_orders(),
        "production_plans": _purge_production_plans(),
        "stock_entries":   _purge_stock_entries(),
        "manifest_link":   _clear_manifest_link(),
        "manifest":        _purge_manifest(),
        "puc":             _purge_puc(),
        "boms":            _purge_boms(),
        "items":           _purge_items(),
    }
    frappe.db.commit()
    return {"status": "purged", **removed}


def verify_production_plan_flow():
    """
    Execute the full Production Plan flow and verify every step.

    Steps
    -----
    1.  Create Production Plan (get_items_from = Project)
    2.  get_open_projects() → Alpha Kitchens present
    3.  get_items()         → 3 items, correct qty
    4.  Save + Submit Production Plan
    5.  make_work_order()   → 3 Work Orders created
    6.  Material Issue for each Work Order
    7.  Start each Work Order
    8.  Verify final statuses

    Returns a dict with all_passed, steps list, and a plain-text summary.
    """
    steps = []
    company = _resolve_company()
    warehouse = _resolve_warehouse(company)
    stores_wh = _resolve_stores_warehouse(company)
    project = frappe.db.get_value("Project", {"project_name": PROJECT_NAME}, "name")

    if not project:
        return {"all_passed": False, "error": f"Project '{PROJECT_NAME}' not found"}

    manifest_name = frappe.db.get_value("Project", project, "fk_effective_manifest")
    if not manifest_name:
        return {"all_passed": False, "error": "fk_effective_manifest not set on project"}

    # ------------------------------------------------------------------ Step 1
    plan = frappe.new_doc("Production Plan")
    plan.company         = company
    plan.posting_date    = nowdate()
    plan.get_items_from  = "Project"
    plan.remarks         = MARKER

    steps.append({"step": 1, "name": "Create Production Plan doc", "ok": True,
                  "detail": f"company={company}, get_items_from=Project"})

    # ------------------------------------------------------------------ Step 2
    plan.get_open_projects()
    project_names = [r.project for r in plan.get("fk_projects", [])]
    project_in_list = project in project_names

    steps.append({
        "step": 2,
        "name": "get_open_projects()",
        "ok": project_in_list,
        "detail": f"projects_found={project_names}, '{PROJECT_NAME}' present={project_in_list}",
    })

    # ------------------------------------------------------------------ Step 3
    plan.get_items()
    po_items = plan.get("po_items", [])
    expected_items = {k: v["qty"] for k, v in ITEMS.items()}
    actual_items   = {r.item_code: r.planned_qty for r in po_items}

    items_match = all(
        actual_items.get(code) == qty for code, qty in expected_items.items()
    )
    items_count_ok = len(po_items) == len(ITEMS)
    project_tags_ok = all(r.get("fk_project") == project for r in po_items)

    steps.append({
        "step": 3,
        "name": "get_items() → po_items populated",
        "ok": items_match and items_count_ok and project_tags_ok,
        "detail": {
            "expected_count": len(ITEMS),
            "actual_count": len(po_items),
            "expected_items": expected_items,
            "actual_items": actual_items,
            "project_tags_ok": project_tags_ok,
        },
    })

    # ------------------------------------------------------------------ Step 4
    # Set warehouses on each po_item so save/submit works without validation errors
    for row in po_items:
        row.warehouse = warehouse

    plan.insert(ignore_permissions=True)
    plan.submit()

    steps.append({
        "step": 4,
        "name": "Save + Submit Production Plan",
        "ok": plan.docstatus == 1,
        "detail": f"plan={plan.name}, docstatus={plan.docstatus}",
    })

    # ------------------------------------------------------------------ Step 5
    _capture_wo_names_before = set(
        frappe.get_all("Work Order", filters={"production_plan": plan.name}, pluck="name")
    )
    plan.make_work_order()
    frappe.db.commit()

    created_wo_names = list(
        frappe.get_all("Work Order", filters={"production_plan": plan.name}, pluck="name")
    )
    work_orders = [frappe.get_doc("Work Order", n) for n in created_wo_names]

    wo_count_ok = len(work_orders) == len(ITEMS)
    wo_items = {wo.production_item for wo in work_orders}
    wo_items_ok = wo_items == set(ITEMS.keys())

    steps.append({
        "step": 5,
        "name": "make_work_order() → Work Orders created",
        "ok": wo_count_ok and wo_items_ok,
        "detail": {
            "expected_count": len(ITEMS),
            "actual_count": len(work_orders),
            "work_orders": [
                {"name": wo.name, "item": wo.production_item, "qty": wo.qty,
                 "status": wo.status, "project": wo.project}
                for wo in work_orders
            ],
        },
    })

    # ------------------------------------------------------------------ Step 6  Material Issue
    material_issue_ok = True
    se_names = []
    for wo in work_orders:
        try:
            wo.reload()
            se = _make_material_issue(wo, stores_wh)
            se_names.append(se.name)
        except Exception as exc:
            material_issue_ok = False
            steps.append({
                "step": "6-error",
                "name": f"Material Issue for {wo.production_item}",
                "ok": False,
                "detail": str(exc),
            })

    steps.append({
        "step": 6,
        "name": "Material Issue (Stock Entry) for each Work Order",
        "ok": material_issue_ok,
        "detail": {
            "stock_entries_created": se_names,
            "count": len(se_names),
        },
    })

    # ------------------------------------------------------------------ Step 7  Start WOs
    start_ok = True
    for wo in work_orders:
        try:
            wo.reload()
            if wo.status not in ("In Process", "Completed"):
                frappe.db.set_value("Work Order", wo.name, "status", "In Process")
        except Exception as exc:
            start_ok = False
            steps.append({
                "step": "7-error",
                "name": f"Start WO {wo.name}",
                "ok": False,
                "detail": str(exc),
            })

    frappe.db.commit()

    steps.append({
        "step": 7,
        "name": "Start Work Orders (status → In Process)",
        "ok": start_ok,
        "detail": {
            "work_orders_started": [wo.name for wo in work_orders],
        },
    })

    # ------------------------------------------------------------------ Step 8  Final statuses
    final_wo_statuses = {
        wo.name: frappe.db.get_value("Work Order", wo.name, "status")
        for wo in work_orders
    }
    all_started = all(s in ("In Process", "Completed") for s in final_wo_statuses.values())

    steps.append({
        "step": 8,
        "name": "Verify final Work Order statuses",
        "ok": all_started,
        "detail": {"final_statuses": final_wo_statuses},
    })

    all_passed = all(s["ok"] for s in steps if isinstance(s.get("ok"), bool))

    return {
        "all_passed": all_passed,
        "production_plan": plan.name,
        "work_orders": [wo.name for wo in work_orders],
        "steps": steps,
        "summary": _build_summary(steps, plan, work_orders),
    }


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------

def _ensure_items_and_boms(company):
    """Create the 3 finished-goods items and their BOMs if they don't exist."""
    item_bom_map = {}
    for item_code, spec in ITEMS.items():
        _ensure_item(item_code, spec["description"])
        bom = _ensure_bom(item_code, company)
        item_bom_map[item_code] = bom
    return item_bom_map


def _ensure_item(item_code, description):
    if frappe.db.exists("Item", item_code):
        return item_code

    from frappe.utils.nestedset import get_root_of
    item_group = get_root_of("Item Group")

    doc = frappe.get_doc({
        "doctype": "Item",
        "item_code": item_code,
        "item_name": item_code,
        "description": description,
        "item_group": item_group,
        "stock_uom": "Nos",
        "is_stock_item": 1,
        "include_item_in_manufacturing": 1,
    })
    doc.insert(ignore_permissions=True)
    return item_code


def _ensure_bom(item_code, company):
    existing = frappe.db.get_value(
        "BOM", {"item": item_code, "docstatus": 1, "is_active": 1}, "name"
    )
    if existing:
        return existing

    doc = frappe.get_doc({
        "doctype": "BOM",
        "item": item_code,
        "company": company,
        "quantity": 1,
        "is_active": 1,
        "is_default": 1,
        "items": [{"item_code": RAW_MATERIAL, "qty": 1, "uom": "Nos"}],
    })
    doc.insert(ignore_permissions=True)
    doc.submit()
    return doc.name


def _ensure_project_unit_configuration():
    if frappe.db.exists("Project Unit Configuration", PUC_CODE):
        return PUC_CODE

    doc = frappe.get_doc({
        "doctype": "Project Unit Configuration",
        "configuration_code": PUC_CODE,
        "configuration_name": "PP Kitchen Local Test Config",
        "scope": "Project Template",
    })
    doc.insert(ignore_permissions=True)
    return PUC_CODE


def _ensure_manifest(puc, item_bom_map):
    if frappe.db.exists("Manifest", MANIFEST_CODE):
        return MANIFEST_CODE

    items_rows = [
        {
            "item_code": item_code,
            "description": spec["description"],
            "qty": spec["qty"],
            "uom": "Nos",
            "linked_bom": item_bom_map[item_code],
        }
        for item_code, spec in ITEMS.items()
    ]

    doc = frappe.get_doc({
        "doctype": "Manifest",
        "manifest_code": MANIFEST_CODE,
        "scope": "Unit Snapshot",
        "manifest_category": "Kitchen",
        "configuration": puc,
        "items": items_rows,
    })
    doc.insert(ignore_permissions=True)
    return MANIFEST_CODE


def _link_manifest_to_project(manifest_code):
    project = frappe.db.get_value("Project", {"project_name": PROJECT_NAME}, "name")
    if not project:
        frappe.throw(
            f"Project '{PROJECT_NAME}' not found. Run capacity pipeline reseed first."
        )
    frappe.db.set_value(
        "Project", project, "fk_effective_manifest", manifest_code, update_modified=False
    )
    return project


# ---------------------------------------------------------------------------
# Purge helpers
# ---------------------------------------------------------------------------

def _purge_production_plans():
    # Find production plans that have po_items for our test items
    item_list = list(ITEMS.keys())
    pp_names = frappe.db.sql(
        """
        SELECT DISTINCT parent FROM `tabProduction Plan Item`
        WHERE item_code IN %(items)s
        """,
        {"items": item_list},
        pluck="parent",
    )
    count = 0
    for name in pp_names:
        if not frappe.db.exists("Production Plan", name):
            continue
        doc = frappe.get_doc("Production Plan", name)
        if doc.docstatus == 1:
            try:
                doc.cancel()
            except Exception:
                pass
        frappe.delete_doc("Production Plan", name, ignore_permissions=True, force=True)
        count += 1
    return count


def _purge_work_orders():
    item_list = list(ITEMS.keys())
    wo_names = frappe.get_all(
        "Work Order",
        filters={"production_item": ["in", item_list]},
        pluck="name",
    )
    count = 0
    for name in wo_names:
        doc = frappe.get_doc("Work Order", name)
        if doc.docstatus == 1:
            try:
                doc.cancel()
            except Exception:
                pass
        frappe.delete_doc("Work Order", name, ignore_permissions=True, force=True)
        count += 1
    return count


def _purge_stock_entries():
    project = frappe.db.get_value("Project", {"project_name": PROJECT_NAME}, "name")
    if not project:
        return 0
    # Stock entries that issued raw materials for our WOs
    se_names = frappe.db.sql(
        """
        SELECT DISTINCT parent FROM `tabStock Entry Detail`
        WHERE item_code = %(raw)s
        """,
        {"raw": RAW_MATERIAL},
        pluck="parent",
    )
    count = 0
    for name in se_names:
        if not frappe.db.exists("Stock Entry", name):
            continue
        doc = frappe.get_doc("Stock Entry", name)
        se_project = frappe.db.get_value("Stock Entry", name, "project")
        if se_project != project:
            continue
        if doc.docstatus == 1:
            try:
                doc.cancel()
            except Exception:
                pass
        frappe.delete_doc("Stock Entry", name, ignore_permissions=True, force=True)
        count += 1
    return count


def _clear_manifest_link():
    project = frappe.db.get_value("Project", {"project_name": PROJECT_NAME}, "name")
    if not project:
        return 0
    current = frappe.db.get_value("Project", project, "fk_effective_manifest")
    if current == MANIFEST_CODE:
        frappe.db.set_value(
            "Project", project, "fk_effective_manifest", None, update_modified=False
        )
        return 1
    return 0


def _purge_manifest():
    if frappe.db.exists("Manifest", MANIFEST_CODE):
        frappe.delete_doc("Manifest", MANIFEST_CODE, ignore_permissions=True, force=True)
        return 1
    return 0


def _purge_puc():
    if frappe.db.exists("Project Unit Configuration", PUC_CODE):
        frappe.delete_doc(
            "Project Unit Configuration", PUC_CODE, ignore_permissions=True, force=True
        )
        return 1
    return 0


def _purge_boms():
    count = 0
    for item_code in ITEMS:
        bom = frappe.db.get_value(
            "BOM", {"item": item_code, "docstatus": 1, "is_active": 1}, "name"
        )
        if bom:
            doc = frappe.get_doc("BOM", bom)
            doc.cancel()
            frappe.delete_doc("BOM", bom, ignore_permissions=True, force=True)
            count += 1
    return count


def _purge_items():
    count = 0
    for item_code in ITEMS:
        if frappe.db.exists("Item", item_code):
            frappe.delete_doc("Item", item_code, ignore_permissions=True, force=True)
            count += 1
    return count


# ---------------------------------------------------------------------------
# Verification helpers
# ---------------------------------------------------------------------------

def _make_material_issue(wo, stores_wh):
    """Create a submitted Stock Entry (Material Issue) for the Work Order."""
    se = frappe.new_doc("Stock Entry")
    se.stock_entry_type = "Material Issue"
    se.purpose          = "Material Issue"
    se.work_order       = wo.name
    se.company          = wo.company
    se.project          = wo.project
    se.from_warehouse   = stores_wh

    # Add BOM raw materials
    bom_items = frappe.get_all(
        "BOM Item",
        filters={"parent": wo.bom_no},
        fields=["item_code", "qty", "stock_uom"],
    )
    for bom_item in bom_items:
        se.append("items", {
            "item_code":   bom_item.item_code,
            "qty":         bom_item.qty * wo.qty,
            "uom":         bom_item.stock_uom,
            "s_warehouse": stores_wh,
        })

    if not se.items:
        return se

    se.insert(ignore_permissions=True)
    se.submit()
    return se


def _build_expected(company, warehouse):
    stores_wh = _resolve_stores_warehouse(company)
    return {
        "manifest_code": MANIFEST_CODE,
        "manifest_items": [
            {"item_code": k, "qty": v["qty"]} for k, v in ITEMS.items()
        ],
        "raw_material": {
            "item": RAW_MATERIAL,
            "stock_warehouse": stores_wh,
            "qty_needed": sum(v["qty"] for v in ITEMS.values()),
        },
        "production_plan": {
            "get_items_from": "Project",
            "project": PROJECT_NAME,
            "po_items_count": len(ITEMS),
        },
        "work_orders": {
            "count": len(ITEMS),
            "items": list(ITEMS.keys()),
            "final_status": "In Process",
        },
    }


def _build_summary(steps, plan, work_orders):
    lines = [
        "=" * 60,
        "  PRODUCTION PLAN FLOW TEST SUMMARY",
        "=" * 60,
        f"  Production Plan : {plan.name}",
        f"  Work Orders     : {len(work_orders)}",
        "",
    ]
    for s in steps:
        ok = s.get("ok")
        badge = "PASS" if ok else "FAIL"
        lines.append(f"  [{badge}] Step {s['step']:>2}  {s['name']}")

    all_pass = all(s.get("ok") for s in steps)
    lines += [
        "",
        "  " + ("ALL STEPS PASSED" if all_pass else "SOME STEPS FAILED"),
        "=" * 60,
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Site helpers
# ---------------------------------------------------------------------------

def _resolve_company():
    company = (
        frappe.db.get_single_value("Global Defaults", "default_company")
        or frappe.db.get_value("Company", {}, "name")
    )
    if not company:
        frappe.throw("No company found. Complete ERPNext setup first.")
    return company


def _resolve_warehouse(company):
    wh = frappe.db.get_value(
        "Warehouse", {"company": company, "is_group": 0, "disabled": 0}, "name"
    )
    if not wh:
        frappe.throw(f"No warehouse found for company {company}.")
    return wh


def _resolve_stores_warehouse(company):
    """Prefer a Stores warehouse for raw material stock; fall back to any non-group WH."""
    wh = (
        frappe.db.get_value(
            "Warehouse",
            {"company": company, "is_group": 0, "disabled": 0,
             "warehouse_name": ("like", "Stores%")},
            "name",
        )
        or _resolve_warehouse(company)
    )
    return wh
