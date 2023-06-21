import pandas as pd
import geopandas as gpd
import numpy as np
import functools as ft
from shapely.geometry import LineString, Point, Polygon
import yaml


# Load the configuration file
with open("../config.yaml") as file:
    config = yaml.safe_load(file)


# Dataset 1
def get_energy_consumption(
    data_path=config["Paths"]["energy_consumption_path"],
    year=config["Params"]["year"],
    municipality=config["Params"]["municipality"],
):
    df = pd.read_csv(data_path, delimiter=";")

    df = df.rename(
        columns={
            "Verbruiksjaar": "year",
            "Hoofdgemeente": "municipality",
            "Energie": "consumption_type",
            "Richting": "energy_flow",
            "Straat": "street",
            "Aantal Toegangspunten": "number_access_points",
            "Benaderend verbruik (kWh)": "annual_energy_use",
        }
    )

    # translate headings
    df["consumption_type"] = df.consumption_type.replace(
        {"Elektriciteit": "electricity", "Aardgas": "natural_gas"}
    )
    df["energy_flow"] = df.energy_flow.replace(
        {"Afname": "offtake", "Injectie": "injection"}
    )

    # convert year to datetime
    df["year"] = pd.to_datetime(df["year"], format="%Y")

    # select only gent data
    df = df[df["municipality"] == municipality.upper()].reset_index()

    # fill na with 0 (assumption that na relates to no reading)
    df = df.fillna(0)

    # put street names in lower case
    df.street = df.street.str.lower()

    # Take just 2013 data
    df = df[df.year == year]

    # drop unessecary columns
    df = df.drop(columns=["Regio", "index"])

    # pivot so that energy types and flows are seperated
    df = df.pivot_table(
        index="street",
        columns=["consumption_type", "energy_flow"],
        values=["annual_energy_use", "number_access_points"],
    ).reset_index()

    # Reset column names
    df.columns = df.columns.map("_".join)

    df.rename(columns={"street__": "street"}, inplace=True)

    df.drop(
        columns=[
            "annual_energy_use_electricity_injection",
            "number_access_points_electricity_injection",
        ],
        inplace=True,
    )

    return df


# Dataset 2
def get_ev_points(
    data_path=config["Paths"]["ev_points_path"], zip_codes=config["Params"]["zip_codes"]
):
    df = pd.read_csv(data_path, delimiter=";")

    # Translate headings
    df = df.rename(
        columns={
            "Jaartal indienstname": "installation_year",
            "Postcode": "postcode",
            "Vermogen (kVA)": "installation_max_power",
            "Spanningsniveau aansluiting": "voltage_level",
        }
    )
    # Drop unessecary columns
    df = df.drop(
        columns=[
            "Postcode (hiërarchisch)",
            "Uniek_order_ID",
            "Postcode Numeriek",
        ]
    )
    # Add clearer values for voltage level
    df["voltage_level"] = df.voltage_level.replace(
        {"LS": "low_voltage", "MS": "medium_voltage"}
    )

    # convert year to datetime
    df["installation_year"] = pd.to_datetime(df["installation_year"], format="%Y")

    # convert postcode to string
    df["postcode"] = df["postcode"].astype("str")

    # Extract lat and lon from centroid
    df["lat"] = df["centroid"].str.split(",").str[0]
    df["lon"] = df["centroid"].str.split(",").str[1]
    df.drop(columns=["centroid"], inplace=True)

    ## Take only gent postcodes
    df = df[df["postcode"].isin(zip_codes)]

    ## Locations are the same for all rows in a postcode, so drop duplicates by aggregating installation power
    df = df.groupby(["postcode"]).agg({"installation_max_power": "sum"}).reset_index()

    return df


