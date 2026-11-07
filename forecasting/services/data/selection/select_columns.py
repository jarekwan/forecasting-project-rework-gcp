# import io
# import os
# from typing import Dict, List

# import pandas as pd
# from google.cloud import storage


# DATAFRAME_OBJECT = "data/processed/df.pkl"
# SELECTED_DATAFRAME_OBJECT = "data/processed/df_selected.pkl"
# SELECTED_COLUMNS_OBJECT = "data/processed/selected_columns.txt"


# def _get_bucket():
#     bucket_name = os.environ.get("GCS_BUCKET_NAME")
#     if not bucket_name:
#         raise ValueError("Brak zmiennej środowiskowej GCS_BUCKET_NAME.")

#     return storage.Client().bucket(bucket_name)


# def _read_dataframe(object_name: str) -> pd.DataFrame:
#     blob = _get_bucket().blob(object_name)

#     if not blob.exists():
#         raise FileNotFoundError(
#             f"Nie znaleziono pliku: gs://{blob.bucket.name}/{object_name}"
#         )

#     return pd.read_pickle(io.BytesIO(blob.download_as_bytes()))


# def get_saved_columns() -> List[str]:
#     """Odczytuje df.pkl i zwraca jego nazwy kolumn."""
#     df = _read_dataframe(DATAFRAME_OBJECT)
#     return [str(column) for column in df.columns]


# def select_dataframe_columns(selected_columns: List[str]) -> Dict:
#     """Zapisuje wybrane nazwy kolumn oraz df_selected.pkl w GCS."""
#     if not selected_columns:
#         raise ValueError("Zaznacz przynajmniej jedną kolumnę.")

#     if len(selected_columns) != len(set(selected_columns)):
#         raise ValueError("Lista zaznaczonych kolumn zawiera powtórzenia.")

#     df = _read_dataframe(DATAFRAME_OBJECT)
#     original_columns = {str(column): column for column in df.columns}

#     missing_columns = [
#         column for column in selected_columns
#         if column not in original_columns
#     ]
#     if missing_columns:
#         raise ValueError(f"Nie znaleziono kolumn: {missing_columns}")

#     selected_df = df[
#         [original_columns[column] for column in selected_columns]
#     ].copy()

#     bucket = _get_bucket()

#     dataframe_buffer = io.BytesIO()
#     selected_df.to_pickle(dataframe_buffer)
#     dataframe_buffer.seek(0)

#     bucket.blob(SELECTED_DATAFRAME_OBJECT).upload_from_file(
#         dataframe_buffer,
#         content_type="application/octet-stream",
#     )

#     bucket.blob(SELECTED_COLUMNS_OBJECT).upload_from_string(
#         "\n".join(selected_columns) + "\n",
#         content_type="text/plain; charset=utf-8",
#     )

#     saved_df = _read_dataframe(SELECTED_DATAFRAME_OBJECT)

#     print("\nPRÓBKA df_selected.pkl ODCZYTANA Z BUCKETA:")
#     print(saved_df.head(10).to_string(index=False))

#     return {
#         "selected_dataframe_file": (
#             f"gs://{bucket.name}/{SELECTED_DATAFRAME_OBJECT}"
#         ),
#         "selected_columns_file": (
#             f"gs://{bucket.name}/{SELECTED_COLUMNS_OBJECT}"
#         ),
#         "rows": len(saved_df),
#         "columns": [str(column) for column in saved_df.columns],
#         "preview_html": saved_df.head(10).to_html(
#             index=False,
#             escape=True,
#         ),
#     }


import io
import os
from abc import ABC, abstractmethod
from typing import Dict, List

import pandas as pd
from google.cloud import storage


DATAFRAME_OBJECT = "data/processed/df.pkl"
SELECTED_DATAFRAME_OBJECT = "data/processed/df_selected.pkl"
SELECTED_COLUMNS_OBJECT = "data/processed/selected_columns.txt"


# Adapter: wspólny interfejs dostępu do plików w Cloud Storage.
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


# Repository: odpowiada za odczyt i zapis danych oraz listy wybranych kolumn.
class SelectedColumnsRepository:
    def __init__(self, storage_adapter: ObjectStorage):
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
        selected_columns: List[str],
        object_name: str,
    ) -> None:
        content = ("\n".join(selected_columns) + "\n").encode("utf-8")

        self._storage.upload_bytes(
            object_name,
            content,
            "text/plain; charset=utf-8",
        )


def _repository() -> SelectedColumnsRepository:
    return SelectedColumnsRepository(GoogleCloudStorageAdapter())


# Zachowane funkcje pomocnicze modułu.
def _get_bucket():
    bucket_name = os.environ.get("GCS_BUCKET_NAME")
    if not bucket_name:
        raise ValueError("Brak zmiennej środowiskowej GCS_BUCKET_NAME.")

    return storage.Client().bucket(bucket_name)


def _read_dataframe(object_name: str) -> pd.DataFrame:
    return _repository().read_dataframe(object_name)


class ColumnSelectionService:
    """Odczytuje kolumny źródłowe i zapisuje wybrany DataFrame."""

    def __init__(self, repository: SelectedColumnsRepository):
        self._repository = repository

    def get_saved_columns(self) -> List[str]:
        dataframe = self._repository.read_dataframe(DATAFRAME_OBJECT)
        return [str(column) for column in dataframe.columns]

    def select_columns(self, selected_columns: List[str]) -> Dict:
        if not selected_columns:
            raise ValueError("Zaznacz przynajmniej jedną kolumnę.")

        if len(selected_columns) != len(set(selected_columns)):
            raise ValueError("Lista zaznaczonych kolumn zawiera powtórzenia.")

        dataframe = self._repository.read_dataframe(DATAFRAME_OBJECT)
        original_columns = {
            str(column): column
            for column in dataframe.columns
        }

        missing_columns = [
            column
            for column in selected_columns
            if column not in original_columns
        ]
        if missing_columns:
            raise ValueError(f"Nie znaleziono kolumn: {missing_columns}")

        selected_dataframe = dataframe[
            [original_columns[column] for column in selected_columns]
        ].copy()

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

        print("\nPRÓBKA df_selected.pkl ODCZYTANA Z BUCKETA:")
        print(saved_dataframe.head(10).to_string(index=False))

        return {
            "selected_dataframe_file": (
                f"gs://{self._repository.bucket_name}/"
                f"{SELECTED_DATAFRAME_OBJECT}"
            ),
            "selected_columns_file": (
                f"gs://{self._repository.bucket_name}/"
                f"{SELECTED_COLUMNS_OBJECT}"
            ),
            "rows": len(saved_dataframe),
            "columns": [
                str(column)
                for column in saved_dataframe.columns
            ],
            "preview_html": saved_dataframe.head(10).to_html(
                index=False,
                escape=True,
            ),
        }


# Zachowane funkcje wywoływane przez columns_ui.py.
def get_saved_columns() -> List[str]:
    return ColumnSelectionService(_repository()).get_saved_columns()


def select_dataframe_columns(selected_columns: List[str]) -> Dict:
    return ColumnSelectionService(_repository()).select_columns(
        selected_columns
    )