
import io
import os
from abc import ABC, abstractmethod
from typing import Any

import pandas as pd
from google.cloud import storage


INPUT_OBJECT = "data/processed/df_lags.pkl"
OUTPUT_OBJECT = "data/processed/df_rolling.pkl"
SETTINGS_OBJECT = "data/processed/rolling_method.txt"


class ObjectStorage(ABC):
    """Kontrakt operacji Cloud Storage potrzebnych w tym module."""

    @property
    @abstractmethod
    def bucket_name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def read_bytes(self, object_name: str) -> bytes:
        raise NotImplementedError

    @abstractmethod
    def upload_bytes(
        self,
        object_name: str,
        content: bytes,
        content_type: str,
    ) -> None:
        raise NotImplementedError


class GoogleCloudStorageAdapter(ObjectStorage):
    """Dostosowuje operacje GCS do interfejsu ObjectStorage."""

    def __init__(self, bucket: storage.Bucket) -> None:
        self._bucket = bucket

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


class RollingStatsStore(ABC):
    """Kontrakt zapisu i odczytu potrzebny usłudze statystyk kroczących."""

    @abstractmethod
    def read_dataframe(self, object_name: str) -> pd.DataFrame:
        raise NotImplementedError

    @abstractmethod
    def save_dataframe(
        self,
        dataframe: pd.DataFrame,
        object_name: str,
    ) -> str:
        raise NotImplementedError

    @abstractmethod
    def save_settings(
        self,
        column: str,
        window: int,
        aggregation: str,
        object_name: str,
    ) -> str:
        raise NotImplementedError


class RollingStatsRepository(RollingStatsStore):
    """Zapisuje i odczytuje DataFrame'y oraz ustawienia przez adapter."""

    def __init__(self, storage_adapter: ObjectStorage) -> None:
        self._storage = storage_adapter

    def read_dataframe(self, object_name: str) -> pd.DataFrame:
        content = self._storage.read_bytes(object_name)
        return pd.read_pickle(io.BytesIO(content))

    def save_dataframe(
        self,
        dataframe: pd.DataFrame,
        object_name: str,
    ) -> str:
        buffer = io.BytesIO()
        dataframe.to_pickle(buffer)
        self._storage.upload_bytes(
            object_name,
            buffer.getvalue(),
            "application/octet-stream",
        )
        return f"gs://{self._storage.bucket_name}/{object_name}"

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
        return f"gs://{self._storage.bucket_name}/{object_name}"


class RollingAggregationStrategy(ABC):
    """Kontrakt sposobu obliczania statystyki kroczącej."""

    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def calculate(self, series: pd.Series, window: int) -> pd.Series:
        raise NotImplementedError


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


def _numeric_column_names(dataframe: pd.DataFrame) -> list[str]:
    """Zwraca nazwy kolumn liczbowych dostępnych do obliczeń."""
    return [
        str(column)
        for column in dataframe.columns
        if pd.api.types.is_numeric_dtype(dataframe[column])
    ]


def _build_source_preview(dataframe: pd.DataFrame) -> dict[str, Any]:
    """Przygotowuje listę kolumn liczbowych i HTML próbki dla UI."""
    numeric_columns = _numeric_column_names(dataframe)
    if not numeric_columns:
        raise ValueError("W df_lags.pkl nie ma kolumn liczbowych.")

    return {
        "columns": numeric_columns,
        "preview_html": dataframe.head(10).to_html(
            index=False,
            escape=True,
        ),
    }


def _resolve_column(dataframe: pd.DataFrame, column_name: str) -> Any:
    """Odnajduje oryginalną etykietę kolumny wybranej w formularzu."""
    column_names = {str(column): column for column in dataframe.columns}
    if column_name not in column_names:
        raise ValueError(f"Nie znaleziono kolumny: {column_name}.")
    return column_names[column_name]


def _validate_numeric_column(
    dataframe: pd.DataFrame,
    column: Any,
    column_name: str,
) -> None:
    """Sprawdza, czy wybrana kolumna zawiera wartości liczbowe."""
    if not pd.api.types.is_numeric_dtype(dataframe[column]):
        raise ValueError(f"Kolumna „{column_name}” nie jest liczbowa.")


def _validate_window(window: int) -> None:
    """Sprawdza, czy rozmiar okna rolling jest dodatni."""
    if window <= 0:
        raise ValueError("Rozmiar okna musi być większy od zera.")