# Dataset 3
def get_energy_decentral_production(
    data_path=config["Paths"]["energy_decentral_production_path"],
    zip_codes=config["Params"]["zip_codes"],
):
    df = pd.read_csv(data_path, delimiter=";")

    # Translate headings
    df = df.rename(
        columns={
            "Jaartal indienstname": "installation_date",
            "Type technologie": "technology_type",
            "Vermogen (kVA)": "power_capacity",
            "Gemeente Nis Code": "municipality_code",
            "Spanningsniveau aansluiting": "voltage_level",
            "Postcode": "postcode",
        }
    )

    # Drop unessecary columns
    df = df.drop(
        columns=["Postcode (hiërarchisch)", "Uniek_order_ID", "municipality_code"]
    )

    # Add clearer values for voltage level and technology type
    df["voltage_level"] = df.voltage_level.replace(
        {"LS": "low_voltage", "MS": "medium_voltage"}
    )
    df["technology_type"] = df.technology_type.replace(
        {
            "Zonne-Energie (PV)": "solar",
            "Windenergie": "wind",
            "Andere": "others",
            "WKK Aardgas": "natural_gas",
            "Brandstofcel": "fuel_cell",
            "WKK Biomassa/Biogas": "Biomass/Biogas",
        }
    )
    # only take solar
    df = df[df.technology_type == "solar"]
    df.drop(columns=["technology_type"], inplace=True)

    # conert postcode to string
    df["postcode"] = df["postcode"].astype(str).str[0:4]

    # convert year to datetime
    df["installation_date"] = pd.to_datetime(df["installation_date"], format="%Y")

    # fill na with 0 (assumption that na relates to no reading)
    df["power_capacity"] = df.power_capacity.fillna(0)
    df["installation_date"] = df.installation_date.fillna(df.installation_date.max())
    df["voltage_level"] = df.voltage_level.fillna("unknown")

    ## filter down using postcode to only gent postcodes
    df = df[df.postcode.isin(zip_codes)]

    ## Locations are the same for all rows in a postcode, so drop duplicates by aggregating power capacity (only solar is included but will aggregate anyway in case more are added)
    df = df.groupby(["postcode"]).agg({"power_capacity": "sum"}).reset_index()

    return df



# Dataset 4
def get_average_income(
    data_path=config["Paths"]["average_income_path"], sector_code_prefix=config["Params"]["sector_id_prefix"]
):
    df = pd.read_csv(data_path, delimiter=";")

    
    df.columns=['sector','sector_code','total_net_taxable_income','interquartile_coeff_of_taxpayers','interquartile_asymmetry_of_taxpayers','avg_net_tax_income']
    
    #add sector_code_preffix to sector_code
    df['sector_code'] = sector_code_prefix + df['sector_code'].astype(str)
    
    #add a training '- to any sector_code that is 8 digits long
    df['sector_code'] = df['sector_code'].apply(lambda x: x + '-' if len(x) == 8 else x)
    
    #replace all x with np.nan
    df.replace('x', np.nan, inplace=True)
    
    #convert columns to float
    df[['total_net_taxable_income','interquartile_coeff_of_taxpayers','interquartile_asymmetry_of_taxpayers','avg_net_tax_income']] = df[['total_net_taxable_income','interquartile_coeff_of_taxpayers','interquartile_asymmetry_of_taxpayers','avg_net_tax_income']].copy().astype(float)

    df.drop(columns=['sector'], inplace=True)
    
    return df



# Dataset 5
def get_rent_prices(data_path=config["Paths"]["rent_prices_path"]):
    df = pd.read_csv(data_path, delimiter=",")

    # Drop unessecary columns
    df = df.drop(
        columns=["Unnamed: 0", "country", "region", "province", "district", "locality"]
    )

    #  dropna coords
    df = df.dropna(subset=["lat", "long"])

    # convert datetyprd
    df["id"] = df["id"].astype("str")
    df["price_main_value"] = df["price_main_value"].astype("float")
    df["postal_code"] = df["postal_code"].astype("str")

    gdf = gpd.GeoDataFrame(df)
    # Convert latitude and longitude columns to geometry column
    gdf["geometry"] = gpd.points_from_xy(gdf["long"], gdf["lat"])

    # set street to lower case
    df["street"] = df["street"].str.lower()

    # rename columns
    df.rename(columns={"postal_code": "postcode"}, inplace=True)

    return gdf


