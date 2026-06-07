# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

"""Capacity Pipeline Report

Shows monthly kitchen production demand per project alongside calculated
workstation capacity (derived from BOM operations + Workstation working hours /
holiday lists).  Demand uses Job Cards when present: completed cards use
actual total time (time logs by month, or total_time_in_mins); open cards use
scheduled time (time_required). Otherwise uses Project expected delivery /
start dates and unit quantity (fk_unit_qty).
Displays demand utilisation % and free capacity.

Query budget: 7 SQL statements — no per-row or per-project round-trips.
"""

import calendar
import re
from collections import defaultdict
from datetime import date, timedelta

import frappe
from frappe import _
from frappe.utils import flt, getdate, get_first_day, get_last_day, add_months


_WEEK_START_SQL = "DATE(DATE_SUB({field}, INTERVAL WEEKDAY({field}) DAY))"
SITE_PARENT_FIELD = "fk_parent_project"


def _project_kitchen_bom(project):
    """Effective kitchen BOM — Unit tab (fk_effective_bom) wins over legacy kitchen_bom."""
    return getattr(project, "fk_effective_bom", None) or getattr(project, "kitchen_bom", None)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def execute(filters=None):
    filters = frappe._dict(filters or {})
    _apply_default_bom_filter(filters)
    granularity = filters.get("granularity") or "Monthly"
    if granularity == "Weekly":
        periods = _build_week_list(filters)
    else:
        periods = _build_month_list(filters)
    columns = _get_columns(periods, granularity)
    data = _get_data(filters, periods, granularity)
    return columns, data


@frappe.whitelist()
def get_default_bom(company=None):
    """
    Return the best default BOM for the Capacity Pipeline filter.

    Prefer the BOM assigned to the most active projects (fk_effective_bom or
    kitchen_bom), then fall back to the most recently created active BOM.
    """
    company = company or frappe.defaults.get_user_default("Company")
    if not company:
        return None

    has_fk_bom = frappe.db.has_column("Project", "fk_effective_bom")
    fk_select = "p.fk_effective_bom" if has_fk_bom else "NULL"
    row = frappe.db.sql(
        f"""
        SELECT bom_name, COUNT(*) AS project_count
        FROM (
            SELECT COALESCE({fk_select}, p.kitchen_bom) AS bom_name
            FROM `tabProject` p
            WHERE
                p.company = %(company)s
                AND p.docstatus < 2
                AND p.status NOT IN ('Cancelled', 'Completed')
                AND COALESCE({fk_select}, p.kitchen_bom) IS NOT NULL
        ) AS assigned
        INNER JOIN `tabBOM` b ON b.name = assigned.bom_name
        WHERE b.company = %(company)s AND b.docstatus = 1 AND b.is_active = 1
        GROUP BY bom_name
        ORDER BY project_count DESC, bom_name DESC
        LIMIT 1
        """,
        {"company": company},
        as_dict=True,
    )
    if row:
        return row[0].bom_name

    return frappe.db.get_value(
        "BOM",
        {"company": company, "docstatus": 1, "is_active": 1},
        "name",
        order_by="creation desc",
    )


def _normalize_report_filters(filters):
    """Accept dict or JSON string from RPC / xcall."""
    if isinstance(filters, str):
        filters = frappe.parse_json(filters)
    return frappe._dict(filters or {})


@frappe.whitelist()
def get_pipeline_totals(filters=None):
    """
    Total kitchen units for the KPI card.

    Sums fk_unit_qty on all active kitchen unit Projects (project_type Kitchen,
    not Site parents) for the selected company / project scope. One item = one
    kitchen. Does not filter by the report date range or BOM — the table and
    chart still respect those filters.
    """
    filters = _normalize_report_filters(filters)
    all_filters = frappe._dict(filters)
    all_filters.bom = None
    projects = _q_projects(all_filters)
    demand_projects = _projects_for_demand_total(projects)
    project_names = [p.name for p in demand_projects]

    total_kitchens = _count_pipeline_kitchen_units(project_names)
    return {
        "total_demand": total_kitchens,
        "total_kitchens": total_kitchens,
        "project_count": _count_pipeline_kitchen_unit_projects(project_names),
    }


def _project_schedule_date_sql(prefix="p"):
    """Best available planned delivery date on a Project row."""
    return f"COALESCE({prefix}.expected_end_date, {prefix}.expected_start_date)"


def _project_unit_qty_sql(prefix="p"):
    """Unit quantity on a Project row (defaults to 1)."""
    if frappe.db.has_column("Project", "fk_unit_qty"):
        return f"GREATEST(COALESCE({prefix}.fk_unit_qty, 1), 1)"
    return "1"


def _project_is_kitchen_sql(prefix="p"):
    return (
        f"(IFNULL({prefix}.kitchen_required, 0) = 1 "
        f"OR IFNULL({prefix}.project_type, '') = 'Kitchen')"
    )


def _project_is_wardrobe_sql(prefix="p"):
    return (
        f"(IFNULL({prefix}.wardrobe_required, 0) = 1 "
        f"OR IFNULL({prefix}.project_type, '') = 'Robe')"
    )


def _pipeline_kitchen_units_sql(project_names, from_date=None, to_date=None):
    """Shared FROM/WHERE for kitchen unit projects in the pipeline."""
    schedule = _project_schedule_date_sql("p")
    date_cond = ""
    params = {"project_names": project_names}
    if from_date and to_date:
        date_cond = f"AND {schedule} BETWEEN %(from_date)s AND %(to_date)s"
        params["from_date"] = from_date
        params["to_date"] = to_date

    return (
        f"""
        FROM `tabProject` p
        WHERE
            p.name IN %(project_names)s
            AND IFNULL(p.project_type, '') != 'Site'
            {date_cond}
            AND """
        + _project_is_kitchen_sql("p"),
        params,
    )


def _count_pipeline_kitchen_units(project_names, from_date=None, to_date=None):
    """Sum fk_unit_qty — total kitchens unit projects plan to make."""
    if not project_names:
        return 0

    sql_from, params = _pipeline_kitchen_units_sql(
        project_names, from_date, to_date
    )
    qty = _project_unit_qty_sql("p")
    return int(
        frappe.db.sql(f"SELECT COALESCE(SUM({qty}), 0) {sql_from}", params)[0][0]
        or 0
    )


def _count_pipeline_kitchen_unit_projects(project_names, from_date=None, to_date=None):
    """Count distinct kitchen unit projects in the pipeline."""
    if not project_names:
        return 0

    sql_from, params = _pipeline_kitchen_units_sql(
        project_names, from_date, to_date
    )
    return int(
        frappe.db.sql(f"SELECT COUNT(DISTINCT p.name) {sql_from}", params)[0][0]
        or 0
    )


def _apply_default_bom_filter(filters):
    """Use the latest active BOM when none is selected or the selection is invalid."""
    bom = filters.get("bom")
    if bom and frappe.db.exists(
        "BOM", {"name": bom, "docstatus": 1, "is_active": 1}
    ):
        return

    default_bom = get_default_bom(filters.get("company"))
    if default_bom:
        filters.bom = default_bom


# ---------------------------------------------------------------------------
# Columns (dynamic – one per month)
# ---------------------------------------------------------------------------

def _get_columns(periods, granularity="Monthly"):
    col_width = 72 if granularity == "Weekly" else 96
    cols = [
        {
            "fieldname": "project",
            "label": _("PROJECT"),
            "fieldtype": "Data",
            "width": 220,
        }
    ]
    for period in periods:
        pkey, plabel = period[0], period[1]
        cols.append(
            {
                "fieldname": pkey,
                "label": plabel,
                "fieldtype": "Data",
                "width": col_width,
            }
        )
    return cols


# ---------------------------------------------------------------------------
# Main data assembly
# ---------------------------------------------------------------------------

