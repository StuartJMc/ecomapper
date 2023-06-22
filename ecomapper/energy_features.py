import pandas as pd
import geopandas as gpd
import numpy as np
import functools as ft
from shapely.geometry import LineString, Point, Polygon
import yaml

# Load the existing YAML file
with open("../config.yaml", "r") as yaml_file:
    config = yaml.safe_load(yaml_file)


def calculate_energy_split(df, column, other_residential_energy_ratio=5):
    residential = [
        "Continuous urban fabric (S.L. : > 80%)",
        "Discontinuous dense urban fabric (S.L. : 50% -  80%)",
        "Discontinuous medium density urban fabric (S.L. : 30% - 50%)",
        "Discontinuous low density urban fabric (S.L. : 10% - 30%)",
        "Discontinuous very low density urban fabric (S.L. : < 10%)",
        "Isolated structures",
    ]

    other_consumers = [
        "Industrial, commercial, public, military and private units",
        "Sports and leisure facilities",
        "Arable land (annual crops)",
        "Port areas",
        "Mineral extraction and dump sites",
        "Railways and associated land",
        "Construction sites",
    ]

    n_residential = df[df.item2012.isin(residential)].shape[0]
    n_other_consumers = df[df.item2012.isin(other_consumers)].shape[0]

    weighted_count = n_residential + n_other_consumers * other_residential_energy_ratio

    # mean because the total street consumption is joined to each address
    total_consumption = df[column].mean()

    if n_residential > 0 and n_other_consumers > 0:
        total_residential_consumption = total_consumption * (
            n_residential / weighted_count
        )
        total_other_consumption = total_consumption - total_residential_consumption
        residential_consumption_per_address = (
            total_residential_consumption / n_residential
        )
        other_consumption_per_address = total_other_consumption / n_other_consumers

    elif n_residential == 0 and n_other_consumers > 0:
        residential_consumption_per_address = 0
        other_consumption_per_address = total_consumption / n_other_consumers

    elif n_residential > 0 and n_other_consumers == 0:
        residential_consumption_per_address = total_consumption / n_residential
        other_consumption_per_address = 0

    else:
        residential_consumption_per_address = 0
        other_consumption_per_address = 0

    return {
        "residential_" + column[18:] + "_address": residential_consumption_per_address,
        "other_" + column[18:] + "_address": other_consumption_per_address,
    }

def group_energy_split(group, other_residential_energy_ratio=5):
    electricity_consumption = calculate_energy_split(
        group, "annual_energy_use_electricity_offtake", other_residential_energy_ratio
    )
    gas_consumption = calculate_energy_split(
        group, "annual_energy_use_natural_gas_offtake", other_residential_energy_ratio
    )

    combined = {**electricity_consumption, **gas_consumption}
    return pd.DataFrame(combined, index=[0])

def create_energy_income_ratio(
    df,
    gas_price=config["Params"]["gas_price"],
    electricity_price=config["Params"]["electricity_price"],
):
    grouped_df = df.groupby("streetname").apply(group_energy_split)
    grouped_df.reset_index(inplace=True)
    grouped_df.drop(columns="level_1", inplace=True)

    df_join = df.merge(grouped_df, how="left", on="streetname")

    # set other energy to null for residential areas
    df_join.loc[
        df_join.land_use_type == "residential", "other_natural_gas_offtake_address"
    ] = np.nan
    df_join.loc[
        df_join.land_use_type == "residential", "other_electricity_offtake_address"
    ] = np.nan

    # set residential energy to null for other areas
    df_join.loc[
        df_join.land_use_type == "other_consumers",
        "residential_natural_gas_offtake_address",
    ] = np.nan
    df_join.loc[
        df_join.land_use_type == "other_consumers",
        "residential_electricity_offtake_address",
    ] = np.nan

    # set nan uses to nan
    df_join.loc[
        df_join.land_use_type == np.nan, "residential_natural_gas_offtake_address"
    ] = np.nan
    df_join.loc[
        df_join.land_use_type == np.nan, "residential_electricity_offtake_address"
    ] = np.nan

    df_join["energy_cost_residential"] = (
        df_join.residential_natural_gas_offtake_address * gas_price
        + df_join.residential_electricity_offtake_address * electricity_price
    )
    df_join["energy_cost_residential_percent_income"] = df_join.apply(
        lambda x: x.energy_cost_residential / x.avg_net_tax_income
        if x.land_use_type == "residential"
        else np.nan,
        axis=1,
    )

    # set rows with energy percent greater than 80 to null
    df_join.loc[
        df_join.energy_cost_residential_percent_income > 0.8,
        "energy_cost_residential_percent_income",
    ] = np.nan

    return df_join

def calculate_solar_cost(df, cost_per_m2=config["Params"]["solar_panel_cost_per_m2"]):
    df["solar_cost"] = df.solar_opportunity_area * cost_per_m2

    return df

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

def calculate_green_energy(
    df, green_energy_ratio=config["Params"]["green_energy_ratio"]
):
    df_energy = (
        df[
            [
                "residential_electricity_offtake_address",
                "residential_natural_gas_offtake_address",
                "other_electricity_offtake_address",
                "other_natural_gas_offtake_address",
            ]
        ]
        .copy()
        .fillna(0)
    )

    df["all_energy"] = (
        df_energy.residential_electricity_offtake_address
        + df_energy.residential_natural_gas_offtake_address
        + df_energy.other_electricity_offtake_address
        + df_energy.other_natural_gas_offtake_address
    )
    df["green_energy"] = df.all_energy * green_energy_ratio
    df["fossil_energy"] = df.all_energy - df.green_energy

    return df
