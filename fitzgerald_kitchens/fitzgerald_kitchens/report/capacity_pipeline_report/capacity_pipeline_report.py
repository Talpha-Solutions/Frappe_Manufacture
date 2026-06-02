# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

"""Capacity Pipeline Report

Shows monthly kitchen production demand per project alongside calculated
workstation capacity (derived from BOM operations + Workstation working hours /
holiday lists).  Demand uses Job Cards when present: completed cards use
actual total time (time logs by month, or total_time_in_mins); open cards use
scheduled time (time_required). Otherwise falls back to Development Unit
delivery planned dates.
Displays demand utilisation % and free capacity.

Query budget: 7 SQL statements — no per-row or per-project round-trips.
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
    _apply_default_bom_filter(filters)
    months = _build_month_list(filters)
    columns = _get_columns(months)
    data = _get_data(filters, months)
    return columns, data


@frappe.whitelist()
def get_default_bom(company=None):
    """Return the most recently created active submitted BOM for the company."""
    company = company or frappe.defaults.get_user_default("Company")
    if not company:
        return None

    return frappe.db.get_value(
        "BOM",
        {"company": company, "docstatus": 1, "is_active": 1},
        "name",
        order_by="creation desc",
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
    bom_list = _get_capacity_bom_list(filters, projects)

    operations = _q_bom_operations(bom_list) if bom_list else []
    bottleneck = _get_bottleneck_operation(operations)
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
        operations,
        ws_map,
        ws_by_type,
        holidays_map,
        downtime_map,
        months,
        uniform_capacity=bool(filters.get("bom")),
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

    data.extend(_build_summary_rows(months, demand_map, projects, capacity_result, filters))
    return data


def _get_capacity_bom_list(filters, projects):
    """Capacity is always driven by the selected BOM (defaults to latest active BOM)."""
    if filters.get("bom"):
        return [filters.bom]
    return []


def _build_summary_rows(months, demand_map, projects, capacity_result, filters=None):
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
    if filters and filters.get("bom"):
        cap_row["subtitle"] = _get_bom_capacity_subtitle(filters.bom)
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
    bom_cond = "AND p.fk_effective_bom = %(bom)s" if filters.get("bom") else ""

    rows = frappe.db.sql(
        f"""
        SELECT
            p.name,
            p.project_name,
            p.customer,
            p.fk_effective_bom,
            COUNT(du.name) AS unit_count
        FROM
            `tabProject` p
            LEFT JOIN `tabDevelopment Unit` du ON du.project = p.name
        WHERE
            p.docstatus < 2
            AND p.status NOT IN ('Cancelled', 'Completed')
            {company_cond}
            {project_cond}
            {bom_cond}
        GROUP BY
            p.name, p.project_name, p.customer, p.fk_effective_bom
        ORDER BY
            p.project_name
        """,
        {
            "company": filters.get("company"),
            "project": filters.get("project"),
            "bom": filters.get("bom"),
        },
        as_dict=True,
    )

    return rows


# ---------------------------------------------------------------------------
# Q2 – Demand per project per month
# ---------------------------------------------------------------------------

def _q_demand(project_names, from_date, to_date, bom_list, bottleneck):
    """Job Card actual time when available; else Delivery stage planned dates."""
    if not project_names:
        return {}

    if bom_list and bottleneck and _has_job_card_activity(
        project_names, bom_list, from_date, to_date
    ):
        return _q_job_card_demand(
            project_names, from_date, to_date, bom_list, bottleneck
        )

    return _q_delivery_demand(project_names, from_date, to_date)


def _has_job_card_activity(project_names, bom_list, from_date, to_date):
    """Return True when job cards exist for the filtered projects in the report period."""
    return bool(
        frappe.db.sql(
            """
            SELECT 1
            FROM `tabJob Card` jc
            WHERE
                jc.docstatus < 2
                AND jc.project IN %(project_names)s
                AND jc.bom_no IN %(bom_list)s
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
                "bom_list": bom_list,
                "from_datetime": f"{from_date} 00:00:00",
                "to_datetime": f"{to_date} 23:59:59",
                "from_date": from_date,
                "to_date": to_date,
            },
        )
    )


