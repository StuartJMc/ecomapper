import pandas as pd
import geopandas as gpd
import numpy as np
import functools as ft
from shapely.geometry import LineString, Point, Polygon
from helpers.feature_eng import (
    get_energy_consumption,
    get_ev_points,
    get_energy_decentral_production,
    get_average_income,
    get_rent_prices,
    get_address_data,
    get_sector_boundaries,
    get_statistical_sector_mapping,
    get_bimd_data,
    get_solar_data,
    get_sector_population,
    get_urban_atlas,
)
import yaml

# Load the existing YAML file
with open("../config.yaml", "r") as yaml_file:
    config = yaml.safe_load(yaml_file)


def update_feature_column_config(df):
    geometry_columns = [col for col in df.columns if df[col].dtype.name == "geometry"]
    config["Columns"]["geometry_columns"] = geometry_columns

    location_columns = [
        "sector_code",
        "postcode",
        "sector",
        "housenumber",
        "boxnumber",
        "id",
        "year",
        "status",
        "status_valid_from",
        "streetname",
        "lat",
        "lon",
        "lat_solar",
        "lon_solar",
        "address_id",
    ]
    config["Columns"]["location_columns"] = location_columns

    # taken mannually, may need to update
    solar_columns = [
        "building_type",
        "building_cat",
        "building_surface_area",
        "building_length",
        "solar_opportunity_area",
        "solar_opportunity_3d",
        "solar_irradiation",
        "total_solar_irradiation",
        "solar_id",
        "energy_production",
        "top_10_per_energy_prod_in_500m",
    ]
    config["Columns"]["solar_columns"] = solar_columns

    features = [
        col
        for col in df.columns
        if col not in geometry_columns and col not in location_columns
    ]
    config["Columns"]["features_columns"] = features

    info_columns = [col for col in features if col not in solar_columns]
    config["Columns"]["info_columns"] = info_columns

    # Write the updated data back to the YAML file
    with open("../config.yaml", "w") as yaml_file:
        yaml.dump(config, yaml_file)


def handle_missing_values(df):
    # fill missing solar columns which are objects with 'not_available'
    solar_object_columns = (
        df[config["Columns"]["solar_columns"]].select_dtypes(include=["object"]).columns
    )
    df[solar_object_columns] = (
        df[solar_object_columns].fillna("not_available").astype(str)
    )
    
    #drop rows where population is missing
    df = df.dropna(subset=["population"])

    # fill rest with unkown
    object_columns = df.select_dtypes(include=["object"]).columns
    df[object_columns] = df[object_columns].fillna("unknown").astype(str)

    # fill solar number columns with 0
    solar_number_columns = (
        df[config["Columns"]["solar_columns"]].select_dtypes(include=["number"]).columns
    )
    df[solar_number_columns] = df[solar_number_columns].fillna(0).astype(float)

    # fill number columns not in solar with mean of their streetname
    number_columns = df.select_dtypes(include=["number"]).columns
    number_columns = [col for col in number_columns if col not in solar_number_columns]
    df[number_columns] = df.groupby("streetname")[number_columns].transform(
        lambda x: x.fillna(x.mean())
    )

    # fill remainder of number columns with mean from their sector
    df[number_columns] = df.groupby("sector")[number_columns].transform(
        lambda x: x.fillna(x.mean())
    )

    # fill remainder of number columns with mean from their postcode
    df[number_columns] = df.groupby("postcode")[number_columns].transform(
        lambda x: x.fillna(x.mean())
    )

    # fill remainder of number columns with mean from their city
    df[number_columns] = df[number_columns].fillna(df[number_columns].mean())

    return df


def recursive_nearest_join(
    df_base, df_solar, join_attempts=3, max_distance=20, verbose=False
):
    joined_ids = []
    joined_solar_ids = []

    df_target = pd.DataFrame()
    for attempt in range(join_attempts):
        if attempt != 0:
            df_base_subset = df_base[~df_base.index.isin(joined_ids)]
            df_solar_subset = df_solar[~df_solar.solar_id.isin(joined_solar_ids)]
        else:
            df_base_subset = df_base.copy()
            df_solar_subset = df_solar.copy()
        # join with s_join nearest
        dfs = [df_base_subset, df_solar_subset]
        df_base_sjoin_nearest = ft.reduce(
            lambda left, right: gpd.sjoin_nearest(
                left,
                right,
                how="inner",
                max_distance=max_distance,
                distance_col="solar_to_address_distance",
            ),
            dfs,
        )

        # Take only the rows for the same solar panel id that has the shortest distance
        df_base_sjoin_nearest = df_base_sjoin_nearest.sort_values(
            "solar_to_address_distance"
        ).drop_duplicates(subset=["solar_id"], keep="first")
        joined_ids = joined_ids + df_base_sjoin_nearest.index.to_list()
        joined_solar_ids = joined_solar_ids + list(
            df_base_sjoin_nearest.solar_id.unique()
        )

        df_target = pd.concat([df_target, df_base_sjoin_nearest])

    if verbose:
        # find the % of unique solar panels within 20 meters out of the total non null ids
        unique_solar_panels = len(
            df_target[df_target["solar_to_address_distance"] <= max_distance]
            .groupby(["solar_id"])
            .count()
        )

        print(
            f"Number of unique solar panel ids before join: {df_solar.solar_id.nunique()}"
        )
        print(f"The number of rows joins {df_target.shape[0]}")
        print(
            f"Number of solar panels within {max_distance} meters: {len(df_target[df_target['solar_to_address_distance'] <= max_distance])}"
        )
        print(
            f"Number of unique solar Ids under {max_distance}m: {unique_solar_panels}, as a percentage of the solar data: {round(unique_solar_panels/df_solar.solar_id.nunique()*100,2)}%"
        )

    return df_target


