import os
import pandas as pd
from model import predict


def main():
    df = pd.read_csv('data.csv')
    print(predict(df))


if __name__ == '__main__':
    main()
