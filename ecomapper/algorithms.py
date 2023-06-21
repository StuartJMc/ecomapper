"""Module for storing algorithms for defining energy communities."""
import pandas as pd
from sklearn.cluster import KMeans
import numpy as np


class CommunitySelect:
    """A callable class for defining energy communities."""

    def __init__(self, X):
        self.X = X

        self.criteria = None
        self.num_clusters = None

        self.X_selected = None

    def _select_participants(self):
        """Define the energy community based on column criteria.

        This method creates a mask based on the criteria and returns the subset of the DataFrame.
        """
        mask = pd.Series(True, index=self.X.index)

        for feature, (operation, value) in self.criteria.items():
            if operation == ">":
                mask = mask & (self.X[feature] > value)
            elif operation == ">=":
                mask = mask & (self.X[feature] >= value)
            elif operation == "<":
                mask = mask & (self.X[feature] < value)
            elif operation == "<=":
                mask = mask & (self.X[feature] <= value)
            elif operation == "==":
                mask = mask & (self.X[feature] == value)
            else:
                raise ValueError(f"Unsupported operation: {operation}")

        return self.X[mask].copy()

    def _spatial_cluster(self, X):
        """
        Perform K-means clustering on the latitude and longitude columns of a DataFrame.

        Args:
            df (pd.DataFrame): The input DataFrame.
            num_clusters (int): The number of clusters to create.

        Returns:
            pd.DataFrame: DataFrame with the latitude, longitude, and corresponding cluster labels.
        """
        # Extract latitude and longitude columns
        lat_lon = X[["lat", "lon"]].values

        # Perform K-means clustering
        kmeans = KMeans(n_clusters=self.num_clusters)
        labels = kmeans.fit_predict(lat_lon)

        # Create a new DataFrame with the latitude, longitude, and cluster labels
        clusters_df = X.copy()
        clusters_df["cluster"] = labels

        # calculate the centroid of each cluster and join to the dataframe
        centroids = kmeans.cluster_centers_
        centroids_df = pd.DataFrame(centroids, columns=["lat", "lon"]).reset_index()
        centroids_df.columns = ["cluster", "lat_centroid", "lon_centroid"]
        clusters_df = clusters_df.merge(centroids_df, on="cluster", how="left")

        return clusters_df

    def create(self, algorithm="spatial_cluster", criteria=None, num_clusters=20):
        """Create the energy community based off chosen algorithm.

        algorithm (str): The algorithm to use for creating the energy community.
        criteria (dict): The criteria to use for selecting participants (from which the algorithm operates).
        num_clusters (int): The number of clusters to create (for spatial clustering).

        Returns:
            gpd.GeoDataFrame: DataFrame with the selected participants and their assign cluster (community).

        """
        if criteria is not None:
            self.criteria = criteria
            self.X_selected = self._select_participants()

        if algorithm == "spatial_cluster":
            self.num_clusters = num_clusters
            self.X_selected = self._spatial_cluster(self.X_selected)

        return self.X_selected

    def get_cluster_summary(self):
        """Generates aggergated stats for each cluster.

        Returns:
            pd.DataFrame: summary dataframe
        """
        features = self.X.columns.to_list()
        num_features = self.X_selected[features].select_dtypes("number").columns
        # cat_features = self.X_selected[features].select_dtypes('object').columns

        agg_dict = {}
        for col in features:
            if col in num_features:
                agg_dict[col] = np.mean  # Use mean for numerical features

        # Perform groupby using the aggregation dictionary
        grouped = self.X_selected.groupby("cluster").agg(agg_dict)

        return grouped