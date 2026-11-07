# import io
# import json
# import os

# import joblib
# import pandas as pd
# from google.cloud import storage
# from sklearn.compose import ColumnTransformer
# from sklearn.pipeline import Pipeline
# from sklearn.preprocessing import OneHotEncoder, StandardScaler


# X_TRAIN_OBJECT = "data/processed/X_train.pkl"
# X_TEST_OBJECT = "data/processed/X_test.pkl"
# Y_TRAIN_OBJECT = "data/processed/y_train.pkl"
# Y_TEST_OBJECT = "data/processed/y_test.pkl"

# X_TRAIN_TRANSFORMED_OBJECT = "data/processed/X_train_transformed.pkl"
# X_TEST_TRANSFORMED_OBJECT = "data/processed/X_test_transformed.pkl"
# PREPROCESSOR_OBJECT = "data/processed/preprocessor_pipeline.pkl"
# TRANSFORM_SETTINGS_OBJECT = "data/processed/transform_settings.json"


# def _get_bucket():
#     bucket_name = os.environ.get("GCS_BUCKET_NAME")
#     if not bucket_name:
#         raise ValueError("Brak zmiennej środowiskowej GCS_BUCKET_NAME.")

#     return storage.Client().bucket(bucket_name)


# def _read_pickle(object_name: str):
#     bucket = _get_bucket()
#     blob = bucket.blob(object_name)

#     if not blob.exists():
#         raise FileNotFoundError(
#             f"Nie znaleziono pliku gs://{bucket.name}/{object_name}"
#         )

#     return pd.read_pickle(io.BytesIO(blob.download_as_bytes()))


# def _save_pickle(value, object_name: str) -> None:
#     bucket = _get_bucket()
#     buffer = io.BytesIO()
#     value.to_pickle(buffer)
#     buffer.seek(0)

#     bucket.blob(object_name).upload_from_file(
#         buffer,
#         content_type="application/octet-stream",
#     )


# def get_transform_summary() -> dict:
#     """Odczytuje X_train i X_test z bucketa i przygotowuje listę kolumn."""
#     X_train = _read_pickle(X_TRAIN_OBJECT)
#     X_test = _read_pickle(X_TEST_OBJECT)

#     if list(X_train.columns) != list(X_test.columns):
#         raise ValueError("X_train i X_test mają różne kolumny.")

#     return {
#         "columns": [str(column) for column in X_train.columns],
#         "preview_html": X_train.head(10).to_html(index=False, escape=True),
#         "rows": len(X_train),
#     }


# def transform_data(column_methods: list[str]) -> dict:
#     """
#     Stosuje wybory użytkownika:
#     - scale: StandardScaler,
#     - onehot: OneHotEncoder,
#     - passthrough: pozostawienie kolumny bez zmian.

#     Pipeline jest dopasowywany wyłącznie na X_train.
#     """
#     X_train = _read_pickle(X_TRAIN_OBJECT)
#     X_test = _read_pickle(X_TEST_OBJECT)
#     y_train = _read_pickle(Y_TRAIN_OBJECT)
#     y_test = _read_pickle(Y_TEST_OBJECT)

#     columns = list(X_train.columns)

#     if list(X_test.columns) != columns:
#         raise ValueError("X_train i X_test mają różne kolumny.")

#     if len(column_methods) != len(columns):
#         raise ValueError(
#             "Nie otrzymałem wyboru metody dla każdej kolumny."
#         )

#     allowed_methods = {"scale", "onehot", "passthrough"}
#     invalid_methods = [
#         method for method in column_methods if method not in allowed_methods
#     ]
#     if invalid_methods:
#         raise ValueError(f"Nieznana metoda transformacji: {invalid_methods}")

#     scale_columns = []
#     onehot_columns = []
#     passthrough_columns = []

#     for column, method in zip(columns, column_methods):
#         if method == "scale":
#             if not pd.api.types.is_numeric_dtype(X_train[column]):
#                 raise ValueError(
#                     f"Kolumna „{column}” nie jest liczbowa, "
#                     "więc nie można zastosować StandardScaler."
#                 )
#             scale_columns.append(column)

#         elif method == "onehot":
#             onehot_columns.append(column)

