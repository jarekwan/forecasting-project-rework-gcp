

import io
import os
from abc import ABC, abstractmethod
from collections.abc import Hashable
from typing import TypedDict

import pandas as pd
from google.cloud import storage


DATAFRAME_OBJECT = "data/processed/df.pkl"
SELECTED_DATAFRAME_OBJECT = "data/processed/df_selected.pkl"
SELECTED_COLUMNS_OBJECT = "data/processed/selected_columns.txt"


def _get_bucket():
    """Zwraca bucket skonfigurowany przez GCS_BUCKET_NAME."""
    bucket_name = os.environ.get("GCS_BUCKET_NAME")
    if not bucket_name:
        raise ValueError("Brak zmiennej środowiskowej GCS_BUCKET_NAME.")

    return storage.Client().bucket(bucket_name)


class ObjectStorage(ABC):
    """Kontrakt operacji na obiektach w magazynie plików."""

    @property
    @abstractmethod
    def bucket_name(self) -> str:
        ...

    @abstractmethod
    def read_bytes(self, object_name: str) -> bytes:
        ...

    @abstractmethod
    def upload_bytes(
        self,
        object_name: str,
        content: bytes,
        content_type: str,
    ) -> None:
        ...


class GoogleCloudStorageAdapter(ObjectStorage):
    """Udostępnia operacje Cloud Storage przez interfejs ObjectStorage."""

    def __init__(self) -> None:
        self._bucket = _get_bucket()

    @property
    def bucket_name(self) -> str:
        return self._bucket.name

    def read_bytes(self, object_name: str) -> bytes:
        blob = self._bucket.blob(object_name)
        if not blob.exists():
            raise FileNotFoundError(
                f"Nie znaleziono pliku: gs://{self.bucket_name}/{object_name}"
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


class ColumnSelectionRepositoryInterface(ABC):
    """Operacje danych wymagane przez usługę wyboru kolumn."""

    @property
    @abstractmethod
    def bucket_name(self) -> str:
        ...

    @abstractmethod
    def read_dataframe(self, object_name: str) -> pd.DataFrame:
        ...

    @abstractmethod
    def save_dataframe(
        self,
        dataframe: pd.DataFrame,
        object_name: str,
    ) -> None:
        ...

    @abstractmethod
    def save_selected_columns(
        self,
        selected_columns: list[str],
        object_name: str,
    ) -> None:
        ...


class SelectedColumnsRepository(ColumnSelectionRepositoryInterface):
    """Odczytuje i zapisuje DataFrame oraz wybrane kolumny."""

    def __init__(self, storage_adapter: ObjectStorage) -> None:
        self._storage = storage_adapter

    @property
    def bucket_name(self) -> str:
        return self._storage.bucket_name

    def read_dataframe(self, object_name: str) -> pd.DataFrame:
        content = self._storage.read_bytes(object_name)
        return pd.read_pickle(io.BytesIO(content))

    def save_dataframe(
        self,
        dataframe: pd.DataFrame,
        object_name: str,
    ) -> None:
        buffer = io.BytesIO()
        dataframe.to_pickle(buffer)
        self._storage.upload_bytes(
            object_name,
            buffer.getvalue(),
            "application/octet-stream",
        )

    def save_selected_columns(
        self,
        selected_columns: list[str],
        object_name: str,
    ) -> None:
        content = ("\n".join(selected_columns) + "\n").encode("utf-8")
        self._storage.upload_bytes(
            object_name,
            content,
            "text/plain; charset=utf-8",
        )


class ColumnSelectionResult(TypedDict):
    selected_dataframe_file: str
    selected_columns_file: str
    rows: int
    columns: list[str]
    preview_html: str


def _repository() -> SelectedColumnsRepository:
    """Tworzy produkcyjne repozytorium i adapter Cloud Storage."""
    return SelectedColumnsRepository(GoogleCloudStorageAdapter())


def _read_dataframe(object_name: str) -> pd.DataFrame:
    """Zachowana funkcja pomocnicza do odczytu DataFrame'u."""
    return _repository().read_dataframe(object_name)


def _validate_selection(
    selected_columns: list[str],
    available_columns: dict[str, Hashable],
) -> None:
    """Sprawdza, czy wybór jest niepusty, bez powtórzeń i zawiera istniejące kolumny."""
    if not selected_columns:
        raise ValueError("Zaznacz przynajmniej jedną kolumnę.")

    if len(selected_columns) != len(set(selected_columns)):
        raise ValueError("Lista zaznaczonych kolumn zawiera powtórzenia.")

    missing_columns = [
        column for column in selected_columns if column not in available_columns
    ]
    if missing_columns:
        raise ValueError(f"Nie znaleziono kolumn: {missing_columns}")


def _select_dataframe(
    dataframe: pd.DataFrame,
    selected_columns: list[str],
    original_columns: dict[str, Hashable],
) -> pd.DataFrame:
    """Tworzy kopię DataFrame'u ograniczoną do wskazanych kolumn."""
    source_column_names = [
        original_columns[column] for column in selected_columns
    ]
    return dataframe[source_column_names].copy()


def _print_saved_preview(dataframe: pd.DataFrame) -> None:
    """Wypisuje próbkę zapisanego DataFrame'u w logu aplikacji."""
    print("\nPRÓBKA df_selected.pkl ODCZYTANA Z BUCKETA:")
    print(dataframe.head(10).to_string(index=False))


def _build_result(
    dataframe: pd.DataFrame,
    bucket_name: str,
) -> ColumnSelectionResult:
    """Buduje wynik zwracany przez funkcję wyboru kolumn."""
    return {
        "selected_dataframe_file": (
            f"gs://{bucket_name}/{SELECTED_DATAFRAME_OBJECT}"
        ),
        "selected_columns_file": (
            f"gs://{bucket_name}/{SELECTED_COLUMNS_OBJECT}"
        ),
        "rows": len(dataframe),
        "columns": [str(column) for column in dataframe.columns],
        "preview_html": dataframe.head(10).to_html(
            index=False,
            escape=True,
        ),
    }


class ColumnSelectionService:
    """Obsługuje przypadek użycia: wybór i zapis kolumn DataFrame'u."""

    def __init__(self, repository: ColumnSelectionRepositoryInterface) -> None:
        self._repository = repository

    def get_saved_columns(self) -> list[str]:
        dataframe = self._repository.read_dataframe(DATAFRAME_OBJECT)
        return [str(column) for column in dataframe.columns]

    def select_columns(
        self,
        selected_columns: list[str],
    ) -> ColumnSelectionResult:
        source_dataframe = self._repository.read_dataframe(DATAFRAME_OBJECT)
        original_columns = {
            str(column): column for column in source_dataframe.columns
        }
        _validate_selection(selected_columns, original_columns)

        selected_dataframe = _select_dataframe(
            source_dataframe,
            selected_columns,
            original_columns,
        )
        self._repository.save_dataframe(
            selected_dataframe,
            SELECTED_DATAFRAME_OBJECT,
        )
        self._repository.save_selected_columns(
            selected_columns,
            SELECTED_COLUMNS_OBJECT,
        )

        saved_dataframe = self._repository.read_dataframe(
            SELECTED_DATAFRAME_OBJECT
        )
        _print_saved_preview(saved_dataframe)

        return _build_result(saved_dataframe, self._repository.bucket_name)


def get_saved_columns() -> list[str]:
    """Punkt wejścia zachowany dla columns_ui.py."""
    return ColumnSelectionService(_repository()).get_saved_columns()


def select_dataframe_columns(
    selected_columns: list[str],
) -> ColumnSelectionResult:
    """Punkt wejścia zachowany dla formularza columns_ui.py."""
    return ColumnSelectionService(_repository()).select_columns(selected_columns)