def _get_data(filters, periods, granularity="Monthly"):
    if not periods:
        return []

    from_date = _period_start(periods[0])
    to_date = _period_end(periods[-1])

    projects = _q_projects(filters)
    project_names = [p.name for p in projects]
    bom_list = _get_capacity_bom_list(filters, projects)

    operations = _q_bom_operations(bom_list) if bom_list else []
    bottleneck = _get_bottleneck_operation(operations)

    if granularity == "Weekly":
        demand_map = (
            _q_demand_weekly(
                project_names,
                from_date,
                to_date,
                bom_list,
                bottleneck,
            )
            if project_names
            else {}
        )
        product_breakdown = (
            _q_weekly_product_breakdown(projects, project_names, from_date, to_date)
            if project_names
            else {}
        )
    else:
        demand_map = (
            _q_demand(
                project_names,
                from_date,
                to_date,
                bom_list,
                bottleneck,
            )
            if project_names
            else {}
        )
        product_breakdown = (
            _q_monthly_product_breakdown(projects, project_names, from_date, to_date)
            if project_names
            else {}
        )

    _apply_site_breakdown_all_children(
        projects,
        demand_map,
        product_breakdown,
        periods,
        from_date,
        to_date,
        granularity,
        filters,
    )
    _set_site_subtitle_totals(projects)

    workstation_names = list({op.workstation for op in operations if op.workstation})
    workstation_types = list(
        {
            op.workstation_type
            for op in operations
            if op.workstation_type and not op.workstation
        }
    )
    workstations = (
        _q_workstations(workstation_names, workstation_types)
        if (workstation_names or workstation_types)
        else []
    )

    holiday_lists = list({ws.holiday_list for ws in workstations if ws.holiday_list})
    holidays_map = _q_holidays(holiday_lists, from_date, to_date) if holiday_lists else {}

    ws_map = {ws.name: ws for ws in workstations}
    ws_by_type = _group_workstations_by_type(workstations)

    if granularity == "Weekly":
        downtime_map = (
            _q_downtime_weekly(list(ws_map.keys()), from_date, to_date) if ws_map else {}
        )
        capacity_result = _calc_capacity_per_week(
            operations,
            ws_map,
            ws_by_type,
            holidays_map,
            downtime_map,
            periods,
        )
    else:
        downtime_map = _q_downtime(list(ws_map.keys()), from_date, to_date) if ws_map else {}
        capacity_result = _calc_capacity_per_month(
            operations,
            ws_map,
            ws_by_type,
            holidays_map,
            downtime_map,
            periods,
        )

    data = []
    site_name_by_id = {
        p.name: p.project_name or p.name
        for p in projects
        if getattr(p, "project_type", None) == "Site"
    }
    for idx, proj in enumerate(
        sorted(projects, key=lambda p: (p.project_name or p.name).lower())
    ):
        proj_demand = demand_map.get(proj.name, {})
        row = {
            "project": proj.project_name or proj.name,
            "project_id": proj.name,
            "project_type": getattr(proj, "project_type", None) or "",
            "chart_label": _chart_label_for_project(proj, site_name_by_id),
            "subtitle": _project_subtitle(proj),
            "row_type": "project",
            "color_index": idx,
        }
        for period in periods:
            pkey = period[0]
            row[pkey] = proj_demand.get(pkey, 0)
            period_split = product_breakdown.get(proj.name, {}).get(pkey, {})
            row[f"{pkey}_kitchen"] = period_split.get("kitchen", 0)
            row[f"{pkey}_wardrobe"] = period_split.get("wardrobe", 0)
        data.append(row)

    data.extend(
        _build_summary_rows(
            periods, demand_map, projects, capacity_result, filters, granularity
        )
    )
    return data


def _get_capacity_bom_list(filters, projects):
    """Capacity is always driven by the selected BOM (defaults to latest active BOM)."""
    if filters.get("bom"):
        return [filters.bom]
    return []


def _projects_for_demand_total(projects):
    """Exclude Site rows from totals — demand is already on child kitchen projects."""
    if not frappe.db.has_column("Project", SITE_PARENT_FIELD):
        return projects
    if not any(getattr(p, "project_type", None) == "Site" for p in projects):
        return projects
    return [p for p in projects if getattr(p, "project_type", None) != "Site"]


def _build_summary_rows(periods, demand_map, projects, capacity_result, filters=None, granularity="Monthly"):
    """Append separator + downtime + capacity / demand / free capacity summary rows."""
    rows = []
    period_keys = [period[0] for period in periods]
    demand_projects = _projects_for_demand_total(projects)

    sep = {"project": " ", "row_type": "separator"}
    for pkey in period_keys:
        sep[pkey] = 0
    rows.append(sep)

    period_demand = {
        pkey: sum(demand_map.get(p.name, {}).get(pkey, 0) for p in demand_projects)
        for pkey in period_keys
    }

    downtime_row = {"project": _("Downtime (mins)"), "row_type": "downtime", "bold": 1}
    for pkey in period_keys:
        downtime_row[pkey] = capacity_result["downtime_total"].get(pkey, 0)
    rows.append(downtime_row)

    cap_label = _("Capacity / week") if granularity == "Weekly" else _("Capacity per month")
    cap_row = {"project": cap_label, "row_type": "capacity", "bold": 1}
    if filters and filters.get("bom"):
        cap_row["subtitle"] = _get_bom_capacity_subtitle(filters.bom)
    for pkey in period_keys:
        actual = capacity_result["actual"].get(pkey, 0)
        theoretical = capacity_result["theoretical"].get(pkey, 0)
        cap_row[pkey] = f"{actual}/{theoretical}"
        cap_row[f"{pkey}_actual"] = actual
        cap_row[f"{pkey}_theoretical"] = theoretical
    rows.append(cap_row)

    dem_row = {"project": _("Demand · utilisation"), "row_type": "demand", "bold": 1}
    for pkey in period_keys:
        cap = capacity_result["actual"].get(pkey) or 0
        dem = period_demand.get(pkey, 0)
        dem_row[pkey] = dem
        dem_row[f"{pkey}_pct"] = flt(dem / cap * 100, 0) if cap else 0
    rows.append(dem_row)

    free_row = {"project": _("Free capacity"), "row_type": "free", "bold": 1}
    for pkey in period_keys:
        cap = capacity_result["actual"].get(pkey) or 0
        dem = period_demand.get(pkey, 0)
        free_row[pkey] = cap - dem
    rows.append(free_row)

    return rows


# ---------------------------------------------------------------------------
# Q1 – Projects
# ---------------------------------------------------------------------------

def _q_projects(filters):
    """Return active projects with type and kitchen / wardrobe flags."""
    company_cond = "AND p.company = %(company)s" if filters.get("company") else ""
    project_cond = "AND p.name = %(project)s" if filters.get("project") else ""
    has_parent = frappe.db.has_column("Project", SITE_PARENT_FIELD)
    parent_select = f", p.{SITE_PARENT_FIELD}" if has_parent else ""

    rows = frappe.db.sql(
        f"""
        SELECT
            p.name,
            p.project_name,
            p.customer,
            p.fk_effective_bom,
            p.project_type,
            p.kitchen_bom,
            p.kitchen_required,
            p.wardrobe_bom,
            p.wardrobe_required{parent_select}
        FROM
            `tabProject` p
        WHERE
            p.docstatus < 2
            AND p.status NOT IN ('Cancelled', 'Completed')
            {company_cond}
            {project_cond}
        ORDER BY
            p.project_name
        """,
        {
            "company": filters.get("company"),
            "project": filters.get("project"),
        },
        as_dict=True,
    )

    filtered = _filter_projects_by_bom(rows, filters.get("bom"))
    return _append_site_parent_projects(filtered, filters)


def _append_site_parent_projects(projects, filters):
    """Include Site parents when child kitchen projects are in the report."""
    if not frappe.db.has_column("Project", SITE_PARENT_FIELD):
        return projects

    have = {p.name for p in projects}
    parent_names = {
        getattr(p, SITE_PARENT_FIELD, None)
        for p in projects
        if getattr(p, SITE_PARENT_FIELD, None) and getattr(p, SITE_PARENT_FIELD, None) not in have
    }
    if not parent_names:
        return projects

    company_cond = "AND p.company = %(company)s" if filters.get("company") else ""
    parents = frappe.db.sql(
        f"""
        SELECT
            p.name,
            p.project_name,
            p.customer,
            p.project_type,
            p.fk_effective_bom,
            p.kitchen_bom,
            p.kitchen_required,
            p.wardrobe_bom,
            p.wardrobe_required,
            p.{SITE_PARENT_FIELD}
        FROM
            `tabProject` p
        WHERE
            p.name IN %(parent_names)s
            AND p.project_type = 'Site'
            AND p.docstatus < 2
            AND p.status NOT IN ('Cancelled', 'Completed')
            {company_cond}
        """,
        {
            "parent_names": list(parent_names),
            "company": filters.get("company"),
        },
        as_dict=True,
    )
    return list(projects) + parents


def _q_all_site_projects(filters):
    """All active Site (parent) projects for the report company — not BOM-filtered."""
    if not frappe.db.has_column("Project", SITE_PARENT_FIELD):
        return []

    company_cond = "AND p.company = %(company)s" if filters.get("company") else ""
    project_cond = "AND p.name = %(project)s" if filters.get("project") else ""

    return frappe.db.sql(
        f"""
        SELECT
            p.name,
            p.project_name,
            p.customer,
            p.fk_effective_bom,
            p.project_type,
            p.kitchen_bom,
            p.kitchen_required,
            p.wardrobe_bom,
            p.wardrobe_required,
            p.{SITE_PARENT_FIELD}
        FROM
            `tabProject` p
        WHERE
            p.project_type = 'Site'
            AND p.docstatus < 2
            AND p.status NOT IN ('Cancelled', 'Completed')
            {company_cond}
            {project_cond}
        ORDER BY
            p.project_name
        """,
        {
            "company": filters.get("company"),
            "project": filters.get("project"),
        },
        as_dict=True,
    )


