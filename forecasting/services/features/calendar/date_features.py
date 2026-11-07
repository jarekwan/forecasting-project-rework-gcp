# import io
# import os

# import pandas as pd
# from google.cloud import storage


# INPUT_OBJECT = "data/processed/df_clean.pkl"
# OUTPUT_OBJECT = "data/processed/df_date_features.pkl"


# def _get_bucket():
#     bucket_name = os.environ.get("GCS_BUCKET_NAME")
#     if not bucket_name:
#         raise RuntimeError("Brak zmiennej środowiskowej GCS_BUCKET_NAME.")

#     return storage.Client().bucket(bucket_name)


# def _read_dataframe(object_name: str) -> pd.DataFrame:
#     bucket = _get_bucket()
#     blob = bucket.blob(object_name)

#     if not blob.exists():
#         raise FileNotFoundError(
#             f"Nie znaleziono pliku gs://{bucket.name}/{object_name}"
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


# def date_features() -> dict:
#     """Tworzy cechy daty automatycznie z DatetimeIndex i zapisuje DataFrame."""
#     df = _read_dataframe(INPUT_OBJECT)

#     if not isinstance(df.index, pd.DatetimeIndex):
#         raise ValueError(
#             "Data w df_clean.pkl nie jest indeksem DatetimeIndex. "
#             "Sprawdź, czy set_date.py zachował datę jako indeks."
#         )

#     if df.empty:
#         raise ValueError("df_clean.pkl nie zawiera danych.")

#     df = df.sort_index().copy()

#     # Data jest indeksem. Nie dodajemy jej jako kolumny do cech modelu.
#     df["year"] = df.index.year
#     df["month"] = df.index.month
#     df["day"] = df.index.day
#     df["dayofweek"] = df.index.dayofweek

#     output_path = _save_dataframe(df, OUTPUT_OBJECT)
#     saved_df = _read_dataframe(OUTPUT_OBJECT)

#     print("\nPRÓBKA df_date_features.pkl ODCZYTANA Z BUCKETA:")
#     print(saved_df.head(10).to_string(index=True), flush=True)

#     return {
#         "dataframe_file": output_path,
#         "rows": len(saved_df),
#         "columns": [str(column) for column in saved_df.columns],
#         "preview_html": saved_df.head(10).to_html(
#             index=True,
#             escape=True,
#         ),
#     }



import io
import os
from abc import ABC, abstractmethod

import pandas as pd
from google.cloud import storage


INPUT_OBJECT = "data/processed/df_clean.pkl"
OUTPUT_OBJECT = "data/processed/df_date_features.pkl"


def _get_bucket():
    bucket_name = os.environ.get("GCS_BUCKET_NAME")
    if not bucket_name:
        raise RuntimeError("Brak zmiennej środowiskowej GCS_BUCKET_NAME.")

    return storage.Client().bucket(bucket_name)


# ---------------------------------------------------------------------
# Interfejs i adapter Cloud Storage
# ---------------------------------------------------------------------

class ObjectStorage(ABC):
    """Interfejs operacji na plikach potrzebnych temu modułowi."""

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
    def write_bytes(
        self,
        object_name: str,
        content: bytes,
        content_type: str,
    ) -> None:
        raise NotImplementedError


class GoogleCloudStorageAdapter(ObjectStorage):
    """Ukrywa szczegóły klienta Google Cloud Storage."""

    def __init__(self, bucket):
        self._bucket = bucket

    @property
    def bucket_name(self) -> str:
        return self._bucket.name

    def exists(self, object_name: str) -> bool:
        return self._bucket.blob(object_name).exists()

    def read_bytes(self, object_name: str) -> bytes:
        return self._bucket.blob(object_name).download_as_bytes()

    def write_bytes(
        self,
        object_name: str,
        content: bytes,
        content_type: str,
    ) -> None:
        buffer = io.BytesIO(content)
        self._bucket.blob(object_name).upload_from_file(
            buffer,
            content_type=content_type,
        )


# ---------------------------------------------------------------------
# Repozytorium DataFrame'ów
# ---------------------------------------------------------------------

