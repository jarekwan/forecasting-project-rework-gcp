


import io
import json
import os
from abc import ABC, abstractmethod
from typing import Any

import pandas as pd
from google.cloud import storage


INPUT_OBJECT = "data/processed/df_date.pkl"
METHOD_OBJECT = "data/processed/clean_method.txt"
OUTPUT_OBJECT = "data/processed/df_clean.pkl"

ALLOWED_METHODS = {"drop", "zero", "ffill", "mean", "none"}


class ObjectStorage(ABC):
    """Kontrakt operacji Cloud Storage używanych przez moduł czyszczenia."""

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
    """Dostosowuje bucket GCS do interfejsu ObjectStorage."""

    def __init__(self, bucket: storage.Bucket) -> None:
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


class CleaningRepository(ABC):
    """Kontrakt odczytu i zapisu danych etapu czyszczenia."""

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
    """Odczytuje i zapisuje DataFrame'y oraz ustawienia w GCS."""

    def __init__(
        self,
        object_storage: ObjectStorage,
        bucket_name: str,
    ) -> None:
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
        dataframe: pd.DataFrame,
        object_name: str,
    ) -> str:
        buffer = io.BytesIO()
        dataframe.to_pickle(buffer)

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


class MissingValueStrategy(ABC):
    """Kontrakt jednej metody obsługi brakujących wartości w kolumnie."""

    @abstractmethod
    def apply(
        self,
        dataframe: pd.DataFrame,
        column: Any,
    ) -> pd.DataFrame:
        raise NotImplementedError


class DropMissingStrategy(MissingValueStrategy):
    def apply(
        self,
        dataframe: pd.DataFrame,
        column: Any,
    ) -> pd.DataFrame:
        return dataframe.loc[dataframe[column].notna()].copy()


class FillZeroStrategy(MissingValueStrategy):
    def apply(
        self,
        dataframe: pd.DataFrame,
        column: Any,
    ) -> pd.DataFrame:
        dataframe[column] = dataframe[column].fillna(0)
        return dataframe


class ForwardFillStrategy(MissingValueStrategy):
    def apply(
        self,
        dataframe: pd.DataFrame,
        column: Any,
    ) -> pd.DataFrame:
        dataframe[column] = dataframe[column].ffill()
        return dataframe


class MeanOrForwardFillStrategy(MissingValueStrategy):
    """Dla liczbowych używa średniej, dla pozostałych poprzedniej wartości."""

    def apply(
        self,
        dataframe: pd.DataFrame,
        column: Any,
    ) -> pd.DataFrame:
        if pd.api.types.is_numeric_dtype(dataframe[column]):
            dataframe[column] = dataframe[column].fillna(
                dataframe[column].mean()
            )
        else:
            dataframe[column] = dataframe[column].ffill()

        return dataframe


class KeepMissingStrategy(MissingValueStrategy):
    def apply(
        self,
        dataframe: pd.DataFrame,
        column: Any,
    ) -> pd.DataFrame:
        return dataframe


def _create_strategies() -> dict[str, MissingValueStrategy]:
    """Tworzy mapę nazw metod na ich wymienne strategie."""
    return {
        "drop": DropMissingStrategy(),
        "zero": FillZeroStrategy(),
        "ffill": ForwardFillStrategy(),
        "mean": MeanOrForwardFillStrategy(),
        "none": KeepMissingStrategy(),
    }


def _build_cleaning_options(
    dataframe: pd.DataFrame,
) -> list[dict[str, str | int]]:
    """Przygotowuje dla UI nazwę każdej kolumny i liczbę jej braków."""
    return [
        {
            "column": str(column),
            "missing": int(dataframe[column].isna().sum()),
        }
        for column in dataframe.columns
    ]


def _validate_cleaning_methods(
    dataframe: pd.DataFrame,
    methods: dict[str, str],
    allowed_methods: set[str],
) -> None:
    """Sprawdza kompletność ustawień i poprawność nazw metod."""
    dataframe_columns = {str(column) for column in dataframe.columns}
    if set(methods) != dataframe_columns:
        raise ValueError("Wybierz metodę dla każdej kolumny.")

    invalid_methods = {
        column: method
        for column, method in methods.items()
        if method not in allowed_methods
    }
    if invalid_methods:
        raise ValueError(
            f"Nieznane metody czyszczenia: {invalid_methods}"
        )


