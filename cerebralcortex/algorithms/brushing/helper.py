from cerebralcortex.core.datatypes.datastream import DataStream
from cerebralcortex.core.metadata_manager.stream.metadata import Metadata
from datetime import datetime, timedelta

from cerebralcortex.core.metadata_manager.stream.metadata import Metadata, DataDescriptor, ModuleMetadata
from cerebralcortex.core.util.spark_helper import get_or_create_sc
import re
import sys
from typing import List
import numpy as np
import os
import pathlib
import unittest
import warnings

from cerebralcortex import Kernel
from cerebralcortex.test_suite.test_object_storage import TestObjectStorage
from cerebralcortex.test_suite.test_sql_storage import SqlStorageTest
from cerebralcortex.test_suite.test_stream import DataStreamTest
from functools import reduce
import math
import pickle
import pandas as pd
from datetime import timedelta
from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql.functions import udf
from pyspark.sql.types import *
# from pyspark.sql.functions import pandas_udf,PandasUDFType
from operator import attrgetter
from pyspark.sql.types import StructType
from pyspark.sql.functions import pandas_udf, PandasUDFType
from pyspark.sql.window import Window



def get_orientation_data(ds, wrist, ori=1, is_new_device=False,
                         accelerometer_x="accelerometer_x",accelerometer_y="accelerometer_y",accelerometer_z="accelerometer_z",
                         gyroscope_x="gyroscope_x",gyroscope_y="gyroscope_y",gyroscope_z="gyroscope_z"):
    left_ori = {"old": {0: [1, 1, 1], 1: [1, 1, 1], 2: [-1, -1, 1], 3: [-1, 1, 1], 4: [1, -1, 1]},
                "new": {0: [-1, 1, 1], 1: [-1, 1, 1], 2: [1, -1, 1], 3: [1, 1, 1], 4: [-1, -1, 1]}}
    right_ori = {"old": {0: [1, -1, 1], 1: [1, -1, 1], 2: [-1, 1, 1], 3: [-1, -1, 1], 4: [1, 1, 1]},
                 "new": {0: [1, 1, 1], 1: [1, 1, 1], 2: [-1, -1, 1], 3: [-1, 1, 1], 4: [1, -1, 1]}}
    if is_new_device:
        left_fac = left_ori.get("new").get(ori)
        right_fac = right_ori.get("new").get(ori)

    else:
        left_fac = left_ori.get("old").get(ori)
        right_fac = right_ori.get("old").get(ori)

    if wrist == "left":
        fac = left_fac
    elif wrist == "right":
        fac = right_fac
    else:
        raise Exception("wrist can only be left or right.")

    data = ds.withColumn(gyroscope_x, ds[gyroscope_x] * fac[0]) \
        .withColumn(gyroscope_y, ds[gyroscope_y] * fac[1]) \
        .withColumn(gyroscope_z, ds[gyroscope_z] * fac[2])\
        .withColumn(accelerometer_x, ds[accelerometer_x] * fac[0]) \
        .withColumn(accelerometer_y, ds[accelerometer_y] * fac[1]) \
        .withColumn(accelerometer_z, ds[accelerometer_z] * fac[2])

    return data


def get_candidates(ds, uper_limit:float=0.1, lower_limit:float=0.1, threshold:float=0.5):
    window = Window.partitionBy(["user", "version"]).rowsBetween(-3, 3).orderBy("timestamp")
    window2 = Window.orderBy("timestamp")

    df1 = ds.withColumn("candidate", F.when(F.col("accelerometer_y")>uper_limit, F.lit(1)).otherwise(F.lit(0)))

    df = df1.withColumn("candidate",
                         F.when((F.avg(df1.candidate).over(window)) >= 0.5, F.lit(1))
                         .otherwise(F.lit(0)))

    df2 = df.withColumn(
        "userChange",
        (F.col("user") != F.lag("user").over(window2)).cast("int")
    ) \
        .withColumn(
        "candidateChange",
        (F.col("candidate") != F.lag("candidate").over(window2)).cast("int")
    ) \
        .fillna(
        0,
        subset=["userChange", "candidateChange"]
    ) \
        .withColumn(
        "indicator",
        (~((F.col("userChange") == 0) & (F.col("candidateChange") == 0))).cast("int")
    ) \
        .withColumn(
        "group",
        F.sum(F.col("indicator")).over(window2.rangeBetween(Window.unboundedPreceding, 0))
    ).drop("userChange").drop("candidateChange").drop("indicator")

    # df3=df2.groupBy("user", "group") \
    #     .agg(
    #     F.min("timestamp").alias("start_time"),
    #     F.max("timestamp").alias("end_time"),
    #     F.min("candidate").alias("candidate")
    # ) \
    #     .drop("group")

    return df2

