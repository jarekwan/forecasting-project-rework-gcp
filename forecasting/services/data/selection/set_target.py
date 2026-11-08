
import io
import json
import os
from abc import ABC, abstractmethod
from typing import Any

import pandas as pd
from google.cloud import storage


INPUT_OBJECT = "data/processed/df_rolling.pkl"

X_TRAIN_OBJECT = "data/processed/X_train.pkl"
X_TEST_OBJECT = "data/processed/X_test.pkl"
Y_TRAIN_OBJECT = "data/processed/y_train.pkl"
Y_TEST_OBJECT = "data/processed/y_test.pkl"
SETTINGS_OBJECT = "data/processed/target_settings.json"


class ObjectStorage(ABC):
    """Kontrakt operacji Cloud Storage potrzebnych w tym module."""

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


class TargetDataStore(ABC):
    """Kontrakt repozytorium używany przez logikę przygotowania celu."""

    @abstractmethod
    def read_dataframe(self, object_name: str) -> pd.DataFrame:
        raise NotImplementedError

    @abstractmethod
    def save_pickle(self, value: Any, object_name: str) -> str:
        raise NotImplementedError

    @abstractmethod
    def save_json(
        self,
        value: dict[str, Any],
        object_name: str,
    ) -> str:
        raise NotImplementedError


class TargetDataRepository(TargetDataStore):
    """Odczytuje i zapisuje DataFrame'y, Series oraz ustawienia w GCS."""

    def __init__(self, storage_adapter: ObjectStorage) -> None:
        self._storage = storage_adapter

    def read_dataframe(self, object_name: str) -> pd.DataFrame:
        content = self._storage.read_bytes(object_name)
        return pd.read_pickle(io.BytesIO(content))

    def save_pickle(self, value: Any, object_name: str) -> str:
        buffer = io.BytesIO()
        value.to_pickle(buffer)
        self._storage.upload_bytes(
            object_name,
            buffer.getvalue(),
            "application/octet-stream",
        )
        return f"gs://{self._storage.bucket_name}/{object_name}"

    def save_json(
        self,
        value: dict[str, Any],
        object_name: str,
    ) -> str:
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
        return f"gs://{self._storage.bucket_name}/{object_name}"


def _validate_datetime_index(dataframe: pd.DataFrame) -> str:
    """Sprawdza indeks daty i zwraca jego nazwę używaną w UI."""
    if not isinstance(dataframe.index, pd.DatetimeIndex):
        raise ValueError(
            "Data w df_rolling.pkl nie jest indeksem DatetimeIndex. "
            "Uruchom ponownie etapy od przygotowania daty."
        )
    return str(dataframe.index.name or "date")


