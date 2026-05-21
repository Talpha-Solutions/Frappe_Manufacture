STANDARD_DEVELOPMENT_STAGES = [
	{
		"stage_name": "Spec Agreed",
		"sequence": 10,
		"default_progress_percentage": 10,
		"evidence_required": "No",
		"customer_visible": 1,
		"stage_category": "Commercial",
	},
	{
		"stage_name": "Room Surveyed",
		"sequence": 20,
		"default_progress_percentage": 20,
		"evidence_required": "Optional",
		"customer_visible": 1,
		"stage_category": "Survey",
	},
	{
		"stage_name": "Kitchen Designed",
		"sequence": 30,
		"default_progress_percentage": 30,
		"evidence_required": "No",
		"customer_visible": 1,
		"stage_category": "Design",
	},
	{
		"stage_name": "Kitchen Manufactured",
		"sequence": 40,
		"default_progress_percentage": 50,
		"evidence_required": "No",
		"customer_visible": 1,
		"stage_category": "Manufacturing",
	},
	{
		"stage_name": "Kitchen Assembled",
		"sequence": 50,
		"default_progress_percentage": 60,
		"evidence_required": "No",
		"customer_visible": 1,
		"stage_category": "Manufacturing",
	},
	{
		"stage_name": "Kitchen Delivered",
		"sequence": 60,
		"default_progress_percentage": 75,
		"evidence_required": "Yes",
		"customer_visible": 1,
		"stage_category": "Delivery",
	},
	{
		"stage_name": "Kitchen Fitted",
		"sequence": 70,
		"default_progress_percentage": 90,
		"evidence_required": "Yes",
		"customer_visible": 1,
		"stage_category": "Installation",
	},
	{
		"stage_name": "Kitchen Handed Over",
		"sequence": 80,
		"default_progress_percentage": 100,
		"evidence_required": "Yes",
		"customer_visible": 1,
		"stage_category": "Handover",
	},
	{
		"stage_name": "Kitchen Paid For",
		"sequence": 90,
		"default_progress_percentage": 100,
		"evidence_required": "No",
		"customer_visible": 0,
		"stage_category": "Finance",
	},
]

STANDARD_STAGE_NAMES = {stage["stage_name"] for stage in STANDARD_DEVELOPMENT_STAGES}

STANDARD_STAGES_BY_NAME = {stage["stage_name"]: stage for stage in STANDARD_DEVELOPMENT_STAGES}


def normalize_evidence_required(value):
	if value in ("No", "Optional", "Yes"):
		return value
	if value in (1, "1", 1.0, "1.0", True):
		return "Yes"
	return "No"


def get_default_unit_stage_rows():
	"""Default rows for Development Unit → Stages child table."""
	return [
		{
			"stage": stage["stage_name"],
			"sequence": stage["sequence"],
			"progress_percentage": stage["default_progress_percentage"],
			"evidence_required": stage["evidence_required"],
			"customer_visible": stage["customer_visible"],
			"status": "Pending",
		}
		for stage in STANDARD_DEVELOPMENT_STAGES
	]