def _q_site_child_names(site_name):
    """All active unit project names linked to a Site parent."""
    if not frappe.db.has_column("Project", SITE_PARENT_FIELD):
        return []

    return frappe.db.sql_list(
        f"""
        SELECT
            p.name
        FROM
            `tabProject` p
        WHERE
            p.{SITE_PARENT_FIELD} = %(site)s
            AND IFNULL(p.project_type, '') != 'Site'
            AND p.docstatus < 2
            AND p.status NOT IN ('Cancelled', 'Completed')
        ORDER BY
            p.project_name
        """,
        {"site": site_name},
    )


def _q_projects_by_names(project_names):
    """Load project rows for a list of names (used for Site child rollups)."""
    if not project_names:
        return []

    has_parent = frappe.db.has_column("Project", SITE_PARENT_FIELD)
    parent_select = f", p.{SITE_PARENT_FIELD}" if has_parent else ""

    return frappe.db.sql(
        f"""
        SELECT
            p.name,
            p.project_name,
            p.customer,
            p.fk_effective_bom,
            p.project_type,
            p.kitchen_bom,
            p.kitchen_required,
            p.wardrobe_bom,
            p.wardrobe_required{parent_select}
        FROM
            `tabProject` p
        WHERE
            p.name IN %(project_names)s
        ORDER BY
            p.project_name
        """,
        {"project_names": project_names},
        as_dict=True,
    )


def _merge_site_projects(projects, all_sites):
    """Ensure every Site parent appears in the project list for breakdown rows."""
    have = {p.name for p in projects}
    for site in all_sites:
        if site.name not in have:
            projects.append(site)
            have.add(site.name)
    return projects


def _apply_site_breakdown_all_children(
    projects,
    demand_map,
    product_breakdown,
    periods,
    from_date,
    to_date,
    granularity,
    filters,
):
    """
    Detailed monthly breakdown: every Site row shows demand from all child unit
    projects (kitchen + wardrobe), regardless of the selected BOM filter.
    """
    all_sites = _q_all_site_projects(filters)
    if not all_sites:
        return

    _merge_site_projects(projects, all_sites)

    for site in all_sites:
        site_demand = demand_map.setdefault(site.name, {})
        site_breakdown = product_breakdown.setdefault(site.name, {})
        child_names = _q_site_child_names(site.name)
        if not child_names:
            for period in periods:
                pkey = period[0]
                site_demand[pkey] = 0
                site_breakdown[pkey] = {"kitchen": 0, "wardrobe": 0}
            continue

        child_projects = _q_projects_by_names(child_names)
        child_demand = _aggregate_demand_all_projects(
            child_projects, from_date, to_date, granularity
        )
        if granularity == "Weekly":
            child_breakdown = _q_weekly_product_breakdown(
                child_projects, child_names, from_date, to_date
            )
        else:
            child_breakdown = _q_monthly_product_breakdown(
                child_projects, child_names, from_date, to_date
            )

        for period in periods:
            pkey = period[0]
            site_demand[pkey] = sum(
                int(child_demand.get(child, {}).get(pkey, 0) or 0)
                for child in child_names
            )
            month_kitchen = sum(
                int(
                    child_breakdown.get(child, {})
                    .get(pkey, {})
                    .get("kitchen", 0)
                    or 0
                )
                for child in child_names
            )
            month_robe = sum(
                int(
                    child_breakdown.get(child, {})
                    .get(pkey, {})
                    .get("wardrobe", 0)
                    or 0
                )
                for child in child_names
            )
            site_breakdown[pkey] = {
                "kitchen": month_kitchen,
                "wardrobe": month_robe,
            }


def _rollup_site_demand(projects, demand_map, product_breakdown, periods):
    """Site rows: monthly cells = sum of child projects included in the report."""
    if not frappe.db.has_column("Project", SITE_PARENT_FIELD):
        return

    site_names = {p.name for p in projects if getattr(p, "project_type", None) == "Site"}
    if not site_names:
        return

    children_by_site = defaultdict(list)
    for proj in projects:
        parent = getattr(proj, SITE_PARENT_FIELD, None)
        if parent in site_names and proj.name not in site_names:
            children_by_site[parent].append(proj.name)

    for site_name in site_names:
        child_names = children_by_site.get(site_name, [])

        for period in periods:
            pkey = period[0]
            month_demand = sum(
                int(demand_map.get(child, {}).get(pkey, 0) or 0)
                for child in child_names
            )
            demand_map[site_name][pkey] = month_demand

            month_kitchen = sum(
                int(
                    product_breakdown.get(child, {})
                    .get(pkey, {})
                    .get("kitchen", 0)
                    or 0
                )
                for child in child_names
            )
            month_robe = sum(
                int(
                    product_breakdown.get(child, {})
                    .get(pkey, {})
                    .get("wardrobe", 0)
                    or 0
                )
                for child in child_names
            )

            if child_names:
                product_breakdown[site_name][pkey] = {
                    "kitchen": month_kitchen,
                    "wardrobe": month_robe,
                }


def _query_site_structural_totals(site_name):
    """Kitchen / wardrobe quantities on all active child unit projects under a Site."""
    if not frappe.db.has_column("Project", SITE_PARENT_FIELD):
        return {"houses": 0, "kitchens": 0, "wardrobes": 0}

    has_house = frappe.db.has_column("Project", "fk_house_number")
    house_key = "COALESCE(NULLIF(p.fk_house_number, ''), p.name)" if has_house else "p.name"
    qty = _project_unit_qty_sql("p")
    kitchen = _project_is_kitchen_sql("p")
    wardrobe = _project_is_wardrobe_sql("p")

    rows = frappe.db.sql(
        f"""
        SELECT
            {house_key} AS house_key,
            SUM(CASE WHEN {kitchen} THEN {qty} ELSE 0 END) AS kitchen_qty,
            SUM(CASE WHEN {wardrobe} THEN {qty} ELSE 0 END) AS wardrobe_qty
        FROM
            `tabProject` p
        WHERE
            p.{SITE_PARENT_FIELD} = %(site)s
            AND IFNULL(p.project_type, '') != 'Site'
            AND p.docstatus < 2
            AND p.status NOT IN ('Cancelled', 'Completed')
        GROUP BY
            house_key
        """,
        {"site": site_name},
        as_dict=True,
    )

    return {
        "houses": len(rows),
        "kitchens": sum(int(row.kitchen_qty or 0) for row in rows),
        "wardrobes": sum(int(row.wardrobe_qty or 0) for row in rows),
    }


def _set_site_subtitle_totals(projects):
    """
    Site subtitle: distinct units (houses) outside brackets; kitchen / wardrobe
    quantities inside — from all active child projects under the Site.
    """
    site_projects = [
        p for p in projects if getattr(p, "project_type", None) == "Site"
    ]
    if not site_projects:
        return

    for site in site_projects:
        structural = _query_site_structural_totals(site.name)
        site.site_house_count = structural["houses"]
        site.site_unit_count = structural["houses"]
        site.site_kitchen_count = structural["kitchens"]
        site.site_robe_count = structural["wardrobes"]


def _filter_projects_by_bom(projects, bom):
    if not bom:
        return projects
    return [p for p in projects if _project_kitchen_bom(p) == bom]


def _aggregate_demand_all_projects(projects, from_date, to_date, granularity="Monthly"):
    """Sum demand per project using each project's kitchen BOM (BOM filter not applied)."""
    demand_map = defaultdict(dict)
    if not projects:
        return demand_map

    by_bom = defaultdict(list)
    no_bom_names = []

    for proj in projects:
        kitchen_bom = _project_kitchen_bom(proj)
        if kitchen_bom:
            by_bom[kitchen_bom].append(proj.name)
        else:
            no_bom_names.append(proj.name)

    for bom, project_names in by_bom.items():
        if not project_names:
            continue
        operations = _q_bom_operations([bom])
        bottleneck = _get_bottleneck_operation(operations)
        if granularity == "Weekly":
            group_demand = _q_demand_weekly(
                project_names, from_date, to_date, [bom], bottleneck
            )
        else:
            group_demand = _q_demand(
                project_names, from_date, to_date, [bom], bottleneck
            )
        for project_name, period_vals in group_demand.items():
            demand_map[project_name].update(period_vals)

    if no_bom_names:
        if granularity == "Weekly":
            delivery_demand = _q_project_demand_weekly(
                no_bom_names, from_date, to_date
            )
        else:
            delivery_demand = _q_project_demand(
                no_bom_names, from_date, to_date
            )
        for project_name, period_vals in delivery_demand.items():
            demand_map[project_name].update(period_vals)

    return demand_map


# ---------------------------------------------------------------------------
# Q2 – Demand per project per month
# ---------------------------------------------------------------------------

def _merge_period_demand_maps(project_demand, job_card_demand):
    """Use project planned dates as baseline; job-card demand overrides when present."""
    merged = defaultdict(dict)
    for project in set(project_demand) | set(job_card_demand):
        base = project_demand.get(project, {})
        overlay = job_card_demand.get(project, {})
        for pkey in set(base) | set(overlay):
            if overlay.get(pkey):
                merged[project][pkey] = int(overlay[pkey])
            else:
                merged[project][pkey] = int(base.get(pkey, 0) or 0)
    return merged


