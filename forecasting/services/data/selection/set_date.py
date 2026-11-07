# import io
# import os

# import pandas as pd
# from google.cloud import storage


# SELECTED_OBJECT = "data/processed/df_selected.pkl"
# ADJUSTED_OBJECT = "data/processed/df_eda_adjusted.pkl"
# TYPES_OBJECT = "data/processed/column_types.csv"
# SETTINGS_OBJECT = "data/processed/date_settings.txt"
# OUTPUT_OBJECT = "data/processed/df_date.pkl"


# def _get_bucket():
#     bucket_name = os.environ.get("GCS_BUCKET_NAME")
#     if not bucket_name:
#         raise ValueError("Brak zmiennej środowiskowej GCS_BUCKET_NAME.")

#     return storage.Client().bucket(bucket_name)


# def _input_object() -> str:
#     """Wybiera korektę EDA, jeśli użytkownik ją zapisał."""
#     bucket = _get_bucket()
#     if bucket.blob(ADJUSTED_OBJECT).exists():
#         return ADJUSTED_OBJECT
#     return SELECTED_OBJECT


# def _read_bytes(object_name: str) -> bytes:
#     bucket = _get_bucket()
#     blob = bucket.blob(object_name)

#     if not blob.exists():
#         raise FileNotFoundError(
#             f"Nie znaleziono pliku: gs://{bucket.name}/{object_name}"
#         )

#     return blob.download_as_bytes()


# def _read_pickle(object_name: str) -> pd.DataFrame:
#     return pd.read_pickle(io.BytesIO(_read_bytes(object_name)))


# def get_date_column_options() -> list[str]:
#     """Zwraca wykryte daty dostępne w aktualnym DataFrame."""
#     df = _read_pickle(_input_object())
#     bucket = _get_bucket()
#     types_blob = bucket.blob(TYPES_OBJECT)

#     if types_blob.exists():
#         types_df = pd.read_csv(
#             io.BytesIO(types_blob.download_as_bytes())
#         )
#         if {"type", "column"}.issubset(types_df.columns):
#             date_columns = types_df.loc[
#                 types_df["type"] == "datetime",
#                 "column",
#             ].astype(str).tolist()

#             current_columns = {str(column) for column in df.columns}
#             date_columns = [
#                 column for column in date_columns
#                 if column in current_columns
#             ]
#             if date_columns:
#                 return date_columns

#     return [str(column) for column in df.columns]


# def save_date_settings(
#     date_column: str,
#     duplicate_method: str,
#     fill_method: str,
# ) -> str:
#     """Zapisuje ustawienia daty, obsługi duplikatów i braków."""
#     if duplicate_method not in ("mean", "sum"):
#         raise ValueError("Nieprawidłowa metoda obsługi duplikatów.")

#     if fill_method not in ("zero", "ffill", "mean"):
#         raise ValueError("Nieprawidłowa metoda uzupełniania braków.")

#     df = _read_pickle(_input_object())
#     available_columns = {str(column) for column in df.columns}

#     if date_column not in available_columns:
#         raise ValueError(f"Nie znaleziono kolumny: {date_column}")

#     settings = f"{date_column}\n{duplicate_method}\n{fill_method}\n"

#     bucket = _get_bucket()
#     bucket.blob(SETTINGS_OBJECT).upload_from_string(
#         settings,
#         content_type="text/plain; charset=utf-8",
#     )

#     return f"gs://{bucket.name}/{SETTINGS_OBJECT}"


# def set_date() -> dict:
#     """Przetwarza wybrany DataFrame i zapisuje datę jako indeks."""
#     df = _read_pickle(_input_object())

#     settings = _read_bytes(SETTINGS_OBJECT).decode("utf-8").splitlines()
#     if len(settings) < 3:
#         raise ValueError("Plik date_settings.txt ma nieprawidłową zawartość.")

#     date_column_name, duplicate_method, fill_method = settings[:3]

#     original_columns = {str(column): column for column in df.columns}
#     if date_column_name not in original_columns:
#         raise ValueError(f"Nie znaleziono kolumny daty: {date_column_name}")

#     date_column = original_columns[date_column_name]
#     df[date_column] = pd.to_datetime(df[date_column], errors="coerce")
#     df = df.dropna(subset=[date_column])

#     if df.empty:
#         raise ValueError("Nie znaleziono żadnych poprawnych dat.")

