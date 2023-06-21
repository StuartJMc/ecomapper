"""Script to create an interactive dashboard for the MVP"""
# Things to add
# Limit on number in cluster
# summary stats in tooltip
# mapping of clusters to solar locations
# filter for top n locations for each cluster or for whole
# Add filtering off map or table?
# filtering for residential status
# add control for dinstance from centroid cluster
# add calculated to table

import numpy as np  # np mean, np random
import pandas as pd  # read csv, df manipulation
import plotly.graph_objects as go  # interactive charts
import streamlit as st  # 🎈 data web app development
import geopandas as gpd
import plotly.express as px
from shapely.geometry import Point
from algorithms import CommunitySelect
import yaml

st.set_page_config(
    page_title="City of Gent - MVP Community Creator",
    page_icon="⚡",
    layout="wide",
)

# Load the configuration file
with open("phase-3/config.yaml") as file:
    config = yaml.safe_load(file)


# Set DataLoad Function
@st.cache_data
def get_data() -> pd.DataFrame:
    """Load selected features and geometry columns."""
    columns = (
        config["Columns"]["selected_columns"]
        + config["Columns"]["geometry_columns"]
        + ["lat", "lon"]
    )
    return gpd.read_parquet(config["Dashboard-Params"]["feature_table_path"])[columns]


@st.cache_data
def get_solar_data() -> pd.DataFrame:
    """Load solar data

    Returns:
        GeoDataFrame: Solar data
    """
    df = gpd.read_parquet(config["Dashboard-Params"]["solar_table_path"])  # [columns]
    return df


def map_scatter_plot(df, column="cluster"):
    """Plot the clusters on a map

    Args:
        df (gpd.GeoDataFrame): DataFrame containing clusters and coordinates
        column (str, optional): Name of column distinguishing the clusters. Defaults to "cluster".

    Returns:
        Plotly figure of clusters on a map
    """
    fig = go.Figure()
    # Add scattermapbox trace
    fig.add_trace(
        go.Scattermapbox(
            lat=df["lat"],
            lon=df["lon"],
            mode="markers",
            marker=dict(
                size=8,
                opacity=0.5,
                color=df[column],
                colorscale="viridis",
                showscale=False,
            ),
            customdata=df[column],
            hovertemplate="<b>Latitude</b>: %{lat}<br>"
            "<b>Longitude</b>: %{lon}<br>"
            "<b>Cluster</b>: %{customdata}<extra></extra>",
        )
    )
    # Update map layout
    fig.update_layout(
        height=800,
        width=900,
        mapbox=dict(style="carto-positron", zoom=10, center=dict(lat=51.05, lon=3.73)),
    )

    return fig


def get_top_n(data, column, n):
    """Get top n rows of a dataframe

    Args:
        df (gpd.GeoDataFrame): DataFrame contain information
        column (str): Column to plot
        n (int): Top n rows to include

    Returns:
        top n rows of a dataframe
    """
    sorted_data = data.sort_values(column, ascending=False)
    top_data = sorted_data.iloc[:n]
    return top_data


def top_n_map_scatter_plot(df, column, n, fig):
    """Plot the top n solar sites

    Args:
        df (gpd.GeoDataFrame): DataFrame contain information on solar sites
        column (str): Column to plot
        n (int): Top n rows to include
        fig (plotly fig): Plotly fig to add atrace

    Returns:
        Plotly fig with additional trace
    """
    # select top n
    df_top = get_top_n(df, column, n)

    fig.add_trace(
        go.Scattermapbox(
            lat=df_top["lat_solar"],
            lon=df_top["lon_solar"],
            mode="markers",
            marker=dict(size=5, color="black", opacity=0.7),
            text=df_top[column],
        )
    )
    return fig