def generate_energy_proximity(df_base, df_sol, buffer=500, top_percentile=0.1):
    df_base["address_id"] = df_base.index

    # take top 10% of solar buildings by energy production
    # trim down
    df_sol = df_sol.sort_values(by="energy_production", ascending=False).head(
        int(len(df_sol) * top_percentile)
    )
    df_sol = df_sol[["energy_production", "centroid"]].copy()

    # trim_down
    df = df_base[["address_id", "coordinates", "sector"]].copy()
    df["coordinates_meters"] = df["coordinates"].to_crs(epsg=3857)
    df = df.set_geometry("coordinates_meters")

    df_sol["centroid_meters"] = df_sol["centroid"].to_crs(epsg=3857)
    df_sol["radius_meters"] = df_sol["centroid_meters"].buffer(buffer)
    df_sol = df_sol.set_geometry("radius_meters")

    # join with solar dataa
    dfs = [df, df_sol]
    df_join = ft.reduce(lambda left, right: gpd.sjoin(left, right, how="left"), dfs)

    df_energy_proximity = df_join.groupby("address_id").agg(
        {"energy_production": "sum"}
    )

    df_energy_proximity.rename(
        columns={"energy_production": "top_10_per_energy_prod_in_500m"}, inplace=True
    )

    df_base = df_base.merge(df_energy_proximity, how="left", on="address_id")

    return df_base


def create_info_table():
    df_energy_consumption = get_energy_consumption()

    df_ev_points = get_ev_points()

    df_energy_dc_prod = get_energy_decentral_production()

    df_average_income = get_average_income()

    df_mapping_gent = get_statistical_sector_mapping()

    gdf_sector = get_sector_boundaries()

    gdf_address = get_address_data()

    df_solar = get_solar_data()

    df_index = get_bimd_data()

    df_population = get_sector_population()
    
    df_land = get_urban_atlas()

    # join at sector_code
    dfs = [gdf_sector, df_mapping_gent, df_index, df_population, df_average_income]
    gdf_base = ft.reduce(
        lambda left, right: pd.merge(left, right, on="sector_code", how="left"), dfs
    )
    gdf_base

    # perform a spatial join to map the addresses to the sector
    dfs = [gdf_base, gdf_address]
    df_base = ft.reduce(lambda left, right: gpd.sjoin(left, right), dfs)
    df_base.drop(columns=["index_right"], inplace=True)
    df_base

    # join on postcode
    dfs = [df_base, df_ev_points, df_energy_dc_prod]
    df_base = ft.reduce(
        lambda left, right: pd.merge(left, right, on="postcode", how="left"), dfs
    )
    df_base

    # perform a join on streetname
    dfs = [df_base, df_energy_consumption]
    df_base = ft.reduce(
        lambda left, right: pd.merge(
            left, right, left_on="streetname", right_on="street", how="left"
        ),
        dfs,
    )
    df_base
    
    #perform a spatial join to get land use
    df_base = df_base.set_geometry("coordinates")

    df_base= df_base.sjoin(df_land,how='left')
    df_base.drop(columns=['index_right'],inplace=True)

    # spatially join with solar building outlines
    # set geometry column to coordinates for join

    # set geometry column to coordinates for join
    df_base["coordinates_meters"] = df_base["coordinates"].to_crs(epsg=3857)
    df_base = df_base.set_geometry("coordinates_meters")

    df_solar["centroid_meters"] = df_solar["centroid"].to_crs(epsg=3857)
    df_solar = df_solar.set_geometry("centroid_meters")

    # join with solar data (reccurively joining nearest points within 200 meters)
    # column drop was done first as some columns were preventing the sjoin
    df_target = recursive_nearest_join(
        df_base, df_solar, join_attempts=5, max_distance=200, verbose=True
    )
    df_base = pd.concat(
        [df_base.loc[~df_base.index.isin(df_target.index)], df_target], sort=False
    )

    # create energy proximity column
    df_base = generate_energy_proximity(df_base, df_solar)

    # drop redundant columns
    df_base.drop(columns=["index_right", "coordinates_meters"], inplace=True)

    df_base = df_base.set_geometry("coordinates")

    # update config file
    update_feature_column_config(df_base)

    df_base = handle_missing_values(df_base)

    return df_base