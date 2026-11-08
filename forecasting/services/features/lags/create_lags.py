
import io
import os
from abc import ABC, abstractmethod
from typing import Any

import pandas as pd
from google.cloud import storage


INPUT_OBJECT = "data/processed/df_date_features.pkl"
OUTPUT_OBJECT = "data/processed/df_lags.pkl"
SETTINGS_OBJECT = "data/processed/lags_method.txt"


class ObjectStorage(ABC):
    """Kontrakt operacji Cloud Storage potrzebnych w tym module."""

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
    """Udostępnia operacje GCS przez interfejs ObjectStorage."""

    def __init__(self, bucket: storage.Bucket) -> None:
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


class LagRepository(ABC):
    """Kontrakt odczytu i zapisu plików etapu tworzenia lagów."""

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
        dataframe: pd.DataFrame,
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
    """Czyta i zapisuje DataFrame'y oraz ustawienia w GCS."""

    def __init__(self, object_storage: ObjectStorage) -> None:
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


def _resolve_column(dataframe: pd.DataFrame, column_name: str) -> Any:
    """Zwraca oryginalną etykietę kolumny wybraną w formularzu."""
    column_names = {str(column): column for column in dataframe.columns}
    if column_name not in column_names:
        raise ValueError(f"Nie znaleziono kolumny: {column_name}")
    return column_names[column_name]


def _parse_lag_values(lags_text: str) -> list[int]:
    """Konwertuje tekst z formularza na listę liczb całkowitych."""
    lags: list[int] = []

    for raw_value in lags_text.split(","):
        value = raw_value.strip()
        if not value:
            continue

        try:
            lags.append(int(value))
        except ValueError as error:
            raise ValueError(
                f"Wartość laga „{value}” nie jest liczbą całkowitą."
            ) from error

    return lags


def _validate_lag_values(lags: list[int]) -> None:
    """Sprawdza, czy lista lagów jest niepusta, dodatnia i bez powtórzeń."""
    if not lags:
        raise ValueError(
            "Podaj przynajmniej jedną wartość lag, np. 1,2,7."
        )

    if any(lag <= 0 for lag in lags):
        raise ValueError("Wartości lag muszą być większe od zera.")

    if len(lags) != len(set(lags)):
        raise ValueError("Nie podawaj powtarzających się wartości lag.")


def _add_lag_columns(
    dataframe: pd.DataFrame,
    column_name: str,
    source_column: Any,
    lags: list[int],
) -> pd.DataFrame:
    """Dodaje przesuniętą kolumnę dla każdego podanego laga."""
    result = dataframe.copy()

    for lag in lags:
        result[f"{column_name}_lag_{lag}"] = result[source_column].shift(lag)

    return result


def _build_source_preview(dataframe: pd.DataFrame) -> dict[str, Any]:
    """Buduje listę kolumn i HTML próbki danych dla formularza UI."""
    return {
        "columns": [str(column) for column in dataframe.columns],
        "preview_html": dataframe.head(10).to_html(
            index=False,
            escape=True,
        ),
    }


def _format_lag_settings(column: str, lags: list[int]) -> str:
    """Zapisuje wybraną kolumnę i lagi w dotychczasowym formacie tekstowym."""
    return f"{column}\n{','.join(map(str, lags))}\n"


def _print_saved_preview(dataframe: pd.DataFrame) -> None:
    """Wypisuje próbkę zapisanego DataFrame'u do logu."""
    print("\nPRÓBKA df_lags.pkl ODCZYTANA Z BUCKETA:", flush=True)
    print(dataframe.head(10).to_string(index=False), flush=True)


def _build_lag_result(
    dataframe: pd.DataFrame,
    dataframe_path: str,
    settings_path: str,
) -> dict[str, Any]:
    """Buduje odpowiedź zgodną z formularzem create_lags_ui.py."""
    return {
        "dataframe_file": dataframe_path,
        "settings_file": settings_path,
        "rows": len(dataframe),
        "columns": [str(column) for column in dataframe.columns],
        "preview_html": dataframe.head(10).to_html(
            index=False,
            escape=True,
        ),
    }


class LagFeatureGenerator:
    """Tworzy cechy lag dla wskazanej kolumny DataFrame'u."""

    def create(
        self,
        dataframe: pd.DataFrame,
        column: str,
        lags_text: str,
    ) -> tuple[pd.DataFrame, list[int]]:
        source_column = _resolve_column(dataframe, column)
        lags = self._parse_lags(lags_text)
        result = _add_lag_columns(
            dataframe,
            column,
            source_column,
            lags,
        )
        return result, lags

    @staticmethod
    def _parse_lags(lags_text: str) -> list[int]:
        """Zachowany punkt wejścia do parsowania i walidacji lagów."""
        lags = _parse_lag_values(lags_text)
        _validate_lag_values(lags)
        return lags


class CreateLagsService:
    """Koordynuje odczyt źródła, generowanie lagów i zapis wyników."""

    def __init__(
        self,
        repository: LagRepository,
        generator: LagFeatureGenerator,
    ) -> None:
        self._repository = repository
        self._generator = generator

    def get_source_preview(self) -> dict[str, Any]:
        dataframe = self._repository.read_dataframe(INPUT_OBJECT)
        return _build_source_preview(dataframe)

    def create_lags(
        self,
        column: str,
        lags_text: str,
    ) -> dict[str, Any]:
        """Koordynuje utworzenie i zapis lagów."""
        dataframe = self._repository.read_dataframe(INPUT_OBJECT)
        dataframe_with_lags, lags = self._generator.create(
            dataframe,
            column,
            lags_text,
        )

        dataframe_path = self._repository.save_dataframe(
            dataframe_with_lags,
            OUTPUT_OBJECT,
        )
        settings_path = self._repository.save_settings(
            _format_lag_settings(column, lags),
            SETTINGS_OBJECT,
        )

        saved_dataframe = self._repository.read_dataframe(OUTPUT_OBJECT)
        _print_saved_preview(saved_dataframe)

        return _build_lag_result(
            saved_dataframe,
            dataframe_path,
            settings_path,
        )


def _get_bucket() -> storage.Bucket:
    """Zwraca bucket GCS wskazany przez GCS_BUCKET_NAME."""
    bucket_name = os.environ.get("GCS_BUCKET_NAME")
    if not bucket_name:
        raise ValueError("Brak zmiennej środowiskowej GCS_BUCKET_NAME.")
    return storage.Client().bucket(bucket_name)


def _create_repository() -> GCSLagRepository:
    """Tworzy repozytorium GCS używane przez ten moduł."""
    object_storage = GoogleCloudStorageAdapter(_get_bucket())
    return GCSLagRepository(object_storage)


def _create_service() -> CreateLagsService:
    """Składa usługę z repozytorium i generatora lagów."""
    return CreateLagsService(
        repository=_create_repository(),
        generator=LagFeatureGenerator(),
    )


# Zachowane funkcje pomocnicze i publiczne używane przez UI.
def _read_dataframe(object_name: str) -> pd.DataFrame:
    return _create_repository().read_dataframe(object_name)


def _save_dataframe(dataframe: pd.DataFrame, object_name: str) -> str:
    return _create_repository().save_dataframe(dataframe, object_name)


def get_lag_source_preview() -> dict[str, Any]:
    return _create_service().get_source_preview()


def create_lags(column: str, lags_text: str) -> dict[str, Any]:
    return _create_service().create_lags(column, lags_text)