#         else:
#             passthrough_columns.append(column)

#     if not scale_columns and not onehot_columns:
#         raise ValueError(
#             "Wybierz przynajmniej jedną kolumnę do StandardScaler "
#             "albo OneHotEncoder."
#         )

#     transformers = []

#     if scale_columns:
#         transformers.append(
#             ("numeric", StandardScaler(), scale_columns)
#         )

#     if onehot_columns:
#         try:
#             encoder = OneHotEncoder(
#                 handle_unknown="ignore",
#                 sparse_output=False,
#             )
#         except TypeError:
#             # Obsługa starszych wersji scikit-learn.
#             encoder = OneHotEncoder(
#                 handle_unknown="ignore",
#                 sparse=False,
#             )

#         transformers.append(
#             ("categorical", encoder, onehot_columns)
#         )

#     preprocessor = ColumnTransformer(
#         transformers=transformers,
#         remainder="passthrough",
#         verbose_feature_names_out=True,
#     )

#     pipeline = Pipeline(
#         steps=[
#             ("preprocessor", preprocessor),
#         ]
#     )

#     # Dopasowanie wyłącznie na zbiorze treningowym.
#     train_array = pipeline.fit_transform(X_train)

#     # X_test jest tylko przekształcany; nie jest używany do fit.
#     test_array = pipeline.transform(X_test)

#     feature_names = pipeline.get_feature_names_out().tolist()

#     X_train_transformed = pd.DataFrame(
#         train_array,
#         columns=feature_names,
#         index=X_train.index,
#     )
#     X_test_transformed = pd.DataFrame(
#         test_array,
#         columns=feature_names,
#         index=X_test.index,
#     )

#     _save_pickle(
#         X_train_transformed,
#         X_TRAIN_TRANSFORMED_OBJECT,
#     )
#     _save_pickle(
#         X_test_transformed,
#         X_TEST_TRANSFORMED_OBJECT,
#     )

#     bucket = _get_bucket()
#     pipeline_buffer = io.BytesIO()
#     joblib.dump(pipeline, pipeline_buffer)
#     pipeline_buffer.seek(0)

#     bucket.blob(PREPROCESSOR_OBJECT).upload_from_file(
#         pipeline_buffer,
#         content_type="application/octet-stream",
#     )

#     settings = {
#         "StandardScaler": [str(column) for column in scale_columns],
#         "OneHotEncoder": [str(column) for column in onehot_columns],
#         "passthrough": [str(column) for column in passthrough_columns],
#     }
#     bucket.blob(TRANSFORM_SETTINGS_OBJECT).upload_from_string(
#         json.dumps(settings, ensure_ascii=False, indent=2),
#         content_type="application/json; charset=utf-8",
#     )

#     # Klucze z liczbą wierszy X i y są zwracane jawnie,
#     # żeby strona wynikowa nie odwoływała się do brakującego y_train_rows.
#     return {
#         "bucket": bucket.name,
#         "X_train_file": (
#             f"gs://{bucket.name}/{X_TRAIN_TRANSFORMED_OBJECT}"
#         ),
#         "X_test_file": (
#             f"gs://{bucket.name}/{X_TEST_TRANSFORMED_OBJECT}"
#         ),
#         "preprocessor_file": (
#             f"gs://{bucket.name}/{PREPROCESSOR_OBJECT}"
#         ),
#         "settings_file": (
#             f"gs://{bucket.name}/{TRANSFORM_SETTINGS_OBJECT}"
#         ),
#         "X_train_rows": len(X_train_transformed),
#         "X_test_rows": len(X_test_transformed),
#         "y_train_rows": len(y_train),
#         "y_test_rows": len(y_test),
#         "columns": feature_names,
#         "selected_methods": settings,
#         "preview_html": X_train_transformed.head(10).to_html(
#             index=False,
#             escape=True,
#         ),
#     }

import io
import json
import os
from abc import ABC, abstractmethod

import joblib
import pandas as pd
from google.cloud import storage
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


X_TRAIN_OBJECT = "data/processed/X_train.pkl"
X_TEST_OBJECT = "data/processed/X_test.pkl"
Y_TRAIN_OBJECT = "data/processed/y_train.pkl"
Y_TEST_OBJECT = "data/processed/y_test.pkl"