def _q_delivery_demand(project_names, from_date, to_date):
    """
    Count Development Units whose Delivery stage is planned in each month.

    Used when no Job Card production data exists for the filtered projects.
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
        mkey = "m_" + row.ym.replace("-", "_")
        demand_map[row.project][mkey] = int(row.units)

    return demand_map


def _get_bottleneck_operation(operations):
    """Return the BOM operation that limits capacity (longest time per unit)."""
    valid = [op for op in (operations or []) if flt(op.time_in_mins) > 0]
    if not valid:
        return None
    return max(valid, key=lambda op: flt(op.time_in_mins))


def _q_job_card_demand(project_names, from_date, to_date, bom_list, bottleneck):
    """
    Derive monthly demand (kitchen units) from Job Cards on the bottleneck operation.

    Per job card:
    - **Completed** → actual minutes (time logs by month, or total_time_in_mins)
    - **Not completed** → scheduled minutes (time_required) in the planned month

    Minutes are divided by the bottleneck operation time to estimate units produced.
    """
    if not project_names or not bom_list or not bottleneck:
        return {}

    bottleneck_time = flt(bottleneck.time_in_mins)
    if bottleneck_time <= 0:
        return {}

    ws_cond = ""
    params = {
        "project_names": project_names,
        "bom_list": bom_list,
        "from_datetime": f"{from_date} 00:00:00",
        "to_datetime": f"{to_date} 23:59:59",
        "from_date": from_date,
        "to_date": to_date,
    }

    if bottleneck.workstation:
        ws_cond = "AND jc.workstation = %(workstation)s"
        params["workstation"] = bottleneck.workstation
    elif bottleneck.workstation_type:
        ws_cond = "AND jc.workstation_type = %(workstation_type)s"
        params["workstation_type"] = bottleneck.workstation_type

    if bottleneck.operation:
        ws_cond += " AND jc.operation = %(operation)s"
        params["operation"] = bottleneck.operation

    # Completed job cards — actual time from time logs, grouped by log month.
    completed_log_rows = frappe.db.sql(
        f"""
        SELECT
            jc.project,
            DATE_FORMAT(jctl.from_time, '%%Y-%%m') AS ym,
            SUM(jctl.time_in_mins) AS mins
        FROM
            `tabJob Card` jc
            INNER JOIN `tabJob Card Time Log` jctl ON jctl.parent = jc.name
        WHERE
            jc.docstatus < 2
            AND jc.status = 'Completed'
            AND jc.project IN %(project_names)s
            AND jc.bom_no IN %(bom_list)s
            AND jctl.from_time >= %(from_datetime)s
            AND jctl.from_time <= %(to_datetime)s
            {ws_cond}
        GROUP BY
            jc.project, ym
        """,
        params,
        as_dict=True,
    )

    # Completed job cards without time logs — actual total on completion month.
    completed_total_rows = frappe.db.sql(
        f"""
        SELECT
            jc.project,
            DATE_FORMAT(COALESCE(jc.actual_end_date, jc.posting_date), '%%Y-%%m') AS ym,
            SUM(jc.total_time_in_mins) AS mins
        FROM
            `tabJob Card` jc
        WHERE
            jc.docstatus < 2
            AND jc.status = 'Completed'
            AND jc.project IN %(project_names)s
            AND jc.bom_no IN %(bom_list)s
            AND COALESCE(jc.actual_end_date, jc.posting_date) >= %(from_datetime)s
            AND COALESCE(jc.actual_end_date, jc.posting_date) <= %(to_datetime)s
            AND IFNULL(jc.total_time_in_mins, 0) > 0
            AND NOT EXISTS (
                SELECT 1
                FROM `tabJob Card Time Log` jctl
                WHERE jctl.parent = jc.name
            )
            {ws_cond}
        GROUP BY
            jc.project, ym
        """,
        params,
        as_dict=True,
    )

    # Open / in-progress job cards — scheduled time in the planned month.
    scheduled_rows = frappe.db.sql(
        f"""
        SELECT
            jc.project,
            DATE_FORMAT(COALESCE(jc.expected_start_date, jc.posting_date), '%%Y-%%m') AS ym,
            SUM(
                CASE
                    WHEN IFNULL(jc.time_required, 0) > 0 THEN jc.time_required
                    ELSE IFNULL(jc.for_quantity, 0) * %(bottleneck_time)s
                END
            ) AS mins
        FROM
            `tabJob Card` jc
        WHERE
            jc.docstatus < 2
            AND jc.status NOT IN ('Completed', 'Cancelled')
            AND jc.project IN %(project_names)s
            AND jc.bom_no IN %(bom_list)s
            AND COALESCE(jc.expected_start_date, jc.posting_date) >= %(from_date)s
            AND COALESCE(jc.expected_start_date, jc.posting_date) <= %(to_date)s
            {ws_cond}
        GROUP BY
            jc.project, ym
        """,
        {**params, "bottleneck_time": bottleneck_time},
        as_dict=True,
    )

    mins_map = defaultdict(lambda: defaultdict(float))
    for row in completed_log_rows + completed_total_rows + scheduled_rows:
        if not row.project or not row.ym:
            continue
        mkey = "m_" + row.ym.replace("-", "_")
        mins_map[row.project][mkey] += flt(row.mins)

    demand_map = defaultdict(dict)
    for project, month_mins in mins_map.items():
        for mkey, mins in month_mins.items():
            demand_map[project][mkey] = int(mins / bottleneck_time)

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

def _calc_capacity_per_month(
    operations, ws_map, ws_by_type, holidays_map, downtime_map, months, uniform_capacity=False
):
    """
    Compute bottleneck capacity before and after downtime.

    When uniform_capacity is True (BOM selected), theoretical capacity is the same
    every month — derived from the selected BOM operations and a reference working
    month. Actual capacity only varies with monthly downtime on those workstations.
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

    if uniform_capacity and months:
        ref_mdate = months[0][2]
        base_ws_avail = _calc_workstation_availability(ws_map, ref_mdate, holidays_map)
        base_type_avail = _aggregate_type_availability(base_ws_avail, ws_by_type)
        base_theoretical, _ = _calc_bottleneck_capacity(
            operations, base_ws_avail, base_type_avail
        )

        for mkey, _mlabel, _mdate in months:
            ws_downtime = {
                ws_name: downtime_map.get((ws_name, mkey), 0) for ws_name in ws_map
            }
            type_downtime = _aggregate_type_downtime(ws_downtime, ws_by_type)
            _, actual = _calc_bottleneck_capacity(
                operations,
                base_ws_avail,
                base_type_avail,
                ws_downtime,
                type_downtime,
            )
            result["theoretical"][mkey] = base_theoretical
            result["actual"][mkey] = actual
            result["downtime_total"][mkey] = int(downtime_by_month.get(mkey, 0))

        return result

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
