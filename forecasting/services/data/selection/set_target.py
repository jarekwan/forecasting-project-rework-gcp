# import io
# import json
# import os

# import pandas as pd
# from google.cloud import storage


# INPUT_OBJECT = "data/processed/df_rolling.pkl"

# X_TRAIN_OBJECT = "data/processed/X_train.pkl"
# X_TEST_OBJECT = "data/processed/X_test.pkl"
# Y_TRAIN_OBJECT = "data/processed/y_train.pkl"
# Y_TEST_OBJECT = "data/processed/y_test.pkl"
# SETTINGS_OBJECT = "data/processed/target_settings.json"


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
#             f"Nie znaleziono pliku gs://{bucket.name}/{object_name}"
#         )

#     return pd.read_pickle(io.BytesIO(blob.download_as_bytes()))


# def _save_pickle(value, object_name: str) -> str:
#     bucket = _get_bucket()
#     buffer = io.BytesIO()
#     value.to_pickle(buffer)
#     buffer.seek(0)

#     bucket.blob(object_name).upload_from_file(
#         buffer,
#         content_type="application/octet-stream",
#     )

#     return f"gs://{bucket.name}/{object_name}"


# def get_target_options() -> dict:
#     """Zwraca numeryczne kolumny celu i nazwę indeksu daty."""
#     df = _read_dataframe(INPUT_OBJECT)

#     if df.empty:
#         raise ValueError("df_rolling.pkl nie zawiera danych.")

#     if not isinstance(df.index, pd.DatetimeIndex):
#         raise ValueError(
#             "Data w df_rolling.pkl nie jest indeksem DatetimeIndex. "
#             "Uruchom ponownie etapy od przygotowania daty."
#         )

#     if not df.index.is_monotonic_increasing:
#         df = df.sort_index()

#     if not df.index.is_unique:
#         raise ValueError(
#             "Indeks daty zawiera duplikaty. Sprawdź etap przygotowania daty."
#         )

#     target_columns = [
#         str(column)
#         for column in df.select_dtypes(include="number").columns
#     ]

#     if not target_columns:
#         raise ValueError("Nie znaleziono numerycznych kolumn celu.")

#     date_name = str(df.index.name or "date")

#     return {
#         "target_columns": target_columns,
#         "date_columns": [date_name],
#         "preview_html": df.head(10).to_html(index=True, escape=True),
#     }


# def prepare_train_test(
#     target_column: str,
#     date_column: str,
#     test_fraction: float,
# ) -> dict:
#     """
#     Używa indeksu daty do chronologicznego podziału.
#     Indeks zostaje zachowany dla kontroli kolejności, ale nie trafia do X jako kolumna.
#     """
#     df = _read_dataframe(INPUT_OBJECT)

#     if not isinstance(df.index, pd.DatetimeIndex):
#         raise ValueError(
#             "Data w df_rolling.pkl nie jest indeksem DatetimeIndex. "
#             "Uruchom ponownie etapy od przygotowania daty."
#         )

#     expected_date_name = str(df.index.name or "date")
#     if date_column != expected_date_name:
#         raise ValueError(
#             f"Wybrana data „{date_column}” nie jest indeksem daty "
#             f"„{expected_date_name}”."
#         )

#     if target_column not in {str(column) for column in df.columns}:
#         raise ValueError(f"Nie znaleziono kolumny celu: {target_column}")

#     original_columns = {str(column): column for column in df.columns}
#     target = original_columns[target_column]

#     if not pd.api.types.is_numeric_dtype(df[target]):
#         raise ValueError(
#             f"Kolumna celu „{target_column}” musi zawierać dane liczbowe."
#         )

#     if not 0 < test_fraction < 1:
#         raise ValueError("Udział testowy musi być większy od 0 i mniejszy od 1.")

#     # Chronologiczne sortowanie po indeksie daty.
#     df = df.sort_index().copy()

#     # Nie pozwala, by surowa data była kolumną cech X.
#     # Data pozostaje indeksem i służy do zachowania kolejności.
#     if target in df.columns:
#         y = df[target].copy()
#         X = df.drop(columns=[target]).copy()
#     else:
#         raise ValueError(f"Nie znaleziono kolumny celu: {target_column}")

#     valid_target_rows = y.notna()
#     X = X.loc[valid_target_rows]
#     y = y.loc[valid_target_rows]

#     if len(X) < 2:
#         raise ValueError("Za mało poprawnych wierszy do podziału train/test.")

#     split_point = int(len(X) * (1 - test_fraction))
#     if split_point < 1 or split_point >= len(X):
#         raise ValueError("Podział daje pusty zbiór treningowy albo testowy.")

