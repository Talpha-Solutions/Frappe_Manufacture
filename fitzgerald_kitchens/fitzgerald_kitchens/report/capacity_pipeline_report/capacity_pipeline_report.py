# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

"""Capacity Pipeline Report

Shows monthly kitchen delivery demand per project alongside the calculated
workstation capacity (derived from BOM operations + Workstation working hours /
holiday lists).  Displays demand utilisation % and free capacity.

Query budget: 6 SQL statements — no per-row or per-project round-trips.
"""

import calendar
from collections import defaultdict
from datetime import date

import frappe
from frappe import _
from frappe.utils import flt, getdate, get_first_day, get_last_day, add_months


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def execute(filters=None):
    filters = frappe._dict(filters or {})
    months = _build_month_list(filters)
    columns = _get_columns(months)
    data = _get_data(filters, months)
    return columns, data


# ---------------------------------------------------------------------------
# Columns (dynamic – one per month)
# ---------------------------------------------------------------------------

def _get_columns(months):
    cols = [
        {
            "fieldname": "project",
            "label": _("PROJECT"),
            "fieldtype": "Data",
            "width": 220,
        }
    ]
    for mkey, mlabel, _mdate in months:
        cols.append(
            {
                "fieldname": mkey,
                "label": mlabel,
                "fieldtype": "Data",
                "width": 96,
            }
        )
    return cols


# ---------------------------------------------------------------------------
# Main data assembly
# ---------------------------------------------------------------------------

def _get_data(filters, months):
    if not months:
        return []

    from_date = months[0][2]
    to_date = get_last_day(months[-1][2])

    projects = _q_projects(filters)
    project_names = [p.name for p in projects]
    bom_list = list({p.kitchen_bom for p in projects if p.kitchen_bom})

    demand_map = _q_demand(project_names, from_date, to_date) if project_names else {}

    operations = _q_bom_operations(bom_list) if bom_list else []
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
    downtime_map = _q_downtime(list(ws_map.keys()), from_date, to_date) if ws_map else {}
    capacity_result = _calc_capacity_per_month(
        operations, ws_map, ws_by_type, holidays_map, downtime_map, months
    )

    data = []
    for idx, proj in enumerate(sorted(projects, key=lambda p: (p.project_name or p.name).lower())):
        proj_demand = demand_map.get(proj.name, {})
        row = {
            "project": proj.project_name or proj.name,
            "project_id": proj.name,
            "subtitle": _project_subtitle(proj),
            "row_type": "project",
            "color_index": idx,
        }
        for mkey, _mlabel, _mdate in months:
            row[mkey] = proj_demand.get(mkey, 0)
        data.append(row)

    data.extend(_build_summary_rows(months, demand_map, projects, capacity_result))
    return data


def _build_summary_rows(months, demand_map, projects, capacity_result):
    """Append separator + downtime + capacity / demand / free capacity summary rows."""
    rows = []

    sep = {"project": " ", "row_type": "separator"}
    for mkey, _mlabel, _mdate in months:
        sep[mkey] = 0
    rows.append(sep)

    month_demand = {
        mkey: sum(demand_map.get(p.name, {}).get(mkey, 0) for p in projects)
        for mkey, _, _ in months
    }

    downtime_row = {"project": _("Downtime (mins)"), "row_type": "downtime", "bold": 1}
    for mkey, _mlabel, _mdate in months:
        downtime_row[mkey] = capacity_result["downtime_total"].get(mkey, 0)
    rows.append(downtime_row)

    cap_row = {"project": _("Capacity / month"), "row_type": "capacity", "bold": 1}
    for mkey, _mlabel, _mdate in months:
        actual = capacity_result["actual"].get(mkey, 0)
        theoretical = capacity_result["theoretical"].get(mkey, 0)
        cap_row[mkey] = f"{actual}/{theoretical}"
        cap_row[f"{mkey}_actual"] = actual
        cap_row[f"{mkey}_theoretical"] = theoretical
    rows.append(cap_row)

    dem_row = {"project": _("Demand · utilisation"), "row_type": "demand", "bold": 1}
    for mkey, _mlabel, _mdate in months:
        cap = capacity_result["actual"].get(mkey) or 0
        dem = month_demand.get(mkey, 0)
        dem_row[mkey] = dem
        dem_row[f"{mkey}_pct"] = flt(dem / cap * 100, 0) if cap else 0
    rows.append(dem_row)

    free_row = {"project": _("Free capacity"), "row_type": "free", "bold": 1}
    for mkey, _mlabel, _mdate in months:
        cap = capacity_result["actual"].get(mkey) or 0
        dem = month_demand.get(mkey, 0)
        free_row[mkey] = cap - dem
    rows.append(free_row)

    return rows