def _merge_product_breakdown_maps(project_breakdown, job_card_breakdown):
    """Use project planned dates as baseline; job-card breakdown overrides when present."""
    merged = defaultdict(dict)
    for project in set(project_breakdown) | set(job_card_breakdown):
        base = project_breakdown.get(project, {})
        overlay = job_card_breakdown.get(project, {})
        for pkey in set(base) | set(overlay):
            overlay_split = overlay.get(pkey) or {}
            if overlay_split.get("kitchen") or overlay_split.get("wardrobe"):
                merged[project][pkey] = overlay_split
            elif pkey in base:
                merged[project][pkey] = base[pkey]
    return merged


def _q_demand(project_names, from_date, to_date, bom_list=None, bottleneck=None):
    """Job Card actual/scheduled time when available; else Project planned delivery dates."""
    if not project_names:
        return {}

    project_demand = _q_project_demand(project_names, from_date, to_date)
    if not _has_job_card_activity_any(project_names, from_date, to_date):
        return project_demand

    job_card_demand = _q_job_card_demand(project_names, from_date, to_date)
    return _merge_period_demand_maps(project_demand, job_card_demand)


def _q_project_demand(project_names, from_date, to_date):
    """
    Count Project unit quantity scheduled in each month via expected dates.

    Used when no Job Card production data exists for the filtered projects.
    """
    if not project_names:
        return {}

    schedule = _project_schedule_date_sql("p")
    qty = _project_unit_qty_sql("p")
    rows = frappe.db.sql(
        f"""
        SELECT
            p.name AS project,
            DATE_FORMAT({schedule}, '%%Y-%%m') AS ym,
            SUM({qty}) AS units
        FROM
            `tabProject` p
        WHERE
            p.name IN %(project_names)s
            AND IFNULL(p.project_type, '') != 'Site'
            AND {schedule} BETWEEN %(from_date)s AND %(to_date)s
        GROUP BY
            p.name, ym
        """,
        {
            "from_date": from_date,
            "to_date": to_date,
            "project_names": project_names,
        },
        as_dict=True,
    )

    demand_map = defaultdict(dict)
    for row in rows:
        if not row.project or not row.ym:
            continue
        mkey = "m_" + row.ym.replace("-", "_")
        demand_map[row.project][mkey] = int(row.units or 0)

    return demand_map


def _q_monthly_product_breakdown(projects, project_names, from_date, to_date):
    """Kitchen / wardrobe unit counts per project per month (for cell tooltips)."""
    if not project_names:
        return {}

    project_breakdown = _q_project_product_breakdown(
        project_names, from_date, to_date
    )
    proj_map = {p.name: p for p in projects}
    if not _has_job_card_activity_any(project_names, from_date, to_date):
        return project_breakdown

    job_card_breakdown = _q_job_card_product_breakdown(
        project_names, from_date, to_date, proj_map
    )
    return _merge_product_breakdown_maps(project_breakdown, job_card_breakdown)


def _has_job_card_activity_any(project_names, from_date, to_date):
    """Return True when any project job cards exist in the report period."""
    return bool(
        frappe.db.sql(
            """
            SELECT 1
            FROM `tabJob Card` jc
            WHERE
                jc.docstatus < 2
                AND jc.project IN %(project_names)s
                AND (
                    (
                        jc.status = 'Completed'
                        AND (
                            EXISTS (
                                SELECT 1
                                FROM `tabJob Card Time Log` jctl
                                WHERE
                                    jctl.parent = jc.name
                                    AND jctl.from_time >= %(from_datetime)s
                                    AND jctl.from_time <= %(to_datetime)s
                            )
                            OR (
                                COALESCE(jc.actual_end_date, jc.posting_date) >= %(from_datetime)s
                                AND COALESCE(jc.actual_end_date, jc.posting_date) <= %(to_datetime)s
                                AND IFNULL(jc.total_time_in_mins, 0) > 0
                            )
                        )
                    )
                    OR (
                        jc.status NOT IN ('Completed', 'Cancelled')
                        AND COALESCE(jc.expected_start_date, jc.posting_date) >= %(from_date)s
                        AND COALESCE(jc.expected_start_date, jc.posting_date) <= %(to_date)s
                    )
                )
            LIMIT 1
            """,
            {
                "project_names": project_names,
                "from_datetime": f"{from_date} 00:00:00",
                "to_datetime": f"{to_date} 23:59:59",
                "from_date": from_date,
                "to_date": to_date,
            },
        )
    )


def _get_bottleneck_times_for_boms(bom_names):
    times = {}
    for bom in bom_names:
        if not bom:
            continue
        bottleneck = _get_bottleneck_operation(_q_bom_operations([bom]))
        if bottleneck and flt(bottleneck.time_in_mins) > 0:
            times[bom] = flt(bottleneck.time_in_mins)
    return times


def _get_bottleneck_times_for_projects(projects):
    bom_names = {
        bom
        for proj in projects
        for bom in (_project_kitchen_bom(proj), proj.wardrobe_bom)
        if bom
    }
    return _get_bottleneck_times_for_boms(bom_names)


def _job_card_scheduled_mins_sql():
    return """
        CASE
            WHEN IFNULL(jc.time_required, 0) > 0 THEN jc.time_required
            ELSE IFNULL(jc.for_quantity, 0) * IFNULL(
                (
                    SELECT MAX(bo.time_in_mins)
                    FROM `tabBOM Operation` bo
                    WHERE bo.parent = jc.bom_no AND bo.time_in_mins > 0
                ),
                0
            )
        END
    """


def _classify_project_bom(proj, bom_no):
    if bom_no and bom_no == _project_kitchen_bom(proj):
        return "kitchen"
    if bom_no and bom_no == proj.wardrobe_bom:
        return "wardrobe"
    return None


def _q_job_card_product_breakdown(project_names, from_date, to_date, proj_map):
    projects = list(proj_map.values())
    bottleneck_times = _get_bottleneck_times_for_projects(projects)
    params = {
        "project_names": project_names,
        "from_datetime": f"{from_date} 00:00:00",
        "to_datetime": f"{to_date} 23:59:59",
        "from_date": from_date,
        "to_date": to_date,
    }

    completed_log_rows = frappe.db.sql(
        """
        SELECT
            jc.project,
            jc.bom_no,
            DATE_FORMAT(jctl.from_time, '%%Y-%%m') AS ym,
            SUM(jctl.time_in_mins) AS mins
        FROM
            `tabJob Card` jc
            INNER JOIN `tabJob Card Time Log` jctl ON jctl.parent = jc.name
        WHERE
            jc.docstatus < 2
            AND jc.status = 'Completed'
            AND jc.project IN %(project_names)s
            AND jctl.from_time >= %(from_datetime)s
            AND jctl.from_time <= %(to_datetime)s
        GROUP BY
            jc.project, jc.bom_no, ym
        """,
        params,
        as_dict=True,
    )

    completed_total_rows = frappe.db.sql(
        """
        SELECT
            jc.project,
            jc.bom_no,
            DATE_FORMAT(COALESCE(jc.actual_end_date, jc.posting_date), '%%Y-%%m') AS ym,
            SUM(jc.total_time_in_mins) AS mins
        FROM
            `tabJob Card` jc
        WHERE
            jc.docstatus < 2
            AND jc.status = 'Completed'
            AND jc.project IN %(project_names)s
            AND COALESCE(jc.actual_end_date, jc.posting_date) >= %(from_datetime)s
            AND COALESCE(jc.actual_end_date, jc.posting_date) <= %(to_datetime)s
            AND IFNULL(jc.total_time_in_mins, 0) > 0
            AND NOT EXISTS (
                SELECT 1
                FROM `tabJob Card Time Log` jctl
                WHERE jctl.parent = jc.name
            )
        GROUP BY
            jc.project, jc.bom_no, ym
        """,
        params,
        as_dict=True,
    )

    scheduled_rows = frappe.db.sql(
        """
        SELECT
            jc.project,
            jc.bom_no,
            DATE_FORMAT(COALESCE(jc.expected_start_date, jc.posting_date), '%%Y-%%m') AS ym,
            SUM(
                CASE
                    WHEN IFNULL(jc.time_required, 0) > 0 THEN jc.time_required
                    ELSE IFNULL(jc.for_quantity, 0) * IFNULL(
                        (
                            SELECT MAX(bo.time_in_mins)
                            FROM `tabBOM Operation` bo
                            WHERE bo.parent = jc.bom_no AND bo.time_in_mins > 0
                        ),
                        0
                    )
                END
            ) AS mins
        FROM
            `tabJob Card` jc
        WHERE
            jc.docstatus < 2
            AND jc.status NOT IN ('Completed', 'Cancelled')
            AND jc.project IN %(project_names)s
            AND COALESCE(jc.expected_start_date, jc.posting_date) >= %(from_date)s
            AND COALESCE(jc.expected_start_date, jc.posting_date) <= %(to_date)s
        GROUP BY
            jc.project, jc.bom_no, ym
        """,
        params,
        as_dict=True,
    )

    mins_map = defaultdict(lambda: defaultdict(float))
    for row in completed_log_rows + completed_total_rows + scheduled_rows:
        if not row.project or not row.ym or not row.bom_no:
            continue
        mkey = "m_" + row.ym.replace("-", "_")
        mins_map[row.project][(row.bom_no, mkey)] += flt(row.mins)

    breakdown = defaultdict(dict)
    for project, bom_month_mins in mins_map.items():
        proj = proj_map.get(project)
        if not proj:
            continue
        for (bom_no, mkey), mins in bom_month_mins.items():
            category = _classify_project_bom(proj, bom_no)
            if not category:
                continue
            bottleneck_time = bottleneck_times.get(bom_no)
            if not bottleneck_time:
                continue
            bucket = breakdown[project].setdefault(mkey, {"kitchen": 0, "wardrobe": 0})
            bucket[category] += int(mins / bottleneck_time)

    return breakdown


