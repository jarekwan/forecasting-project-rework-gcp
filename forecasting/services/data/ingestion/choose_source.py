

import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, TypedDict

import pandas as pd
import requests
from google.cloud import storage


PROJECT_DIR = Path(__file__).resolve().parents[4]
DATA_DIR = PROJECT_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
PROCESSED_DIR = DATA_DIR / "processed"
DATAFRAME_PATH = PROCESSED_DIR / "df.pkl"

GCS_UPLOAD_PREFIX = "data/uploads"
GCS_PROCESSED_PREFIX = "data/processed"
GCS_DATAFRAME_BLOB = f"{GCS_PROCESSED_PREFIX}/df.pkl"


class DataFramePreview(TypedDict):
    rows: int
    columns: list[Any]
    preview: list[dict[str, Any]]


def _get_bucket_name() -> str:
    """Zwraca nazwę bucketu z konfiguracji środowiska."""
    bucket_name = os.environ.get("GCS_BUCKET_NAME")
    if not bucket_name:
        raise RuntimeError(
            "Ustaw zmienną GCS_BUCKET_NAME w konfiguracji usługi Cloud Run."
        )
    return bucket_name


def get_gcs_bucket() -> storage.Bucket:
    """Zwraca bucket Cloud Storage wskazany przez GCS_BUCKET_NAME."""
    return storage.Client().bucket(_get_bucket_name())


# ---------------------------------------------------------------------
# Odczyt danych ze źródeł
# ---------------------------------------------------------------------

class DataSource(ABC):
    """Kontrakt źródła, które potrafi wczytać dane do DataFrame'u."""

    @abstractmethod
    def load(self, location: str) -> pd.DataFrame:
        raise NotImplementedError


class CsvDataSource(DataSource):
    """Wczytuje DataFrame z pliku CSV."""

    def load(self, location: str) -> pd.DataFrame:
        path = Path(location)
        if not path.is_file():
            raise FileNotFoundError(f"Nie znaleziono pliku CSV: {path}")
        return pd.read_csv(path)


class JsonDataSource(DataSource):
    """Wczytuje DataFrame z pliku JSON."""

    def load(self, location: str) -> pd.DataFrame:
        path = Path(location)
        if not path.is_file():
            raise FileNotFoundError(f"Nie znaleziono pliku JSON: {path}")
        return pd.read_json(path)


class ApiDataSource(DataSource):
    """Pobiera dane JSON z API i normalizuje je do DataFrame'u."""

    def load(self, location: str) -> pd.DataFrame:
        response = requests.get(location, timeout=30)
        response.raise_for_status()
        return pd.json_normalize(response.json())


def _normalize_source_type(source_type: str) -> str:
    """Normalizuje nazwę typu źródła do postaci używanej przez fabrykę."""
    normalized = source_type.strip().lower()
    if not normalized:
        raise ValueError("Typ źródła nie może być pusty.")
    return normalized


class DataSourceFactory:
    """Tworzy obiekt strategii wczytywania dla wskazanego typu źródła."""

    def __init__(
        self,
        source_types: dict[str, type[DataSource]] | None = None,
    ) -> None:
        self._source_types: dict[str, type[DataSource]] = {
            "csv": CsvDataSource,
            "json": JsonDataSource,
            "api": ApiDataSource,
        }

        if source_types:
            for source_type, source_class in source_types.items():
                self.register(source_type, source_class)

    def register(
        self,
        source_type: str,
        source_class: type[DataSource],
    ) -> None:
        """Rejestruje nowy typ źródła bez zmiany logiki serwisu."""
        if not isinstance(source_class, type) or not issubclass(
            source_class,
            DataSource,
        ):
            raise TypeError("Źródło musi dziedziczyć po DataSource.")

        self._source_types[_normalize_source_type(source_type)] = source_class

    def create(self, source_type: str) -> DataSource:
        """Tworzy strategię dla typu źródła albo zgłasza błąd."""
        normalized = _normalize_source_type(source_type)
        source_class = self._source_types.get(normalized)

        if source_class is None:
            raise ValueError("Nieznany typ źródła.")

        return source_class()


class DataIngestionService:
    """Wczytuje dane, delegując konkretną pracę wybranej strategii."""

    def __init__(self, source_factory: DataSourceFactory) -> None:
        self._source_factory = source_factory

    def load(self, source_type: str, location: str) -> pd.DataFrame:
        source = self._source_factory.create(source_type)
        return source.load(location)


# ---------------------------------------------------------------------
# Dostęp do Cloud Storage
# ---------------------------------------------------------------------

