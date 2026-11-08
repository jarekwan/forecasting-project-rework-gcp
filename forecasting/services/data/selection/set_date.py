
import io
import os
from abc import ABC, abstractmethod
from typing import Any

import pandas as pd
from google.cloud import storage


SELECTED_OBJECT = "data/processed/df_selected.pkl"
ADJUSTED_OBJECT = "data/processed/df_eda_adjusted.pkl"
TYPES_OBJECT = "data/processed/column_types.csv"
SETTINGS_OBJECT = "data/processed/date_settings.txt"
OUTPUT_OBJECT = "data/processed/df_date.pkl"


class ObjectStorage(ABC):
    """Kontrakt operacji Cloud Storage używanych w tym module."""

    @property
    @abstractmethod
    def bucket_name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def exists(self, object_name: str) -> bool:
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
    """Dostosowuje klienta GCS do kontraktu ObjectStorage."""

    def __init__(self) -> None:
        bucket_name = os.environ.get("GCS_BUCKET_NAME")
        if not bucket_name:
            raise ValueError("Brak zmiennej środowiskowej GCS_BUCKET_NAME.")
        self._bucket = storage.Client().bucket(bucket_name)

    @property
    def bucket_name(self) -> str:
        return self._bucket.name

    def exists(self, object_name: str) -> bool:
        return self._bucket.blob(object_name).exists()

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


class DateProcessingRepository:
    """Odczytuje i zapisuje obiekty potrzebne etapowi przygotowania dat."""

    def __init__(self, storage_adapter: ObjectStorage) -> None:
        self._storage = storage_adapter

    @property
    def bucket_name(self) -> str:
        return self._storage.bucket_name

    def input_object(self) -> str:
        """Zwraca skorygowany DataFrame, jeśli EDA go wcześniej zapisało."""
        if self._storage.exists(ADJUSTED_OBJECT):
            return ADJUSTED_OBJECT
        return SELECTED_OBJECT

    def read_bytes(self, object_name: str) -> bytes:
        return self._storage.read_bytes(object_name)

    def read_dataframe(self, object_name: str) -> pd.DataFrame:
        return pd.read_pickle(
            io.BytesIO(self._storage.read_bytes(object_name))
        )

    def read_column_types(self) -> pd.DataFrame | None:
        if not self._storage.exists(TYPES_OBJECT):
            return None
        return pd.read_csv(
            io.BytesIO(self._storage.read_bytes(TYPES_OBJECT))
        )

    def save_settings(
        self,
        date_column: str,
        duplicate_method: str,
        fill_method: str,
    ) -> str:
        content = f"{date_column}\n{duplicate_method}\n{fill_method}\n"
        self._storage.upload_bytes(
            SETTINGS_OBJECT,
            content.encode("utf-8"),
            "text/plain; charset=utf-8",
        )
        return f"gs://{self.bucket_name}/{SETTINGS_OBJECT}"

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
        return f"gs://{self.bucket_name}/{object_name}"


def _repository() -> DateProcessingRepository:
    return DateProcessingRepository(GoogleCloudStorageAdapter())


# Zachowane funkcje pomocnicze modułu dla dotychczasowych wywołań.
def _get_bucket():
    bucket_name = os.environ.get("GCS_BUCKET_NAME")
    if not bucket_name:
        raise ValueError("Brak zmiennej środowiskowej GCS_BUCKET_NAME.")
    return storage.Client().bucket(bucket_name)


def _input_object() -> str:
    return _repository().input_object()


def _read_bytes(object_name: str) -> bytes:
    return _repository().read_bytes(object_name)


def _read_pickle(object_name: str) -> pd.DataFrame:
    return _repository().read_dataframe(object_name)


class DuplicateAggregationStrategy(ABC):
    """Kontrakt strategii agregowania liczbowych duplikatów dat."""

    @abstractmethod
    def aggregate(self, grouped_data: Any) -> pd.DataFrame:
        raise NotImplementedError


class MeanAggregationStrategy(DuplicateAggregationStrategy):
    def aggregate(self, grouped_data: Any) -> pd.DataFrame:
        return grouped_data.mean()


class SumAggregationStrategy(DuplicateAggregationStrategy):
    def aggregate(self, grouped_data: Any) -> pd.DataFrame:
        return grouped_data.sum()


class DuplicateAggregationFactory:
    """Tworzy strategię na podstawie ustawienia formularza."""

    _strategies = {
        "mean": MeanAggregationStrategy,
        "sum": SumAggregationStrategy,
    }

    @classmethod
    def create(cls, method: str) -> DuplicateAggregationStrategy:
        strategy_class = cls._strategies.get(method)
        if strategy_class is None:
            raise ValueError("Nieprawidłowa metoda obsługi duplikatów.")
        return strategy_class()