def get_max_features(ds):
    features_schema = StructType([
        StructField("timestamp", TimestampType()),
        StructField("localtime", TimestampType()),
        StructField("user", StringType()),
        StructField("version", IntegerType()),
        StructField("start_time", TimestampType()),
        StructField("end_time", TimestampType()),
        StructField("max_accl_mean", FloatType()),
        StructField("max_accl_median", FloatType()),
        StructField("max_accl_skew", FloatType()),
        StructField("max_accl_kurt", FloatType()),
        StructField("max_accl_power", FloatType()),
        StructField("max_accl_zero_cross_rate", FloatType()),
        StructField("max_accl_fft_centroid", FloatType()),
        StructField("max_accl_fft_spread", FloatType()),
        StructField("max_accl_spectral_entropy", FloatType()),
        StructField("max_accl_spectral_entropy_old", FloatType()),
        StructField("max_accl_fft_flux", FloatType()),
        StructField("max_accl_spectral_folloff", FloatType())
    ])
    @pandas_udf(features_schema, PandasUDFType.GROUPED_MAP)
    def get_max_vals_features(df):
        vals = []
        vals.append(df['timestamp'].iloc[0])
        vals.append(df['localtime'].iloc[0])
        vals.append(df['user'].iloc[0])
        vals.append(df['version'].iloc[0])
        vals.append(df['timestamp'].iloc[0])
        vals.append(df['timestamp'].iloc[-1])

        vals.append(max(df["accelerometer_x_mean"],df["accelerometer_y_mean"],df["accelerometer_z_mean"]))
        vals.append(max(df["accelerometer_x_median"], df["accelerometer_y_median"], df["accelerometer_z_median"]))
        vals.append(max(df["accelerometer_x_stddev"], df["accelerometer_y_stddev"], df["accelerometer_z_stddev"]))
        vals.append(max(df["accelerometer_x_skew"], df["accelerometer_y_skew"], df["accelerometer_z_skew"]))
        vals.append(max(df["accelerometer_x_kurt"], df["accelerometer_y_kurt"], df["accelerometer_z_kurt"]))
        vals.append(max(df["accelerometer_x_power"], df["accelerometer_y_power"], df["accelerometer_z_power"]))
        vals.append(max(df["accelerometer_x_zero_cross_rate"], df["accelerometer_y_zero_cross_rate"], df["accelerometer_z_zero_cross_rate"]))
        vals.append(max(df["accelerometer_x_fft_centroid"], df["accelerometer_y_fft_centroid"], df["accelerometer_z_fft_centroid"]))
        vals.append(max(df["accelerometer_x_fft_spread"], df["accelerometer_y_fft_spread"], df["accelerometer_z_fft_spread"]))
        vals.append(max(df["accelerometer_x_spectral_entropy"], df["accelerometer_y_spectral_entropy"], df["accelerometer_z_spectral_entropy"]))
        vals.append(max(df["accelerometer_x_spectral_entropy_old"], df["accelerometer_y_spectral_entropy_old"], df["accelerometer_z_spectral_entropy_old"]))
        vals.append(max(df["accelerometer_x_fft_flux"], df["accelerometer_y_fft_flux"], df["accelerometer_z_fft_flux"]))
        vals.append(max(df["accelerometer_x_spectral_folloff"], df["accelerometer_y_spectral_folloff"], df["accelerometer_z_spectral_folloff"]))

        results = pd.DataFrame([vals],
                     columns=["timestamp",  "localtime", "user", "version", "start_time", "end_time", "max_accl_mean", "max_accl_median", "max_accl_skew", "max_accl_kurt", "max_accl_power", "max_accl_zero_cross_rate", "max_accl_fft_centroid", "max_accl_fft_spread", "max_accl_spectral_entropy","max_accl_spectral_entropy_old",  "max_accl_fft_flux",  "max_accl_spectral_folloff"])

        return results

    # return ds.withColumn("max_accl_mean",
    #                      F.greatest(ds.accelerometer_x_mean, ds.accelerometer_y_mean,
    #                                 ds.accelerometer_z_mean)) \
    #     .withColumn("max_accl_median",
    #                 F.greatest(ds.accelerometer_x_median, ds.accelerometer_y_median,
    #                            ds.accelerometer_z_median)) \
    #     .withColumn("max_accl_stddev",
    #                 F.greatest(ds.accelerometer_x_stddev, ds.accelerometer_y_stddev,
    #                            ds.accelerometer_z_stddev)) \
    #     .withColumn("max_accl_skew", F.greatest(ds.accelerometer_x_skew, ds.accelerometer_y_skew,
    #                                             ds.accelerometer_z_skew)) \
    #     .withColumn("max_accl_kurt", F.greatest(ds.accelerometer_x_kurt, ds.accelerometer_y_kurt,
    #                                             ds.accelerometer_z_kurt)) \
    #     .withColumn("max_accl_power", F.greatest(ds.accelerometer_x_power, ds.accelerometer_y_power,
    #                                              ds.accelerometer_z_power)) \
    #     .withColumn("max_accl_zero_cross_rate",
    #                 F.greatest(ds.accelerometer_x_zero_cross_rate, ds.accelerometer_y_zero_cross_rate,
    #                            ds.accelerometer_z_zero_cross_rate)) \
    #     .withColumn("max_accl_fft_centroid",
    #                 F.greatest(ds.accelerometer_x_fft_centroid, ds.accelerometer_y_fft_centroid,
    #                            ds.accelerometer_z_fft_centroid)) \
    #     .withColumn("max_accl_fft_spread",
    #                 F.greatest(ds.accelerometer_x_fft_spread, ds.accelerometer_y_fft_spread,
    #                            ds.accelerometer_z_fft_spread)) \
    #     .withColumn("max_accl_spectral_entropy", F.greatest(ds.accelerometer_x_spectral_entropy,
    #                                                         ds.accelerometer_y_spectral_entropy,
    #                                                         ds.accelerometer_z_spectral_entropy)) \
    #     .withColumn("max_accl_spectral_entropy_old", F.greatest(ds.accelerometer_x_spectral_entropy_old,
    #                                                             ds.accelerometer_y_spectral_entropy_old,
    #                                                             ds.accelerometer_z_spectral_entropy_old)) \
    #     .withColumn("max_accl_fft_flux",
    #                 F.greatest(ds.accelerometer_x_fft_flux, ds.accelerometer_y_fft_flux,
    #                            ds.accelerometer_z_fft_flux)) \
    #     .withColumn("max_accl_spectral_folloff", F.greatest(ds.accelerometer_x_spectral_folloff,
    #                                                     ds.accelerometer_y_spectral_folloff,
    #                                                     ds.accelerometer_z_spectral_folloff))


