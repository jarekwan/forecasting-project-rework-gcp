

import io
import os
from abc import ABC, abstractmethod
from typing import Any

import pandas as pd
from google.cloud import storage


INPUT_OBJECT = "data/processed/df_clean.pkl"
OUTPUT_OBJECT = "data/processed/df_date_features.pkl"


class ObjectStorage(ABC):
    """Kontrakt operacji Cloud Storage używanych do obsługi DataFrame'ów."""

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


class GoogleCloudStorageAdapter(ObjectStorage):
    """Dostosowuje bucket GCS do interfejsu ObjectStorage."""

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


class DateFeaturesRepository(ABC):
    """Kontrakt odczytu i zapisu DataFrame'ów etapu cech kalendarzowych."""

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


class GCSDateFeaturesRepository(DateFeaturesRepository):
    """Odczytuje i zapisuje DataFrame'y przez adapter Cloud Storage."""

    def __init__(self, object_storage: ObjectStorage) -> None:
        self._object_storage = object_storage

    @property
    def bucket_name(self) -> str:
        return self._object_storage.bucket_name

    def read_dataframe(self, object_name: str) -> pd.DataFrame:
        if not self._object_storage.exists(object_name):
            raise FileNotFoundError(
                f"Nie znaleziono pliku "
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


def _validate_input_dataframe(dataframe: pd.DataFrame) -> None:
    """Sprawdza warunki wejściowe wymagane do tworzenia cech daty."""
    if not isinstance(dataframe.index, pd.DatetimeIndex):
        raise ValueError(
            "Data w df_clean.pkl nie jest indeksem DatetimeIndex. "
            "Sprawdź, czy set_date.py zachował datę jako indeks."
        )

    if dataframe.empty:
        raise ValueError("df_clean.pkl nie zawiera danych.")


def _add_calendar_features(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Dodaje rok, miesiąc, dzień miesiąca i dzień tygodnia."""
    result = dataframe.copy()
    result["year"] = result.index.year
    result["month"] = result.index.month
    result["day"] = result.index.day
    result["dayofweek"] = result.index.dayofweek
    return result


class DateFeatureGenerator:
    """Tworzy cechy kalendarzowe z indeksu DatetimeIndex."""

    def transform(self, dataframe: pd.DataFrame) -> pd.DataFrame:
        _validate_input_dataframe(dataframe)
        sorted_dataframe = dataframe.sort_index()
        return _add_calendar_features(sorted_dataframe)


def _build_date_features_result(
    dataframe: pd.DataFrame,
    output_path: str,
) -> dict[str, Any]:
    """Przygotowuje wynik używany przez date_features_ui.py."""
    return {
        "dataframe_file": output_path,
        "rows": len(dataframe),
        "columns": [str(column) for column in dataframe.columns],
        "preview_html": dataframe.head(10).to_html(
            index=True,
            escape=True,
        ),
    }


def _print_saved_preview(dataframe: pd.DataFrame) -> None:
    """Wypisuje próbkę zapisanego DataFrame'u do logu."""
    print("\nPRÓBKA df_date_features.pkl ODCZYTANA Z BUCKETA:")
    print(dataframe.head(10).to_string(index=True), flush=True)


class DateFeaturesService:
    """Koordynuje tworzenie, zapis i zwrócenie cech daty."""

    def __init__(
        self,
        repository: DateFeaturesRepository,
        generator: DateFeatureGenerator,
    ) -> None:
        self._repository = repository
        self._generator = generator

    def run(self) -> dict[str, Any]:
        """Koordynuje etapy przygotowania DataFrame'u z cechami daty."""
        dataframe = self._repository.read_dataframe(INPUT_OBJECT)
        transformed_dataframe = self._generator.transform(dataframe)

        output_path = self._repository.save_dataframe(
            transformed_dataframe,
            OUTPUT_OBJECT,
        )
        saved_dataframe = self._repository.read_dataframe(OUTPUT_OBJECT)

        _print_saved_preview(saved_dataframe)
        return _build_date_features_result(saved_dataframe, output_path)


def _get_bucket() -> storage.Bucket:
    """Zwraca bucket GCS wskazany przez GCS_BUCKET_NAME."""
    bucket_name = os.environ.get("GCS_BUCKET_NAME")
    if not bucket_name:
        raise RuntimeError("Brak zmiennej środowiskowej GCS_BUCKET_NAME.")

    return storage.Client().bucket(bucket_name)


def _create_repository() -> GCSDateFeaturesRepository:
    """Tworzy repozytorium GCS używane przez ten moduł."""
    object_storage = GoogleCloudStorageAdapter(_get_bucket())
    return GCSDateFeaturesRepository(object_storage)


def _create_service() -> DateFeaturesService:
    """Składa usługę z repozytorium i generatora cech daty."""
    return DateFeaturesService(
        repository=_create_repository(),
        generator=DateFeatureGenerator(),
    )


# Zachowane funkcje pomocnicze używane w tym module lub przez inne moduły.
def _read_dataframe(object_name: str) -> pd.DataFrame:
    return _create_repository().read_dataframe(object_name)


def _save_dataframe(dataframe: pd.DataFrame, object_name: str) -> str:
    return _create_repository().save_dataframe(dataframe, object_name)


def date_features() -> dict[str, Any]:
    """Publiczna funkcja uruchamiająca tworzenie cech dla date_features_ui."""
    return _create_service().run()