#     numeric_columns = [
#         column
#         for column in df.select_dtypes(include="number").columns
#         if column != date_column
#     ]
#     other_columns = [
#         column
#         for column in df.columns
#         if column != date_column and column not in numeric_columns
#     ]

#     grouped = df.groupby(date_column, sort=True)
#     parts = []

#     if numeric_columns:
#         numeric_data = grouped[numeric_columns]
#         if duplicate_method == "mean":
#             parts.append(numeric_data.mean())
#         elif duplicate_method == "sum":
#             parts.append(numeric_data.sum())
#         else:
#             raise ValueError("Nieprawidłowa metoda obsługi duplikatów.")

#     if other_columns:
#         parts.append(grouped[other_columns].first())

#     if parts:
#         result = pd.concat(parts, axis=1)
#     else:
#         result = pd.DataFrame(index=grouped.size().index)

#     result.index = pd.DatetimeIndex(result.index)
#     result.index.name = str(date_column_name)

#     full_range = pd.date_range(
#         start=result.index.min(),
#         end=result.index.max(),
#         freq="D",
#     )
#     result = result.reindex(full_range)
#     result.index.name = str(date_column_name)

#     if fill_method == "zero":
#         if numeric_columns:
#             result[numeric_columns] = result[numeric_columns].fillna(0)
#     elif fill_method == "ffill":
#         result = result.ffill()
#     elif fill_method == "mean":
#         if numeric_columns:
#             result[numeric_columns] = result[numeric_columns].fillna(
#                 result[numeric_columns].mean()
#             )
#     else:
#         raise ValueError("Nieprawidłowa metoda uzupełniania braków.")

#     result = result.sort_index()

#     buffer = io.BytesIO()
#     result.to_pickle(buffer)
#     buffer.seek(0)

#     bucket = _get_bucket()
#     output_blob = bucket.blob(OUTPUT_OBJECT)
#     output_blob.upload_from_file(
#         buffer,
#         content_type="application/octet-stream",
#     )

#     saved_df = _read_pickle(OUTPUT_OBJECT)

#     print(
#         f"df_date.pkl zapisany w: gs://{bucket.name}/{OUTPUT_OBJECT}",
#         flush=True,
#     )
#     print(saved_df.head(10).to_string(), flush=True)

#     return {
#         "dataframe_file": f"gs://{bucket.name}/{OUTPUT_OBJECT}",
#         "rows": len(saved_df),
#         "columns": [str(column) for column in saved_df.columns],
#         "preview_html": saved_df.head(10).to_html(
#             index=True,
#             escape=True,
#         ),
#     }

import io
import os
from abc import ABC, abstractmethod

import pandas as pd
from google.cloud import storage


SELECTED_OBJECT = "data/processed/df_selected.pkl"
ADJUSTED_OBJECT = "data/processed/df_eda_adjusted.pkl"
TYPES_OBJECT = "data/processed/column_types.csv"
SETTINGS_OBJECT = "data/processed/date_settings.txt"
OUTPUT_OBJECT = "data/processed/df_date.pkl"


# Adapter: wspólny interfejs dostępu do obiektów w Cloud Storage.
class ObjectStorage(ABC):
    @property
    @abstractmethod
    def bucket_name(self) -> str:
        pass

    @abstractmethod
    def exists(self, object_name: str) -> bool:
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

    def exists(self, object_name: str) -> bool:
        return self._bucket.blob(object_name).exists()

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


# Repository: odpowiada za odczyt i zapis plików oraz DataFrame'ów.
class DateProcessingRepository:
    def __init__(self, storage_adapter: ObjectStorage):
        self._storage = storage_adapter

    @property
    def bucket_name(self) -> str:
        return self._storage.bucket_name

    def input_object(self) -> str:
        """Wybiera skorygowany DataFrame, jeśli istnieje."""
        if self._storage.exists(ADJUSTED_OBJECT):
            return ADJUSTED_OBJECT
        return SELECTED_OBJECT

    def read_bytes(self, object_name: str) -> bytes:
        return self._storage.read_bytes(object_name)

    def read_dataframe(self, object_name: str) -> pd.DataFrame:
        return pd.read_pickle(
            io.BytesIO(self._storage.read_bytes(object_name))
        )

    def read_column_types(self) -> pd.DataFrame | None:
        if not self._storage.exists(TYPES_OBJECT):
            return None

        return pd.read_csv(
            io.BytesIO(self._storage.read_bytes(TYPES_OBJECT))
        )

    def save_settings(
        self,
        date_column: str,
        duplicate_method: str,
        fill_method: str,
    ) -> str:
        settings = (
            f"{date_column}\n"
            f"{duplicate_method}\n"
            f"{fill_method}\n"
        )
        self._storage.upload_bytes(
            SETTINGS_OBJECT,
            settings.encode("utf-8"),
            "text/plain; charset=utf-8",
        )
        return f"gs://{self.bucket_name}/{SETTINGS_OBJECT}"

    def save_dataframe(
        self,
        dataframe: pd.DataFrame,
        object_name: str,
    ) -> str:
        buffer = io.BytesIO()
        dataframe.to_pickle(buffer)

        self._storage.upload_bytes(
            object_name,
            buffer.getvalue(),
            "application/octet-stream",
        )
        return f"gs://{self.bucket_name}/{object_name}"