def _q_project_product_breakdown(project_names, from_date, to_date):
    schedule = _project_schedule_date_sql("p")
    qty = _project_unit_qty_sql("p")
    kitchen = _project_is_kitchen_sql("p")
    wardrobe = _project_is_wardrobe_sql("p")
    rows = frappe.db.sql(
        f"""
        SELECT
            p.name AS project,
            DATE_FORMAT({schedule}, '%%Y-%%m') AS ym,
            SUM(CASE WHEN {kitchen} THEN {qty} ELSE 0 END) AS kitchen,
            SUM(CASE WHEN {wardrobe} THEN {qty} ELSE 0 END) AS wardrobe
        FROM
            `tabProject` p
        WHERE
            p.name IN %(project_names)s
            AND IFNULL(p.project_type, '') != 'Site'
            AND {schedule} BETWEEN %(from_date)s AND %(to_date)s
        GROUP BY
            p.name, ym
        """,
        {
            "from_date": from_date,
            "to_date": to_date,
            "project_names": project_names,
        },
        as_dict=True,
    )

    breakdown = defaultdict(dict)
    for row in rows:
        if not row.project or not row.ym:
            continue
        mkey = "m_" + row.ym.replace("-", "_")
        breakdown[row.project][mkey] = {
            "kitchen": int(row.kitchen or 0),
            "wardrobe": int(row.wardrobe or 0),
        }
    return breakdown


def _get_bottleneck_operation(operations):
    """Return the BOM operation that limits capacity (longest time per unit)."""
    valid = [op for op in (operations or []) if flt(op.time_in_mins) > 0]
    if not valid:
        return None
    return max(valid, key=lambda op: flt(op.time_in_mins))


def _q_job_card_demand(project_names, from_date, to_date):
    """
    Derive monthly demand from all Job Cards on each project (no BOM filter).

    Per job card:
    - **Completed** → actual minutes (time logs by month, or total_time_in_mins)
    - **Not completed** → scheduled minutes (time_required) in the planned month

    Minutes are divided by each job card BOM bottleneck operation time.
    """
    if not project_names:
        return {}

    params = {
        "project_names": project_names,
        "from_datetime": f"{from_date} 00:00:00",
        "to_datetime": f"{to_date} 23:59:59",
        "from_date": from_date,
        "to_date": to_date,
    }
    scheduled_mins = _job_card_scheduled_mins_sql()

    completed_log_rows = frappe.db.sql(
        """
        SELECT
            jc.project,
            jc.bom_no,
            DATE_FORMAT(jctl.from_time, '%%Y-%%m') AS ym,
            SUM(jctl.time_in_mins) AS mins
        FROM
            `tabJob Card` jc
            INNER JOIN `tabJob Card Time Log` jctl ON jctl.parent = jc.name
        WHERE
            jc.docstatus < 2
            AND jc.status = 'Completed'
            AND jc.project IN %(project_names)s
            AND jctl.from_time >= %(from_datetime)s
            AND jctl.from_time <= %(to_datetime)s
        GROUP BY
            jc.project, jc.bom_no, ym
        """,
        params,
        as_dict=True,
    )

    completed_total_rows = frappe.db.sql(
        """
        SELECT
            jc.project,
            jc.bom_no,
            DATE_FORMAT(COALESCE(jc.actual_end_date, jc.posting_date), '%%Y-%%m') AS ym,
            SUM(jc.total_time_in_mins) AS mins
        FROM
            `tabJob Card` jc
        WHERE
            jc.docstatus < 2
            AND jc.status = 'Completed'
            AND jc.project IN %(project_names)s
            AND COALESCE(jc.actual_end_date, jc.posting_date) >= %(from_datetime)s
            AND COALESCE(jc.actual_end_date, jc.posting_date) <= %(to_datetime)s
            AND IFNULL(jc.total_time_in_mins, 0) > 0
            AND NOT EXISTS (
                SELECT 1
                FROM `tabJob Card Time Log` jctl
                WHERE jctl.parent = jc.name
            )
        GROUP BY
            jc.project, jc.bom_no, ym
        """,
        params,
        as_dict=True,
    )

    scheduled_rows = frappe.db.sql(
        f"""
        SELECT
            jc.project,
            jc.bom_no,
            DATE_FORMAT(COALESCE(jc.expected_start_date, jc.posting_date), '%%Y-%%m') AS ym,
            SUM({scheduled_mins}) AS mins
        FROM
            `tabJob Card` jc
        WHERE
            jc.docstatus < 2
            AND jc.status NOT IN ('Completed', 'Cancelled')
            AND jc.project IN %(project_names)s
            AND COALESCE(jc.expected_start_date, jc.posting_date) >= %(from_date)s
            AND COALESCE(jc.expected_start_date, jc.posting_date) <= %(to_date)s
        GROUP BY
            jc.project, jc.bom_no, ym
        """,
        params,
        as_dict=True,
    )

    mins_map = defaultdict(lambda: defaultdict(float))
    bom_names = set()
    for row in completed_log_rows + completed_total_rows + scheduled_rows:
        if not row.project or not row.ym or not row.bom_no:
            continue
        mkey = "m_" + row.ym.replace("-", "_")
        mins_map[row.project][(row.bom_no, mkey)] += flt(row.mins)
        bom_names.add(row.bom_no)

    bottleneck_times = _get_bottleneck_times_for_boms(bom_names)

    demand_map = defaultdict(dict)
    for project, bom_month_mins in mins_map.items():
        for (bom_no, mkey), mins in bom_month_mins.items():
            bottleneck_time = bottleneck_times.get(bom_no)
            if not bottleneck_time:
                continue
            demand_map[project][mkey] = demand_map[project].get(mkey, 0) + int(
                mins / bottleneck_time
            )

    return demand_map


# ---------------------------------------------------------------------------
# Weekly demand / capacity (separate from monthly calculations)
# ---------------------------------------------------------------------------

def _week_start(d):
    d = getdate(d)
    return d - timedelta(days=d.weekday())


def _week_end(week_start):
    return getdate(week_start) + timedelta(days=6)


def _week_key_from_date(d):
    d = getdate(d)
    return f"w_{d.year}_{d.month:02d}_{d.day:02d}"


def _week_start_sql(field):
    return _WEEK_START_SQL.format(field=field)


def _period_start(period):
    return getdate(period[2])


def _period_end(period):
    if len(period) > 3:
        return getdate(period[3])
    return get_last_day(getdate(period[2]))


def _count_weekdays_in_range(start, end):
    start = getdate(start)
    end = getdate(end)
    count = 0
    current = start
    while current <= end:
        if current.weekday() < 5:
            count += 1
        current += timedelta(days=1)
    return count


def _count_weekday_holidays_in_range(holiday_dates, start, end):
    start = getdate(start)
    end = getdate(end)
    return sum(
        1
        for holiday in holiday_dates
        if start <= getdate(holiday) <= end and getdate(holiday).weekday() < 5
    )


def _q_demand_weekly(project_names, from_date, to_date, bom_list=None, bottleneck=None):
    if not project_names:
        return {}

    project_demand = _q_project_demand_weekly(project_names, from_date, to_date)
    if not _has_job_card_activity_any(project_names, from_date, to_date):
        return project_demand

    job_card_demand = _q_job_card_demand_weekly(project_names, from_date, to_date)
    return _merge_period_demand_maps(project_demand, job_card_demand)


def _q_project_demand_weekly(project_names, from_date, to_date):
    if not project_names:
        return {}

    schedule = _project_schedule_date_sql("p")
    qty = _project_unit_qty_sql("p")
    week_start = _week_start_sql(schedule)
    rows = frappe.db.sql(
        f"""
        SELECT
            p.name AS project,
            {week_start} AS week_start,
            SUM({qty}) AS units
        FROM
            `tabProject` p
        WHERE
            p.name IN %(project_names)s
            AND IFNULL(p.project_type, '') != 'Site'
            AND {schedule} BETWEEN %(from_date)s AND %(to_date)s
        GROUP BY
            p.name, week_start
        """,
        {
            "from_date": from_date,
            "to_date": to_date,
            "project_names": project_names,
        },
        as_dict=True,
    )

    demand_map = defaultdict(dict)
    for row in rows:
        if not row.project or not row.week_start:
            continue
        demand_map[row.project][_week_key_from_date(row.week_start)] = int(row.units or 0)

    return demand_map


