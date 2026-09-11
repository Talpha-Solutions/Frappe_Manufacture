# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

"""Compatibility shim — prefer fitzgerald_kitchens.fitzgerald_kitchens.offline_engine.catalog."""

from fitzgerald_kitchens.fitzgerald_kitchens.offline_engine.catalog import (  # noqa: F401
	get_all_features,
	get_feature,
	is_feature_enabled,
	list_enabled_features,
)
