# import io
# import os

# import pandas as pd
# from google.cloud import storage


# INPUT_OBJECT = "data/processed/df_lags.pkl"
# OUTPUT_OBJECT = "data/processed/df_rolling.pkl"
# SETTINGS_OBJECT = "data/processed/rolling_method.txt"


# def _get_bucket():
#     bucket_name = os.environ.get("GCS_BUCKET_NAME")
#     if not bucket_name:
#         raise ValueError("Brak zmiennej środowiskowej GCS_BUCKET_NAME.")

#     return storage.Client().bucket(bucket_name)


# def _read_dataframe(object_name: str) -> pd.DataFrame:
#     bucket = _get_bucket()
#     blob = bucket.blob(object_name)

#     if not blob.exists():
#         raise FileNotFoundError(
#             f"Nie znaleziono pliku: gs://{bucket.name}/{object_name}"
#         )

#     return pd.read_pickle(io.BytesIO(blob.download_as_bytes()))


# def _save_dataframe(df: pd.DataFrame, object_name: str) -> str:
#     bucket = _get_bucket()
#     buffer = io.BytesIO()
#     df.to_pickle(buffer)
#     buffer.seek(0)

#     bucket.blob(object_name).upload_from_file(
#         buffer,
#         content_type="application/octet-stream",
#     )

#     return f"gs://{bucket.name}/{object_name}"


# def get_rolling_source_preview() -> dict:
#     """Zwraca próbkę df_lags.pkl i jego kolumny liczbowe."""
#     df = _read_dataframe(INPUT_OBJECT)
#     numeric_columns = [
#         str(column)
#         for column in df.columns
#         if pd.api.types.is_numeric_dtype(df[column])
#     ]

#     if not numeric_columns:
#         raise ValueError("W df_lags.pkl nie ma kolumn liczbowych.")

#     return {
#         "columns": numeric_columns,
#         "preview_html": df.head(10).to_html(index=False, escape=True),
#     }


# def rolling_stats(column: str, window: int, aggregation: str) -> dict:
#     """Tworzy statystykę kroczącą i zapisuje df_rolling.pkl w GCS."""
#     df = _read_dataframe(INPUT_OBJECT)
#     column_names = {str(existing): existing for existing in df.columns}

#     if column not in column_names:
#         raise ValueError(f"Nie znaleziono kolumny: {column}.")

#     if not pd.api.types.is_numeric_dtype(df[column_names[column]]):
#         raise ValueError(f"Kolumna „{column}” nie jest liczbowa.")

#     if window <= 0:
#         raise ValueError("Rozmiar okna musi być większy od zera.")

#     if aggregation not in {"mean", "sum", "median"}:
#         raise ValueError("Wybierz mean, sum albo median.")

#     original_column = column_names[column]
#     new_column = f"{column}_{aggregation}_{window}"

#     df[new_column] = df[original_column].rolling(window=window).agg(aggregation)

#     # Tak jak w wersji z Gita: uzupełnij braki w kolumnach lag i rolling zerami.
#     for existing_column in df.columns:
#         name = str(existing_column)
#         if (
#             "_lag_" in name
#             or "_mean_" in name
#             or "_sum_" in name
#             or "_median_" in name
#         ):
#             df[existing_column] = df[existing_column].fillna(0)

#     bucket = _get_bucket()
#     dataframe_path = _save_dataframe(df, OUTPUT_OBJECT)

#     settings = f"{column}\n{window}\n{aggregation}\n"
#     bucket.blob(SETTINGS_OBJECT).upload_from_string(
#         settings,
#         content_type="text/plain; charset=utf-8",
#     )

#     saved_df = _read_dataframe(OUTPUT_OBJECT)

#     print("\nPRÓBKA df_rolling.pkl ODCZYTANA Z BUCKETA:", flush=True)
#     print(saved_df.head(10).to_string(index=False), flush=True)