class DateFeaturesRepository(ABC):
    """Interfejs dostępu do danych etapu tworzenia cech daty."""

    @property
    @abstractmethod
    def bucket_name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def read_dataframe(self, object_name: str) -> pd.DataFrame:
        raise NotImplementedError

    @abstractmethod
    def save_dataframe(
        self,
        df: pd.DataFrame,
        object_name: str,
    ) -> str:
        raise NotImplementedError


class GCSDateFeaturesRepository(DateFeaturesRepository):
    """Odczytuje i zapisuje DataFrame'y w GCS."""

    def __init__(self, object_storage: ObjectStorage):
        self._object_storage = object_storage

    @property
    def bucket_name(self) -> str:
        return self._object_storage.bucket_name

    def read_dataframe(self, object_name: str) -> pd.DataFrame:
        if not self._object_storage.exists(object_name):
            raise FileNotFoundError(
                f"Nie znaleziono pliku "
                f"gs://{self.bucket_name}/{object_name}"
            )

        content = self._object_storage.read_bytes(object_name)
        return pd.read_pickle(io.BytesIO(content))

    def save_dataframe(
        self,
        df: pd.DataFrame,
        object_name: str,
    ) -> str:
        buffer = io.BytesIO()
        df.to_pickle(buffer)

        self._object_storage.write_bytes(
            object_name,
            buffer.getvalue(),
            "application/octet-stream",
        )

        return f"gs://{self.bucket_name}/{object_name}"


# ---------------------------------------------------------------------
# Logika tworzenia cech daty
# ---------------------------------------------------------------------

class DateFeatureGenerator:
    """Tworzy cechy kalendarzowe z indeksu DatetimeIndex."""

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        if not isinstance(df.index, pd.DatetimeIndex):
            raise ValueError(
                "Data w df_clean.pkl nie jest indeksem DatetimeIndex. "
                "Sprawdź, czy set_date.py zachował datę jako indeks."
            )

        if df.empty:
            raise ValueError("df_clean.pkl nie zawiera danych.")

        result = df.sort_index().copy()

        # Data pozostaje indeksem i nie staje się kolumną cech.
        result["year"] = result.index.year
        result["month"] = result.index.month
        result["day"] = result.index.day
        result["dayofweek"] = result.index.dayofweek

        return result


class DateFeaturesService:
    """Koordynuje odczyt, tworzenie cech i zapis wyniku."""

    def __init__(
        self,
        repository: DateFeaturesRepository,
        generator: DateFeatureGenerator,
    ):
        self._repository = repository
        self._generator = generator

    def run(self) -> dict:
        df = self._repository.read_dataframe(INPUT_OBJECT)
        result_df = self._generator.transform(df)

        output_path = self._repository.save_dataframe(
            result_df,
            OUTPUT_OBJECT,
        )
        saved_df = self._repository.read_dataframe(OUTPUT_OBJECT)

        print("\nPRÓBKA df_date_features.pkl ODCZYTANA Z BUCKETA:")
        print(saved_df.head(10).to_string(index=True), flush=True)

        return {
            "dataframe_file": output_path,
            "rows": len(saved_df),
            "columns": [str(column) for column in saved_df.columns],
            "preview_html": saved_df.head(10).to_html(
                index=True,
                escape=True,
            ),
        }


def _create_repository() -> GCSDateFeaturesRepository:
    object_storage = GoogleCloudStorageAdapter(_get_bucket())
    return GCSDateFeaturesRepository(object_storage)


def _create_service() -> DateFeaturesService:
    return DateFeaturesService(
        repository=_create_repository(),
        generator=DateFeatureGenerator(),
    )


# ---------------------------------------------------------------------
# Zachowane funkcje pomocnicze i publiczna funkcja używana przez UI.
# ---------------------------------------------------------------------

def _read_dataframe(object_name: str) -> pd.DataFrame:
    return _create_repository().read_dataframe(object_name)


def _save_dataframe(df: pd.DataFrame, object_name: str) -> str:
    return _create_repository().save_dataframe(df, object_name)


def date_features() -> dict:
    return _create_service().run()