def _q_job_card_demand_weekly(project_names, from_date, to_date):
    """Weekly demand from all project job cards (see _q_job_card_demand)."""
    if not project_names:
        return {}

    params = {
        "project_names": project_names,
        "from_datetime": f"{from_date} 00:00:00",
        "to_datetime": f"{to_date} 23:59:59",
        "from_date": from_date,
        "to_date": to_date,
    }
    scheduled_mins = _job_card_scheduled_mins_sql()

    log_week = _week_start_sql("jctl.from_time")
    completed_log_rows = frappe.db.sql(
        f"""
        SELECT
            jc.project,
            jc.bom_no,
            {log_week} AS week_start,
            SUM(jctl.time_in_mins) AS mins
        FROM
            `tabJob Card` jc
            INNER JOIN `tabJob Card Time Log` jctl ON jctl.parent = jc.name
        WHERE
            jc.docstatus < 2
            AND jc.status = 'Completed'
            AND jc.project IN %(project_names)s
            AND jctl.from_time >= %(from_datetime)s
            AND jctl.from_time <= %(to_datetime)s
        GROUP BY
            jc.project, jc.bom_no, week_start
        """,
        params,
        as_dict=True,
    )

    actual_week = _week_start_sql("COALESCE(jc.actual_end_date, jc.posting_date)")
    completed_total_rows = frappe.db.sql(
        f"""
        SELECT
            jc.project,
            jc.bom_no,
            {actual_week} AS week_start,
            SUM(jc.total_time_in_mins) AS mins
        FROM
            `tabJob Card` jc
        WHERE
            jc.docstatus < 2
            AND jc.status = 'Completed'
            AND jc.project IN %(project_names)s
            AND COALESCE(jc.actual_end_date, jc.posting_date) >= %(from_datetime)s
            AND COALESCE(jc.actual_end_date, jc.posting_date) <= %(to_datetime)s
            AND IFNULL(jc.total_time_in_mins, 0) > 0
            AND NOT EXISTS (
                SELECT 1
                FROM `tabJob Card Time Log` jctl
                WHERE jctl.parent = jc.name
            )
        GROUP BY
            jc.project, jc.bom_no, week_start
        """,
        params,
        as_dict=True,
    )

    scheduled_week = _week_start_sql("COALESCE(jc.expected_start_date, jc.posting_date)")
    scheduled_rows = frappe.db.sql(
        f"""
        SELECT
            jc.project,
            jc.bom_no,
            {scheduled_week} AS week_start,
            SUM({scheduled_mins}) AS mins
        FROM
            `tabJob Card` jc
        WHERE
            jc.docstatus < 2
            AND jc.status NOT IN ('Completed', 'Cancelled')
            AND jc.project IN %(project_names)s
            AND COALESCE(jc.expected_start_date, jc.posting_date) >= %(from_date)s
            AND COALESCE(jc.expected_start_date, jc.posting_date) <= %(to_date)s
        GROUP BY
            jc.project, jc.bom_no, week_start
        """,
        params,
        as_dict=True,
    )

    mins_map = defaultdict(lambda: defaultdict(float))
    bom_names = set()
    for row in completed_log_rows + completed_total_rows + scheduled_rows:
        if not row.project or not row.week_start or not row.bom_no:
            continue
        wkey = _week_key_from_date(row.week_start)
        mins_map[row.project][(row.bom_no, wkey)] += flt(row.mins)
        bom_names.add(row.bom_no)

    bottleneck_times = _get_bottleneck_times_for_boms(bom_names)

    demand_map = defaultdict(dict)
    for project, bom_week_mins in mins_map.items():
        for (bom_no, wkey), mins in bom_week_mins.items():
            bottleneck_time = bottleneck_times.get(bom_no)
            if not bottleneck_time:
                continue
            demand_map[project][wkey] = demand_map[project].get(wkey, 0) + int(
                mins / bottleneck_time
            )

    return demand_map


def _q_weekly_product_breakdown(projects, project_names, from_date, to_date):
    if not project_names:
        return {}

    project_breakdown = _q_project_product_breakdown_weekly(
        project_names, from_date, to_date
    )
    proj_map = {p.name: p for p in projects}
    if not _has_job_card_activity_any(project_names, from_date, to_date):
        return project_breakdown

    job_card_breakdown = _q_job_card_product_breakdown_weekly(
        project_names, from_date, to_date, proj_map
    )
    return _merge_product_breakdown_maps(project_breakdown, job_card_breakdown)


def _q_job_card_product_breakdown_weekly(project_names, from_date, to_date, proj_map):
    projects = list(proj_map.values())
    bottleneck_times = _get_bottleneck_times_for_projects(projects)
    params = {
        "project_names": project_names,
        "from_datetime": f"{from_date} 00:00:00",
        "to_datetime": f"{to_date} 23:59:59",
        "from_date": from_date,
        "to_date": to_date,
    }

    log_week = _week_start_sql("jctl.from_time")
    completed_log_rows = frappe.db.sql(
        f"""
        SELECT
            jc.project,
            jc.bom_no,
            {log_week} AS week_start,
            SUM(jctl.time_in_mins) AS mins
        FROM
            `tabJob Card` jc
            INNER JOIN `tabJob Card Time Log` jctl ON jctl.parent = jc.name
        WHERE
            jc.docstatus < 2
            AND jc.status = 'Completed'
            AND jc.project IN %(project_names)s
            AND jctl.from_time >= %(from_datetime)s
            AND jctl.from_time <= %(to_datetime)s
        GROUP BY
            jc.project, jc.bom_no, week_start
        """,
        params,
        as_dict=True,
    )

    actual_week = _week_start_sql("COALESCE(jc.actual_end_date, jc.posting_date)")
    completed_total_rows = frappe.db.sql(
        f"""
        SELECT
            jc.project,
            jc.bom_no,
            {actual_week} AS week_start,
            SUM(jc.total_time_in_mins) AS mins
        FROM
            `tabJob Card` jc
        WHERE
            jc.docstatus < 2
            AND jc.status = 'Completed'
            AND jc.project IN %(project_names)s
            AND COALESCE(jc.actual_end_date, jc.posting_date) >= %(from_datetime)s
            AND COALESCE(jc.actual_end_date, jc.posting_date) <= %(to_datetime)s
            AND IFNULL(jc.total_time_in_mins, 0) > 0
            AND NOT EXISTS (
                SELECT 1
                FROM `tabJob Card Time Log` jctl
                WHERE jctl.parent = jc.name
            )
        GROUP BY
            jc.project, jc.bom_no, week_start
        """,
        params,
        as_dict=True,
    )

    scheduled_week = _week_start_sql("COALESCE(jc.expected_start_date, jc.posting_date)")
    scheduled_rows = frappe.db.sql(
        f"""
        SELECT
            jc.project,
            jc.bom_no,
            {scheduled_week} AS week_start,
            SUM(
                CASE
                    WHEN IFNULL(jc.time_required, 0) > 0 THEN jc.time_required
                    ELSE IFNULL(jc.for_quantity, 0) * IFNULL(
                        (
                            SELECT MAX(bo.time_in_mins)
                            FROM `tabBOM Operation` bo
                            WHERE bo.parent = jc.bom_no AND bo.time_in_mins > 0
                        ),
                        0
                    )
                END
            ) AS mins
        FROM
            `tabJob Card` jc
        WHERE
            jc.docstatus < 2
            AND jc.status NOT IN ('Completed', 'Cancelled')
            AND jc.project IN %(project_names)s
            AND COALESCE(jc.expected_start_date, jc.posting_date) >= %(from_date)s
            AND COALESCE(jc.expected_start_date, jc.posting_date) <= %(to_date)s
        GROUP BY
            jc.project, jc.bom_no, week_start
        """,
        params,
        as_dict=True,
    )

    mins_map = defaultdict(lambda: defaultdict(float))
    for row in completed_log_rows + completed_total_rows + scheduled_rows:
        if not row.project or not row.week_start or not row.bom_no:
            continue
        wkey = _week_key_from_date(row.week_start)
        mins_map[row.project][(row.bom_no, wkey)] += flt(row.mins)

    breakdown = defaultdict(dict)
    for project, bom_week_mins in mins_map.items():
        proj = proj_map.get(project)
        if not proj:
            continue
        for (bom_no, wkey), mins in bom_week_mins.items():
            category = _classify_project_bom(proj, bom_no)
            if not category:
                continue
            bottleneck_time = bottleneck_times.get(bom_no)
            if not bottleneck_time:
                continue
            bucket = breakdown[project].setdefault(wkey, {"kitchen": 0, "wardrobe": 0})
            bucket[category] += int(mins / bottleneck_time)

    return breakdown


