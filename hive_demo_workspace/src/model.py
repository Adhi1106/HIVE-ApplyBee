import numpy as np


def predict(df):
    return np.mean(df.select_dtypes('number').values)