def _sort_by_date(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Zwraca kopię danych posortowaną chronologicznie po indeksie."""
    return dataframe.sort_index().copy()


def _get_numeric_target_columns(dataframe: pd.DataFrame) -> list[str]:
    """Wybiera numeryczne kolumny, które mogą być celem modelu."""
    return [
        str(column)
        for column in dataframe.select_dtypes(include="number").columns
    ]


def _build_target_options(dataframe: pd.DataFrame) -> dict[str, Any]:
    """Buduje kolumny formularza oraz HTML podglądu danych."""
    if dataframe.empty:
        raise ValueError("df_rolling.pkl nie zawiera danych.")

    date_name = _validate_datetime_index(dataframe)
    sorted_dataframe = _sort_by_date(dataframe)

    if not sorted_dataframe.index.is_unique:
        raise ValueError(
            "Indeks daty zawiera duplikaty. "
            "Sprawdź etap przygotowania daty."
        )

    target_columns = _get_numeric_target_columns(sorted_dataframe)
    if not target_columns:
        raise ValueError("Nie znaleziono numerycznych kolumn celu.")

    return {
        "target_columns": target_columns,
        "date_columns": [date_name],
        "preview_html": sorted_dataframe.head(10).to_html(
            index=True,
            escape=True,
        ),
    }


def _resolve_target_column(
    dataframe: pd.DataFrame,
    target_column_name: str,
) -> Any:
    """Odnajduje oryginalną etykietę kolumny celu wybraną w UI."""
    columns_by_name = {
        str(column): column
        for column in dataframe.columns
    }
    if target_column_name not in columns_by_name:
        raise ValueError(
            f"Nie znaleziono kolumny celu: {target_column_name}"
        )
    return columns_by_name[target_column_name]


def _validate_numeric_target(
    dataframe: pd.DataFrame,
    target_column: Any,
    target_column_name: str,
) -> None:
    """Sprawdza, czy wybrana kolumna celu jest liczbowa."""
    if not pd.api.types.is_numeric_dtype(dataframe[target_column]):
        raise ValueError(
            f"Kolumna celu „{target_column_name}” "
            "musi zawierać dane liczbowe."
        )


def _validate_date_selection(
    selected_date_name: str,
    expected_date_name: str,
) -> None:
    """Sprawdza, czy formularz wskazuje nazwę indeksu daty."""
    if selected_date_name != expected_date_name:
        raise ValueError(
            f"Wybrana data „{selected_date_name}” nie jest indeksem daty "
            f"„{expected_date_name}”."
        )


def _validate_test_fraction(test_fraction: float) -> None:
    """Sprawdza, czy udział zbioru testowego mieści się między 0 i 1."""
    if not 0 < test_fraction < 1:
        raise ValueError(
            "Udział testowy musi być większy od 0 i mniejszy od 1."
        )


def _build_features_and_target(
    dataframe: pd.DataFrame,
    target_column: Any,
) -> tuple[pd.DataFrame, pd.Series]:
    """Rozdziela cechy X i cel y oraz usuwa wiersze bez wartości celu."""
    target = dataframe[target_column].copy()
    features = dataframe.drop(columns=[target_column]).copy()
    valid_target_rows = target.notna()
    return features.loc[valid_target_rows], target.loc[valid_target_rows]


def _calculate_split_point(row_count: int, test_fraction: float) -> int:
    """Wyznacza granicę chronologicznego podziału train/test."""
    if row_count < 2:
        raise ValueError("Za mało poprawnych wierszy do podziału train/test.")

    split_point = int(row_count * (1 - test_fraction))
    if split_point < 1 or split_point >= row_count:
        raise ValueError(
            "Podział daje pusty zbiór treningowy albo testowy."
        )
    return split_point


def _split_train_test(
    features: pd.DataFrame,
    target: pd.Series,
    test_fraction: float,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
    """Dzieli X i y chronologicznie na zbiory treningowe i testowe."""
    split_point = _calculate_split_point(len(features), test_fraction)
    return (
        features.iloc[:split_point].copy(),
        features.iloc[split_point:].copy(),
        target.iloc[:split_point].copy(),
        target.iloc[split_point:].copy(),
    )


def _save_train_test_datasets(
    repository: TargetDataStore,
    X_train: pd.DataFrame,
    X_test: pd.DataFrame,
    y_train: pd.Series,
    y_test: pd.Series,
) -> dict[str, str]:
    """Zapisuje cztery pliki pickle zbiorów X i y w GCS."""
    return {
        "X_train_file": repository.save_pickle(X_train, X_TRAIN_OBJECT),
        "X_test_file": repository.save_pickle(X_test, X_TEST_OBJECT),
        "y_train_file": repository.save_pickle(y_train, Y_TRAIN_OBJECT),
        "y_test_file": repository.save_pickle(y_test, Y_TEST_OBJECT),
    }


def _build_target_settings(
    target_column: str,
    date_index: str,
    test_fraction: float,
    features: pd.DataFrame,
    X_train: pd.DataFrame,
    X_test: pd.DataFrame,
) -> dict[str, Any]:
    """Buduje ustawienia podziału zapisywane w target_settings.json."""
    return {
        "target_column": target_column,
        "date_index": date_index,
        "test_fraction": float(test_fraction),
        "feature_columns": [str(column) for column in features.columns],
        "train_rows": len(X_train),
        "test_rows": len(X_test),
    }


def _build_train_preview(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    target_column: str,
) -> str:
    """Buduje HTML próbki zbioru treningowego z dołączonym celem y."""
    preview = X_train.head(10).copy()
    preview[target_column] = y_train.head(10)
    return preview.to_html(index=True, escape=True)


def _build_train_test_result(
    target_column: str,
    date_column: str,
    features: pd.DataFrame,
    X_train: pd.DataFrame,
    X_test: pd.DataFrame,
    files: dict[str, str],
    settings_file: str,
    preview_html: str,
) -> dict[str, Any]:
    """Buduje odpowiedź używaną przez set_target_ui.py."""
    return {
        "target_column": target_column,
        "date_column": date_column,
        "feature_columns": [str(column) for column in features.columns],
        "train_rows": len(X_train),
        "test_rows": len(X_test),
        **files,
        "settings_file": settings_file,
        "preview_html": preview_html,
    }


class TargetPreparationService:
    """Koordynuje wybór celu i chronologiczny podział X oraz y."""

    def __init__(self, repository: TargetDataStore) -> None:
        self._repository = repository

    def get_options(self) -> dict[str, Any]:
        dataframe = self._repository.read_dataframe(INPUT_OBJECT)
        return _build_target_options(dataframe)

    def prepare_train_test(
        self,
        target_column: str,
        date_column: str,
        test_fraction: float,
    ) -> dict[str, Any]:
        """Koordynuje walidację, podział i zapis danych treningowych."""
        dataframe = self._repository.read_dataframe(INPUT_OBJECT)
        expected_date_name = _validate_datetime_index(dataframe)
        _validate_date_selection(date_column, expected_date_name)

        target_column_label = _resolve_target_column(
            dataframe,
            target_column,
        )
        _validate_numeric_target(
            dataframe,
            target_column_label,
            target_column,
        )
        _validate_test_fraction(test_fraction)

        sorted_dataframe = _sort_by_date(dataframe)
        features, target = _build_features_and_target(
            sorted_dataframe,
            target_column_label,
        )
        X_train, X_test, y_train, y_test = _split_train_test(
            features,
            target,
            test_fraction,
        )

        files = _save_train_test_datasets(
            self._repository,
            X_train,
            X_test,
            y_train,
            y_test,
        )
        settings_file = self._repository.save_json(
            _build_target_settings(
                target_column,
                expected_date_name,
                test_fraction,
                features,
                X_train,
                X_test,
            ),
            SETTINGS_OBJECT,
        )
        preview_html = _build_train_preview(
            X_train,
            y_train,
            target_column,
        )

        return _build_train_test_result(
            target_column,
            expected_date_name,
            features,
            X_train,
            X_test,
            files,
            settings_file,
            preview_html,
        )


def _get_bucket() -> storage.Bucket:
    """Zwraca bucket GCS wskazany przez GCS_BUCKET_NAME."""
    bucket_name = os.environ.get("GCS_BUCKET_NAME")
    if not bucket_name:
        raise ValueError("Brak zmiennej środowiskowej GCS_BUCKET_NAME.")
    return storage.Client().bucket(bucket_name)


def _repository() -> TargetDataRepository:
    """Tworzy repozytorium GCS dla modułu przygotowania celu."""
    return TargetDataRepository(GoogleCloudStorageAdapter(_get_bucket()))


def _create_service() -> TargetPreparationService:
    """Składa usługę z repozytorium GCS."""
    return TargetPreparationService(_repository())


# Zachowane funkcje pomocnicze i publiczne używane przez set_target_ui.py.
def _read_dataframe(object_name: str) -> pd.DataFrame:
    return _repository().read_dataframe(object_name)


def _save_pickle(value: Any, object_name: str) -> str:
    return _repository().save_pickle(value, object_name)


def get_target_options() -> dict[str, Any]:
    return _create_service().get_options()


def prepare_train_test(
    target_column: str,
    date_column: str,
    test_fraction: float,
) -> dict[str, Any]:
    return _create_service().prepare_train_test(
        target_column,
        date_column,
        test_fraction,
    )