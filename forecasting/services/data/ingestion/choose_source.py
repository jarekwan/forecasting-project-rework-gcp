# import os
# from pathlib import Path

# import pandas as pd
# import requests
# from google.cloud import storage

# PROJECT_DIR = Path(__file__).resolve().parent
# DATA_DIR = PROJECT_DIR / "data"
# UPLOAD_DIR = DATA_DIR / "uploads"
# PROCESSED_DIR = DATA_DIR / "processed"
# DATAFRAME_PATH = PROCESSED_DIR / "df.pkl"

# GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME")
# GCS_UPLOAD_PREFIX = "data/uploads"
# GCS_PROCESSED_PREFIX = "data/processed"
# GCS_DATAFRAME_BLOB = f"{GCS_PROCESSED_PREFIX}/df.pkl"


# def get_gcs_bucket():
#     """Zwraca bucket Cloud Storage ustawiony dla usługi."""
#     if not GCS_BUCKET_NAME:
#         raise RuntimeError(
#             "Ustaw zmienną GCS_BUCKET_NAME w konfiguracji usługi Cloud Run."
#         )

#     return storage.Client().bucket(GCS_BUCKET_NAME)


# def clear_saved_data() -> None:
#     """Usuwa poprzednie pliki lokalne i kopie z Cloud Storage."""
#     bucket = get_gcs_bucket()

#     for prefix in (f"{GCS_UPLOAD_PREFIX}/", f"{GCS_PROCESSED_PREFIX}/"):
#         for blob in bucket.list_blobs(prefix=prefix):
#             blob.delete()

#     for folder in (UPLOAD_DIR, PROCESSED_DIR):
#         folder.mkdir(parents=True, exist_ok=True)

#         for file_path in folder.iterdir():
#             if file_path.is_file():
#                 file_path.unlink()


# def save_dataframe(df: pd.DataFrame) -> str:
#     """Zapisuje DataFrame jako df.pkl lokalnie i w Cloud Storage."""
#     PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
#     UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

#     # Zachowuje dotychczasowy zapis lokalny.
#     df.to_pickle(DATAFRAME_PATH)

#     bucket = get_gcs_bucket()

#     # Kopiuje przesłany CSV do Cloud Storage.
#     for file_path in UPLOAD_DIR.iterdir():
#         if file_path.is_file():
#             blob_name = f"{GCS_UPLOAD_PREFIX}/{file_path.name}"
#             bucket.blob(blob_name).upload_from_filename(str(file_path))

#     # Kopiuje df.pkl do Cloud Storage.
#     bucket.blob(GCS_DATAFRAME_BLOB).upload_from_filename(
#         str(DATAFRAME_PATH)
#     )

#     gcs_path = f"gs://{GCS_BUCKET_NAME}/{GCS_DATAFRAME_BLOB}"
#     print(f"DataFrame zapisany w: {gcs_path}", flush=True)

#     return gcs_path


# def get_saved_dataframe_preview() -> dict:
#     """Odczytuje df.pkl z Cloud Storage, wypisuje próbkę i zwraca ją do API."""
#     bucket = get_gcs_bucket()
#     blob = bucket.blob(GCS_DATAFRAME_BLOB)

#     if not blob.exists():
#         raise FileNotFoundError(
#             f"Nie znaleziono pliku gs://{GCS_BUCKET_NAME}/{GCS_DATAFRAME_BLOB}"
#         )

#     PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
#     blob.download_to_filename(str(DATAFRAME_PATH))

#     df = pd.read_pickle(DATAFRAME_PATH)

#     print("\nPRÓBKA DATAFRAME ODCZYTANA Z PICKLE:", flush=True)
#     print(df.head(10).to_string(index=False), flush=True)

#     return {
#         "rows": len(df),
#         "columns": list(df.columns),
#         "preview": df.head(10).to_dict(orient="records"),
#     }


# def load_data(source_type: str, location: str) -> pd.DataFrame:
#     if source_type == "csv":
#         path = Path(location)
#         if not path.exists():
#             raise FileNotFoundError(f"Nie znaleziono pliku: {path}")

#         # Tak samo jak w kodzie z GitHuba: domyślny separator przecinek.
#         return pd.read_csv(path)

#     if source_type == "json":
#         path = Path(location)
#         if not path.exists():
#             raise FileNotFoundError(f"Nie znaleziono pliku: {path}")
#         return pd.read_json(path)

#     if source_type == "api":
#         response = requests.get(location, timeout=30)
#         response.raise_for_status()
#         return pd.json_normalize(response.json())

#     raise ValueError("Nieznany typ źródła.")


# def choose_source() -> pd.DataFrame:
#     while True:
#         print("\nWYBIERZ ŹRÓDŁO DANYCH")
#         print("1. CSV")
#         print("2. JSON")
#         print("3. API")

#         choice = input("Wpisz 1, 2 albo 3: ").strip()