def _add_rolling_column(
    dataframe: pd.DataFrame,
    source_column: Any,
    output_column: str,
    window: int,
    strategy: RollingAggregationStrategy,
) -> pd.DataFrame:
    """Oblicza i dodaje jedną kolumnę statystyki kroczącej."""
    result = dataframe.copy()
    result[output_column] = strategy.calculate(result[source_column], window)
    return result


def _fill_engineered_column_gaps(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Uzupełnia zerami braki w kolumnach lag i statystyk kroczących."""
    result = dataframe.copy()
    feature_markers = ("_lag_", "_mean_", "_sum_", "_median_")

    for column in result.columns:
        if any(marker in str(column) for marker in feature_markers):
            result[column] = result[column].fillna(0)

    return result


def _build_rolling_result(
    dataframe: pd.DataFrame,
    dataframe_path: str,
    settings_path: str,
) -> dict[str, Any]:
    """Buduje słownik wyniku używany przez rolling_stats_ui.py."""
    return {
        "dataframe_file": dataframe_path,
        "settings_file": settings_path,
        "rows": len(dataframe),
        "columns": [str(column) for column in dataframe.columns],
        "preview_html": dataframe.head(10).to_html(
            index=False,
            escape=True,
        ),
    }


def _print_saved_preview(dataframe: pd.DataFrame) -> None:
    """Wypisuje próbkę zapisanego DataFrame'u do logu."""
    print("\nPRÓBKA df_rolling.pkl ODCZYTANA Z BUCKETA:", flush=True)
    print(dataframe.head(10).to_string(index=False), flush=True)


class RollingStatsService:
    """Koordynuje przypadki użycia statystyk kroczących."""

    def __init__(self, repository: RollingStatsStore) -> None:
        self._repository = repository

    def get_source_preview(self) -> dict[str, Any]:
        dataframe = self._repository.read_dataframe(INPUT_OBJECT)
        return _build_source_preview(dataframe)

    def create(
        self,
        column: str,
        window: int,
        aggregation: str,
    ) -> dict[str, Any]:
        """Koordynuje walidację, obliczenie, zapis i odpowiedź dla UI."""
        dataframe = self._repository.read_dataframe(INPUT_OBJECT)
        source_column = _resolve_column(dataframe, column)
        _validate_numeric_column(dataframe, source_column, column)
        _validate_window(window)
        strategy = RollingAggregationFactory.create(aggregation)

        output_column = f"{column}_{strategy.name}_{window}"
        dataframe = _add_rolling_column(
            dataframe,
            source_column,
            output_column,
            window,
            strategy,
        )
        dataframe = _fill_engineered_column_gaps(dataframe)

        dataframe_path = self._repository.save_dataframe(
            dataframe,
            OUTPUT_OBJECT,
        )
        settings_path = self._repository.save_settings(
            column,
            window,
            strategy.name,
            SETTINGS_OBJECT,
        )
        saved_dataframe = self._repository.read_dataframe(OUTPUT_OBJECT)

        _print_saved_preview(saved_dataframe)
        return _build_rolling_result(
            saved_dataframe,
            dataframe_path,
            settings_path,
        )


def _get_bucket() -> storage.Bucket:
    """Zwraca bucket GCS wskazany przez GCS_BUCKET_NAME."""
    bucket_name = os.environ.get("GCS_BUCKET_NAME")
    if not bucket_name:
        raise ValueError("Brak zmiennej środowiskowej GCS_BUCKET_NAME.")
    return storage.Client().bucket(bucket_name)


def _repository() -> RollingStatsRepository:
    return RollingStatsRepository(GoogleCloudStorageAdapter(_get_bucket()))


# Zachowane dotychczasowe funkcje pomocnicze i publiczne.
def _read_dataframe(object_name: str) -> pd.DataFrame:
    return _repository().read_dataframe(object_name)


def _save_dataframe(dataframe: pd.DataFrame, object_name: str) -> str:
    return _repository().save_dataframe(dataframe, object_name)


def _create_service() -> RollingStatsService:
    return RollingStatsService(_repository())


def get_rolling_source_preview() -> dict[str, Any]:
    return _create_service().get_source_preview()


def rolling_stats(
    column: str,
    window: int,
    aggregation: str,
) -> dict[str, Any]:
    return _create_service().create(column, window, aggregation)