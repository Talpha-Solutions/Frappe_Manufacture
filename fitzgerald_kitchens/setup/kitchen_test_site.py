# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

"""Backward-compatible aliases — use capacity_pipeline_test_data instead."""

from fitzgerald_kitchens.setup.capacity_pipeline_test_data import (
	insert_capacity_pipeline_test_data as seed_kitchen_test_data,
	purge_kitchen_local_capacity_pipeline_test_data,
	reseed_kitchen_local_capacity_pipeline_test_data,
	reset_kitchen_local_delivery_data as reset_kitchen_test_delivery_data,
	show_demand_and_free_capacity,
	verify_all_kitchen_local_capacity_pipeline,
	verify_capacity_pipeline_test_data,
	verify_pipeline_kpi,
)
