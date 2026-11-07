


import io
import json
import os
from abc import ABC, abstractmethod

import pandas as pd
from google.cloud import storage


INPUT_OBJECT = "data/processed/df_date.pkl"
METHOD_OBJECT = "data/processed/clean_method.txt"
OUTPUT_OBJECT = "data/processed/df_clean.pkl"

ALLOWED_METHODS = {"drop", "zero", "ffill", "mean", "none"}





# ---------------------------------------------------------------------
# Interfejs i adapter Cloud Storage
# ---------------------------------------------------------------------

class ObjectStorage(ABC):
    """Interfejs operacji na obiektach potrzebnych temu modułowi."""

    @abstractmethod
    def exists(self, object_name: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def read_bytes(self, object_name: str) -> bytes:
        raise NotImplementedError

    @abstractmethod
    def read_text(self, object_name: str) -> str:
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

    def exists(self, object_name: str) -> bool:
        return self._bucket.blob(object_name).exists()

    def read_bytes(self, object_name: str) -> bytes:
        return self._bucket.blob(object_name).download_as_bytes()

    def read_text(self, object_name: str) -> str:
        return self._bucket.blob(object_name).download_as_text()

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
# Odpowiada za odczyt i zapis DataFrame'ów oraz ustawień.
# ---------------------------------------------------------------------

class CleaningRepository(ABC):
    """Interfejs dostępu do danych etapu czyszczenia."""

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
    def read_methods(self) -> dict[str, str]:
        raise NotImplementedError

    @abstractmethod
    def save_methods(self, methods: dict[str, str]) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def bucket_name(self) -> str:
        raise NotImplementedError


class GCSCleaningRepository(CleaningRepository):
    """Odczytuje i zapisuje dane etapu czyszczenia w GCS."""

    def __init__(self, object_storage: ObjectStorage, bucket_name: str):
        self._object_storage = object_storage
        self._bucket_name = bucket_name

    @property
    def bucket_name(self) -> str:
        return self._bucket_name

    def read_dataframe(self, object_name: str) -> pd.DataFrame:
        if not self._object_storage.exists(object_name):
            raise FileNotFoundError(
                f"Nie znaleziono pliku "
                f"gs://{self._bucket_name}/{object_name}"
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

        return f"gs://{self._bucket_name}/{object_name}"

    def read_methods(self) -> dict[str, str]:
        if not self._object_storage.exists(METHOD_OBJECT):
            raise FileNotFoundError(
                f"Nie znaleziono pliku "
                f"gs://{self._bucket_name}/{METHOD_OBJECT}"
            )

        return json.loads(self._object_storage.read_text(METHOD_OBJECT))

    def save_methods(self, methods: dict[str, str]) -> str:
        self._object_storage.write_text(
            METHOD_OBJECT,
            json.dumps(methods, ensure_ascii=False),
            "text/plain; charset=utf-8",
        )

        return f"gs://{self._bucket_name}/{METHOD_OBJECT}"


# ---------------------------------------------------------------------
# Strategie uzupełniania braków
# Każda metoda czyszczenia ma osobną klasę.
# ---------------------------------------------------------------------

class MissingValueStrategy(ABC):
    """Wspólny interfejs dla metod obsługi brakujących wartości."""

    @abstractmethod
    def apply(self, df: pd.DataFrame, column) -> pd.DataFrame:
        raise NotImplementedError


class DropMissingStrategy(MissingValueStrategy):
    def apply(self, df: pd.DataFrame, column) -> pd.DataFrame:
        return df.loc[df[column].notna()].copy()


class FillZeroStrategy(MissingValueStrategy):
    def apply(self, df: pd.DataFrame, column) -> pd.DataFrame:
        df[column] = df[column].fillna(0)
        return df


class ForwardFillStrategy(MissingValueStrategy):
    def apply(self, df: pd.DataFrame, column) -> pd.DataFrame:
        df[column] = df[column].ffill()
        return df


class MeanOrForwardFillStrategy(MissingValueStrategy):
    def apply(self, df: pd.DataFrame, column) -> pd.DataFrame:
        if pd.api.types.is_numeric_dtype(df[column]):
            df[column] = df[column].fillna(df[column].mean())
        else:
            df[column] = df[column].ffill()

        return df


class KeepMissingStrategy(MissingValueStrategy):
    def apply(self, df: pd.DataFrame, column) -> pd.DataFrame:
        return df


def _create_strategies() -> dict[str, MissingValueStrategy]:
    """Tworzy strategie odpowiadające dotychczasowym metodom."""
    return {
        "drop": DropMissingStrategy(),
        "zero": FillZeroStrategy(),
        "ffill": ForwardFillStrategy(),
        "mean": MeanOrForwardFillStrategy(),
        "none": KeepMissingStrategy(),
    }


# ---------------------------------------------------------------------
# Logika etapu czyszczenia
# ---------------------------------------------------------------------

class CleanDataService:
    """Koordynuje walidację ustawień i czyszczenie DataFrame'u."""

    def __init__(
        self,
        repository: CleaningRepository,
        strategies: dict[str, MissingValueStrategy],
    ):
        self._repository = repository
        self._strategies = strategies

    def get_cleaning_options(self) -> list[dict]:
        df = self._repository.read_dataframe(INPUT_OBJECT)

        return [
            {
                "column": str(column),
                "missing": int(df[column].isna().sum()),
            }
            for column in df.columns
        ]

    def save_cleaning_methods(
        self,
        methods: dict[str, str],
    ) -> str:
        df = self._repository.read_dataframe(INPUT_OBJECT)
        columns = {str(column) for column in df.columns}

        if set(methods) != columns:
            raise ValueError("Wybierz metodę dla każdej kolumny.")

        invalid = {
            column: method
            for column, method in methods.items()
            if method not in self._strategies
        }
        if invalid:
            raise ValueError(f"Nieznane metody czyszczenia: {invalid}")

        return self._repository.save_methods(methods)

    def clean_data(self) -> dict:
        df = self._repository.read_dataframe(INPUT_OBJECT)
        methods = self._repository.read_methods()
        column_names = {str(column): column for column in df.columns}

        for column_name, method in methods.items():
            if column_name not in column_names:
                raise ValueError(f"Nie znaleziono kolumny: {column_name}")

            strategy = self._strategies.get(method)
            if strategy is None:
                raise ValueError(f"Nieznana metoda: {method}")

            column = column_names[column_name]
            df = strategy.apply(df, column)

        output_path = self._repository.save_dataframe(df, OUTPUT_OBJECT)
        saved_df = self._repository.read_dataframe(OUTPUT_OBJECT)

        print("\nPRÓBKA df_clean.pkl ODCZYTANA Z BUCKETA:")
        print(saved_df.head(10).to_string(index=False), flush=True)

        return {
            "dataframe_file": output_path,
            "rows": len(saved_df),
            "columns": [str(column) for column in saved_df.columns],
            "preview_html": saved_df.head(10).to_html(
                index=True,
                escape=True,
            ),
        }


def _create_service() -> CleanDataService:
    bucket = _get_bucket()
    bucket_name = bucket.name
    object_storage = GoogleCloudStorageAdapter(bucket)

    repository = GCSCleaningRepository(
        object_storage=object_storage,
        bucket_name=bucket_name,
    )

    return CleanDataService(
        repository=repository,
        strategies=_create_strategies(),
    )


# ---------------------------------------------------------------------
# Zachowane funkcje publiczne i pomocnicze
# Inne moduły nadal mogą importować je pod dotychczasowymi nazwami.
# ---------------------------------------------------------------------

def _read_dataframe(object_name: str) -> pd.DataFrame:
    return _create_service()._repository.read_dataframe(object_name)


def _save_dataframe(df: pd.DataFrame, object_name: str) -> str:
    return _create_service()._repository.save_dataframe(df, object_name)


def get_cleaning_options() -> list[dict]:
    return _create_service().get_cleaning_options()


def save_cleaning_methods(methods: dict[str, str]) -> str:
    return _create_service().save_cleaning_methods(methods)


def clean_data() -> dict:
    return _create_service().clean_data()