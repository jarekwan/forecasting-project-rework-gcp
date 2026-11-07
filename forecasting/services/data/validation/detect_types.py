# import io
# import os

# import pandas as pd
# from pandas.api.types import (
#     is_bool_dtype,
#     is_datetime64_any_dtype,
#     is_numeric_dtype,
# )
# from google.cloud import storage


# INPUT_OBJECT = "data/processed/df_selected.pkl"
# OUTPUT_OBJECT = "data/processed/column_types.csv"


# def _get_bucket():
#     bucket_name = os.environ.get("GCS_BUCKET_NAME")
#     if not bucket_name:
#         raise ValueError("Brak zmiennej środowiskowej GCS_BUCKET_NAME.")

#     return storage.Client().bucket(bucket_name)


# def _read_pickle(object_name: str) -> pd.DataFrame:
#     bucket = _get_bucket()
#     blob = bucket.blob(object_name)

#     if not blob.exists():
#         raise FileNotFoundError(
#             f"Nie znaleziono pliku: gs://{bucket.name}/{object_name}"
#         )

#     return pd.read_pickle(io.BytesIO(blob.download_as_bytes()))


# def _looks_like_datetime(series: pd.Series) -> bool:
#     if is_datetime64_any_dtype(series):
#         return True

#     values = series.dropna()
#     if values.empty:
#         return False

#     parsed = pd.to_datetime(values.astype(str), errors="coerce")
#     return parsed.notna().mean() >= 0.8


# def detect_types() -> dict[str, list[str]]:
#     """Rozpoznaje typy kolumn w df_selected.pkl i zapisuje column_types.csv."""
#     df = _read_pickle(INPUT_OBJECT)

#     result = {
#         "numerical": [],
#         "categorical": [],
#         "datetime": [],
#     }

#     rows = []

#     for column in df.columns:
#         column_name = str(column)
#         series = df[column]

#         if is_numeric_dtype(series) and not is_bool_dtype(series):
#             column_type = "numerical"
#         elif _looks_like_datetime(series):
#             column_type = "datetime"
#         else:
#             column_type = "categorical"

#         result[column_type].append(column_name)
#         rows.append([column_name, column_type])

#     output = io.StringIO()
#     pd.DataFrame(rows, columns=["column", "type"]).to_csv(
#         output,
#         index=False,
#     )

#     bucket = _get_bucket()
#     bucket.blob(OUTPUT_OBJECT).upload_from_string(
#         output.getvalue(),
#         content_type="text/csv",
#     )

#     print(
#         f"Typy kolumn zapisane w: "
#         f"gs://{bucket.name}/{OUTPUT_OBJECT}",
#         flush=True,
#     )
#     print(result, flush=True)

#     return result


import io
import os
from abc import ABC, abstractmethod

import pandas as pd
from google.cloud import storage
from pandas.api.types import (
    is_bool_dtype,
    is_datetime64_any_dtype,
    is_numeric_dtype,
)


INPUT_OBJECT = "data/processed/df_selected.pkl"
OUTPUT_OBJECT = "data/processed/column_types.csv"


def _get_bucket():
    bucket_name = os.environ.get("GCS_BUCKET_NAME")
    if not bucket_name:
        raise RuntimeError("Brak zmiennej środowiskowej GCS_BUCKET_NAME.")

    return storage.Client().bucket(bucket_name)


# ---------------------------------------------------------------------
# Interfejs i adapter Cloud Storage
# ---------------------------------------------------------------------

class ObjectStorage(ABC):
    """Interfejs operacji GCS używanych przez ten moduł."""

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
    def write_text(
        self,
        object_name: str,
        content: str,
        content_type: str,
    ) -> None:
        raise NotImplementedError


class GoogleCloudStorageAdapter(ObjectStorage):
    """Udostępnia Cloud Storage przez interfejs ObjectStorage."""

    def __init__(self, bucket):
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


# ---------------------------------------------------------------------
# Repozytorium DataFrame'u i raportu
# ---------------------------------------------------------------------

class ColumnTypeRepository(ABC):
    """Interfejs odczytu danych i zapisu raportu typów."""

    @property
    @abstractmethod
    def bucket_name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def read_dataframe(self, object_name: str) -> pd.DataFrame:
        raise NotImplementedError

    @abstractmethod
    def save_report(self, rows: list[list[str]]) -> str:
        raise NotImplementedError