X_TRAIN_TRANSFORMED_OBJECT = "data/processed/X_train_transformed.pkl"
X_TEST_TRANSFORMED_OBJECT = "data/processed/X_test_transformed.pkl"
PREPROCESSOR_OBJECT = "data/processed/preprocessor_pipeline.pkl"
TRANSFORM_SETTINGS_OBJECT = "data/processed/transform_settings.json"


# Adapter: wspólny interfejs dostępu do Cloud Storage.
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
            raise ValueError(
                "Brak zmiennej środowiskowej GCS_BUCKET_NAME."
            )

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


# Repository: odczytuje i zapisuje dane używane przez ten etap.
class TransformDataRepository:
    def __init__(self, storage_adapter: ObjectStorage):
        self._storage = storage_adapter

    @property
    def bucket_name(self) -> str:
        return self._storage.bucket_name

    def read_pickle(self, object_name: str):
        content = self._storage.read_bytes(object_name)
        return pd.read_pickle(io.BytesIO(content))

    def save_pickle(self, value, object_name: str) -> None:
        buffer = io.BytesIO()
        value.to_pickle(buffer)
        self._storage.upload_bytes(
            object_name,
            buffer.getvalue(),
            "application/octet-stream",
        )

    def save_joblib(self, value, object_name: str) -> None:
        buffer = io.BytesIO()
        joblib.dump(value, buffer)
        self._storage.upload_bytes(
            object_name,
            buffer.getvalue(),
            "application/octet-stream",
        )

    def save_json(self, value: dict, object_name: str) -> None:
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


def _repository() -> TransformDataRepository:
    return TransformDataRepository(GoogleCloudStorageAdapter())


# Zachowane dotychczasowe funkcje pomocnicze.
def _get_bucket():
    bucket_name = os.environ.get("GCS_BUCKET_NAME")
    if not bucket_name:
        raise ValueError("Brak zmiennej środowiskowej GCS_BUCKET_NAME.")
    return storage.Client().bucket(bucket_name)


def _read_pickle(object_name: str):
    return _repository().read_pickle(object_name)


def _save_pickle(value, object_name: str) -> None:
    _repository().save_pickle(value, object_name)


class ColumnTransformerFactory:
    """Buduje ColumnTransformer według wyborów użytkownika."""

    @staticmethod
    def create(
        column_methods: list[str],
        columns: list,
        X_train: pd.DataFrame,
    ) -> tuple[ColumnTransformer, dict]:
        if len(column_methods) != len(columns):
            raise ValueError(
                "Nie otrzymałem wyboru metody dla każdej kolumny."
            )

        allowed_methods = {"scale", "onehot", "passthrough"}
        invalid_methods = [
            method
            for method in column_methods
            if method not in allowed_methods
        ]
        if invalid_methods:
            raise ValueError(
                f"Nieznana metoda transformacji: {invalid_methods}"
            )

        scale_columns = []
        onehot_columns = []
        passthrough_columns = []

        for column, method in zip(columns, column_methods):
            if method == "scale":
                if not pd.api.types.is_numeric_dtype(X_train[column]):
                    raise ValueError(
                        f"Kolumna „{column}” nie jest liczbowa, "
                        "więc nie można zastosować StandardScaler."
                    )
                scale_columns.append(column)

            elif method == "onehot":
                onehot_columns.append(column)

            else:
                passthrough_columns.append(column)

        if not scale_columns and not onehot_columns:
            raise ValueError(
                "Wybierz przynajmniej jedną kolumnę do StandardScaler "
                "albo OneHotEncoder."
            )

        transformers = []

        if scale_columns:
            transformers.append(
                ("numeric", StandardScaler(), scale_columns)
            )

        if onehot_columns:
            try:
                encoder = OneHotEncoder(
                    handle_unknown="ignore",
                    sparse_output=False,
                )
            except TypeError:
                # Obsługa starszych wersji scikit-learn.
                encoder = OneHotEncoder(
                    handle_unknown="ignore",
                    sparse=False,
                )

            transformers.append(
                ("categorical", encoder, onehot_columns)
            )

        preprocessor = ColumnTransformer(
            transformers=transformers,
            remainder="passthrough",
            verbose_feature_names_out=True,
        )

        settings = {
            "StandardScaler": [
                str(column) for column in scale_columns
            ],
            "OneHotEncoder": [
                str(column) for column in onehot_columns
            ],
            "passthrough": [
                str(column) for column in passthrough_columns
            ],
        }

        return preprocessor, settings