def _repository() -> DateProcessingRepository:
    return DateProcessingRepository(GoogleCloudStorageAdapter())


# Zachowane dotychczasowe funkcje pomocnicze modułu.
def _get_bucket():
    bucket_name = os.environ.get("GCS_BUCKET_NAME")
    if not bucket_name:
        raise ValueError("Brak zmiennej środowiskowej GCS_BUCKET_NAME.")
    return storage.Client().bucket(bucket_name)


def _input_object() -> str:
    return _repository().input_object()


def _read_bytes(object_name: str) -> bytes:
    return _repository().read_bytes(object_name)


def _read_pickle(object_name: str) -> pd.DataFrame:
    return _repository().read_dataframe(object_name)


# Strategy: osobna klasa obsługuje każdą metodę agregacji duplikatów.
class DuplicateAggregationStrategy(ABC):
    @abstractmethod
    def aggregate(self, grouped_data) -> pd.DataFrame:
        pass


class MeanAggregationStrategy(DuplicateAggregationStrategy):
    def aggregate(self, grouped_data) -> pd.DataFrame:
        return grouped_data.mean()


class SumAggregationStrategy(DuplicateAggregationStrategy):
    def aggregate(self, grouped_data) -> pd.DataFrame:
        return grouped_data.sum()


class DuplicateAggregationFactory:
    _strategies = {
        "mean": MeanAggregationStrategy,
        "sum": SumAggregationStrategy,
    }

    @classmethod
    def create(cls, method: str) -> DuplicateAggregationStrategy:
        strategy_class = cls._strategies.get(method)
        if strategy_class is None:
            raise ValueError("Nieprawidłowa metoda obsługi duplikatów.")
        return strategy_class()


# Strategy: osobna klasa obsługuje każdą metodę uzupełniania braków.
class MissingDateFillStrategy(ABC):
    @abstractmethod
    def fill(
        self,
        dataframe: pd.DataFrame,
        numeric_columns: list,
    ) -> pd.DataFrame:
        pass


class ZeroFillStrategy(MissingDateFillStrategy):
    def fill(
        self,
        dataframe: pd.DataFrame,
        numeric_columns: list,
    ) -> pd.DataFrame:
        if numeric_columns:
            dataframe[numeric_columns] = dataframe[numeric_columns].fillna(0)
        return dataframe


class ForwardFillStrategy(MissingDateFillStrategy):
    def fill(
        self,
        dataframe: pd.DataFrame,
        numeric_columns: list,
    ) -> pd.DataFrame:
        return dataframe.ffill()


class MeanFillStrategy(MissingDateFillStrategy):
    def fill(
        self,
        dataframe: pd.DataFrame,
        numeric_columns: list,
    ) -> pd.DataFrame:
        if numeric_columns:
            dataframe[numeric_columns] = dataframe[numeric_columns].fillna(
                dataframe[numeric_columns].mean()
            )
        return dataframe


class MissingDateFillFactory:
    _strategies = {
        "zero": ZeroFillStrategy,
        "ffill": ForwardFillStrategy,
        "mean": MeanFillStrategy,
    }

    @classmethod
    def create(cls, method: str) -> MissingDateFillStrategy:
        strategy_class = cls._strategies.get(method)
        if strategy_class is None:
            raise ValueError("Nieprawidłowa metoda uzupełniania braków.")
        return strategy_class()