class MissingDateFillStrategy(ABC):
    """Kontrakt strategii uzupełniania brakujących wartości."""

    @abstractmethod
    def fill(
        self,
        dataframe: pd.DataFrame,
        numeric_columns: list[Any],
    ) -> pd.DataFrame:
        raise NotImplementedError


class ZeroFillStrategy(MissingDateFillStrategy):
    def fill(
        self,
        dataframe: pd.DataFrame,
        numeric_columns: list[Any],
    ) -> pd.DataFrame:
        result = dataframe.copy()
        if numeric_columns:
            result[numeric_columns] = result[numeric_columns].fillna(0)
        return result


class ForwardFillStrategy(MissingDateFillStrategy):
    def fill(
        self,
        dataframe: pd.DataFrame,
        numeric_columns: list[Any],
    ) -> pd.DataFrame:
        return dataframe.ffill()


class MeanFillStrategy(MissingDateFillStrategy):
    def fill(
        self,
        dataframe: pd.DataFrame,
        numeric_columns: list[Any],
    ) -> pd.DataFrame:
        result = dataframe.copy()
        if numeric_columns:
            result[numeric_columns] = result[numeric_columns].fillna(
                result[numeric_columns].mean()
            )
        return result


class MissingDateFillFactory:
    """Tworzy strategię uzupełniania braków wskazaną przez użytkownika."""

    _strategies = {
        "zero": ZeroFillStrategy,
        "ffill": ForwardFillStrategy,
        "mean": MeanFillStrategy,
    }

    @classmethod
    def create(cls, method: str) -> MissingDateFillStrategy:
        strategy_class = cls._strategies.get(method)
        if strategy_class is None:
            raise ValueError("Nieprawidłowa metoda uzupełniania braków.")
        return strategy_class()


def _available_date_columns(
    dataframe: pd.DataFrame,
    types_dataframe: pd.DataFrame | None,
) -> list[str]:
    """Wybiera wykryte kolumny dat, a przy braku raportu zwraca wszystkie."""
    if (
        types_dataframe is not None
        and {"type", "column"}.issubset(types_dataframe.columns)
    ):
        detected = types_dataframe.loc[
            types_dataframe["type"] == "datetime",
            "column",
        ].astype(str).tolist()
        current_columns = {str(column) for column in dataframe.columns}
        detected = [column for column in detected if column in current_columns]
        if detected:
            return detected
    return [str(column) for column in dataframe.columns]


def _validate_date_settings(
    date_column: str,
    duplicate_method: str,
    fill_method: str,
    dataframe: pd.DataFrame,
) -> None:
    """Sprawdza metody i nazwę kolumny przed zapisaniem ustawień."""
    DuplicateAggregationFactory.create(duplicate_method)
    MissingDateFillFactory.create(fill_method)
    available_columns = {str(column) for column in dataframe.columns}
    if date_column not in available_columns:
        raise ValueError(f"Nie znaleziono kolumny: {date_column}")


def _read_date_settings(content: bytes) -> tuple[str, str, str]:
    """Odczytuje trzy ustawienia z dotychczasowego pliku tekstowego."""
    lines = content.decode("utf-8").splitlines()
    if len(lines) < 3:
        raise ValueError(
            "Plik date_settings.txt ma nieprawidłową zawartość."
        )
    date_column, duplicate_method, fill_method = lines[:3]
    return date_column, duplicate_method, fill_method


def _resolve_date_column(
    dataframe: pd.DataFrame,
    date_column_name: str,
) -> Any:
    """Mapuje nazwę z formularza na rzeczywistą etykietę kolumny."""
    original_columns = {str(column): column for column in dataframe.columns}
    if date_column_name not in original_columns:
        raise ValueError(f"Nie znaleziono kolumny daty: {date_column_name}")
    return original_columns[date_column_name]


def _convert_and_filter_dates(
    dataframe: pd.DataFrame,
    date_column: Any,
) -> pd.DataFrame:
    """Konwertuje daty i usuwa wiersze z niepoprawną datą."""
    result = dataframe.copy()
    result[date_column] = pd.to_datetime(
        result[date_column],
        errors="coerce",
    )
    result = result.dropna(subset=[date_column])
    if result.empty:
        raise ValueError("Nie znaleziono żadnych poprawnych dat.")
    return result


def _split_numeric_and_other_columns(
    dataframe: pd.DataFrame,
    date_column: Any,
) -> tuple[list[Any], list[Any]]:
    """Rozdziela kolumny liczbowe od pozostałych."""
    numeric_columns = [
        column
        for column in dataframe.select_dtypes(include="number").columns
        if column != date_column
    ]
    other_columns = [
        column
        for column in dataframe.columns
        if column != date_column and column not in numeric_columns
    ]
    return numeric_columns, other_columns


