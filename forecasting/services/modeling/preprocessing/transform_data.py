
import io
import json
import os
from abc import ABC, abstractmethod
from typing import Any

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

ALLOWED_METHODS = {"scale", "onehot", "passthrough"}


class ObjectStorage(ABC):
    """Kontrakt operacji Cloud Storage używanych przez ten moduł."""

    @property
    @abstractmethod
    def bucket_name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def read_bytes(self, object_name: str) -> bytes:
        raise NotImplementedError

    @abstractmethod
    def upload_bytes(
        self,
        object_name: str,
        content: bytes,
        content_type: str,
    ) -> None:
        raise NotImplementedError


class GoogleCloudStorageAdapter(ObjectStorage):
    """Dostosowuje operacje GCS do interfejsu ObjectStorage."""

    def __init__(self, bucket: storage.Bucket) -> None:
        self._bucket = bucket

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


class TransformDataStore(ABC):
    """Kontrakt repozytorium używany przez usługę transformacji danych."""

    @property
    @abstractmethod
    def bucket_name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def read_pickle(self, object_name: str) -> Any:
        raise NotImplementedError

    @abstractmethod
    def save_pickle(self, value: Any, object_name: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def save_joblib(self, value: Any, object_name: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def save_json(
        self,
        value: dict[str, Any],
        object_name: str,
    ) -> None:
        raise NotImplementedError


class TransformDataRepository(TransformDataStore):
    """Odczytuje i zapisuje pickle, pipeline joblib oraz ustawienia JSON."""

    def __init__(self, storage_adapter: ObjectStorage) -> None:
        self._storage = storage_adapter

    @property
    def bucket_name(self) -> str:
        return self._storage.bucket_name

    def read_pickle(self, object_name: str) -> Any:
        content = self._storage.read_bytes(object_name)
        return pd.read_pickle(io.BytesIO(content))

    def save_pickle(self, value: Any, object_name: str) -> None:
        buffer = io.BytesIO()
        value.to_pickle(buffer)
        self._storage.upload_bytes(
            object_name,
            buffer.getvalue(),
            "application/octet-stream",
        )

    def save_joblib(self, value: Any, object_name: str) -> None:
        buffer = io.BytesIO()
        joblib.dump(value, buffer)
        self._storage.upload_bytes(
            object_name,
            buffer.getvalue(),
            "application/octet-stream",
        )

    def save_json(
        self,
        value: dict[str, Any],
        object_name: str,
    ) -> None:
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


def _get_bucket() -> storage.Bucket:
    """Zwraca bucket GCS wskazany przez GCS_BUCKET_NAME."""
    bucket_name = os.environ.get("GCS_BUCKET_NAME")
    if not bucket_name:
        raise ValueError("Brak zmiennej środowiskowej GCS_BUCKET_NAME.")
    return storage.Client().bucket(bucket_name)


def _repository() -> TransformDataRepository:
    """Tworzy repozytorium GCS używane przez moduł."""
    return TransformDataRepository(
        GoogleCloudStorageAdapter(_get_bucket())
    )


# Zachowane dotychczasowe funkcje pomocnicze.
def _read_pickle(object_name: str) -> Any:
    return _repository().read_pickle(object_name)


def _save_pickle(value: Any, object_name: str) -> None:
    _repository().save_pickle(value, object_name)


def _validate_column_methods(
    column_methods: list[str],
    columns: list[Any],
) -> None:
    """Sprawdza liczbę metod i ich nazwy przed budową transformatora."""
    if len(column_methods) != len(columns):
        raise ValueError(
            "Nie otrzymałem wyboru metody dla każdej kolumny."
        )

    invalid_methods = [
        method
        for method in column_methods
        if method not in ALLOWED_METHODS
    ]
    if invalid_methods:
        raise ValueError(
            f"Nieznana metoda transformacji: {invalid_methods}"
        )


def _group_columns_by_method(
    column_methods: list[str],
    columns: list[Any],
) -> tuple[list[Any], list[Any], list[Any]]:
    """Grupuje kolumny według metody wskazanej w formularzu."""
    scale_columns: list[Any] = []
    onehot_columns: list[Any] = []
    passthrough_columns: list[Any] = []

    for column, method in zip(columns, column_methods):
        if method == "scale":
            scale_columns.append(column)
        elif method == "onehot":
            onehot_columns.append(column)
        else:
            passthrough_columns.append(column)

    return scale_columns, onehot_columns, passthrough_columns


def _validate_scale_columns(
    dataframe: pd.DataFrame,
    columns: list[Any],
) -> None:
    """Sprawdza, czy kolumny StandardScaler są liczbowe."""
    for column in columns:
        if not pd.api.types.is_numeric_dtype(dataframe[column]):
            raise ValueError(
                f"Kolumna „{column}” nie jest liczbowa, "
                "więc nie można zastosować StandardScaler."
            )


def _create_onehot_encoder() -> OneHotEncoder:
    """Tworzy encoder i obsługuje różne wersje scikit-learn."""
    try:
        return OneHotEncoder(
            handle_unknown="ignore",
            sparse_output=False,
        )
    except TypeError:
        # Obsługa starszych wersji scikit-learn.
        return OneHotEncoder(
            handle_unknown="ignore",
            sparse=False,
        )


def _build_transformer_steps(
    scale_columns: list[Any],
    onehot_columns: list[Any],
) -> list[tuple[str, Any, list[Any]]]:
    """Tworzy kroki ColumnTransformer dla skalowania i kodowania."""
    transformers: list[tuple[str, Any, list[Any]]] = []

    if scale_columns:
        transformers.append(
            ("numeric", StandardScaler(), scale_columns)
        )

    if onehot_columns:
        transformers.append(
            ("categorical", _create_onehot_encoder(), onehot_columns)
        )

    return transformers


def _build_transform_settings(
    scale_columns: list[Any],
    onehot_columns: list[Any],
    passthrough_columns: list[Any],
) -> dict[str, list[str]]:
    """Tworzy ustawienia transformacji zapisywane w JSON."""
    return {
        "StandardScaler": [str(column) for column in scale_columns],
        "OneHotEncoder": [str(column) for column in onehot_columns],
        "passthrough": [str(column) for column in passthrough_columns],
    }


class ColumnTransformerFactory:
    """Buduje ColumnTransformer według wyborów użytkownika."""

    @staticmethod
    def create(
        column_methods: list[str],
        columns: list[Any],
        X_train: pd.DataFrame,
    ) -> tuple[ColumnTransformer, dict[str, list[str]]]:
        _validate_column_methods(column_methods, columns)
        scale_columns, onehot_columns, passthrough_columns = (
            _group_columns_by_method(column_methods, columns)
        )
        _validate_scale_columns(X_train, scale_columns)

        if not scale_columns and not onehot_columns:
            raise ValueError(
                "Wybierz przynajmniej jedną kolumnę do StandardScaler "
                "albo OneHotEncoder."
            )

        preprocessor = ColumnTransformer(
            transformers=_build_transformer_steps(
                scale_columns,
                onehot_columns,
            ),
            remainder="passthrough",
            verbose_feature_names_out=True,
        )
        settings = _build_transform_settings(
            scale_columns,
            onehot_columns,
            passthrough_columns,
        )
        return preprocessor, settings


def _validate_matching_columns(
    X_train: pd.DataFrame,
    X_test: pd.DataFrame,
) -> None:
    """Sprawdza, czy zbiory treningowy i testowy mają te same kolumny."""
    if list(X_train.columns) != list(X_test.columns):
        raise ValueError("X_train i X_test mają różne kolumny.")


def _build_training_summary(X_train: pd.DataFrame) -> dict[str, Any]:
    """Buduje kolumny, liczbę wierszy i podgląd dla formularza UI."""
    return {
        "columns": [str(column) for column in X_train.columns],
        "preview_html": X_train.head(10).to_html(
            index=False,
            escape=True,
        ),
        "rows": len(X_train),
    }


def _create_pipeline(preprocessor: ColumnTransformer) -> Pipeline:
    """Umieszcza ColumnTransformer w pipeline scikit-learn."""
    return Pipeline(steps=[("preprocessor", preprocessor)])


def _transform_train_and_test(
    pipeline: Pipeline,
    X_train: pd.DataFrame,
    X_test: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    """Dopasowuje preprocessing na train i stosuje go do train oraz test."""
    train_array = pipeline.fit_transform(X_train)
    test_array = pipeline.transform(X_test)
    feature_names = pipeline.get_feature_names_out().tolist()

    transformed_train = pd.DataFrame(
        train_array,
        columns=feature_names,
        index=X_train.index,
    )
    transformed_test = pd.DataFrame(
        test_array,
        columns=feature_names,
        index=X_test.index,
    )
    return transformed_train, transformed_test, feature_names


def _save_transformation_artifacts(
    repository: TransformDataStore,
    X_train: pd.DataFrame,
    X_test: pd.DataFrame,
    pipeline: Pipeline,
    settings: dict[str, list[str]],
) -> None:
    """Zapisuje przekształcone zbiory, fitted pipeline i wybory kolumn."""
    repository.save_pickle(X_train, X_TRAIN_TRANSFORMED_OBJECT)
    repository.save_pickle(X_test, X_TEST_TRANSFORMED_OBJECT)
    repository.save_joblib(pipeline, PREPROCESSOR_OBJECT)
    repository.save_json(settings, TRANSFORM_SETTINGS_OBJECT)


def _build_transform_result(
    repository: TransformDataStore,
    X_train: pd.DataFrame,
    X_test: pd.DataFrame,
    y_train: Any,
    y_test: Any,
    feature_names: list[str],
    settings: dict[str, list[str]],
) -> dict[str, Any]:
    """Buduje wynik zawierający ścieżki i pola używane przez UI."""
    bucket_name = repository.bucket_name
    return {
        "bucket": bucket_name,
        "X_train_file": (
            f"gs://{bucket_name}/{X_TRAIN_TRANSFORMED_OBJECT}"
        ),
        "X_test_file": (
            f"gs://{bucket_name}/{X_TEST_TRANSFORMED_OBJECT}"
        ),
        "preprocessor_file": (
            f"gs://{bucket_name}/{PREPROCESSOR_OBJECT}"
        ),
        "settings_file": (
            f"gs://{bucket_name}/{TRANSFORM_SETTINGS_OBJECT}"
        ),
        "X_train_rows": len(X_train),
        "X_test_rows": len(X_test),
        "y_train_rows": len(y_train),
        "y_test_rows": len(y_test),
        "columns": feature_names,
        "selected_methods": settings,
        "preview_html": X_train.head(10).to_html(
            index=False,
            escape=True,
        ),
    }


class DataTransformationService:
    """Koordynuje podgląd i transformację zbiorów X_train oraz X_test."""

    def __init__(self, repository: TransformDataStore) -> None:
        self._repository = repository

    def get_summary(self) -> dict[str, Any]:
        X_train = self._repository.read_pickle(X_TRAIN_OBJECT)
        X_test = self._repository.read_pickle(X_TEST_OBJECT)
        _validate_matching_columns(X_train, X_test)
        return _build_training_summary(X_train)

    def transform(self, column_methods: list[str]) -> dict[str, Any]:
        """Koordynuje dopasowanie, transformację i zapis artefaktów."""
        X_train = self._repository.read_pickle(X_TRAIN_OBJECT)
        X_test = self._repository.read_pickle(X_TEST_OBJECT)
        y_train = self._repository.read_pickle(Y_TRAIN_OBJECT)
        y_test = self._repository.read_pickle(Y_TEST_OBJECT)
        _validate_matching_columns(X_train, X_test)

        preprocessor, settings = ColumnTransformerFactory.create(
            column_methods,
            list(X_train.columns),
            X_train,
        )
        pipeline = _create_pipeline(preprocessor)
        transformed_train, transformed_test, feature_names = (
            _transform_train_and_test(pipeline, X_train, X_test)
        )
        _save_transformation_artifacts(
            self._repository,
            transformed_train,
            transformed_test,
            pipeline,
            settings,
        )
        return _build_transform_result(
            self._repository,
            transformed_train,
            transformed_test,
            y_train,
            y_test,
            feature_names,
            settings,
        )


def _create_repository() -> TransformDataRepository:
    """Składa adapter GCS i repozytorium transformacji danych."""
    return TransformDataRepository(
        GoogleCloudStorageAdapter(_get_bucket())
    )


def _create_service() -> DataTransformationService:
    """Tworzy usługę transformacji z repozytorium."""
    return DataTransformationService(_create_repository())


# Zachowane funkcje publiczne wywoływane przez transform_data_ui.py.
def get_transform_summary() -> dict[str, Any]:
    return _create_service().get_summary()


def transform_data(column_methods: list[str]) -> dict[str, Any]:
    return _create_service().transform(column_methods)