class DateProcessingService:
    """Odczytuje ustawienia, przetwarza daty i zapisuje wynik."""

    def __init__(self, repository: DateProcessingRepository):
        self._repository = repository

    def get_date_column_options(self) -> list[str]:
        dataframe = self._repository.read_dataframe(
            self._repository.input_object()
        )
        types_df = self._repository.read_column_types()

        if (
            types_df is not None
            and {"type", "column"}.issubset(types_df.columns)
        ):
            date_columns = types_df.loc[
                types_df["type"] == "datetime",
                "column",
            ].astype(str).tolist()

            current_columns = {
                str(column)
                for column in dataframe.columns
            }
            date_columns = [
                column
                for column in date_columns
                if column in current_columns
            ]
            if date_columns:
                return date_columns

        return [str(column) for column in dataframe.columns]

    def save_date_settings(
        self,
        date_column: str,
        duplicate_method: str,
        fill_method: str,
    ) -> str:
        if duplicate_method not in ("mean", "sum"):
            raise ValueError(
                "Nieprawidłowa metoda obsługi duplikatów."
            )

        if fill_method not in ("zero", "ffill", "mean"):
            raise ValueError(
                "Nieprawidłowa metoda uzupełniania braków."
            )

        dataframe = self._repository.read_dataframe(
            self._repository.input_object()
        )
        available_columns = {
            str(column)
            for column in dataframe.columns
        }

        if date_column not in available_columns:
            raise ValueError(f"Nie znaleziono kolumny: {date_column}")

        return self._repository.save_settings(
            date_column,
            duplicate_method,
            fill_method,
        )

    def process(self) -> dict:
        dataframe = self._repository.read_dataframe(
            self._repository.input_object()
        )

        settings_text = self._repository.read_bytes(
            SETTINGS_OBJECT
        ).decode("utf-8")
        settings = settings_text.splitlines()

        if len(settings) < 3:
            raise ValueError(
                "Plik date_settings.txt ma nieprawidłową zawartość."
            )

        date_column_name, duplicate_method, fill_method = settings[:3]

        original_columns = {
            str(column): column
            for column in dataframe.columns
        }
        if date_column_name not in original_columns:
            raise ValueError(
                f"Nie znaleziono kolumny daty: {date_column_name}"
            )

        date_column = original_columns[date_column_name]
        dataframe[date_column] = pd.to_datetime(
            dataframe[date_column],
            errors="coerce",
        )
        dataframe = dataframe.dropna(subset=[date_column])

        if dataframe.empty:
            raise ValueError("Nie znaleziono żadnych poprawnych dat.")

        numeric_columns = [
            column
            for column in dataframe.select_dtypes(include="number").columns
            if column != date_column
        ]
        other_columns = [
            column
            for column in dataframe.columns
            if column != date_column and column not in numeric_columns
        ]

        grouped = dataframe.groupby(date_column, sort=True)
        parts = []

        if numeric_columns:
            aggregation_strategy = DuplicateAggregationFactory.create(
                duplicate_method
            )
            parts.append(
                aggregation_strategy.aggregate(grouped[numeric_columns])
            )

        if other_columns:
            parts.append(grouped[other_columns].first())

        if parts:
            result = pd.concat(parts, axis=1)
        else:
            result = pd.DataFrame(index=grouped.size().index)

        result.index = pd.DatetimeIndex(result.index)
        result.index.name = str(date_column_name)

        full_range = pd.date_range(
            start=result.index.min(),
            end=result.index.max(),
            freq="D",
        )
        result = result.reindex(full_range)
        result.index.name = str(date_column_name)

        fill_strategy = MissingDateFillFactory.create(fill_method)
        result = fill_strategy.fill(result, numeric_columns)
        result = result.sort_index()

        output_path = self._repository.save_dataframe(
            result,
            OUTPUT_OBJECT,
        )
        saved_df = self._repository.read_dataframe(OUTPUT_OBJECT)

        print(
            f"df_date.pkl zapisany w: "
            f"gs://{self._repository.bucket_name}/{OUTPUT_OBJECT}",
            flush=True,
        )
        print(saved_df.head(10).to_string(), flush=True)

        return {
            "dataframe_file": output_path,
            "rows": len(saved_df),
            "columns": [str(column) for column in saved_df.columns],
            "preview_html": saved_df.head(10).to_html(
                index=True,
                escape=True,
            ),
        }


# Zachowane funkcje używane przez date_ui.py.
def get_date_column_options() -> list[str]:
    return DateProcessingService(_repository()).get_date_column_options()


def save_date_settings(
    date_column: str,
    duplicate_method: str,
    fill_method: str,
) -> str:
    return DateProcessingService(_repository()).save_date_settings(
        date_column,
        duplicate_method,
        fill_method,
    )


def set_date() -> dict:
    return DateProcessingService(_repository()).process()