#     X_train = X.iloc[:split_point].copy()
#     X_test = X.iloc[split_point:].copy()
#     y_train = y.iloc[:split_point].copy()
#     y_test = y.iloc[split_point:].copy()

#     bucket = _get_bucket()

#     X_train_file = _save_pickle(X_train, X_TRAIN_OBJECT)
#     X_test_file = _save_pickle(X_test, X_TEST_OBJECT)
#     y_train_file = _save_pickle(y_train, Y_TRAIN_OBJECT)
#     y_test_file = _save_pickle(y_test, Y_TEST_OBJECT)

#     settings = {
#         "target_column": target_column,
#         "date_index": expected_date_name,
#         "test_fraction": float(test_fraction),
#         "feature_columns": [str(column) for column in X.columns],
#         "train_rows": len(X_train),
#         "test_rows": len(X_test),
#     }

#     settings_blob = bucket.blob(SETTINGS_OBJECT)
#     settings_blob.upload_from_string(
#         json.dumps(settings, ensure_ascii=False, indent=2),
#         content_type="application/json; charset=utf-8",
#     )

#     preview = X_train.head(10).copy()
#     preview[target_column] = y_train.head(10)

#     return {
#         "target_column": target_column,
#         "date_column": expected_date_name,
#         "feature_columns": [str(column) for column in X.columns],
#         "train_rows": len(X_train),
#         "test_rows": len(X_test),
#         "X_train_file": X_train_file,
#         "X_test_file": X_test_file,
#         "y_train_file": y_train_file,
#         "y_test_file": y_test_file,
#         "settings_file": f"gs://{bucket.name}/{SETTINGS_OBJECT}",
#         "preview_html": preview.to_html(index=True, escape=True),
#     }

import io
import json
import os
from abc import ABC, abstractmethod

import pandas as pd
from google.cloud import storage


INPUT_OBJECT = "data/processed/df_rolling.pkl"

X_TRAIN_OBJECT = "data/processed/X_train.pkl"
X_TEST_OBJECT = "data/processed/X_test.pkl"
Y_TRAIN_OBJECT = "data/processed/y_train.pkl"
Y_TEST_OBJECT = "data/processed/y_test.pkl"
SETTINGS_OBJECT = "data/processed/target_settings.json"


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
                f"Nie znaleziono pliku "
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


# Repository: odpowiada za zapis i odczyt DataFrame'ów, Series i ustawień.
class TargetDataRepository:
    def __init__(self, storage_adapter: ObjectStorage):
        self._storage = storage_adapter

    @property
    def bucket_name(self) -> str:
        return self._storage.bucket_name

    def read_dataframe(self, object_name: str) -> pd.DataFrame:
        content = self._storage.read_bytes(object_name)
        return pd.read_pickle(io.BytesIO(content))

    def save_pickle(self, value, object_name: str) -> str:
        buffer = io.BytesIO()
        value.to_pickle(buffer)

        self._storage.upload_bytes(
            object_name,
            buffer.getvalue(),
            "application/octet-stream",
        )
        return f"gs://{self.bucket_name}/{object_name}"

    def save_json(self, value: dict, object_name: str) -> str:
        content = json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
        ).encode("utf-8")

        self._storage.upload_bytes(
            object_name,
            content,
            "application/json; charset=utf-8",
        )
        return f"gs://{self.bucket_name}/{object_name}"


def _repository() -> TargetDataRepository:
    return TargetDataRepository(GoogleCloudStorageAdapter())


# Zachowane dotychczasowe funkcje pomocnicze.
def _get_bucket():
    bucket_name = os.environ.get("GCS_BUCKET_NAME")
    if not bucket_name:
        raise ValueError("Brak zmiennej środowiskowej GCS_BUCKET_NAME.")

    return storage.Client().bucket(bucket_name)


def _read_dataframe(object_name: str) -> pd.DataFrame:
    return _repository().read_dataframe(object_name)


def _save_pickle(value, object_name: str) -> str:
    return _repository().save_pickle(value, object_name)


