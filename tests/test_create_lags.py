import pandas as pd
import pytest

from forecasting.services.features.lags.create_lags import (
    CreateLagsService,
    INPUT_OBJECT,
    LagFeatureGenerator,
    OUTPUT_OBJECT,
    SETTINGS_OBJECT,
)


class InMemoryLagRepository:
    """Repozytorium testowe: przechowuje dane w pamięci, bez GCS."""

    bucket_name = "test-bucket"

    def __init__(self, dataframe):
        self.dataframes = {INPUT_OBJECT: dataframe.copy()}
        self.settings = {}

    def read_dataframe(self, object_name):
        return self.dataframes[object_name].copy()

    def save_dataframe(self, dataframe, object_name):
        self.dataframes[object_name] = dataframe.copy()
        return f"gs://{self.bucket_name}/{object_name}"

    def save_settings(self, settings, object_name):
        self.settings[object_name] = settings
        return f"gs://{self.bucket_name}/{object_name}"


def test_generator_creates_lag_columns():
    generator = LagFeatureGenerator()
    source = pd.DataFrame({"sales": [10, 20, 30]})

    result, lags = generator.create(source, "sales", "1,2")

    assert lags == [1, 2]
    assert pd.isna(result["sales_lag_1"].iloc[0])
    assert result["sales_lag_1"].iloc[1] == 10
    assert pd.isna(result["sales_lag_2"].iloc[1])
    assert result["sales_lag_2"].iloc[2] == 10


def test_generator_rejects_lag_equal_to_zero():
    generator = LagFeatureGenerator()
    source = pd.DataFrame({"sales": [10, 20, 30]})

    with pytest.raises(ValueError, match="większe od zera"):
        generator.create(source, "sales", "0")


def test_service_saves_dataframe_and_lag_settings():
    repository = InMemoryLagRepository(
        pd.DataFrame({"sales": [10, 20, 30]})
    )
    service = CreateLagsService(
        repository=repository,
        generator=LagFeatureGenerator(),
    )

    result = service.create_lags("sales", "1,2")
    saved_dataframe = repository.dataframes[OUTPUT_OBJECT]

    assert "sales_lag_1" in saved_dataframe.columns
    assert "sales_lag_2" in saved_dataframe.columns
    assert result["rows"] == 3
    assert result["dataframe_file"] == (
        f"gs://{repository.bucket_name}/{OUTPUT_OBJECT}"
    )
    assert repository.settings[SETTINGS_OBJECT] == "sales\n1,2\n"