class ObjectStorage(ABC):
    """Kontrakt operacji magazynu używanych przez repozytorium."""

    @property
    @abstractmethod
    def bucket_name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def exists(self, object_name: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def upload_file(self, object_name: str, file_path: Path) -> None:
        raise NotImplementedError

    @abstractmethod
    def download_to_file(
        self,
        object_name: str,
        file_path: Path,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def list_objects(self, prefix: str) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    def delete_object(self, object_name: str) -> None:
        raise NotImplementedError


class GoogleCloudStorageAdapter(ObjectStorage):
    """Realizuje kontrakt ObjectStorage za pomocą Google Cloud Storage."""

    def __init__(self, bucket_name: str) -> None:
        self._bucket_name = bucket_name
        self._bucket = storage.Client().bucket(bucket_name)

    @property
    def bucket_name(self) -> str:
        return self._bucket_name

    def exists(self, object_name: str) -> bool:
        return self._bucket.blob(object_name).exists()

    def upload_file(self, object_name: str, file_path: Path) -> None:
        self._bucket.blob(object_name).upload_from_filename(str(file_path))

    def download_to_file(
        self,
        object_name: str,
        file_path: Path,
    ) -> None:
        self._bucket.blob(object_name).download_to_filename(str(file_path))

    def list_objects(self, prefix: str) -> list[str]:
        return [
            blob.name
            for blob in self._bucket.list_blobs(prefix=prefix)
        ]

    def delete_object(self, object_name: str) -> None:
        self._bucket.blob(object_name).delete()


# ---------------------------------------------------------------------
# Repozytorium danych etapu wczytywania
# ---------------------------------------------------------------------

class DataFrameRepository:
    """Zapisuje, odczytuje i usuwa dane etapu w plikach lokalnych oraz GCS."""

    def __init__(
        self,
        object_storage: ObjectStorage,
        dataframe_path: Path = DATAFRAME_PATH,
        upload_dir: Path = UPLOAD_DIR,
        processed_dir: Path = PROCESSED_DIR,
    ) -> None:
        self._object_storage = object_storage
        self._dataframe_path = dataframe_path
        self._upload_dir = upload_dir
        self._processed_dir = processed_dir

    def clear_saved_data(self) -> None:
        """Usuwa obiekty etapu uploadu/przetwarzania oraz pliki lokalne."""
        for prefix in (f"{GCS_UPLOAD_PREFIX}/", f"{GCS_PROCESSED_PREFIX}/"):
            for object_name in self._object_storage.list_objects(prefix):
                self._object_storage.delete_object(object_name)

        self._clear_local_files(self._upload_dir)
        self._clear_local_files(self._processed_dir)

    @staticmethod
    def _clear_local_files(folder: Path) -> None:
        """Tworzy folder, jeśli go brakuje, i usuwa z niego zwykłe pliki."""
        folder.mkdir(parents=True, exist_ok=True)
        for file_path in folder.iterdir():
            if file_path.is_file():
                file_path.unlink()

    def save_dataframe(self, dataframe: pd.DataFrame) -> str:
        """Zapisuje DataFrame i pliki uploadu lokalnie oraz w GCS."""
        self._upload_dir.mkdir(parents=True, exist_ok=True)
        self._dataframe_path.parent.mkdir(parents=True, exist_ok=True)
        self._processed_dir.mkdir(parents=True, exist_ok=True)

        dataframe.to_pickle(self._dataframe_path)
        self._upload_source_files()
        self._upload_saved_dataframe()

        return (
            f"gs://{self._object_storage.bucket_name}/"
            f"{GCS_DATAFRAME_BLOB}"
        )

    def _upload_source_files(self) -> None:
        """Wysyła zachowane pliki źródłowe do prefiksu uploadu."""
        for file_path in self._upload_dir.iterdir():
            if file_path.is_file():
                object_name = f"{GCS_UPLOAD_PREFIX}/{file_path.name}"
                self._object_storage.upload_file(object_name, file_path)

    def _upload_saved_dataframe(self) -> None:
        """Wysyła zapisany lokalnie DataFrame do GCS."""
        self._object_storage.upload_file(
            GCS_DATAFRAME_BLOB,
            self._dataframe_path,
        )

    def get_saved_dataframe_preview(self) -> DataFramePreview:
        """Pobiera DataFrame z GCS i zwraca jego próbkę dla UI."""
        if not self._object_storage.exists(GCS_DATAFRAME_BLOB):
            raise FileNotFoundError(
                "Nie znaleziono pliku "
                f"gs://{self._object_storage.bucket_name}/"
                f"{GCS_DATAFRAME_BLOB}"
            )

        self._dataframe_path.parent.mkdir(parents=True, exist_ok=True)
        self._object_storage.download_to_file(
            GCS_DATAFRAME_BLOB,
            self._dataframe_path,
        )

        dataframe = pd.read_pickle(self._dataframe_path)
        return {
            "rows": len(dataframe),
            "columns": list(dataframe.columns),
            "preview": dataframe.head(10).to_dict(orient="records"),
        }


# ---------------------------------------------------------------------
# Proces wczytania i zapisania danych
# ---------------------------------------------------------------------

class DataIngestionWorkflow:
    """Koordynuje wczytanie nowego źródła i zapis wyniku."""

    def __init__(
        self,
        ingestion_service: DataIngestionService,
        repository: DataFrameRepository,
    ) -> None:
        self._ingestion_service = ingestion_service
        self._repository = repository

    def ingest(
        self,
        source_type: str,
        location: str,
    ) -> tuple[pd.DataFrame, str]:
        """Wczytuje źródło, czyści poprzedni etap i zapisuje nowy DataFrame."""
        dataframe = self._ingestion_service.load(source_type, location)
        self._repository.clear_saved_data()
        saved_path = self._repository.save_dataframe(dataframe)
        return dataframe, saved_path


# ---------------------------------------------------------------------
# Funkcje zachowane dla obecnego UI i dotychczasowych wywołań
# ---------------------------------------------------------------------

def _create_dataframe_repository() -> DataFrameRepository:
    """Składa adapter GCS i repozytorium w jednym miejscu."""
    object_storage = GoogleCloudStorageAdapter(_get_bucket_name())
    return DataFrameRepository(object_storage)


def _create_ingestion_workflow() -> DataIngestionWorkflow:
    """Tworzy domyślny proces wczytywania używany przez CLI."""
    return DataIngestionWorkflow(
        ingestion_service=DataIngestionService(DataSourceFactory()),
        repository=_create_dataframe_repository(),
    )


def clear_saved_data() -> None:
    """Zachowana funkcja używana przez upload UI."""
    _create_dataframe_repository().clear_saved_data()


def save_dataframe(dataframe: pd.DataFrame) -> str:
    """Zachowana funkcja używana przez upload UI."""
    return _create_dataframe_repository().save_dataframe(dataframe)


def get_saved_dataframe_preview() -> DataFramePreview:
    """Zachowana funkcja używana przez wybór kolumn w UI."""
    return _create_dataframe_repository().get_saved_dataframe_preview()


def load_data(
    source_type: str,
    location: str,
    source_factory: DataSourceFactory | None = None,
) -> pd.DataFrame:
    """Zachowana funkcja wczytywania z możliwością podania fabryki."""
    factory = (
        source_factory
        if source_factory is not None
        else DataSourceFactory()
    )
    return DataIngestionService(factory).load(source_type, location)


# ---------------------------------------------------------------------
# Interfejs terminalowy
# ---------------------------------------------------------------------

class ConsoleSourcePrompt:
    """Obsługuje wyłącznie pytania i komunikaty w terminalu."""

    _OPTIONS = {
        "1": ("csv", "Podaj ścieżkę do pliku CSV: "),
        "2": ("json", "Podaj ścieżkę do pliku JSON: "),
        "3": ("api", "Wklej adres API: "),
    }

    def ask_for_source(self) -> tuple[str, str]:
        while True:
            print("\nWYBIERZ ŹRÓDŁO DANYCH")
            print("1. CSV")
            print("2. JSON")
            print("3. API")

            choice = input("Wpisz 1, 2 albo 3: ").strip()
            option = self._OPTIONS.get(choice)

            if option is None:
                print("Wybierz 1, 2 albo 3.")
                continue

            source_type, location_prompt = option
            location = input(location_prompt).strip()
            return source_type, location

    @staticmethod
    def show_success(dataframe: pd.DataFrame, saved_path: str) -> None:
        print("\nDANE WCZYTANE POPRAWNIE")
        print(dataframe.head(10))
        print(f"\nDataFrame zapisany w: {saved_path}")

    @staticmethod
    def show_error(error: Exception) -> None:
        print(f"\nBŁĄD: {error}")


class ConsoleIngestionController:
    """Łączy wybór terminalowy z procesem wczytania danych."""

    def __init__(
        self,
        prompt: ConsoleSourcePrompt,
        workflow: DataIngestionWorkflow,
    ) -> None:
        self._prompt = prompt
        self._workflow = workflow

    def run(self) -> pd.DataFrame:
        while True:
            source_type, location = self._prompt.ask_for_source()

            try:
                dataframe, saved_path = self._workflow.ingest(
                    source_type,
                    location,
                )
            except Exception as error:
                self._prompt.show_error(error)
                continue

            self._prompt.show_success(dataframe, saved_path)
            return dataframe


def choose_source() -> pd.DataFrame:
    """Zachowany punkt wejścia do interaktywnego wyboru w terminalu."""
    controller = ConsoleIngestionController(
        prompt=ConsoleSourcePrompt(),
        workflow=_create_ingestion_workflow(),
    )
    return controller.run()


if __name__ == "__main__":
    selected_data = choose_source()