#     return {
#         "dataframe_file": dataframe_path,
#         "settings_file": f"gs://{bucket.name}/{SETTINGS_OBJECT}",
#         "rows": len(saved_df),
#         "columns": [str(column) for column in saved_df.columns],
#         "preview_html": saved_df.head(10).to_html(index=False, escape=True),
#     }


import io
import os
from abc import ABC, abstractmethod

import pandas as pd
from google.cloud import storage


INPUT_OBJECT = "data/processed/df_lags.pkl"
OUTPUT_OBJECT = "data/processed/df_rolling.pkl"
SETTINGS_OBJECT = "data/processed/rolling_method.txt"


# Adapter: interfejs dostępu do obiektów w Cloud Storage.
class ObjectStorage(ABC):
    @property
    @abstractmethod
    def bucket_name(self) -> str:
        pass

    @abstractmethod
    def read_bytes(self, object_name: str) -> bytes:
        pass

    @abstractmethod
    def upload_bytes(
        self,
        object_name: str,
        content: bytes,
        content_type: str,
    ) -> None:
        pass


class GoogleCloudStorageAdapter(ObjectStorage):
    def __init__(self):
        bucket_name = os.environ.get("GCS_BUCKET_NAME")
        if not bucket_name:
            raise ValueError("Brak zmiennej środowiskowej GCS_BUCKET_NAME.")

        self._bucket = storage.Client().bucket(bucket_name)

    @property
    def bucket_name(self) -> str:
        return self._bucket.name

    def read_bytes(self, object_name: str) -> bytes:
        blob = self._bucket.blob(object_name)
        if not blob.exists():
            raise FileNotFoundError(
                f"Nie znaleziono pliku: "
                f"gs://{self.bucket_name}/{object_name}"
            )
        return blob.download_as_bytes()

    def upload_bytes(
        self,
        object_name: str,
        content: bytes,
        content_type: str,
    ) -> None:
        self._bucket.blob(object_name).upload_from_string(
            content,
            content_type=content_type,
        )


# Repository: zapisuje i odczytuje DataFrame'y oraz ustawienia.
class RollingStatsRepository:
    def __init__(self, storage_adapter: ObjectStorage):
        self._storage = storage_adapter

    @property
    def bucket_name(self) -> str:
        return self._storage.bucket_name

    def read_dataframe(self, object_name: str) -> pd.DataFrame:
        content = self._storage.read_bytes(object_name)
        return pd.read_pickle(io.BytesIO(content))

    def save_dataframe(self, df: pd.DataFrame, object_name: str) -> str:
        buffer = io.BytesIO()
        df.to_pickle(buffer)

        self._storage.upload_bytes(
            object_name,
            buffer.getvalue(),
            "application/octet-stream",
        )
        return f"gs://{self.bucket_name}/{object_name}"

    def save_settings(
        self,
        column: str,
        window: int,
        aggregation: str,
        object_name: str,
    ) -> str:
        settings = f"{column}\n{window}\n{aggregation}\n"
        self._storage.upload_bytes(
            object_name,
            settings.encode("utf-8"),
            "text/plain; charset=utf-8",
        )
        return f"gs://{self.bucket_name}/{object_name}"


def _repository() -> RollingStatsRepository:
    return RollingStatsRepository(GoogleCloudStorageAdapter())


# Zachowane dotychczasowe funkcje pomocnicze.
def _get_bucket():
    bucket_name = os.environ.get("GCS_BUCKET_NAME")
    if not bucket_name:
        raise ValueError("Brak zmiennej środowiskowej GCS_BUCKET_NAME.")
    return storage.Client().bucket(bucket_name)


def _read_dataframe(object_name: str) -> pd.DataFrame:
    return _repository().read_dataframe(object_name)


def _save_dataframe(df: pd.DataFrame, object_name: str) -> str:
    return _repository().save_dataframe(df, object_name)


