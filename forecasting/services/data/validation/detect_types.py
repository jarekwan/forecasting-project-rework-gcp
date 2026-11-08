

import io
import os
from abc import ABC, abstractmethod

import pandas as pd
from google.cloud import storage
from google.cloud.storage.bucket import Bucket
from pandas.api.types import (
    is_bool_dtype,
    is_datetime64_any_dtype,
    is_numeric_dtype,
)


INPUT_OBJECT = "data/processed/df_selected.pkl"
OUTPUT_OBJECT = "data/processed/column_types.csv"


def _get_bucket() -> Bucket:
    """Zwraca bucket wskazany przez zmienną GCS_BUCKET_NAME."""
    bucket_name = os.environ.get("GCS_BUCKET_NAME")
    if not bucket_name:
        raise RuntimeError("Brak zmiennej środowiskowej GCS_BUCKET_NAME.")

    return storage.Client().bucket(bucket_name)


class ObjectStorage(ABC):
    """Kontrakt operacji Cloud Storage wykorzystywanych przez repozytorium."""

    @property
    @abstractmethod
    def bucket_name(self) -> str:
        ...

    @abstractmethod
    def exists(self, object_name: str) -> bool:
        ...

    @abstractmethod
    def read_bytes(self, object_name: str) -> bytes:
        ...

    @abstractmethod
    def write_text(
        self,
        object_name: str,
        content: str,
        content_type: str,
    ) -> None:
        ...


class GoogleCloudStorageAdapter(ObjectStorage):
    """Udostępnia Cloud Storage przez interfejs ObjectStorage."""

    def __init__(self, bucket: Bucket) -> None:
        self._bucket = bucket

    @property
    def bucket_name(self) -> str:
        return self._bucket.name

    def exists(self, object_name: str) -> bool:
        return self._bucket.blob(object_name).exists()

    def read_bytes(self, object_name: str) -> bytes:
        return self._bucket.blob(object_name).download_as_bytes()

    def write_text(
        self,
        object_name: str,
        content: str,
        content_type: str,
    ) -> None:
        self._bucket.blob(object_name).upload_from_string(
            content,
            content_type=content_type,
        )


class ColumnTypeRepository(ABC):
    """Kontrakt odczytu DataFrame'u i zapisu raportu typów."""

    @property
    @abstractmethod
    def bucket_name(self) -> str:
        ...

    @abstractmethod
    def read_dataframe(self, object_name: str) -> pd.DataFrame:
        ...

    @abstractmethod
    def save_report(self, rows: list[list[str]]) -> str:
        ...


class GCSColumnTypeRepository(ColumnTypeRepository):
    """Odczytuje DataFrame i zapisuje raport typów w GCS."""

    def __init__(self, object_storage: ObjectStorage) -> None:
        self._object_storage = object_storage

    @property
    def bucket_name(self) -> str:
        return self._object_storage.bucket_name

    def read_dataframe(self, object_name: str) -> pd.DataFrame:
        if not self._object_storage.exists(object_name):
            raise FileNotFoundError(
                f"Nie znaleziono pliku: "
                f"gs://{self.bucket_name}/{object_name}"
            )

        content = self._object_storage.read_bytes(object_name)
        return pd.read_pickle(io.BytesIO(content))

    def save_report(self, rows: list[list[str]]) -> str:
        report_dataframe = pd.DataFrame(rows, columns=["column", "type"])
        output = io.StringIO()
        report_dataframe.to_csv(output, index=False)

        self._object_storage.write_text(
            OUTPUT_OBJECT,
            output.getvalue(),
            "text/csv",
        )

        return f"gs://{self.bucket_name}/{OUTPUT_OBJECT}"


class ColumnTypeRule(ABC):
    """Kontrakt pojedynczej reguły rozpoznawania typu kolumny."""

    @abstractmethod
    def detect(self, series: pd.Series) -> str | None:
        ...


