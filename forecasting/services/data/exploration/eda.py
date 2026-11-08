

import base64
import io
import json
import os
from abc import ABC, abstractmethod

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from google.cloud import storage
from pandas.api.types import is_bool_dtype, is_numeric_dtype


INPUT_OBJECT = "data/processed/df_selected.pkl"
ADJUSTED_OBJECT = "data/processed/df_eda_adjusted.pkl"
ADJUSTMENT_SETTINGS_OBJECT = "data/processed/eda_adjustments.json"

STATISTICS_OBJECT = "data/processed/descriptive_statistics.csv"
SKEWNESS_OBJECT = "data/processed/eda_skewness.csv"
OUTLIERS_OBJECT = "data/processed/eda_outliers.csv"
CORRELATION_OBJECT = "data/processed/eda_correlation_matrix.csv"
CORRELATED_PAIRS_OBJECT = "data/processed/eda_correlated_pairs.csv"

SKEWNESS_THRESHOLD = 1.0
IQR_MULTIPLIER = 1.5
MAD_MODIFIED_Z_THRESHOLD = 3.5


class ObjectStorage(ABC):
    """Kontrakt operacji na obiektach w Cloud Storage."""

    @property
    @abstractmethod
    def bucket_name(self) -> str:
        ...

    @abstractmethod
    def read_bytes(self, object_name: str) -> bytes:
        ...

    @abstractmethod
    def upload_bytes(
        self,
        object_name: str,
        content: bytes,
        content_type: str,
    ) -> None:
        ...

    @abstractmethod
    def exists(self, object_name: str) -> bool:
        ...

    @abstractmethod
    def delete(self, object_name: str) -> None:
        ...


class GoogleCloudStorageAdapter(ObjectStorage):
    """Wykonuje operacje Cloud Storage przez interfejs ObjectStorage."""

    def __init__(self) -> None:
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

    def exists(self, object_name: str) -> bool:
        return self._bucket.blob(object_name).exists()

    def delete(self, object_name: str) -> None:
        blob = self._bucket.blob(object_name)
        if blob.exists():
            blob.delete()


class EDAReportRepository(ABC):
    """Operacje wymagane przez usługę tworzącą raport EDA."""

    @property
    @abstractmethod
    def bucket_name(self) -> str:
        ...

    @abstractmethod
    def read_dataframe(self, object_name: str) -> pd.DataFrame:
        ...

    @abstractmethod
    def upload_csv(
        self,
        dataframe: pd.DataFrame,
        object_name: str,
    ) -> str:
        ...


class EDAAdjustmentRepository(ABC):
    """Operacje wymagane przez usługę stosującą korekty."""

    @abstractmethod
    def read_dataframe(self, object_name: str) -> pd.DataFrame:
        ...

    @abstractmethod
    def upload_dataframe(
        self,
        dataframe: pd.DataFrame,
        object_name: str,
    ) -> str:
        ...

    @abstractmethod
    def upload_json(self, value: dict, object_name: str) -> str:
        ...

    @abstractmethod
    def delete(self, object_name: str) -> None:
        ...