class TargetPreparationService:
    """Przygotowuje wybór celu oraz chronologiczny podział X i y."""

    def __init__(self, repository: TargetDataRepository):
        self._repository = repository

    def get_options(self) -> dict:
        dataframe = self._repository.read_dataframe(INPUT_OBJECT)

        if dataframe.empty:
            raise ValueError("df_rolling.pkl nie zawiera danych.")

        if not isinstance(dataframe.index, pd.DatetimeIndex):
            raise ValueError(
                "Data w df_rolling.pkl nie jest indeksem DatetimeIndex. "
                "Uruchom ponownie etapy od przygotowania daty."
            )

        if not dataframe.index.is_monotonic_increasing:
            dataframe = dataframe.sort_index()

        if not dataframe.index.is_unique:
            raise ValueError(
                "Indeks daty zawiera duplikaty. "
                "Sprawdź etap przygotowania daty."
            )

        target_columns = [
            str(column)
            for column in dataframe.select_dtypes(include="number").columns
        ]

        if not target_columns:
            raise ValueError("Nie znaleziono numerycznych kolumn celu.")

        date_name = str(dataframe.index.name or "date")

        return {
            "target_columns": target_columns,
            "date_columns": [date_name],
            "preview_html": dataframe.head(10).to_html(
                index=True,
                escape=True,
            ),
        }

    def prepare_train_test(
        self,
        target_column: str,
        date_column: str,
        test_fraction: float,
    ) -> dict:
        dataframe = self._repository.read_dataframe(INPUT_OBJECT)

        if not isinstance(dataframe.index, pd.DatetimeIndex):
            raise ValueError(
                "Data w df_rolling.pkl nie jest indeksem DatetimeIndex. "
                "Uruchom ponownie etapy od przygotowania daty."
            )

        expected_date_name = str(dataframe.index.name or "date")
        if date_column != expected_date_name:
            raise ValueError(
                f"Wybrana data „{date_column}” nie jest indeksem daty "
                f"„{expected_date_name}”."
            )

        original_columns = {
            str(column): column
            for column in dataframe.columns
        }
        if target_column not in original_columns:
            raise ValueError(
                f"Nie znaleziono kolumny celu: {target_column}"
            )

        target = original_columns[target_column]
        if not pd.api.types.is_numeric_dtype(dataframe[target]):
            raise ValueError(
                f"Kolumna celu „{target_column}” "
                "musi zawierać dane liczbowe."
            )

        if not 0 < test_fraction < 1:
            raise ValueError(
                "Udział testowy musi być większy od 0 i mniejszy od 1."
            )

        # Sortuje według indeksu daty, aby podział był chronologiczny.
        dataframe = dataframe.sort_index().copy()

        y = dataframe[target].copy()
        X = dataframe.drop(columns=[target]).copy()

        # Usuwa z X i y te same wiersze, w których cel nie ma wartości.
        valid_target_rows = y.notna()
        X = X.loc[valid_target_rows]
        y = y.loc[valid_target_rows]

        if len(X) < 2:
            raise ValueError(
                "Za mało poprawnych wierszy do podziału train/test."
            )

        split_point = int(len(X) * (1 - test_fraction))
        if split_point < 1 or split_point >= len(X):
            raise ValueError(
                "Podział daje pusty zbiór treningowy albo testowy."
            )

        X_train = X.iloc[:split_point].copy()
        X_test = X.iloc[split_point:].copy()
        y_train = y.iloc[:split_point].copy()
        y_test = y.iloc[split_point:].copy()

        X_train_file = self._repository.save_pickle(
            X_train,
            X_TRAIN_OBJECT,
        )
        X_test_file = self._repository.save_pickle(
            X_test,
            X_TEST_OBJECT,
        )
        y_train_file = self._repository.save_pickle(
            y_train,
            Y_TRAIN_OBJECT,
        )
        y_test_file = self._repository.save_pickle(
            y_test,
            Y_TEST_OBJECT,
        )

        settings = {
            "target_column": target_column,
            "date_index": expected_date_name,
            "test_fraction": float(test_fraction),
            "feature_columns": [
                str(column)
                for column in X.columns
            ],
            "train_rows": len(X_train),
            "test_rows": len(X_test),
        }
        settings_file = self._repository.save_json(
            settings,
            SETTINGS_OBJECT,
        )

        preview = X_train.head(10).copy()
        preview[target_column] = y_train.head(10)

        return {
            "target_column": target_column,
            "date_column": expected_date_name,
            "feature_columns": [
                str(column)
                for column in X.columns
            ],
            "train_rows": len(X_train),
            "test_rows": len(X_test),
            "X_train_file": X_train_file,
            "X_test_file": X_test_file,
            "y_train_file": y_train_file,
            "y_test_file": y_test_file,
            "settings_file": settings_file,
            "preview_html": preview.to_html(
                index=True,
                escape=True,
            ),
        }


# Zachowane funkcje wywoływane przez set_target_ui.py.
def get_target_options() -> dict:
    return TargetPreparationService(_repository()).get_options()


def prepare_train_test(
    target_column: str,
    date_column: str,
    test_fraction: float,
) -> dict:
    return TargetPreparationService(_repository()).prepare_train_test(
        target_column,
        date_column,
        test_fraction,
    )