# Dataset 6
def get_statistical_sector_mapping(
    data_path=config["Paths"]["stat_sector_mapping_path"],
    municipality=config["Params"]["municipality"],
):
    df_mapping = pd.read_csv(data_path)

    # extract postcode
    df_mapping["PostCode"] = df_mapping.PostCode.astype(str).str[:4]

    # use only gent postcodes
    df_mapping = df_mapping[df_mapping.Municipality == municipality]

    # drop duplicates
    df_mapping = df_mapping.drop_duplicates(subset=["StatisticalSector"])

    # make it low
    df_mapping["sector"] = df_mapping.StatisticalSector.str.lower().copy()
    df_mapping.drop(columns=["StatisticalSector"], inplace=True)

    # Drop the constant columns
    unique_counts = df_mapping.nunique()

    # Identify columns with 0 or 1 unique value
    columns_to_drop = unique_counts[unique_counts <= 1].index
    df_mapping = df_mapping.drop(columns_to_drop, axis=1)

    # rename postcode column
    df_mapping.rename(
        columns={"PostCode": "postcode", "NIS9": "sector_code"}, inplace=True
    )

    return df_mapping


# Dataset 7
def get_sector_boundaries(
    data_path=config["Paths"]["sector_boundaries_path"],
    crs=config["Params"]["crs_sectors"],
    municipality=config["Params"]["municipality"],
):
    gdf = gpd.read_file(data_path)

    # define current crs
    gdf = gdf.set_crs(epsg=crs)

    # set crs wo WGS84
    gdf = gdf.to_crs(epsg=4326)

    # Select only gent
    gdf = gdf[gdf["tx_munty_descr_nl"] == municipality]

    # keep only select cols
    gdf = gdf.copy()[["cd_sector", "geometry"]]
    gdf.rename(columns={"cd_sector": "sector_code"}, inplace=True)

    return gdf


# Dataset 8
def get_address_data(
    data_path=config["Paths"]["address_path"], crs=config["Params"]["crs_address"]
):
    df_address = pd.read_parquet(data_path)

    # lowercase street names
    df_address["streetname"] = df_address["streetname_nl"].str.lower()

    # Create a GeoDataFrame from the DataFrame
    geometry = [Point(xy) for xy in zip(df_address["x"], df_address["y"])]
    gdf_address = gpd.GeoDataFrame(df_address, geometry=geometry, crs="EPSG:3812")
    gdf_address = gdf_address.to_crs("EPSG:4326")

    # store seperately so not lost in the join
    gdf_address["coordinates"] = gdf_address["geometry"]
    # extract lat/lon coordinates
    gdf_address["lat"] = gdf_address.geometry.y
    gdf_address["lon"] = gdf_address.geometry.x

    # I think these columns are redundant (for now)
    cols_to_drop = [
        "fid",
        "id",
        "fed_address_id",
        "best_objectid",
        "best_versionid",
        "best_id",
        "position",
        "status_valid_from",
        "status",
        "begin_life_span_version",
        "officially_assigned",
        "postal_info_objectid",
        "streetname_objectid",
        "streetname_nl",
        "streetname_versionid",
        "x",
        "y",
    ]

    gdf_address.drop(cols_to_drop, axis=1, inplace=True)

    gdf_address["address_id"] = gdf_address.index
    return gdf_address