class NumericalColumnRule(ColumnTypeRule):
    """Rozpoznaje kolumny liczbowe, ale nie logiczne."""

    def detect(self, series: pd.Series) -> str | None:
        if is_numeric_dtype(series) and not is_bool_dtype(series):
            return "numerical"
        return None


class DatetimeColumnRule(ColumnTypeRule):
    """Rozpoznaje kolumny zawierające wartości daty i czasu."""

    def detect(self, series: pd.Series) -> str | None:
        if _looks_like_datetime(series):
            return "datetime"
        return None


class ColumnTypeClassifier:
    """Stosuje reguły po kolei; nierozpoznaną kolumnę klasyfikuje jako kategorię."""

    def __init__(self, rules: list[ColumnTypeRule]) -> None:
        self._rules = rules

    def classify(self, series: pd.Series) -> str:
        for rule in self._rules:
            column_type = rule.detect(series)
            if column_type is not None:
                return column_type

        return "categorical"


def _classify_dataframe(
    dataframe: pd.DataFrame,
    classifier: ColumnTypeClassifier,
) -> tuple[dict[str, list[str]], list[list[str]]]:
    """Klasyfikuje kolumny i przygotowuje wiersze raportu."""
    result: dict[str, list[str]] = {
        "numerical": [],
        "categorical": [],
        "datetime": [],
    }
    report_rows: list[list[str]] = []

    for column in dataframe.columns:
        column_name = str(column)
        column_type = classifier.classify(dataframe[column])
        result[column_type].append(column_name)
        report_rows.append([column_name, column_type])

    return result, report_rows


def _print_detection_summary(
    report_path: str,
    result: dict[str, list[str]],
) -> None:
    """Wypisuje lokalizację raportu i wynik klasyfikacji do logu."""
    print(f"Typy kolumn zapisane w: {report_path}", flush=True)
    print(result, flush=True)


class ColumnTypeDetectionService:
    """Koordynuje rozpoznanie typów kolumn i zapis raportu."""

    def __init__(
        self,
        repository: ColumnTypeRepository,
        classifier: ColumnTypeClassifier,
    ) -> None:
        self._repository = repository
        self._classifier = classifier

    def detect_types(self) -> dict[str, list[str]]:
        dataframe = self._repository.read_dataframe(INPUT_OBJECT)
        result, report_rows = _classify_dataframe(dataframe, self._classifier)
        report_path = self._repository.save_report(report_rows)
        _print_detection_summary(report_path, result)
        return result


def _create_repository() -> GCSColumnTypeRepository:
    """Składa adapter GCS i repozytorium używane w produkcji."""
    object_storage = GoogleCloudStorageAdapter(_get_bucket())
    return GCSColumnTypeRepository(object_storage)


def _create_service() -> ColumnTypeDetectionService:
    """Tworzy usługę z produkcyjnym repozytorium i regułami klasyfikacji."""
    classifier = ColumnTypeClassifier(
        rules=[
            NumericalColumnRule(),
            DatetimeColumnRule(),
        ]
    )
    return ColumnTypeDetectionService(
        repository=_create_repository(),
        classifier=classifier,
    )


def _read_pickle(object_name: str) -> pd.DataFrame:
    """Zachowana funkcja pomocnicza do odczytu DataFrame'u z GCS."""
    return _create_repository().read_dataframe(object_name)


def _looks_like_datetime(series: pd.Series) -> bool:
    """Sprawdza, czy kolumna ma typ daty lub zawiera głównie parsowalne daty."""
    if is_datetime64_any_dtype(series):
        return True

    values = series.dropna()
    if values.empty:
        return False

    parsed = pd.to_datetime(values.astype(str), errors="coerce")
    return parsed.notna().mean() >= 0.8


def detect_types() -> dict[str, list[str]]:
    """Punkt wejścia używany przez UI; zwraca typy i zapisuje raport CSV."""
    return _create_service().detect_types()