def _apply_cleaning_methods(
    dataframe: pd.DataFrame,
    methods: dict[str, str],
    strategies: dict[str, MissingValueStrategy],
) -> pd.DataFrame:
    """Zastosowuje wybraną strategię do każdej wskazanej kolumny."""
    column_names = {str(column): column for column in dataframe.columns}
    result = dataframe.copy()

    for column_name, method in methods.items():
        if column_name not in column_names:
            raise ValueError(f"Nie znaleziono kolumny: {column_name}")

        strategy = strategies.get(method)
        if strategy is None:
            raise ValueError(f"Nieznana metoda: {method}")

        result = strategy.apply(result, column_names[column_name])

    return result


def _build_cleaning_result(
    dataframe: pd.DataFrame,
    output_path: str,
) -> dict[str, Any]:
    """Buduje wynik z polami wykorzystywanymi przez clean_data_ui.py."""
    return {
        "dataframe_file": output_path,
        "rows": len(dataframe),
        "columns": [str(column) for column in dataframe.columns],
        "preview_html": dataframe.head(10).to_html(
            index=True,
            escape=True,
        ),
    }


def _print_cleaning_preview(dataframe: pd.DataFrame) -> None:
    """Wypisuje próbkę wyczyszczonego DataFrame'u do logu."""
    print("\nPRÓBKA df_clean.pkl ODCZYTANA Z BUCKETA:")
    print(dataframe.head(10).to_string(index=False), flush=True)


class CleanDataService:
    """Koordynuje operacje etapu czyszczenia danych."""

    def __init__(
        self,
        repository: CleaningRepository,
        strategies: dict[str, MissingValueStrategy],
    ) -> None:
        self._repository = repository
        self._strategies = strategies

    def get_cleaning_options(self) -> list[dict[str, str | int]]:
        dataframe = self._repository.read_dataframe(INPUT_OBJECT)
        return _build_cleaning_options(dataframe)

    def save_cleaning_methods(
        self,
        methods: dict[str, str],
    ) -> str:
        dataframe = self._repository.read_dataframe(INPUT_OBJECT)
        _validate_cleaning_methods(
            dataframe,
            methods,
            set(self._strategies),
        )
        return self._repository.save_methods(methods)

    def clean_data(self) -> dict[str, Any]:
        """Koordynuje odczyt, czyszczenie, zapis i wynik dla UI."""
        dataframe = self._repository.read_dataframe(INPUT_OBJECT)
        methods = self._repository.read_methods()

        cleaned_dataframe = _apply_cleaning_methods(
            dataframe,
            methods,
            self._strategies,
        )
        output_path = self._repository.save_dataframe(
            cleaned_dataframe,
            OUTPUT_OBJECT,
        )
        saved_dataframe = self._repository.read_dataframe(OUTPUT_OBJECT)

        _print_cleaning_preview(saved_dataframe)
        return _build_cleaning_result(saved_dataframe, output_path)


def _get_bucket() -> storage.Bucket:
    """Zwraca bucket GCS wskazany przez GCS_BUCKET_NAME."""
    bucket_name = os.environ.get("GCS_BUCKET_NAME")
    if not bucket_name:
        raise ValueError("Brak zmiennej środowiskowej GCS_BUCKET_NAME.")

    return storage.Client().bucket(bucket_name)


def _create_repository() -> GCSCleaningRepository:
    """Składa adapter GCS i repozytorium dla tego modułu."""
    bucket = _get_bucket()
    object_storage = GoogleCloudStorageAdapter(bucket)
    return GCSCleaningRepository(
        object_storage=object_storage,
        bucket_name=bucket.name,
    )


def _create_service() -> CleanDataService:
    """Tworzy usługę z repozytorium i dostępnymi strategiami."""
    return CleanDataService(
        repository=_create_repository(),
        strategies=_create_strategies(),
    )


# Zachowane publiczne funkcje używane przez clean_data_ui.py.
def _read_dataframe(object_name: str) -> pd.DataFrame:
    return _create_repository().read_dataframe(object_name)


def _save_dataframe(dataframe: pd.DataFrame, object_name: str) -> str:
    return _create_repository().save_dataframe(dataframe, object_name)


def get_cleaning_options() -> list[dict[str, str | int]]:
    return _create_service().get_cleaning_options()


def save_cleaning_methods(methods: dict[str, str]) -> str:
    return _create_service().save_cleaning_methods(methods)


def clean_data() -> dict[str, Any]:
    return _create_service().clean_data()