def _q_project_product_breakdown_weekly(project_names, from_date, to_date):
    schedule = _project_schedule_date_sql("p")
    qty = _project_unit_qty_sql("p")
    kitchen = _project_is_kitchen_sql("p")
    wardrobe = _project_is_wardrobe_sql("p")
    week_start = _week_start_sql(schedule)
    rows = frappe.db.sql(
        f"""
        SELECT
            p.name AS project,
            {week_start} AS week_start,
            SUM(CASE WHEN {kitchen} THEN {qty} ELSE 0 END) AS kitchen,
            SUM(CASE WHEN {wardrobe} THEN {qty} ELSE 0 END) AS wardrobe
        FROM
            `tabProject` p
        WHERE
            p.name IN %(project_names)s
            AND IFNULL(p.project_type, '') != 'Site'
            AND {schedule} BETWEEN %(from_date)s AND %(to_date)s
        GROUP BY
            p.name, week_start
        """,
        {
            "from_date": from_date,
            "to_date": to_date,
            "project_names": project_names,
        },
        as_dict=True,
    )

    breakdown = defaultdict(dict)
    for row in rows:
        if not row.project or not row.week_start:
            continue
        wkey = _week_key_from_date(row.week_start)
        breakdown[row.project][wkey] = {
            "kitchen": int(row.kitchen or 0),
            "wardrobe": int(row.wardrobe or 0),
        }
    return breakdown


def _q_downtime_weekly(workstation_names, from_date, to_date):
    if not workstation_names:
        return {}

    week_start = _week_start_sql("from_time")
    rows = frappe.db.sql(
        f"""
        SELECT
            workstation,
            {week_start} AS week_start,
            SUM(downtime) AS total_mins
        FROM `tabDowntime Entry`
        WHERE
            workstation IN %(workstations)s
            AND from_time >= %(from_date)s
            AND from_time <= %(to_date)s
        GROUP BY
            workstation, week_start
        """,
        {
            "workstations": workstation_names,
            "from_date": from_date,
            "to_date": to_date,
        },
        as_dict=True,
    )

    result = {}
    for row in rows:
        result[(row.workstation, _week_key_from_date(row.week_start))] = flt(row.total_mins)

    return result


def _calc_workstation_availability_range(ws_map, start, end, holidays_map):
    weekdays_in_range = _count_weekdays_in_range(start, end)
    ws_avail = {}
    for ws_name, ws in ws_map.items():
        holidays_in_range = _count_weekday_holidays_in_range(
            holidays_map.get(ws.holiday_list or "", []),
            start,
            end,
        )
        effective_days = max(0, weekdays_in_range - holidays_in_range)
        daily_hours = flt(ws.total_working_hours) or 8.0
        ws_avail[ws_name] = (
            flt(ws.production_capacity or 1) * effective_days * daily_hours * 60.0
        )
    return ws_avail


def _calc_capacity_per_week(
    operations, ws_map, ws_by_type, holidays_map, downtime_map, weeks
):
    week_keys = [wkey for wkey, _, _, _ in weeks]
    result = {
        "theoretical": {wkey: 0 for wkey in week_keys},
        "actual": {wkey: 0 for wkey in week_keys},
        "downtime_total": {wkey: 0 for wkey in week_keys},
    }

    if not operations or not ws_map:
        return result

    downtime_by_week = {wkey: 0 for wkey in week_keys}
    for (ws_name, wkey), mins in downtime_map.items():
        if ws_name in ws_map and wkey in downtime_by_week:
            downtime_by_week[wkey] += mins

    for wkey, _wlabel, week_start, week_end in weeks:
        ws_avail = _calc_workstation_availability_range(
            ws_map, week_start, week_end, holidays_map
        )
        ws_downtime = {
            ws_name: downtime_map.get((ws_name, wkey), 0) for ws_name in ws_map
        }
        type_avail = _aggregate_type_availability(ws_avail, ws_by_type)
        type_downtime = _aggregate_type_downtime(ws_downtime, ws_by_type)

        theoretical, actual = _calc_bottleneck_capacity(
            operations, ws_avail, type_avail, ws_downtime, type_downtime
        )
        result["theoretical"][wkey] = theoretical
        result["actual"][wkey] = actual
        result["downtime_total"][wkey] = int(downtime_by_week.get(wkey, 0))

    return result


def _build_week_list(filters):
    """Return (key, label, week_start, week_end) for each Mon–Sun week in the range."""
    from_date = getdate(filters.get("from_date") or frappe.utils.today())
    to_date_raw = filters.get("to_date")
    if to_date_raw:
        to_date = getdate(to_date_raw)
    else:
        to_date = getdate(add_months(get_first_day(from_date), 11))

    weeks = []
    current = _week_start(from_date)

    while current <= to_date:
        week_end = _week_end(current)
        if week_end >= from_date:
            weeks.append(
                (
                    _week_key_from_date(current),
                    current.strftime("%d %b").upper(),
                    current,
                    week_end,
                )
            )
        current += timedelta(days=7)

    return weeks


# ---------------------------------------------------------------------------
# Q3 – BOM operations (direct + 1-level sub-assembly)
# ---------------------------------------------------------------------------

def _q_bom_operations(bom_list):
    """
    Return all BOM operations from:
      - operations directly on the kitchen BOMs
      - operations on BOM routings
      - operations on sub-assembly BOMs and their routings

    One UNION ALL query; no per-BOM loops.
    """
    if not bom_list:
        return []

    rows = frappe.db.sql(
        """
        SELECT
            bo.operation,
            bo.workstation,
            bo.workstation_type,
            bo.time_in_mins
        FROM `tabBOM Operation` bo
        WHERE
            bo.parent IN %(bom_list)s
            AND bo.time_in_mins > 0

        UNION ALL

        SELECT
            bo.operation,
            bo.workstation,
            bo.workstation_type,
            bo.time_in_mins
        FROM
            tabBOM b
            INNER JOIN `tabBOM Operation` bo ON bo.parent = b.routing
        WHERE
            b.name IN %(bom_list)s
            AND IFNULL(b.routing, '') != ''
            AND bo.time_in_mins > 0

        UNION ALL

        SELECT
            bo.operation,
            bo.workstation,
            bo.workstation_type,
            bo.time_in_mins
        FROM
            `tabBOM Item` bi
            INNER JOIN `tabBOM Operation` bo ON bo.parent = bi.bom_no
        WHERE
            bi.parent IN %(bom_list)s
            AND IFNULL(bi.bom_no, '') != ''
            AND bo.time_in_mins > 0

        UNION ALL

        SELECT
            bo.operation,
            bo.workstation,
            bo.workstation_type,
            bo.time_in_mins
        FROM
            `tabBOM Item` bi
            INNER JOIN tabBOM sub ON sub.name = bi.bom_no
            INNER JOIN `tabBOM Operation` bo ON bo.parent = sub.routing
        WHERE
            bi.parent IN %(bom_list)s
            AND IFNULL(bi.bom_no, '') != ''
            AND IFNULL(sub.routing, '') != ''
            AND bo.time_in_mins > 0
        """,
        {"bom_list": bom_list},
        as_dict=True,
    )

    return rows


# ---------------------------------------------------------------------------
# Q4 – Workstations
# ---------------------------------------------------------------------------

def _q_workstations(workstation_names, workstation_types=None):
    names = list(workstation_names or [])
    types = list(workstation_types or [])
    if not names and not types:
        return []

    conditions = []
    params = {}
    if names:
        conditions.append("name IN %(names)s")
        params["names"] = names
    if types:
        conditions.append("workstation_type IN %(types)s")
        params["types"] = types

    return frappe.db.sql(
        f"""
        SELECT
            name,
            workstation_type,
            production_capacity,
            total_working_hours,
            holiday_list
        FROM `tabWorkstation`
        WHERE
            disabled = 0
            AND ({" OR ".join(conditions)})
        """,
        params,
        as_dict=True,
    )


# ---------------------------------------------------------------------------
# Q5 – Holidays
# ---------------------------------------------------------------------------

def _q_holidays(holiday_lists, from_date, to_date):
    """
    Returns: {holiday_list_name: [date, date, ...]}
    """
    if not holiday_lists:
        return {}

    rows = frappe.db.sql(
        """
        SELECT
            parent AS holiday_list,
            holiday_date
        FROM `tabHoliday`
        WHERE
            parent IN %(lists)s
            AND holiday_date BETWEEN %(from_date)s AND %(to_date)s
        """,
        {"lists": holiday_lists, "from_date": from_date, "to_date": to_date},
        as_dict=True,
    )

    hmap = defaultdict(list)
    for row in rows:
        hmap[row.holiday_list].append(getdate(row.holiday_date))

    return hmap


# ---------------------------------------------------------------------------
# Q6 – Downtime entries per workstation per month
# ---------------------------------------------------------------------------