def get_possible_sites(df, df_solar, radius):
    """Selects only solar sites within a given radius of a community centroid

    Args:
        df (gpd.GeoDataFrame): Main feature table with the clusters and centroids
        df_solar (gpd.GeoDataFrame): Data frame of solar potential sites
        radius (int): Selection radius from cluster centroid

    Returns:
        df_solar reduced to sites within the radius of a cluster centroid
    """
    # get centroid mapping
    centroids_df = df[["cluster", "lat_centroid", "lon_centroid"]].drop_duplicates()

    # Create a GeoDataFrame from the DataFrame
    geometry = [
        Point(xy)
        for xy in zip(centroids_df["lon_centroid"], centroids_df["lat_centroid"])
    ]
    centroids_df = gpd.GeoDataFrame(centroids_df, geometry=geometry, crs="EPSG:4326")
    centroids_df = centroids_df.to_crs(epsg=3857)
    # convert to buffer
    centroids_df["geometry"] = centroids_df.buffer(radius)

    # convert solar to meters
    df_solar["centroid_meters"] = df_solar["centroid"].to_crs(epsg=3857)
    df_solar = df_solar.set_geometry("centroid_meters")

    df_solar_reduced = centroids_df.sjoin(df_solar, how="inner")

    return df_solar_reduced


def main():
    # get data
    df = get_data()
    df_solar = get_solar_data()

    # dashboard title
    st.title("City of Gent - MVP Dashboard")

    # Create a sidebar banner
    st.sidebar.markdown("# Filter")
    st.sidebar.markdown("## Cluster Selection Criteria")
    # filter for number of clusters
    cluster_filter = st.sidebar.slider(
        "Number of Communities", 2, 40, 20, key="cluster_filter"
    )

    # filter for number of solar sites to display
    solar_top_n = st.sidebar.slider(
        "View Top N Solar locations near Communities", 1, 5000, 200
    )

    st.sidebar.markdown("---")
    st.sidebar.markdown("## Community Selection Criteria")

    # - features
    # - avg_net_tax_income
    # - energy_production (can't be used for the usecase)
    # - building_cat (need to build a way to handle object type)
    # - building_length
    # - solar_to_address_distance (need to handle nulls better)
    # - annual_energy_use_natural_gas_offtake
    # - BIMD2011_Score
    # - top_10_per_energy_prod_in_500m
    # - power_capacity

    # define these manually for now
    features = [
        "avg_net_tax_income",
        "building_length",
        "annual_energy_use_natural_gas_offtake",
        "BIMD2011_score",
        "top_10_per_energy_prod_in_500m",
        "power_capacity",
    ]
    operations = [">", "<", "==", "!=", "<=", ">="]
    criteria = {}
    # for each feature create a filter using a slider
    for feature in features:
        # Solar sites Filter
        value_filter = st.sidebar.slider(
            f"Value of {feature}",
            int(df[feature].min()),
            int(df[feature].quantile(0.9)),
            value=int(df[feature].quantile(0.5)),
            key=f"val_filter{feature}",
        )
        operation_filter = st.sidebar.selectbox(
            "Operation", operations, key=f"op_filter{feature}", index=5
        )
        st.sidebar.markdown("---")  # Add a horizontal line
        # update criteria dictionary for filtering
        criteria[feature] = (str(operation_filter), float(value_filter))

    # Create the clusters based on the criteria and a spatial clustering algorithm
    # output is a dataframe of the selected participants and what community they belong in
    community = CommunitySelect(df)
    df_selected = community.create(criteria=criteria, num_clusters=cluster_filter)

    # reduce df_solar so it includes only the solar sites within x meters from the selected communities
    df_solar = get_possible_sites(df_selected, df_solar, 500)

    # create two columns for charts
    fig_col1, fig_col2 = st.columns([3, 2])

    with fig_col1:
        # plot clusters
        fig1 = map_scatter_plot(df_selected)
        # add top percent solar
        fig1 = top_n_map_scatter_plot(df_solar, "energy_production", solar_top_n, fig1)
        st.markdown(f"### Plot of Communities")
        st.write(fig1)

    with fig_col2:
        st.markdown(f"### Summary of Communities")
        # create summarry table
        df_summary = community.get_cluster_summary()
        st.dataframe(df_summary, height=800)


if __name__ == "__main__":
    main()