#         if choice == "1":
#             source_type = "csv"
#             location = input("Podaj ścieżkę do pliku CSV: ").strip()
#         elif choice == "2":
#             source_type = "json"
#             location = input("Podaj ścieżkę do pliku JSON: ").strip()
#         elif choice == "3":
#             source_type = "api"
#             location = input("Wklej adres API: ").strip()
#         else:
#             print("Wybierz 1, 2 albo 3.")
#             continue

#         try:
#             clear_saved_data()
#             df = load_data(source_type, location)
#             saved_path = save_dataframe(df)

#             print("\nDANE WCZYTANE POPRAWNIE")
#             print(df.head(10))
#             print(f"\nDataFrame zapisany w: {saved_path}")

#             return df

#         except Exception as error:
#             print(f"\nBŁĄD: {error}")


# if __name__ == "__main__":
#     selected_data = choose_source()




import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Type

import pandas as pd
import requests
from google.cloud import storage


PROJECT_DIR = Path(__file__).resolve().parents[4]
DATA_DIR = PROJECT_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
PROCESSED_DIR = DATA_DIR / "processed"
DATAFRAME_PATH = PROCESSED_DIR / "df.pkl"

GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME")
GCS_UPLOAD_PREFIX = "data/uploads"
GCS_PROCESSED_PREFIX = "data/processed"
GCS_DATAFRAME_BLOB = f"{GCS_PROCESSED_PREFIX}/df.pkl"


def _get_bucket_name() -> str:
    """Pobiera nazwę bucketa i zgłasza błąd, jeśli jej nie ustawiono."""
    bucket_name = os.environ.get("GCS_BUCKET_NAME", GCS_BUCKET_NAME)

    if not bucket_name:
        raise RuntimeError(
            "Ustaw zmienną GCS_BUCKET_NAME w konfiguracji usługi Cloud Run."
        )

    return bucket_name


def get_gcs_bucket():
    """Zwraca bucket Cloud Storage."""
    return storage.Client().bucket(_get_bucket_name())


# ---------------------------------------------------------------------
# Strategie wczytywania danych
# Każdy rodzaj źródła ma własną klasę realizującą ten sam interfejs.
# ---------------------------------------------------------------------

class DataSource(ABC):
    """Wspólny interfejs dla źródeł danych."""

    @abstractmethod
    def load(self, location: str) -> pd.DataFrame:
        """Wczytuje dane i zwraca je jako DataFrame."""
        raise NotImplementedError


class CsvDataSource(DataSource):
    """Wczytuje dane z pliku CSV."""

    def load(self, location: str) -> pd.DataFrame:
        path = Path(location)

        if not path.exists():
            raise FileNotFoundError(f"Nie znaleziono pliku: {path}")

        # Zachowuje dotychczasowy separator przecinek.
        return pd.read_csv(path)


class JsonDataSource(DataSource):
    """Wczytuje dane z pliku JSON."""

    def load(self, location: str) -> pd.DataFrame:
        path = Path(location)

        if not path.exists():
            raise FileNotFoundError(f"Nie znaleziono pliku: {path}")

        return pd.read_json(path)


class ApiDataSource(DataSource):
    """Pobiera dane z API."""

    def load(self, location: str) -> pd.DataFrame:
        response = requests.get(location, timeout=30)
        response.raise_for_status()
        return pd.json_normalize(response.json())


class DataSourceFactory:
    """
    Tworzy strategię odpowiednią dla wybranego źródła.

    Nowy rodzaj źródła można dodać przez register(), bez dopisywania
    kolejnej gałęzi if w funkcji load_data().
    """

    def __init__(self):
        self._source_types: dict[str, Type[DataSource]] = {
            "csv": CsvDataSource,
            "json": JsonDataSource,
            "api": ApiDataSource,
        }

    def register(
        self,
        source_type: str,
        source_class: Type[DataSource],
    ) -> None:
        if not issubclass(source_class, DataSource):
            raise TypeError("Źródło musi dziedziczyć po DataSource.")

        self._source_types[source_type.lower()] = source_class

    def create(self, source_type: str) -> DataSource:
        source_class = self._source_types.get(source_type.lower())

        if source_class is None:
            raise ValueError("Nieznany typ źródła.")

        return source_class()


class DataIngestionService:
    """Koordynuje wczytanie danych wybraną strategią."""

    def __init__(self, source_factory: DataSourceFactory):
        self._source_factory = source_factory

    def load(
        self,
        source_type: str,
        location: str,
    ) -> pd.DataFrame:
        source = self._source_factory.create(source_type)
        return source.load(location)


# ---------------------------------------------------------------------
# Interfejs i adapter zapisu w Cloud Storage
# ---------------------------------------------------------------------

class ObjectStorage(ABC):
    """Interfejs operacji na obiektach w magazynie danych."""

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
    """Dostosowuje Cloud Storage do interfejsu ObjectStorage."""

    def __init__(self, bucket_name: str):
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
# Repozytorium DataFrame'ów
# Odpowiada za lokalny zapis oraz zapis i odczyt plików w GCS.
# ---------------------------------------------------------------------