class GCSColumnTypeRepository(ColumnTypeRepository):
    """Odczytuje DataFrame i zapisuje raport typów w GCS."""

    def __init__(self, object_storage: ObjectStorage):
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
        report_df = pd.DataFrame(rows, columns=["column", "type"])
        output = io.StringIO()
        report_df.to_csv(output, index=False)

        self._object_storage.write_text(
            OUTPUT_OBJECT,
            output.getvalue(),
            "text/csv",
        )

        return f"gs://{self.bucket_name}/{OUTPUT_OBJECT}"


# ---------------------------------------------------------------------
# Reguły rozpoznawania typów — wzorzec Strategy
# ---------------------------------------------------------------------

class ColumnTypeRule(ABC):
    """Interfejs pojedynczej reguły rozpoznawania typu kolumny."""

    @abstractmethod
    def detect(self, series: pd.Series) -> str | None:
        raise NotImplementedError


class NumericalColumnRule(ColumnTypeRule):
    def detect(self, series: pd.Series) -> str | None:
        if is_numeric_dtype(series) and not is_bool_dtype(series):
            return "numerical"
        return None


class DatetimeColumnRule(ColumnTypeRule):
    def detect(self, series: pd.Series) -> str | None:
        if _looks_like_datetime(series):
            return "datetime"
        return None


class ColumnTypeClassifier:
    """Sprawdza reguły po kolei; nierozpoznaną kolumnę uznaje za kategorię."""

    def __init__(self, rules: list[ColumnTypeRule]):
        self._rules = rules

    def classify(self, series: pd.Series) -> str:
        for rule in self._rules:
            column_type = rule.detect(series)
            if column_type is not None:
                return column_type

        return "categorical"


# ---------------------------------------------------------------------
# Usługa rozpoznawania typów
# ---------------------------------------------------------------------

class ColumnTypeDetectionService:
    """Koordynuje klasyfikację kolumn i zapis raportu."""

    def __init__(
        self,
        repository: ColumnTypeRepository,
        classifier: ColumnTypeClassifier,
    ):
        self._repository = repository
        self._classifier = classifier

    def detect_types(self) -> dict[str, list[str]]:
        df = self._repository.read_dataframe(INPUT_OBJECT)

        result = {
            "numerical": [],
            "categorical": [],
            "datetime": [],
        }
        rows = []

        for column in df.columns:
            column_name = str(column)
            column_type = self._classifier.classify(df[column])

            result[column_type].append(column_name)
            rows.append([column_name, column_type])

        report_path = self._repository.save_report(rows)

        print(
            f"Typy kolumn zapisane w: {report_path}",
            flush=True,
        )
        print(result, flush=True)

        return result


def _create_service() -> ColumnTypeDetectionService:
    bucket = _get_bucket()
    object_storage = GoogleCloudStorageAdapter(bucket)
    repository = GCSColumnTypeRepository(object_storage)

    classifier = ColumnTypeClassifier(
        rules=[
            NumericalColumnRule(),
            DatetimeColumnRule(),
        ]
    )

    return ColumnTypeDetectionService(
        repository=repository,
        classifier=classifier,
    )


# ---------------------------------------------------------------------
# Zachowane funkcje pomocnicze i publiczna funkcja używana przez UI.
# ---------------------------------------------------------------------

def _read_pickle(object_name: str) -> pd.DataFrame:
    bucket = _get_bucket()
    blob = bucket.blob(object_name)

    if not blob.exists():
        raise FileNotFoundError(
            f"Nie znaleziono pliku: gs://{bucket.name}/{object_name}"
        )

    return pd.read_pickle(io.BytesIO(blob.download_as_bytes()))


def _looks_like_datetime(series: pd.Series) -> bool:
    if is_datetime64_any_dtype(series):
        return True

    values = series.dropna()
    if values.empty:
        return False

    parsed = pd.to_datetime(values.astype(str), errors="coerce")
    return parsed.notna().mean() >= 0.8


def detect_types() -> dict[str, list[str]]:
    """Rozpoznaje typy kolumn i zapisuje column_types.csv w GCS."""
    return _create_service().detect_types()