def reorder_columns(ds):
    feature_names = ['accelerometer_x','accelerometer_y', 'accelerometer_z', 'max_accl', 'gyroscope_y', 'gyroscope_x', 'gyroscope_z', 'roll', 'pitch', 'yaw']
    sensor_names = ['mean', 'median', 'stddev', 'skew', 'kurt', 'power', 'zero_cross_rate', "fft_centroid", 'fft_spread', 'spectral_entropy', 'spectral_entropy_old', 'fft_flux', 'spectral_folloff']
    extra_features = ["ax_ay_corr", 'ax_az_corr', 'ay_az_corr', 'gx_gy_corr', 'gx_gz_corr', 'gy_gz_corr', 'ax_ay_mse', 'ax_az_mse', 'ay_az_mse', 'gx_gy_mse', 'gx_gz_mse', 'gy_gz_mse']
    col_names = ["timestamp", "localtime", "user", "version", "start_time", "end_time", "duration"]

    for fn in feature_names:
        for sn in sensor_names:
            col_names.append(fn+"_"+sn)
    col_names.extend(extra_features)
    return ds.select(*col_names)

def classify_brushing(X: pd.DataFrame,model_file_name:str):
    with open(model_file_name, 'rb') as handle:
        clf = pickle.load(handle)
    X=X.values
    X = X[:,6:]
    preds = clf.predict(X)

    return preds
