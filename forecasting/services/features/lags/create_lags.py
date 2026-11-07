# import io
# import os

# import pandas as pd
# from google.cloud import storage


# INPUT_OBJECT = "data/processed/df_date_features.pkl"
# OUTPUT_OBJECT = "data/processed/df_lags.pkl"
# SETTINGS_OBJECT = "data/processed/lags_method.txt"


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


# def get_lag_source_preview() -> dict:
#     """Zwraca kolumny i próbkę df_date_features.pkl."""
#     df = _read_dataframe(INPUT_OBJECT)

#     return {
#         "columns": [str(column) for column in df.columns],
#         "preview_html": df.head(10).to_html(index=False, escape=True),
#     }


# def create_lags(column: str, lags_text: str) -> dict:
#     """Tworzy wybrane kolumny lag i zapisuje df_lags.pkl w GCS."""
#     df = _read_dataframe(INPUT_OBJECT)
#     column_names = {str(existing): existing for existing in df.columns}

#     if column not in column_names:
#         raise ValueError(f"Nie znaleziono kolumny: {column}")

#     lags = []
#     for value in lags_text.split(","):
#         value = value.strip()
#         if not value:
#             continue

#         try:
#             lag = int(value)
#         except ValueError as error:
#             raise ValueError(
#                 f"Wartość laga „{value}” nie jest liczbą całkowitą."
#             ) from error

#         if lag <= 0:
#             raise ValueError("Wartości lag muszą być większe od zera.")

#         lags.append(lag)

#     if not lags:
#         raise ValueError("Podaj przynajmniej jedną wartość lag, np. 1,2,7.")

#     if len(lags) != len(set(lags)):
#         raise ValueError("Nie podawaj powtarzających się wartości lag.")

#     original_column = column_names[column]

#     for lag in lags:
#         df[f"{column}_lag_{lag}"] = df[original_column].shift(lag)

#     bucket = _get_bucket()
#     dataframe_path = _save_dataframe(df, OUTPUT_OBJECT)

#     settings = f"{column}\n{','.join(map(str, lags))}\n"
#     bucket.blob(SETTINGS_OBJECT).upload_from_string(
#         settings,
#         content_type="text/plain; charset=utf-8",
#     )

#     saved_df = _read_dataframe(OUTPUT_OBJECT)

#     print("\nPRÓBKA df_lags.pkl ODCZYTANA Z BUCKETA:", flush=True)
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


INPUT_OBJECT = "data/processed/df_date_features.pkl"
OUTPUT_OBJECT = "data/processed/df_lags.pkl"
SETTINGS_OBJECT = "data/processed/lags_method.txt"


def _get_bucket():
    bucket_name = os.environ.get("GCS_BUCKET_NAME")
    if not bucket_name:
        raise ValueError("Brak zmiennej środowiskowej GCS_BUCKET_NAME.")

    return storage.Client().bucket(bucket_name)


# ---------------------------------------------------------------------
# Interfejs i adapter Cloud Storage
# ---------------------------------------------------------------------

class ObjectStorage(ABC):
    """Interfejs potrzebnych temu modułowi operacji na obiektach."""

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
# Repozytorium
# Odpowiada za odczyt i zapis plików etapu lagów.
# ---------------------------------------------------------------------

class LagRepository(ABC):
    """Interfejs dostępu do danych etapu tworzenia lagów."""

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

    @abstractmethod
    def save_settings(
        self,
        settings: str,
        object_name: str,
    ) -> str:
        raise NotImplementedError


class GCSLagRepository(LagRepository):
    """Czyta i zapisuje pliki etapu lagów w GCS."""

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

    def save_settings(
        self,
        settings: str,
        object_name: str,
    ) -> str:
        self._object_storage.write_text(
            object_name,
            settings,
            "text/plain; charset=utf-8",
        )

        return f"gs://{self.bucket_name}/{object_name}"


# ---------------------------------------------------------------------
# Logika tworzenia cech lag
# ---------------------------------------------------------------------

class LagFeatureGenerator:
    """Waliduje wybór kolumny i lagów oraz tworzy nowe kolumny."""

    def create(
        self,
        df: pd.DataFrame,
        column: str,
        lags_text: str,
    ) -> tuple[pd.DataFrame, list[int]]:
        column_names = {
            str(existing): existing
            for existing in df.columns
        }

        if column not in column_names:
            raise ValueError(f"Nie znaleziono kolumny: {column}")

        lags = self._parse_lags(lags_text)
        original_column = column_names[column]

        for lag in lags:
            df[f"{column}_lag_{lag}"] = df[original_column].shift(lag)

        return df, lags

    @staticmethod
    def _parse_lags(lags_text: str) -> list[int]:
        lags = []

        for value in lags_text.split(","):
            value = value.strip()
            if not value:
                continue

            try:
                lag = int(value)
            except ValueError as error:
                raise ValueError(
                    f"Wartość laga „{value}” nie jest liczbą całkowitą."
                ) from error

            if lag <= 0:
                raise ValueError(
                    "Wartości lag muszą być większe od zera."
                )

            lags.append(lag)

        if not lags:
            raise ValueError(
                "Podaj przynajmniej jedną wartość lag, np. 1,2,7."
            )

        if len(lags) != len(set(lags)):
            raise ValueError(
                "Nie podawaj powtarzających się wartości lag."
            )

        return lags


class CreateLagsService:
    """Koordynuje odczyt, utworzenie lagów i zapis wyników."""

    def __init__(
        self,
        repository: LagRepository,
        generator: LagFeatureGenerator,
    ):
        self._repository = repository
        self._generator = generator

    def get_source_preview(self) -> dict:
        df = self._repository.read_dataframe(INPUT_OBJECT)

        return {
            "columns": [str(column) for column in df.columns],
            "preview_html": df.head(10).to_html(
                index=False,
                escape=True,
            ),
        }

    def create_lags(self, column: str, lags_text: str) -> dict:
        df = self._repository.read_dataframe(INPUT_OBJECT)
        df, lags = self._generator.create(df, column, lags_text)

        dataframe_path = self._repository.save_dataframe(
            df,
            OUTPUT_OBJECT,
        )

        settings = f"{column}\n{','.join(map(str, lags))}\n"
        settings_path = self._repository.save_settings(
            settings,
            SETTINGS_OBJECT,
        )

        saved_df = self._repository.read_dataframe(OUTPUT_OBJECT)

        print("\nPRÓBKA df_lags.pkl ODCZYTANA Z BUCKETA:", flush=True)
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


def _create_repository() -> GCSLagRepository:
    object_storage = GoogleCloudStorageAdapter(_get_bucket())
    return GCSLagRepository(object_storage)


def _create_service() -> CreateLagsService:
    return CreateLagsService(
        repository=_create_repository(),
        generator=LagFeatureGenerator(),
    )


# ---------------------------------------------------------------------
# Zachowane funkcje publiczne używane przez inne moduły.
# ---------------------------------------------------------------------

def _read_dataframe(object_name: str) -> pd.DataFrame:
    return _create_repository().read_dataframe(object_name)


def _save_dataframe(df: pd.DataFrame, object_name: str) -> str:
    return _create_repository().save_dataframe(df, object_name)


def get_lag_source_preview() -> dict:
    return _create_service().get_source_preview()


def create_lags(column: str, lags_text: str) -> dict:
    return _create_service().create_lags(column, lags_text)