# Strategy: każda metoda agregacji ma osobną klasę.
class RollingAggregationStrategy(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    def calculate(
        self,
        series: pd.Series,
        window: int,
    ) -> pd.Series:
        pass


class RollingMeanStrategy(RollingAggregationStrategy):
    @property
    def name(self) -> str:
        return "mean"

    def calculate(self, series: pd.Series, window: int) -> pd.Series:
        return series.rolling(window=window).mean()


class RollingSumStrategy(RollingAggregationStrategy):
    @property
    def name(self) -> str:
        return "sum"

    def calculate(self, series: pd.Series, window: int) -> pd.Series:
        return series.rolling(window=window).sum()


class RollingMedianStrategy(RollingAggregationStrategy):
    @property
    def name(self) -> str:
        return "median"

    def calculate(self, series: pd.Series, window: int) -> pd.Series:
        return series.rolling(window=window).median()


class RollingAggregationFactory:
    """Dobiera strategię na podstawie wartości wybranej w formularzu."""

    _strategies = {
        "mean": RollingMeanStrategy,
        "sum": RollingSumStrategy,
        "median": RollingMedianStrategy,
    }

    @classmethod
    def create(cls, aggregation: str) -> RollingAggregationStrategy:
        strategy_class = cls._strategies.get(aggregation)
        if strategy_class is None:
            raise ValueError("Wybierz mean, sum albo median.")
        return strategy_class()


class RollingStatsService:
    """Tworzy i zapisuje wybraną statystykę kroczącą."""

    def __init__(self, repository: RollingStatsRepository):
        self._repository = repository

    def get_source_preview(self) -> dict:
        df = self._repository.read_dataframe(INPUT_OBJECT)
        numeric_columns = [
            str(column)
            for column in df.columns
            if pd.api.types.is_numeric_dtype(df[column])
        ]

        if not numeric_columns:
            raise ValueError("W df_lags.pkl nie ma kolumn liczbowych.")

        return {
            "columns": numeric_columns,
            "preview_html": df.head(10).to_html(
                index=False,
                escape=True,
            ),
        }

    def create(
        self,
        column: str,
        window: int,
        aggregation: str,
    ) -> dict:
        df = self._repository.read_dataframe(INPUT_OBJECT)
        column_names = {str(existing): existing for existing in df.columns}

        if column not in column_names:
            raise ValueError(f"Nie znaleziono kolumny: {column}.")

        original_column = column_names[column]
        if not pd.api.types.is_numeric_dtype(df[original_column]):
            raise ValueError(f"Kolumna „{column}” nie jest liczbowa.")

        if window <= 0:
            raise ValueError("Rozmiar okna musi być większy od zera.")

        strategy = RollingAggregationFactory.create(aggregation)
        new_column = f"{column}_{strategy.name}_{window}"

        df[new_column] = strategy.calculate(df[original_column], window)

        # Zachowuje dotychczasowe działanie:
        # braki w kolumnach lag i rolling uzupełnia zerami.
        for existing_column in df.columns:
            name = str(existing_column)
            if (
                "_lag_" in name
                or "_mean_" in name
                or "_sum_" in name
                or "_median_" in name
            ):
                df[existing_column] = df[existing_column].fillna(0)

        dataframe_path = self._repository.save_dataframe(
            df,
            OUTPUT_OBJECT,
        )
        settings_path = self._repository.save_settings(
            column,
            window,
            strategy.name,
            SETTINGS_OBJECT,
        )

        saved_df = self._repository.read_dataframe(OUTPUT_OBJECT)

        print("\nPRÓBKA df_rolling.pkl ODCZYTANA Z BUCKETA:", flush=True)
        print(saved_df.head(10).to_string(index=False), flush=True)

        return {
            "dataframe_file": dataframe_path,
            "settings_file": settings_path,
            "rows": len(saved_df),
            "columns": [str(column) for column in saved_df.columns],
            "preview_html": saved_df.head(10).to_html(
                index=False,
                escape=True,
            ),
        }


# Zachowane funkcje wywoływane przez rolling_stats_ui.py.
def get_rolling_source_preview() -> dict:
    return RollingStatsService(_repository()).get_source_preview()


def rolling_stats(column: str, window: int, aggregation: str) -> dict:
    return RollingStatsService(_repository()).create(
        column,
        window,
        aggregation,
    )