class DataFrameRepository:
    """Zapisuje i odczytuje DataFrame'y oraz pliki etapu uploadu."""

    def __init__(
        self,
        object_storage: ObjectStorage,
        dataframe_path: Path = DATAFRAME_PATH,
        upload_dir: Path = UPLOAD_DIR,
        processed_dir: Path = PROCESSED_DIR,
    ):
        self._object_storage = object_storage
        self._dataframe_path = dataframe_path
        self._upload_dir = upload_dir
        self._processed_dir = processed_dir

    def clear_saved_data(self) -> None:
        """Usuwa poprzednie pliki uploadu i przetworzone dane."""
        prefixes = (
            f"{GCS_UPLOAD_PREFIX}/",
            f"{GCS_PROCESSED_PREFIX}/",
        )

        for prefix in prefixes:
            for object_name in self._object_storage.list_objects(prefix):
                self._object_storage.delete_object(object_name)

        for folder in (self._upload_dir, self._processed_dir):
            folder.mkdir(parents=True, exist_ok=True)

            for file_path in folder.iterdir():
                if file_path.is_file():
                    file_path.unlink()

    def save_dataframe(self, df: pd.DataFrame) -> str:
        """Zapisuje df.pkl lokalnie i kopiuje pliki etapu do GCS."""
        self._processed_dir.mkdir(parents=True, exist_ok=True)
        self._upload_dir.mkdir(parents=True, exist_ok=True)

        df.to_pickle(self._dataframe_path)

        for file_path in self._upload_dir.iterdir():
            if file_path.is_file():
                object_name = f"{GCS_UPLOAD_PREFIX}/{file_path.name}"
                self._object_storage.upload_file(object_name, file_path)

        self._object_storage.upload_file(
            GCS_DATAFRAME_BLOB,
            self._dataframe_path,
        )

        gcs_path = (
            f"gs://{self._object_storage.bucket_name}/{GCS_DATAFRAME_BLOB}"
        )
        print(f"DataFrame zapisany w: {gcs_path}", flush=True)

        return gcs_path

    def get_saved_dataframe_preview(self) -> dict:
        """Odczytuje df.pkl z GCS i zwraca próbkę danych."""
        if not self._object_storage.exists(GCS_DATAFRAME_BLOB):
            raise FileNotFoundError(
                "Nie znaleziono pliku "
                f"gs://{self._object_storage.bucket_name}/"
                f"{GCS_DATAFRAME_BLOB}"
            )

        self._processed_dir.mkdir(parents=True, exist_ok=True)
        self._object_storage.download_to_file(
            GCS_DATAFRAME_BLOB,
            self._dataframe_path,
        )

        df = pd.read_pickle(self._dataframe_path)

        print("\nPRÓBKA DATAFRAME ODCZYTANA Z PICKLE:", flush=True)
        print(df.head(10).to_string(index=False), flush=True)

        return {
            "rows": len(df),
            "columns": list(df.columns),
            "preview": df.head(10).to_dict(orient="records"),
        }


def _create_dataframe_repository() -> DataFrameRepository:
    """Tworzy repozytorium z adapterem Cloud Storage."""
    object_storage = GoogleCloudStorageAdapter(_get_bucket_name())
    return DataFrameRepository(object_storage)


# ---------------------------------------------------------------------
# Zachowane funkcje publiczne używane przez app.py i inne moduły.
# ---------------------------------------------------------------------

def clear_saved_data() -> None:
    _create_dataframe_repository().clear_saved_data()


def save_dataframe(df: pd.DataFrame) -> str:
    return _create_dataframe_repository().save_dataframe(df)


def get_saved_dataframe_preview() -> dict:
    return _create_dataframe_repository().get_saved_dataframe_preview()


def load_data(source_type: str, location: str) -> pd.DataFrame:
    """Zachowana funkcja używana przez aplikację."""
    service = DataIngestionService(DataSourceFactory())
    return service.load(source_type, location)


def choose_source() -> pd.DataFrame:
    """Interaktywny wybór źródła w terminalu — zachowany jak wcześniej."""
    while True:
        print("\nWYBIERZ ŹRÓDŁO DANYCH")
        print("1. CSV")
        print("2. JSON")
        print("3. API")

        choice = input("Wpisz 1, 2 albo 3: ").strip()

        if choice == "1":
            source_type = "csv"
            location = input("Podaj ścieżkę do pliku CSV: ").strip()
        elif choice == "2":
            source_type = "json"
            location = input("Podaj ścieżkę do pliku JSON: ").strip()
        elif choice == "3":
            source_type = "api"
            location = input("Wklej adres API: ").strip()
        else:
            print("Wybierz 1, 2 albo 3.")
            continue

        try:
            clear_saved_data()
            df = load_data(source_type, location)
            saved_path = save_dataframe(df)

            print("\nDANE WCZYTANE POPRAWNIE")
            print(df.head(10))
            print(f"\nDataFrame zapisany w: {saved_path}")

            return df

        except Exception as error:
            print(f"\nBŁĄD: {error}")


if __name__ == "__main__":
    selected_data = choose_source()