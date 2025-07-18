import pandas as pd
import numpy as np
from pint import UnitRegistry
import geopandas as gpd
from zonepy import get_zoning_req

def check_fl_area(tidybuilding, tidyzoning, tidyparcel=None):
    """
    Checks whether the floor area of a given building complies with zoning constraints.

    Parameters:
    ----------
    tidybuilding : GeoDataFrame
        A GeoDataFrame containing information about a single building. 
        It must have at least one of the following:
        - 'gross_fl_area' column: Directly specifying the building's floor area.
    tidyzoning : GeoDataFrame
        A GeoDataFrame containing zoning constraints. It may have multiple rows,
        each representing a different zoning rule that applies to the given building.
    tidyparcel : Optional
    
    Returns:
    -------
    DataFrame
        A DataFrame with two columns:
        - 'zoning_id': The index of the corresponding row from `tidyzoning`.
        - 'allowed': A boolean value indicating whether the building's floor area 
          complies with the zoning regulations (True if compliant, False otherwise).
        - 'constraint_min_note': The constraint note for the minimum value.
        - 'constraint_max_note': The constraint note for the maximum value.
    
    How to use:
    check_fl_area_result = check_fl_area(tidybuilding_4_fam, tidyzoning, tidyparcel[tidyparcel['parcel_id'] == '10'])
    """
    ureg = UnitRegistry()
    results = []

    # Calculate the floor area of the building
    if len(tidybuilding['gross_fl_area']) == 1:
        fl_area = tidybuilding['gross_fl_area'].iloc[0]
    else:
        return pd.DataFrame(columns=['zoning_id', 'allowed', 'constraint_min_note', 'constraint_max_note']) # Return an empty DataFrame

    # Iterate through each row in tidyzoning
    for index, zoning_row in tidyzoning.iterrows():
        zoning_req = get_zoning_req(tidybuilding, zoning_row.to_frame().T, tidyparcel)  # ✅ Fix the issue of passing Series

        # Fix the string check here
        if isinstance(zoning_req, str) and zoning_req == "No zoning requirements recorded for this district":
            results.append({'zoning_id': index, 'allowed': True, 'constraint_min_note': None, 'constraint_max_note': None})
            continue
        # If zoning_req is empty, consider it allowed
        if zoning_req is None or zoning_req.empty:
            results.append({'zoning_id': index, 'allowed': True, 'constraint_min_note': None, 'constraint_max_note': None})
            continue
        # Check if zoning constraints include 'fl_area'
        if 'fl_area' in zoning_req['spec_type'].values:
            fl_area_row = zoning_req[zoning_req['spec_type'] == 'fl_area']
            min_fl_area = fl_area_row['min_value'].values[0]  # Extract min values
            max_fl_area = fl_area_row['max_value'].values[0]  # Extract max values
            min_select = fl_area_row['min_select'].values[0]  # Extract min select info
            max_select = fl_area_row['max_select'].values[0]  # Extract max select info
            constraint_min_note = fl_area_row['constraint_min_note'].values[0] # Extract min constraint note
            constraint_max_note = fl_area_row['constraint_max_note'].values[0] # Extract max constraint note
            
            # If min_select or max_select is 'OZFS Error', default to allowed
            if min_select == 'OZFS Error' or max_select == 'OZFS Error':
                results.append({'zoning_id': index, 'allowed': True, 'constraint_min_note': constraint_min_note, 'constraint_max_note': constraint_max_note})
                continue

            # Handle NaN values and list
            # Handle min_fl_area
            if not isinstance(min_fl_area, list):
                min_fl_area = [0] if min_fl_area is None or pd.isna(min_fl_area) or isinstance(min_fl_area, str) else [min_fl_area]
            else:
                # Filter out NaN and None values, ensuring at least one valid value
                min_fl_area = [v for v in min_fl_area if pd.notna(v) and v is not None and not isinstance(v, str)]
                if not min_fl_area:  # If all values are NaN or None, replace with default value
                    min_fl_area = [0]
            # Handle max_fl_area
            if not isinstance(max_fl_area, list):
                max_fl_area = [1000000] if max_fl_area is None or pd.isna(max_fl_area) or isinstance(max_fl_area, str) else [max_fl_area]
            else:
                # Filter out NaN and None values, ensuring at least one valid value
                max_fl_area = [v for v in max_fl_area if pd.notna(v) and v is not None and not isinstance(v, str)]
                if not max_fl_area:  # If all values are NaN or None, replace with default value
                    max_fl_area = [1000000]

            # Get the unit and convert
            unit_column = fl_area_row['unit'].values[0]  # Extract the unit of the specific row
            # Define the unit mapping
            unit_mapping = {
                "square feet": ureg('ft^2'),
                "square meters": ureg('m^2'),
                "acres": ureg('acre')
            }
            target_unit = unit_mapping.get(unit_column, ureg('ft^2'))  # Convert the unit of the specific row to a unit recognized by pint, default is ft^2 if no unit
            # Ensure min/max_fl_area has the correct unit 'ft^2'
            min_fl_area = [ureg.Quantity(v, target_unit).to('ft^2').magnitude for v in min_fl_area]
            max_fl_area = [ureg.Quantity(v, target_unit).to('ft^2').magnitude for v in max_fl_area]

            # Check min condition
            min_check_1 = min(min_fl_area) <= fl_area
            min_check_2 = max(min_fl_area) <= fl_area
            if min_select in ["either", None]:
                min_allowed = min_check_1 or min_check_2
            elif min_select == "unique":
                if min_check_1 and min_check_2:
                    min_allowed = True
                elif not min_check_1 and not min_check_2:
                    min_allowed = False
                else:
                    min_allowed = "MAYBE"
            
            # Check max condition
            max_check_1 = min(max_fl_area) >= fl_area
            max_check_2 = max(max_fl_area) >= fl_area
            if max_select in ["either", None]:
                max_allowed = max_check_1 or max_check_2
            elif max_select == "unique":
                if max_check_1 and max_check_2:
                    max_allowed = True
                elif not max_check_1 and not max_check_2:
                    max_allowed = False
                else:
                    max_allowed = "MAYBE"
            
            # Determine final allowed status
            if min_allowed == "MAYBE" or max_allowed == "MAYBE":
                allowed = "MAYBE"
            else:
                allowed = min_allowed and max_allowed
            
            results.append({'zoning_id': index, 'allowed': allowed, 'constraint_min_note': constraint_min_note, 'constraint_max_note': constraint_max_note})
        else:
            results.append({'zoning_id': index, 'allowed': True, 'constraint_min_note': None, 'constraint_max_note': None})  # If zoning has no constraints, default to True

    return pd.DataFrame(results)