class EDARepository(EDAReportRepository, EDAAdjustmentRepository):
    """Odczytuje i zapisuje formaty danych używane przez EDA."""

    def __init__(self, storage_adapter: ObjectStorage) -> None:
        self._storage = storage_adapter

    @property
    def bucket_name(self) -> str:
        return self._storage.bucket_name

    def read_dataframe(self, object_name: str) -> pd.DataFrame:
        return pd.read_pickle(
            io.BytesIO(self._storage.read_bytes(object_name))
        )

    def upload_dataframe(
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

    def upload_csv(
        self,
        dataframe: pd.DataFrame,
        object_name: str,
    ) -> str:
        content = dataframe.to_csv(index=False).encode("utf-8")

        self._storage.upload_bytes(
            object_name,
            content,
            "text/csv; charset=utf-8",
        )
        return f"gs://{self.bucket_name}/{object_name}"

    def upload_json(
        self,
        value: dict,
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
        return f"gs://{self.bucket_name}/{object_name}"

    def delete(self, object_name: str) -> None:
        self._storage.delete(object_name)


def _repository() -> EDARepository:
    """Składa produkcyjny adapter GCS i repozytorium EDA."""
    return EDARepository(GoogleCloudStorageAdapter())


# Zachowane funkcje pomocnicze modułu.
def _get_bucket():
    bucket_name = os.environ.get("GCS_BUCKET_NAME")
    if not bucket_name:
        raise ValueError("Brak zmiennej środowiskowej GCS_BUCKET_NAME.")
    return storage.Client().bucket(bucket_name)


def _read_dataframe(object_name: str = INPUT_OBJECT) -> pd.DataFrame:
    return _repository().read_dataframe(object_name)


def _upload_dataframe(dataframe: pd.DataFrame, object_name: str) -> str:
    return _repository().upload_dataframe(dataframe, object_name)


def _upload_csv(dataframe: pd.DataFrame, object_name: str) -> str:
    return _repository().upload_csv(dataframe, object_name)


def _numeric_columns(df: pd.DataFrame) -> list:
    """Zwraca kolumny liczbowe, z wyłączeniem kolumn logicznych."""
    return [
        column
        for column in df.columns
        if is_numeric_dtype(df[column]) and not is_bool_dtype(df[column])
    ]


def _numeric_values(series: pd.Series) -> pd.Series:
    """Zwraca wartości liczbowe bez braków i nieskończoności."""
    values = pd.to_numeric(series, errors="coerce")
    return values.replace(
        [float("inf"), float("-inf")],
        pd.NA,
    ).dropna()


class DescriptiveStatisticsAnalyzer:
    """Liczy statystyki opisowe dla kolumn liczbowych."""

    def analyze(self, df: pd.DataFrame) -> pd.DataFrame:
        headers = [
            "Kolumna",
            "Liczba wartości",
            "Średnia",
            "Odchylenie standardowe",
            "Mediana",
            "Q1 (25%)",
            "Q3 (75%)",
            "Minimum",
            "Maksimum",
        ]

        rows = []
        for column in _numeric_columns(df):
            values = _numeric_values(df[column])
            rows.append({
                "Kolumna": str(column),
                "Liczba wartości": int(values.count()),
                "Średnia": values.mean(),
                "Odchylenie standardowe": values.std(),
                "Mediana": values.median(),
                "Q1 (25%)": values.quantile(0.25),
                "Q3 (75%)": values.quantile(0.75),
                "Minimum": values.min(),
                "Maksimum": values.max(),
            })

        result = pd.DataFrame(rows, columns=headers)
        numeric_result_columns = [
            column for column in headers
            if column not in ("Kolumna", "Liczba wartości")
        ]

        if not result.empty:
            result[numeric_result_columns] = (
                result[numeric_result_columns].round(4)
            )

        return result


def get_descriptive_statistics() -> dict:
    """Przygotowuje statystyki opisowe i zwraca wynik dla UI."""
    dataframe = _read_dataframe()
    statistics_df = DescriptiveStatisticsAnalyzer().analyze(dataframe)
    statistics_file = _upload_csv(statistics_df, STATISTICS_OBJECT)

    if statistics_df.empty:
        statistics_html = "<p>Brak wybranych kolumn liczbowych.</p>"
    else:
        statistics_html = statistics_df.to_html(
            index=False,
            escape=True,
        )

    return {
        "statistics_file": statistics_file,
        "statistics_html": statistics_html,
        "columns": [
            str(column) for column in _numeric_columns(dataframe)
        ],
    }


class OutlierStrategy(ABC):
    """Kontrakt strategii wyznaczającej granice wartości odstających."""

    @abstractmethod
    def bounds(self, values: pd.Series) -> tuple[float, float]:
        ...


class IQRStrategy(OutlierStrategy):
    """Wyznacza granice metodą IQR."""

    def bounds(self, values: pd.Series) -> tuple[float, float]:
        q1 = values.quantile(0.25)
        q3 = values.quantile(0.75)
        iqr = q3 - q1
        return (
            q1 - IQR_MULTIPLIER * iqr,
            q3 + IQR_MULTIPLIER * iqr,
        )


class MADStrategy(OutlierStrategy):
    """Wyznacza granice metodą MAD."""

    def bounds(self, values: pd.Series) -> tuple[float, float]:
        median = values.median()
        mad = (values - median).abs().median()

        if not mad or pd.isna(mad):
            return float("-inf"), float("inf")

        distance = MAD_MODIFIED_Z_THRESHOLD * mad / 0.6745
        return median - distance, median + distance


class OutlierDetector:
    """Wybiera IQR lub MAD i zwraca raport oznaczonych wartości."""

    def detect(self, df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
        summaries = []
        flagged_rows = []

        for column in _numeric_columns(df):
            values = _numeric_values(df[column])
            if values.empty:
                continue

            skewness = values.skew()
            if (
                pd.notna(skewness)
                and abs(skewness) > SKEWNESS_THRESHOLD
            ):
                method = "MAD"
                strategy = MADStrategy()
            else:
                method = "IQR"
                strategy = IQRStrategy()

            lower, upper = strategy.bounds(values)
            original_values = pd.to_numeric(df[column], errors="coerce")

            positions = []
            for position, value in enumerate(original_values.tolist()):
                if pd.isna(value):
                    continue
                if value < lower or value > upper:
                    positions.append(position)

            summaries.append({
                "Kolumna": str(column),
                "Skośność": skewness,
                "Metoda": method,
                "Dolna granica": lower,
                "Górna granica": upper,
                "Liczba oznaczonych wartości": len(positions),
            })

            for position in positions:
                flagged_rows.append({
                    "Kolumna": str(column),
                    "Pozycja wiersza": position,
                    "Indeks DataFrame": str(df.index[position]),
                    "Wartość": original_values.iloc[position],
                    "Metoda": method,
                    "Dolna granica": lower,
                    "Górna granica": upper,
                })

        summary_df = pd.DataFrame(
            summaries,
            columns=[
                "Kolumna",
                "Skośność",
                "Metoda",
                "Dolna granica",
                "Górna granica",
                "Liczba oznaczonych wartości",
            ],
        )
        details_df = pd.DataFrame(
            flagged_rows,
            columns=[
                "Kolumna",
                "Pozycja wiersza",
                "Indeks DataFrame",
                "Wartość",
                "Metoda",
                "Dolna granica",
                "Górna granica",
            ],
        )
        return summary_df, details_df


def _find_outliers(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    return OutlierDetector().detect(df)


class EDAPlotter:
    """Tworzy wykresy EDA i przygotowuje je do osadzenia w HTML."""

    @staticmethod
    def _figure_as_html(figure, alt_text: str) -> str:
        buffer = io.BytesIO()
        figure.savefig(buffer, format="png", bbox_inches="tight")
        plt.close(figure)

        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        return (
            f'<img alt="{alt_text}" '
            f'src="data:image/png;base64,{encoded}" '
            f'style="max-width:100%;">'
        )

    def plot_distributions(
        self,
        df: pd.DataFrame,
        numeric_columns: list,
    ) -> str:
        if not numeric_columns:
            return "<p>Brak kolumn liczbowych do narysowania wykresów.</p>"

        figure, axes = plt.subplots(
            nrows=len(numeric_columns),
            ncols=2,
            figsize=(12, max(3, 3 * len(numeric_columns))),
            squeeze=False,
        )

        for row, column in enumerate(numeric_columns):
            values = _numeric_values(df[column])

            axes[row][0].hist(values, bins="auto", edgecolor="black")
            axes[row][0].set_title(f"Histogram: {column}")
            axes[row][0].set_xlabel(str(column))
            axes[row][0].set_ylabel("Liczba obserwacji")

            axes[row][1].boxplot(values, vert=False)
            axes[row][1].set_title(f"Boxplot: {column}")
            axes[row][1].set_xlabel(str(column))

        figure.tight_layout()
        return self._figure_as_html(figure, "Histogramy i boxploty")

    def plot_demand_over_time(
        self,
        df: pd.DataFrame,
        date_column: str,
        demand_column: str,
    ) -> str:
        column_names = {str(column): column for column in df.columns}
        if date_column not in column_names:
            raise ValueError(f"Nie znaleziono kolumny daty: {date_column}")
        if demand_column not in column_names:
            raise ValueError(f"Nie znaleziono kolumny popytu: {demand_column}")

        date_values = pd.to_datetime(
            df[column_names[date_column]],
            errors="coerce",
        )
        demand_values = pd.to_numeric(
            df[column_names[demand_column]],
            errors="coerce",
        )

        plot_df = pd.DataFrame({
            "date": date_values,
            "demand": demand_values,
        }).dropna()

        if plot_df.empty:
            return (
                "<p>Nie znaleziono poprawnych dat i liczbowych "
                "wartości popytu.</p>"
            )

        # Powtarzające się daty są sumowane tylko na potrzeby wykresu.
        plot_df = plot_df.groupby("date", as_index=False)["demand"].sum()
        plot_df = plot_df.sort_values("date")

        figure, axis = plt.subplots(figsize=(12, 4))
        axis.plot(plot_df["date"], plot_df["demand"])
        axis.set_title(f"Popyt w czasie: {demand_column}")
        axis.set_xlabel(date_column)
        axis.set_ylabel(demand_column)
        axis.grid(True, alpha=0.3)
        figure.tight_layout()

        return self._figure_as_html(figure, "Wykres popytu w czasie")


def _plot_distributions(df: pd.DataFrame, numeric_columns: list) -> str:
    return EDAPlotter().plot_distributions(df, numeric_columns)


def _correlation_results(
    df: pd.DataFrame,
    numeric_columns: list,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if len(numeric_columns) < 2:
        return pd.DataFrame(), pd.DataFrame(
            columns=["Kolumna 1", "Kolumna 2", "Korelacja"]
        )

    correlation = df[numeric_columns].corr()
    pairs = []

    for left_position, left in enumerate(numeric_columns):
        for right in numeric_columns[left_position + 1:]:
            value = correlation.loc[left, right]
            if pd.notna(value):
                pairs.append({
                    "Kolumna 1": str(left),
                    "Kolumna 2": str(right),
                    "Korelacja": value,
                    "Siła bezwzględna": abs(value),
                })

    pairs_df = pd.DataFrame(pairs)
    if not pairs_df.empty:
        pairs_df = pairs_df.sort_values(
            "Siła bezwzględna",
            ascending=False,
        ).head(10)
        pairs_df = pairs_df.drop(columns=["Siła bezwzględna"])

    return correlation, pairs_df


def _plot_demand_over_time(
    df: pd.DataFrame,
    date_column: str,
    demand_column: str,
) -> str:
    return EDAPlotter().plot_demand_over_time(
        df,
        date_column,
        demand_column,
    )


class EDAReportService:
    """Koordynuje przygotowanie raportu EDA."""

    def __init__(self, repository: EDAReportRepository) -> None:
        self._repository = repository
        self._plotter = EDAPlotter()
        self._outlier_detector = OutlierDetector()

    def _create_skewness_section(
        self,
        dataframe: pd.DataFrame,
        numeric_columns: list,
    ) -> tuple[pd.DataFrame, str]:
        """Oblicza skośność kolumn i zapisuje jej raport CSV."""
        rows = []
        for column in numeric_columns:
            values = _numeric_values(dataframe[column])
            skewness = values.skew() if not values.empty else float("nan")
            rows.append({
                "Kolumna": str(column),
                "Skośność": skewness,
                "Metoda wykrywania": (
                    "MAD"
                    if pd.notna(skewness)
                    and abs(skewness) > SKEWNESS_THRESHOLD
                    else "IQR"
                ),
            })

        skewness_df = pd.DataFrame(
            rows,
            columns=["Kolumna", "Skośność", "Metoda wykrywania"],
        )
        if not skewness_df.empty:
            skewness_df["Skośność"] = skewness_df["Skośność"].round(4)

        report_file = self._repository.upload_csv(
            skewness_df,
            SKEWNESS_OBJECT,
        )
        return skewness_df, report_file

    def _create_outlier_section(
        self,
        dataframe: pd.DataFrame,
    ) -> tuple[pd.DataFrame, pd.DataFrame, str, str, str]:
        """Wykrywa wartości odstające i przygotowuje dane sekcji raportu."""
        summary_df, details_df = self._outlier_detector.detect(dataframe)
        report_file = self._repository.upload_csv(
            summary_df,
            OUTLIERS_OBJECT,
        )

        if summary_df.empty:
            summary_html = "<p>Brak kolumn liczbowych do sprawdzenia.</p>"
        else:
            summary_html = summary_df.round(4).to_html(
                index=False,
                escape=True,
            )

        if details_df.empty:
            details_html = (
                "<p>Nie oznaczono potencjalnych wartości odstających.</p>"
            )
        else:
            details_html = details_df.head(100).round(4).to_html(
                index=False,
                escape=True,
            )
            if len(details_df) > 100:
                details_html += (
                    f"<p>Pokazano pierwsze 100 z "
                    f"{len(details_df)} oznaczonych wartości. "
                    f"Pełna lista: {report_file}</p>"
                )

        return (
            summary_df,
            details_df,
            report_file,
            summary_html,
            details_html,
        )

    def _create_correlation_section(
        self,
        dataframe: pd.DataFrame,
        numeric_columns: list,
    ) -> tuple[str, str, str, str, pd.DataFrame]:
        """Oblicza korelacje i przygotowuje dane sekcji raportu."""
        correlation, correlated_pairs = _correlation_results(
            dataframe,
            numeric_columns,
        )

        if correlation.empty:
            correlation_html = (
                "<p>Do obliczenia korelacji potrzebne są co najmniej "
                "dwie kolumny liczbowe.</p>"
            )
            correlation_file = ""
        else:
            correlation_html = correlation.round(4).to_html(
                escape=True,
                border=0,
            )
            correlation_file = self._repository.upload_csv(
                correlation.reset_index(names="Kolumna"),
                CORRELATION_OBJECT,
            )

        pairs_file = self._repository.upload_csv(
            correlated_pairs,
            CORRELATED_PAIRS_OBJECT,
        )

        if correlated_pairs.empty:
            pairs_html = "<p>Brak par liczbowych do porównania.</p>"
        else:
            pairs_html = correlated_pairs.round(4).to_html(
                index=False,
                escape=True,
            )

        return (
            correlation_html,
            correlation_file,
            pairs_file,
            pairs_html,
            correlated_pairs,
        )

    def create_report(
        self,
        date_column: str = "",
        demand_column: str = "",
    ) -> dict:
        """Koordynuje sekcje raportu i zwraca wynik używany przez UI."""
        dataframe = self._repository.read_dataframe(INPUT_OBJECT)
        numeric_columns = _numeric_columns(dataframe)

        skewness_df, skewness_file = self._create_skewness_section(
            dataframe,
            numeric_columns,
        )
        (
            outlier_summary,
            outlier_details,
            outlier_file,
            outlier_summary_html,
            outlier_details_html,
        ) = self._create_outlier_section(dataframe)
        (
            correlation_html,
            correlation_file,
            pairs_file,
            pairs_html,
            correlated_pairs,
        ) = self._create_correlation_section(
            dataframe,
            numeric_columns,
        )

        time_plot_html = (
            "<p>Wybierz datę i popyt, aby wyświetlić wykres.</p>"
        )
        if date_column and demand_column:
            time_plot_html = self._plotter.plot_demand_over_time(
                dataframe,
                date_column,
                demand_column,
            )

        outlier_columns = []
        if not outlier_summary.empty:
            outlier_columns = outlier_summary.loc[
                outlier_summary["Liczba oznaczonych wartości"] > 0,
                "Kolumna",
            ].astype(str).tolist()

        correlated_columns = []
        if not correlated_pairs.empty:
            correlated_columns = sorted(set(
                correlated_pairs["Kolumna 1"].tolist()
                + correlated_pairs["Kolumna 2"].tolist()
            ))

        return {
            "dataframe_file": (
                f"gs://{self._repository.bucket_name}/{INPUT_OBJECT}"
            ),
            "rows": len(dataframe),
            "columns": [str(column) for column in dataframe.columns],
            "numeric_columns": [str(column) for column in numeric_columns],
            "date_options": [str(column) for column in dataframe.columns],
            "demand_options": [str(column) for column in numeric_columns],
            "preview_html": dataframe.head(10).to_html(
                index=False,
                escape=True,
            ),
            "skewness_html": (
                skewness_df.to_html(index=False, escape=True)
                if not skewness_df.empty
                else "<p>Brak kolumn liczbowych.</p>"
            ),
            "skewness_file": skewness_file,
            "distribution_html": self._plotter.plot_distributions(
                dataframe,
                numeric_columns,
            ),
            "outlier_summary_html": outlier_summary_html,
            "outlier_details_html": outlier_details_html,
            "outlier_file": outlier_file,
            "correlation_html": correlation_html,
            "correlation_file": correlation_file,
            "correlated_pairs_html": pairs_html,
            "correlated_pairs_file": pairs_file,
            "time_plot_html": time_plot_html,
            "outlier_columns": outlier_columns,
            "correlated_columns": correlated_columns,
        }


class EDAAdjustmentService:
    """Koordynuje korekty wybrane przez użytkownika."""

    def __init__(self, repository: EDAAdjustmentRepository) -> None:
        self._repository = repository
        self._outlier_detector = OutlierDetector()

    def clear_adjustments(self) -> None:
        """Usuwa poprzedni wynik korekt i jego ustawienia z GCS."""
        self._repository.delete(ADJUSTED_OBJECT)
        self._repository.delete(ADJUSTMENT_SETTINGS_OBJECT)

    @staticmethod
    def _validate_drop_columns(
        drop_columns: list[str],
        date_column: str,
        demand_column: str,
        column_names: dict[str, object],
    ) -> None:
        """Sprawdza, czy wskazane kolumny można usunąć."""
        protected_columns = {date_column, demand_column}
        invalid_drops = [
            column
            for column in drop_columns
            if column not in column_names or column in protected_columns
        ]
        if invalid_drops:
            raise ValueError(
                f"Nie można usunąć tych kolumn: {invalid_drops}"
            )

        if len(set(drop_columns)) != len(drop_columns):
            raise ValueError("Lista usuwanych kolumn zawiera powtórzenia.")

    @staticmethod
    def _validate_outlier_actions(
        outlier_actions: dict[str, str],
        drop_columns: list[str],
        column_names: dict[str, object],
    ) -> None:
        """Sprawdza kolumny i działania przesłane w formularzu."""
        for column_name, action in outlier_actions.items():
            if column_name not in column_names:
                raise ValueError(f"Nie znaleziono kolumny: {column_name}")
            if action not in {"keep", "clip", "median"}:
                raise ValueError(f"Nieznana metoda korekty: {action}")
            if column_name in drop_columns and action != "keep":
                raise ValueError(
                    f"Kolumna {column_name} jest równocześnie "
                    "usuwana i korygowana."
                )

    @staticmethod
    def _apply_outlier_actions(
        dataframe: pd.DataFrame,
        outlier_actions: dict[str, str],
        column_names: dict[str, object],
        summary: pd.DataFrame,
        details: pd.DataFrame,
    ) -> None:
        """Stosuje clip lub medianę do oznaczonych wartości."""
        summary_by_column = {
            row["Kolumna"]: row
            for _, row in summary.iterrows()
        }

        for column_name, action in outlier_actions.items():
            if action == "keep":
                continue

            row = summary_by_column.get(column_name)
            if row is None or int(row["Liczba oznaczonych wartości"]) == 0:
                continue

            column = column_names[column_name]
            values = pd.to_numeric(dataframe[column], errors="coerce")

            if action == "clip":
                dataframe[column] = values.clip(
                    lower=row["Dolna granica"],
                    upper=row["Górna granica"],
                )
            elif action == "median":
                flagged_positions = details.loc[
                    details["Kolumna"] == column_name,
                    "Pozycja wiersza",
                ].astype(int).tolist()
                median = values.median()
                column_position = dataframe.columns.get_loc(column)

                for row_position in flagged_positions:
                    dataframe.iloc[row_position, column_position] = median

    @staticmethod
    def _drop_selected_columns(
        dataframe: pd.DataFrame,
        drop_columns: list[str],
        column_names: dict[str, object],
    ) -> pd.DataFrame:
        """Usuwa wskazane kolumny z DataFrame'u."""
        if not drop_columns:
            return dataframe

        return dataframe.drop(
            columns=[column_names[name] for name in drop_columns]
        )

    def _save_adjustments(
        self,
        dataframe: pd.DataFrame,
        outlier_actions: dict[str, str],
        drop_columns: list[str],
        date_column: str,
        demand_column: str,
    ) -> str:
        """Zapisuje DataFrame po korektach i ustawienia korekt."""
        output_file = self._repository.upload_dataframe(
            dataframe,
            ADJUSTED_OBJECT,
        )
        settings = {
            "outlier_actions": outlier_actions,
            "dropped_columns": drop_columns,
            "date_column": date_column,
            "demand_column": demand_column,
            "output_file": output_file,
        }
        self._repository.upload_json(
            settings,
            ADJUSTMENT_SETTINGS_OBJECT,
        )
        return output_file

    @staticmethod
    def _print_saved_preview(dataframe: pd.DataFrame) -> None:
        """Wypisuje próbkę zapisanego DataFrame'u do logu."""
        print(dataframe.head(10).to_string(index=False), flush=True)

    @staticmethod
    def _build_saved_result(
        dataframe: pd.DataFrame,
        output_file: str,
    ) -> dict:
        """Buduje wynik korekt zwracany przez UI."""
        return {
            "dataframe_file": output_file,
            "rows": len(dataframe),
            "columns": [str(column) for column in dataframe.columns],
            "preview_html": dataframe.head(10).to_html(
                index=False,
                escape=True,
            ),
        }

    def apply(
        self,
        outlier_actions: dict[str, str],
        drop_columns: list[str],
        date_column: str,
        demand_column: str,
    ) -> dict:
        """Koordynuje zastosowanie korekt i zwraca zapisany wynik."""
        dataframe = self._repository.read_dataframe(INPUT_OBJECT)
        column_names = {
            str(column): column for column in dataframe.columns
        }

        self._validate_drop_columns(
            drop_columns,
            date_column,
            demand_column,
            column_names,
        )
        self._validate_outlier_actions(
            outlier_actions,
            drop_columns,
            column_names,
        )

        summary, details = self._outlier_detector.detect(dataframe)
        self._apply_outlier_actions(
            dataframe,
            outlier_actions,
            column_names,
            summary,
            details,
        )
        dataframe = self._drop_selected_columns(
            dataframe,
            drop_columns,
            column_names,
        )

        if dataframe.shape[1] == 0:
            raise ValueError("Nie można usunąć wszystkich kolumn.")

        output_file = self._save_adjustments(
            dataframe,
            outlier_actions,
            drop_columns,
            date_column,
            demand_column,
        )
        saved_dataframe = self._repository.read_dataframe(ADJUSTED_OBJECT)
        self._print_saved_preview(saved_dataframe)

        return self._build_saved_result(saved_dataframe, output_file)


# Zachowane funkcje używane przez columns_ui.py.
def get_eda_report(
    date_column: str = "",
    demand_column: str = "",
) -> dict:
    return EDAReportService(_repository()).create_report(
        date_column,
        demand_column,
    )


def clear_eda_adjustments() -> None:
    EDAAdjustmentService(_repository()).clear_adjustments()


def apply_eda_adjustments(
    outlier_actions: dict[str, str],
    drop_columns: list[str],
    date_column: str,
    demand_column: str,
) -> dict:
    return EDAAdjustmentService(_repository()).apply(
        outlier_actions,
        drop_columns,
        date_column,
        demand_column,
    )