def _q_downtime(workstation_names, from_date, to_date):
    """
    Sum Downtime Entry minutes by workstation and calendar month.

    Returns: {(workstation_name, month_key): downtime_mins}
    """
    if not workstation_names:
        return {}

    rows = frappe.db.sql(
        """
        SELECT
            workstation,
            DATE_FORMAT(from_time, '%%Y-%%m') AS ym,
            SUM(downtime) AS total_mins
        FROM `tabDowntime Entry`
        WHERE
            workstation IN %(workstations)s
            AND from_time >= %(from_date)s
            AND from_time <= %(to_date)s
        GROUP BY
            workstation, ym
        """,
        {
            "workstations": workstation_names,
            "from_date": from_date,
            "to_date": to_date,
        },
        as_dict=True,
    )

    result = {}
    for row in rows:
        mkey = "m_" + row.ym.replace("-", "_")
        result[(row.workstation, mkey)] = flt(row.total_mins)

    return result


# ---------------------------------------------------------------------------
# Capacity calculation
# ---------------------------------------------------------------------------

def _calc_capacity_per_month(
    operations, ws_map, ws_by_type, holidays_map, downtime_map, months
):
    """Compute bottleneck capacity before and after downtime for each calendar month."""
    month_keys = [mkey for mkey, _, _ in months]
    result = {
        "theoretical": {mkey: 0 for mkey in month_keys},
        "actual": {mkey: 0 for mkey in month_keys},
        "downtime_total": {mkey: 0 for mkey in month_keys},
    }

    if not operations or not ws_map:
        return result

    downtime_by_month = {mkey: 0 for mkey in month_keys}
    for (ws_name, mkey), mins in downtime_map.items():
        if ws_name in ws_map:
            downtime_by_month[mkey] += mins

    for mkey, _mlabel, mdate in months:
        ws_avail = _calc_workstation_availability(ws_map, mdate, holidays_map)
        ws_downtime = {
            ws_name: downtime_map.get((ws_name, mkey), 0) for ws_name in ws_map
        }
        type_avail = _aggregate_type_availability(ws_avail, ws_by_type)
        type_downtime = _aggregate_type_downtime(ws_downtime, ws_by_type)

        theoretical, actual = _calc_bottleneck_capacity(
            operations, ws_avail, type_avail, ws_downtime, type_downtime
        )
        result["theoretical"][mkey] = theoretical
        result["actual"][mkey] = actual
        result["downtime_total"][mkey] = int(downtime_by_month.get(mkey, 0))

    return result


def _calc_workstation_availability(ws_map, mdate, holidays_map):
    weekdays_in_month = _count_weekdays(mdate.year, mdate.month)
    ws_avail = {}
    for ws_name, ws in ws_map.items():
        holidays_this_month = _count_weekday_holidays_in_month(
            holidays_map.get(ws.holiday_list or "", []),
            mdate.year,
            mdate.month,
        )
        effective_days = max(0, weekdays_in_month - holidays_this_month)
        daily_hours = flt(ws.total_working_hours) or 8.0
        ws_avail[ws_name] = (
            flt(ws.production_capacity or 1) * effective_days * daily_hours * 60.0
        )
    return ws_avail


def _aggregate_type_availability(ws_avail, ws_by_type):
    return {
        ws_type: sum(ws_avail.get(ws.name, 0) for ws in ws_list)
        for ws_type, ws_list in ws_by_type.items()
    }


def _aggregate_type_downtime(ws_downtime, ws_by_type):
    return {
        ws_type: sum(ws_downtime.get(ws.name, 0) for ws in ws_list)
        for ws_type, ws_list in ws_by_type.items()
    }


def _calc_bottleneck_capacity(
    operations, ws_avail, type_avail, ws_downtime=None, type_downtime=None
):
    ws_downtime = ws_downtime or {}
    type_downtime = type_downtime or {}

    min_theoretical = None
    min_actual = None
    for op in operations:
        available_mins = _get_operation_available_mins(op, ws_avail, type_avail)
        downtime_mins = _get_operation_downtime_mins(op, ws_downtime, type_downtime)
        t = flt(op.time_in_mins)
        if t <= 0 or available_mins <= 0:
            continue

        theoretical = available_mins / t
        actual_avail = max(0, available_mins - downtime_mins)
        actual = actual_avail / t if actual_avail > 0 else 0

        if min_theoretical is None or theoretical < min_theoretical:
            min_theoretical = theoretical
        if min_actual is None or actual < min_actual:
            min_actual = actual

    return (
        int(min_theoretical) if min_theoretical is not None else 0,
        int(min_actual) if min_actual is not None else 0,
    )


def _group_workstations_by_type(workstations):
    grouped = defaultdict(list)
    for ws in workstations:
        if ws.workstation_type:
            grouped[ws.workstation_type].append(ws)
    return grouped


def _get_operation_available_mins(op, ws_avail, type_avail):
    if op.workstation:
        return ws_avail.get(op.workstation, 0)
    if op.workstation_type:
        return type_avail.get(op.workstation_type, 0)
    return 0


def _get_operation_downtime_mins(op, ws_downtime, type_downtime):
    if op.workstation:
        return ws_downtime.get(op.workstation, 0)
    if op.workstation_type:
        return type_downtime.get(op.workstation_type, 0)
    return 0


def _count_weekdays(year, month):
    """Count Monday–Friday days in the given month."""
    _, days_in_month = calendar.monthrange(year, month)
    return sum(
        1
        for day in range(1, days_in_month + 1)
        if date(year, month, day).weekday() < 5
    )


def _count_weekday_holidays_in_month(holiday_dates, year, month):
    """Count holidays that fall on a working day (Mon–Fri) in the given month."""
    return sum(
        1
        for holiday in holiday_dates
        if holiday.year == year
        and holiday.month == month
        and holiday.weekday() < 5
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_month_list(filters):
    """
    Return list of (field_key, display_label, first_day_date) for each
    calendar month between from_date and to_date (inclusive).
    """
    from_date = getdate(filters.get("from_date") or frappe.utils.today())
    to_date_raw = filters.get("to_date")
    if to_date_raw:
        to_date = getdate(to_date_raw)
    else:
        to_date = getdate(add_months(get_first_day(from_date), 11))

    months = []
    current = get_first_day(from_date)
    end = get_last_day(to_date)

    while current <= end:
        key = f"m_{current.year}_{current.month:02d}"
        label = current.strftime("%b '%y").upper()   # e.g. "JUN '26"
        months.append((key, label, current))
        current = get_first_day(add_months(current, 1))

    return months


def _infer_site_name_from_project_name(project_name):
    """Best-effort site label when a unit project has no Site parent row."""
    if not project_name:
        return project_name
    if " | " in project_name:
        return project_name.split(" | ", 1)[0].strip()
    match = re.match(r"^(.+?)\s*-\s*Apt\s", project_name, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return project_name


def _chart_label_for_project(proj, site_name_by_id):
    """Label used in chart legend / stacks — always the parent Site name when available."""
    project_name = proj.project_name or proj.name
    if getattr(proj, "project_type", None) == "Site":
        return project_name
    parent = getattr(proj, SITE_PARENT_FIELD, None)
    if parent and parent in site_name_by_id:
        return site_name_by_id[parent]
    return _infer_site_name_from_project_name(project_name)


def _project_subtitle(proj):
    """Site: e.g. 2 Units (2 kitchens, 1 Wardrobe); other types: (Project Type)."""
    project_type = getattr(proj, "project_type", None)

    if project_type == "Site":
        unit_count = int(getattr(proj, "site_house_count", 0) or 0)
        if not unit_count:
            unit_count = int(getattr(proj, "site_unit_count", 0) or 0)
        kitchen_count = int(getattr(proj, "site_kitchen_count", 0) or 0)
        robe_count = int(getattr(proj, "site_robe_count", 0) or 0)

        detail_parts = []
        if kitchen_count:
            detail_parts.append(_("{0} kitchens").format(kitchen_count))
        if robe_count:
            robe_label = _("Wardrobe") if robe_count == 1 else _("Wardrobes")
            detail_parts.append(f"{robe_count} {robe_label}")

        if not unit_count and not detail_parts:
            return ""

        unit_label = _("Unit") if unit_count == 1 else _("Units")
        if detail_parts:
            return f"{unit_count} {unit_label} ({', '.join(detail_parts)})"
        return f"{unit_count} {unit_label}"

    if project_type:
        return f"({project_type})"
    return ""


def _get_bom_capacity_subtitle(bom):
    """Describe the BOM used for capacity — item, operations, and raw materials."""
    item = frappe.db.get_value("BOM", bom, "item") or bom
    operation_count = len(_q_bom_operations([bom]))
    raw_material_count = frappe.db.sql(
        """
        SELECT COUNT(*)
        FROM `tabBOM Item`
        WHERE parent = %s AND IFNULL(bom_no, '') = ''
        """,
        bom,
    )[0][0]
    return _("{0} · {1} operations · {2} raw materials").format(
        item, operation_count, raw_material_count
    )