def _aggregate_duplicate_dates(
    dataframe: pd.DataFrame,
    date_column: Any,
    numeric_columns: list[Any],
    other_columns: list[Any],
    duplicate_method: str,
) -> pd.DataFrame:
    """Agreguje wiersze dla tych samych dat."""
    grouped = dataframe.groupby(date_column, sort=True)
    parts: list[pd.DataFrame] = []

    if numeric_columns:
        strategy = DuplicateAggregationFactory.create(duplicate_method)
        parts.append(strategy.aggregate(grouped[numeric_columns]))
    if other_columns:
        parts.append(grouped[other_columns].first())
    if parts:
        return pd.concat(parts, axis=1)
    return pd.DataFrame(index=grouped.size().index)


def _add_missing_daily_dates(
    dataframe: pd.DataFrame,
    date_column_name: str,
) -> pd.DataFrame:
    """Ustawia datę jako indeks i dodaje brakujące dni."""
    result = dataframe.copy()
    result.index = pd.DatetimeIndex(result.index)
    result.index.name = date_column_name
    full_range = pd.date_range(
        start=result.index.min(),
        end=result.index.max(),
        freq="D",
    )
    result = result.reindex(full_range)
    result.index.name = date_column_name
    return result


def _prepare_date_dataframe(
    dataframe: pd.DataFrame,
    date_column_name: str,
    duplicate_method: str,
    fill_method: str,
) -> pd.DataFrame:
    """Koordynuje transformacje do DataFrame'u z dziennym indeksem dat."""
    date_column = _resolve_date_column(dataframe, date_column_name)
    dated_dataframe = _convert_and_filter_dates(dataframe, date_column)
    numeric_columns, other_columns = _split_numeric_and_other_columns(
        dated_dataframe,
        date_column,
    )
    aggregated = _aggregate_duplicate_dates(
        dated_dataframe,
        date_column,
        numeric_columns,
        other_columns,
        duplicate_method,
    )
    daily_dataframe = _add_missing_daily_dates(
        aggregated,
        date_column_name,
    )
    filled = MissingDateFillFactory.create(fill_method).fill(
        daily_dataframe,
        numeric_columns,
    )
    return filled.sort_index()


def _build_saved_result(
    dataframe: pd.DataFrame,
    output_path: str,
) -> dict[str, Any]:
    """Buduje słownik danych prezentowany przez date_ui.py."""
    return {
        "dataframe_file": output_path,
        "rows": len(dataframe),
        "columns": [str(column) for column in dataframe.columns],
        "preview_html": dataframe.head(10).to_html(
            index=True,
            escape=True,
        ),
    }


def _print_saved_preview(
    bucket_name: str,
    dataframe: pd.DataFrame,
) -> None:
    """Wypisuje lokalizację wyniku i pierwsze wiersze do logu."""
    print(
        f"df_date.pkl zapisany w: gs://{bucket_name}/{OUTPUT_OBJECT}",
        flush=True,
    )
    print(dataframe.head(10).to_string(), flush=True)


class DateProcessingService:
    """Udostępnia przypadki użycia przygotowania danych według dat."""

    def __init__(self, repository: DateProcessingRepository) -> None:
        self._repository = repository

    def get_date_column_options(self) -> list[str]:
        dataframe = self._repository.read_dataframe(
            self._repository.input_object()
        )
        types_dataframe = self._repository.read_column_types()
        return _available_date_columns(dataframe, types_dataframe)

    def save_date_settings(
        self,
        date_column: str,
        duplicate_method: str,
        fill_method: str,
    ) -> str:
        dataframe = self._repository.read_dataframe(
            self._repository.input_object()
        )
        _validate_date_settings(
            date_column,
            duplicate_method,
            fill_method,
            dataframe,
        )
        return self._repository.save_settings(
            date_column,
            duplicate_method,
            fill_method,
        )

    def process(self) -> dict[str, Any]:
        """Koordynuje przetworzenie, zapis i odpowiedź dla UI."""
        dataframe = self._repository.read_dataframe(
            self._repository.input_object()
        )
        date_column, duplicate_method, fill_method = _read_date_settings(
            self._repository.read_bytes(SETTINGS_OBJECT)
        )
        prepared_dataframe = _prepare_date_dataframe(
            dataframe,
            date_column,
            duplicate_method,
            fill_method,
        )
        output_path = self._repository.save_dataframe(
            prepared_dataframe,
            OUTPUT_OBJECT,
        )
        saved_dataframe = self._repository.read_dataframe(OUTPUT_OBJECT)
        _print_saved_preview(
            self._repository.bucket_name,
            saved_dataframe,
        )
        return _build_saved_result(saved_dataframe, output_path)


# Publiczne funkcje zachowane dla date_ui.py.
def get_date_column_options() -> list[str]:
    return DateProcessingService(_repository()).get_date_column_options()


def save_date_settings(
    date_column: str,
    duplicate_method: str,
    fill_method: str,
) -> str:
    return DateProcessingService(_repository()).save_date_settings(
        date_column,
        duplicate_method,
        fill_method,
    )


def set_date() -> dict[str, Any]:
    return DateProcessingService(_repository()).process()