class DataTransformationService:
    """Przygotowuje podgląd i przekształca X_train oraz X_test."""

    def __init__(self, repository: TransformDataRepository):
        self._repository = repository

    def get_summary(self) -> dict:
        X_train = self._repository.read_pickle(X_TRAIN_OBJECT)
        X_test = self._repository.read_pickle(X_TEST_OBJECT)

        if list(X_train.columns) != list(X_test.columns):
            raise ValueError("X_train i X_test mają różne kolumny.")

        return {
            "columns": [str(column) for column in X_train.columns],
            "preview_html": X_train.head(10).to_html(
                index=False,
                escape=True,
            ),
            "rows": len(X_train),
        }

    def transform(self, column_methods: list[str]) -> dict:
        X_train = self._repository.read_pickle(X_TRAIN_OBJECT)
        X_test = self._repository.read_pickle(X_TEST_OBJECT)
        y_train = self._repository.read_pickle(Y_TRAIN_OBJECT)
        y_test = self._repository.read_pickle(Y_TEST_OBJECT)

        columns = list(X_train.columns)

        if list(X_test.columns) != columns:
            raise ValueError("X_train i X_test mają różne kolumny.")

        preprocessor, settings = ColumnTransformerFactory.create(
            column_methods,
            columns,
            X_train,
        )

        pipeline = Pipeline(
            steps=[
                ("preprocessor", preprocessor),
            ]
        )

        # Dopasowanie preprocessing tylko na danych treningowych.
        train_array = pipeline.fit_transform(X_train)

        # Zbiór testowy jest tylko przekształcany.
        test_array = pipeline.transform(X_test)

        feature_names = pipeline.get_feature_names_out().tolist()

        X_train_transformed = pd.DataFrame(
            train_array,
            columns=feature_names,
            index=X_train.index,
        )
        X_test_transformed = pd.DataFrame(
            test_array,
            columns=feature_names,
            index=X_test.index,
        )

        self._repository.save_pickle(
            X_train_transformed,
            X_TRAIN_TRANSFORMED_OBJECT,
        )
        self._repository.save_pickle(
            X_test_transformed,
            X_TEST_TRANSFORMED_OBJECT,
        )
        self._repository.save_joblib(
            pipeline,
            PREPROCESSOR_OBJECT,
        )
        self._repository.save_json(
            settings,
            TRANSFORM_SETTINGS_OBJECT,
        )

        return {
            "bucket": self._repository.bucket_name,
            "X_train_file": (
                f"gs://{self._repository.bucket_name}/"
                f"{X_TRAIN_TRANSFORMED_OBJECT}"
            ),
            "X_test_file": (
                f"gs://{self._repository.bucket_name}/"
                f"{X_TEST_TRANSFORMED_OBJECT}"
            ),
            "preprocessor_file": (
                f"gs://{self._repository.bucket_name}/"
                f"{PREPROCESSOR_OBJECT}"
            ),
            "settings_file": (
                f"gs://{self._repository.bucket_name}/"
                f"{TRANSFORM_SETTINGS_OBJECT}"
            ),
            "X_train_rows": len(X_train_transformed),
            "X_test_rows": len(X_test_transformed),
            "y_train_rows": len(y_train),
            "y_test_rows": len(y_test),
            "columns": feature_names,
            "selected_methods": settings,
            "preview_html": X_train_transformed.head(10).to_html(
                index=False,
                escape=True,
            ),
        }


# Zachowane funkcje wywoływane przez transform_data_ui.py.
def get_transform_summary() -> dict:
    return DataTransformationService(_repository()).get_summary()


def transform_data(column_methods: list[str]) -> dict:
    return DataTransformationService(_repository()).transform(
        column_methods
    )