# ---------------------------------------------------------------------------
# Q1 – Projects
# ---------------------------------------------------------------------------

def _q_projects(filters):
    """Return active projects for the company (with or without kitchen BOM)."""
    company_cond = "AND p.company = %(company)s" if filters.get("company") else ""
    project_cond = "AND p.name = %(project)s" if filters.get("project") else ""

    rows = frappe.db.sql(
        f"""
        SELECT
            p.name,
            p.project_name,
            p.customer,
            p.kitchen_bom,
            p.kitchen_required,
            COUNT(du.name) AS unit_count
        FROM
            `tabProject` p
            LEFT JOIN `tabDevelopment Unit` du ON du.project = p.name
        WHERE
            p.docstatus < 2
            AND p.status NOT IN ('Cancelled', 'Completed')
            {company_cond}
            {project_cond}
        GROUP BY
            p.name, p.project_name, p.customer, p.kitchen_bom, p.kitchen_required
        ORDER BY
            p.project_name
        """,
        {
            "company": filters.get("company"),
            "project": filters.get("project"),
        },
        as_dict=True,
    )

    return rows


# ---------------------------------------------------------------------------
# Q2 – Delivery demand per project per month
# ---------------------------------------------------------------------------

def _q_demand(project_names, from_date, to_date):
    """
    Count Development Units whose Delivery stage is planned in each month.

    Returns: {project_name: {month_key: unit_count}}
    """
    if not project_names:
        return {}

    rows = frappe.db.sql(
        """
        SELECT
            du.project,
            DATE_FORMAT(dus.planned_date, '%%Y-%%m') AS ym,
            COUNT(*) AS units
        FROM
            `tabDevelopment Unit` du
            INNER JOIN `tabDevelopment Unit Stage` dus ON dus.parent = du.name
            INNER JOIN `tabDevelopment Stage` ds ON ds.name = dus.stage
        WHERE
            ds.stage_category = 'Delivery'
            AND dus.planned_date BETWEEN %(from_date)s AND %(to_date)s
            AND du.project IN %(project_names)s
        GROUP BY
            du.project, ym
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
        # Convert "2026-06" → month key "m_2026_06"
        mkey = "m_" + row.ym.replace("-", "_")
        demand_map[row.project][mkey] = int(row.units)

    return demand_map


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

def _calc_capacity_per_month(operations, ws_map, ws_by_type, holidays_map, downtime_map, months):
    """
    For each month, compute bottleneck capacity before and after downtime:

        available_mins(ws, month) =
            production_capacity × working_days × total_working_hours × 60

        theoretical = min(available_mins / time_in_mins)
        actual      = min((available_mins - downtime) / time_in_mins)
    """
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
        weekdays_in_month = _count_weekdays(mdate.year, mdate.month)

        ws_avail = {}
        ws_downtime = {}
        for ws_name, ws in ws_map.items():
            holidays_this_month = sum(
                1
                for h in holidays_map.get(ws.holiday_list or "", [])
                if h.year == mdate.year and h.month == mdate.month
            )
            effective_days = max(0, weekdays_in_month - holidays_this_month)
            daily_hours = flt(ws.total_working_hours) or 8.0
            ws_avail[ws_name] = (
                flt(ws.production_capacity or 1) * effective_days * daily_hours * 60.0
            )
            ws_downtime[ws_name] = downtime_map.get((ws_name, mkey), 0)

        type_avail = {}
        type_downtime = {}
        for ws_type, ws_list in ws_by_type.items():
            type_avail[ws_type] = sum(ws_avail.get(ws.name, 0) for ws in ws_list)
            type_downtime[ws_type] = sum(ws_downtime.get(ws.name, 0) for ws in ws_list)

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

        result["theoretical"][mkey] = int(min_theoretical) if min_theoretical is not None else 0
        result["actual"][mkey] = int(min_actual) if min_actual is not None else 0
        result["downtime_total"][mkey] = int(downtime_by_month.get(mkey, 0))

    return result


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


def _project_subtitle(proj):
    """Build the subtitle line shown under the project name."""
    parts = []
    if getattr(proj, "customer", None):
        parts.append(proj.customer)
    unit_count = int(proj.unit_count or 0)
    if unit_count:
        parts.append(f"{unit_count} units")
    return " · ".join(parts) if parts else ""