# Dataset 9
def get_solar_data(
    data_path=config["Paths"]["solar_path"],
    municipality=config["Params"]["municipality"],
):
    df_solar = gpd.read_file(data_path)

    # rename columns
    df_solar = df_solar.rename(
        columns={
            "GRB_UIDN": "building_iden",
            "GRB_OIDN": "building_object_iden",
            "ENTITEIT": "building_type",
            "TYPE": "building_type_code",
            "LBLTYPE": "building_cat",
            "DATUM_GRB": "geo_creation_date",
            "DATUM_LID": "mapping_date",
            "OPPERVL": "building_surface_area",
            "LENGTE": "building_length",
            "STRAATNMID": "street_id",
            "STRAATNM": "street_name",
            "NISCODE": "municipality_code",
            "GEMEENTE": "municipality",
            "POSTCODE": "post_code",
            "HNRLABEL": "building_number",
            "SOL_OPP": "solar_opportunity_area",
            "SOL_OPP_3D": "solar_opportunity_3d",
            "SLOPE": "roof_slope",
            "ASPECT": "roof_aspect",
            "IRR_SqM": "solar_irradiation",
            "IRR_Tot": "total_solar_irradiation",
            "Type_Dak": "roof_type",
            "Opwek_E": "energy_production",
        }
    )

    # rename building types and categories
    df_solar["building_type"] = df_solar.building_type.replace(
        {
            "Gbg": "building on ground",
            "Gba": "building attachment",
            "Knw": "works of art",
        }
    )
    df_solar["building_cat"] = df_solar.building_cat.replace(
        {
            "hoofdgebouw": "central building",
            "bijgebouw": "annex",
            "afdak": "shed",
            "verdieping": "floor",
            "silo, opslagtank": "silo",
            "uitbreiding": "extension",
            "gebouw afgezoomd met virtuele gevels": "Building lined with virtual facades",
            "schoorsteen": "chimney",
            "watertoren": "water tower",
        }
    )
    df_solar["roof_type"] = df_solar.roof_type.replace(
        {"hellend": "pitched", "plat": "flat"}
    )

    # convert location indicators to string
    df_solar["building_iden"] = df_solar["building_iden"].astype("str")
    df_solar["building_object_iden"] = df_solar["building_object_iden"].astype("str")
    df_solar["building_type_code"] = df_solar["building_type_code"].astype("str")
    df_solar["street_id"] = df_solar["street_id"].astype("str")
    df_solar["post_code"] = df_solar["post_code"].astype("str")

    # convert dates to datetime
    df_solar["geo_creation_date"] = pd.to_datetime(
        df_solar["geo_creation_date"], format="%Y-%m-%d"
    )
    df_solar["mapping_date"] = pd.to_datetime(
        df_solar["mapping_date"], format="%Y-%m-%d"
    )

    # lowercase street names
    df_solar["street_name"] = df_solar["street_name"].str.lower()

    # Select only municipality
    df_solar = df_solar[df_solar["municipality"] == municipality].reset_index()

    # Drop unnecessary columns
    df_solar = df_solar.drop(
        columns=[
            "index",
            "municipality_code",
            "municipality",
            "post_code",
            "street_id",
            "building_iden",
            "building_object_iden",
            "building_type_code",
            "geo_creation_date",
            "mapping_date",
            "street_name",
            "building_number",
            "roof_slope",
            "roof_aspect",
            "roof_type",
        ]
    )

    # convert to WGS84
    df_solar = df_solar.to_crs(epsg=4326)

    # get centroid (after converting geometry to meters)
    df_solar["centroid"] = (
        df_solar["geometry"].to_crs(epsg=3857).centroid.to_crs(epsg=4326)
    )

    # rename geometry
    df_solar.rename(columns={"geometry": "geometry_building"}, inplace=True)

    # use index for a unique identifier
    df_solar["solar_id"] = df_solar.index

    # extract lat/lon coordinates
    df_solar["lat_solar"] = df_solar.centroid.y
    df_solar["lon_solar"] = df_solar.centroid.x

    return df_solar


# Dataset 10
def get_bimd_data(
    data_path=config["Paths"]["bimd_path"],
    sector_prefix=config["Params"]["sector_id_prefix"],
):
    df_index = pd.read_csv(data_path, delimiter=",")

    # rename sector code
    df_index = df_index.rename(columns={"CD_RES_SECTOR": "sector_code"})

    # get only sector codes that start with sector_prefix
    df_index = df_index[df_index["sector_code"].str.startswith(sector_prefix)]

    # drop unnecessary columns (due to not enough geographical variance)
    df_index = df_index.drop(
        columns=[
            "exp_score_crime_domain",
            "rank_crime_domain",
            "deciles_health_domain",
            "deciles_crime_domain",
        ]
    )

    return df_index

#Dataset 11
def get_sector_population(data_path=config['Paths']['stat_sector_populations']):
    df_ss = pd.read_excel(data_path)

    df_ss=df_ss.drop(columns=['TX_DESCR_SECTOR_FR','TX_DESCR_FR'])
    df_ss=df_ss.rename(columns={'CD_SECTOR': 'sector_code', 'TOTAL':'population', 
                                'TX_DESCR_NL': 'municipality'})
    df_ss=df_ss[['sector_code','municipality','population']]
    df_ss_ghent = df_ss[df_ss['municipality'].str.contains('GENT', case=False)]

    df_ss=df_ss.drop(columns=['municipality'])
    
    return df_ss

#Dataset 12
def get_urban_atlas(data_path=config['Paths']['urban_atlas_path']):
    df_land=gpd.read_file(data_path)
    
    #convert to WGS84
    df_land =df_land.to_crs('EPSG:4326')
    
    #lowercase all columns
    df_land.columns = map(str.lower, df_land.columns)
    
    df_land=df_land[['item2012','geometry']]
    
    return df_land