# import io
# import json
# import os

# os.environ["MLFLOW_ALLOW_FILE_STORE"] = "true"

# import pickle
# import tempfile
# import zipfile
# from pathlib import Path

# import mlflow
# import mlflow.sklearn
# import numpy as np
# import pandas as pd
# from google.cloud import storage
# from scipy.stats import randint, uniform
# from sklearn.compose import ColumnTransformer
# from sklearn.ensemble import RandomForestRegressor
# from sklearn.linear_model import Lasso, LinearRegression, Ridge
# from sklearn.metrics import mean_absolute_error, mean_squared_error
# from sklearn.model_selection import GridSearchCV, RandomizedSearchCV, TimeSeriesSplit
# from sklearn.pipeline import Pipeline
# from sklearn.preprocessing import OneHotEncoder, StandardScaler
# from sklearn.svm import SVR


# BUCKET_NAME = os.environ.get("GCS_BUCKET_NAME")

# X_TRAIN_OBJECT = "data/processed/X_train.pkl"
# Y_TRAIN_OBJECT = "data/processed/y_train.pkl"
# X_TEST_OBJECT = "data/processed/X_test.pkl"
# Y_TEST_OBJECT = "data/processed/y_test.pkl"
# TRANSFORM_SETTINGS_OBJECT = "data/processed/transform_settings.json"

# MODEL_OBJECT = "data/processed/trained_model.pkl"
# METRICS_OBJECT = "data/processed/model_metrics.json"
# MLFLOW_PREFIX = "data/processed/mlflow_runs"

# INTEGER_PARAMETERS = {
#     "n_estimators",
#     "max_depth",
#     "min_samples_split",
#     "min_samples_leaf",
#     "degree",
# }
# FLOAT_PARAMETERS = {
#     "C",
#     "epsilon",
#     "tol",
#     "alpha",
#     "learning_rate",
#     "subsample",
# }


# def _get_bucket():
#     if not BUCKET_NAME:
#         raise ValueError("Brakuje zmiennej środowiskowej GCS_BUCKET_NAME.")
#     return storage.Client().bucket(BUCKET_NAME)


# def _read_pickle(bucket, object_name):
#     blob = bucket.blob(object_name)
#     if not blob.exists():
#         raise FileNotFoundError(
#             f"Nie znaleziono gs://{bucket.name}/{object_name}"
#         )
#     return pd.read_pickle(io.BytesIO(blob.download_as_bytes()))


# def _read_json(bucket, object_name):
#     blob = bucket.blob(object_name)
#     if not blob.exists():
#         raise FileNotFoundError(
#             f"Nie znaleziono gs://{bucket.name}/{object_name}"
#         )
#     return json.loads(blob.download_as_text())


# def _upload_pickle(bucket, object_name, value):
#     buffer = io.BytesIO()
#     pickle.dump(value, buffer)
#     buffer.seek(0)
#     bucket.blob(object_name).upload_from_file(
#         buffer,
#         content_type="application/octet-stream",
#     )


# def _upload_json(bucket, object_name, value):
#     bucket.blob(object_name).upload_from_string(
#         json.dumps(value, indent=2, default=str),
#         content_type="application/json",
#     )


# def _make_preprocessor(settings, X):
#     numeric_columns = settings.get("StandardScaler", [])
#     categorical_columns = settings.get("OneHotEncoder", [])
#     passthrough_columns = settings.get("passthrough", [])

#     selected_columns = (
#         numeric_columns + categorical_columns + passthrough_columns
#     )

#     if len(selected_columns) != len(set(selected_columns)):
#         raise ValueError(
#             "Kolumna jest przypisana do więcej niż jednej metody."
#         )

#     missing_columns = [
#         column for column in selected_columns if column not in X.columns
#     ]
#     if missing_columns:
#         raise ValueError(
#             f"Brak kolumn z transform_settings.json: {missing_columns}"
#         )

#     unassigned_columns = [
#         column for column in X.columns if column not in selected_columns
#     ]
#     if unassigned_columns:
#         raise ValueError(
#             "Nie wybrano transformacji dla kolumn: "
#             f"{unassigned_columns}"
#         )

#     transformers = []

#     if numeric_columns:
#         transformers.append(
#             ("numbers", StandardScaler(), numeric_columns)
#         )

#     if categorical_columns:
#         transformers.append(
#             (
#                 "categories",
#                 OneHotEncoder(handle_unknown="ignore"),
#                 categorical_columns,
#             )
#         )

#     if passthrough_columns:
#         transformers.append(
#             ("keep", "passthrough", passthrough_columns)
#         )

#     if not transformers:
#         raise ValueError("Brak kolumn do przetworzenia.")

#     return ColumnTransformer(
#         transformers=transformers,
#         remainder="drop",
#     )


# def _make_model(model_name):
#     if model_name == "linear_regression":
#         return LinearRegression()
#     if model_name == "ridge":
#         return Ridge()
#     if model_name == "lasso":
#         return Lasso(max_iter=10000)
#     if model_name == "random_forest_regressor":
#         return RandomForestRegressor(random_state=42)
#     if model_name == "svr":
#         return SVR()
#     if model_name == "xgboost_regressor":
#         try:
#             from xgboost import XGBRegressor
#         except ImportError as error:
#             raise ValueError(
#                 "XGBoost nie jest zainstalowany. Dodaj xgboost "
#                 "do requirements.txt."
#             ) from error
#         return XGBRegressor(
#             objective="reg:squarederror",
#             random_state=42,
#         )
#     raise ValueError(f"Nieznany model: {model_name}")


# def _make_pipeline(model_name, preprocessor):
#     return Pipeline(
#         steps=[
#             ("preprocessor", preprocessor),
#             ("model", _make_model(model_name)),
#         ]
#     )


# def _prefix_parameters(parameters):
#     return {
#         f"model__{name}": value
#         for name, value in parameters.items()
#     }


# def _time_series_cv(row_count):
#     split_count = min(5, row_count - 1)
#     if split_count < 2:
#         raise ValueError(
#             "Za mało wierszy treningowych do walidacji czasowej."
#         )
#     return TimeSeriesSplit(n_splits=split_count)


# def _random_search_distributions(parameters):
#     distributions = {}

#     for name, value in parameters.items():
#         if isinstance(value, dict) and "min" in value and "max" in value:
#             low = value["min"]
#             high = value["max"]

#             if name in INTEGER_PARAMETERS:
#                 distributions[name] = randint(int(low), int(high) + 1)
#             else:
#                 distributions[name] = uniform(
#                     float(low),
#                     float(high) - float(low),
#                 )
#         elif isinstance(value, list) and value:
#             distributions[name] = value
#         else:
#             raise ValueError(
#                 f"{name}: podaj listę wartości albo zakres min/max."
#             )

#     return distributions


# def _optuna_parameter(trial, name, values):
#     if not isinstance(values, list) or not values:
#         raise ValueError(
#             f"Zakres Optuna dla {name} musi być niepustą listą."
#         )

#     if len(values) == 2 and name in INTEGER_PARAMETERS:
#         return trial.suggest_int(name, int(values[0]), int(values[1]))

#     if len(values) == 2 and name in FLOAT_PARAMETERS:
#         return trial.suggest_float(
#             name,
#             float(values[0]),
#             float(values[1]),
#         )

#     return trial.suggest_categorical(name, values)


# def _fit_with_optuna(
#     model_name,
#     preprocessor,
#     X_train,
#     y_train,
#     search_space,
#     n_trials,
# ):
#     try:
#         import optuna
#     except ImportError as error:
#         raise ValueError(
#             "Optuna nie jest zainstalowana. Dodaj optuna "
#             "do requirements.txt."
#         ) from error

#     if not search_space:
#         raise ValueError("Podaj zakresy parametrów dla Optuna.")

#     cv = _time_series_cv(len(X_train))

#     def objective(trial):
#         parameters = {
#             name: _optuna_parameter(trial, name, values)
#             for name, values in search_space.items()
#         }
#         fold_errors = []

#         for train_indices, validation_indices in cv.split(X_train):
#             model = _make_pipeline(model_name, preprocessor)
#             model.set_params(**_prefix_parameters(parameters))

#             X_fold_train = X_train.iloc[train_indices]
#             X_fold_validation = X_train.iloc[validation_indices]
#             y_fold_train = y_train.iloc[train_indices]
#             y_fold_validation = y_train.iloc[validation_indices]

#             model.fit(X_fold_train, y_fold_train)
#             predictions = model.predict(X_fold_validation)
#             fold_errors.append(
#                 mean_absolute_error(y_fold_validation, predictions)
#             )

#         return float(np.mean(fold_errors))

#     study = optuna.create_study(direction="minimize")
#     study.optimize(objective, n_trials=n_trials)

#     best_model = _make_pipeline(model_name, preprocessor)
#     best_model.set_params(**_prefix_parameters(study.best_params))
#     best_model.fit(X_train, y_train)

#     return best_model, study.best_params, float(study.best_value)


# def _calculate_mape(y_true, y_pred):
#     y_true = np.asarray(y_true, dtype=float)
#     y_pred = np.asarray(y_pred, dtype=float)
#     nonzero_rows = y_true != 0

#     if not np.any(nonzero_rows):
#         return None

#     return float(
#         np.mean(
#             np.abs(
#                 (y_true[nonzero_rows] - y_pred[nonzero_rows])
#                 / y_true[nonzero_rows]
#             )
#         )
#         * 100
#     )


# def train_model(model_name, tuning_method, parameters, n_trials=20):
#     bucket = _get_bucket()

#     X_train = _read_pickle(bucket, X_TRAIN_OBJECT)
#     y_train = _read_pickle(bucket, Y_TRAIN_OBJECT)
#     X_test = _read_pickle(bucket, X_TEST_OBJECT)
#     y_test = _read_pickle(bucket, Y_TEST_OBJECT)
#     transform_settings = _read_json(bucket, TRANSFORM_SETTINGS_OBJECT)

#     if len(X_train) != len(y_train) or len(X_test) != len(y_test):
#         raise ValueError("Liczba wierszy X i y jest niezgodna.")

#     if list(X_train.columns) != list(X_test.columns):
#         raise ValueError("Kolumny X_train i X_test są różne.")

#     X_train = X_train.reset_index(drop=True)
#     X_test = X_test.reset_index(drop=True)
#     y_train = pd.Series(y_train).reset_index(drop=True)
#     y_test = pd.Series(y_test).reset_index(drop=True)

#     preprocessor = _make_preprocessor(transform_settings, X_train)
#     model = _make_pipeline(model_name, preprocessor)
#     best_parameters = {}
#     best_cv_mae = None

#     if tuning_method == "manual":
#         if parameters:
#             model.set_params(**_prefix_parameters(parameters))
#         model.fit(X_train, y_train)
#         best_parameters = parameters

#     elif tuning_method == "grid_search":
#         if not parameters:
#             raise ValueError("Podaj listy wartości dla GridSearch.")

#         search = GridSearchCV(
#             estimator=model,
#             param_grid=_prefix_parameters(parameters),
#             scoring="neg_mean_absolute_error",
#             cv=_time_series_cv(len(X_train)),
#             n_jobs=1,
#         )
#         search.fit(X_train, y_train)
#         model = search.best_estimator_
#         best_parameters = {
#             name.removeprefix("model__"): value
#             for name, value in search.best_params_.items()
#         }
#         best_cv_mae = float(-search.best_score_)

#     elif tuning_method == "random_search":
#         if not parameters:
#             raise ValueError(
#                 "Podaj listy wartości albo zakresy min/max "
#                 "dla RandomizedSearch."
#             )

#         distributions = _random_search_distributions(parameters)
#         combinations = 1
#         for values in distributions.values():
#             if isinstance(values, list):
#                 combinations *= len(values)

#         n_iter = min(20, combinations) if combinations > 1 else 20

#         search = RandomizedSearchCV(
#             estimator=model,
#             param_distributions=_prefix_parameters(distributions),
#             n_iter=n_iter,
#             scoring="neg_mean_absolute_error",
#             cv=_time_series_cv(len(X_train)),
#             random_state=42,
#             n_jobs=1,
#         )
#         search.fit(X_train, y_train)
#         model = search.best_estimator_
#         best_parameters = {
#             name.removeprefix("model__"): value
#             for name, value in search.best_params_.items()
#         }
#         best_cv_mae = float(-search.best_score_)

#     elif tuning_method == "optuna":
#         model, best_parameters, best_cv_mae = _fit_with_optuna(
#             model_name=model_name,
#             preprocessor=preprocessor,
#             X_train=X_train,
#             y_train=y_train,
#             search_space=parameters,
#             n_trials=n_trials,
#         )

#     else:
#         raise ValueError(f"Nieznana metoda strojenia: {tuning_method}")

#     predictions = model.predict(X_test)

#     metrics = {
#         "model": model_name,
#         "tuning_method": tuning_method,
#         "mae": float(mean_absolute_error(y_test, predictions)),
#         "rmse": float(np.sqrt(mean_squared_error(y_test, predictions))),
#         "mape_percent": _calculate_mape(y_test, predictions),
#         "best_parameters": best_parameters,
#         "best_cv_mae": best_cv_mae,
#         "test_rows": int(len(y_test)),
#     }

#     with tempfile.TemporaryDirectory() as temporary_directory:
#         tracking_path = Path(temporary_directory) / "mlruns"
#         tracking_path.mkdir(parents=True, exist_ok=True)

#         mlflow.set_tracking_uri(tracking_path.as_uri())
#         mlflow.set_experiment("ai-engineering")

#         with mlflow.start_run() as run:
#             mlflow.log_param("model", model_name)
#             mlflow.log_param("tuning_method", tuning_method)
#             mlflow.log_param("n_trials", int(n_trials))
#             mlflow.log_text(
#                 json.dumps(parameters, indent=2, default=str),
#                 "input_parameters.json",
#             )
#             mlflow.log_text(
#                 json.dumps(transform_settings, indent=2, default=str),
#                 "transform_settings.json",
#             )

#             for metric_name in ("mae", "rmse", "mape_percent"):
#                 value = metrics[metric_name]
#                 if value is not None:
#                     mlflow.log_metric(metric_name, value)

#             if best_cv_mae is not None:
#                 mlflow.log_metric("best_cv_mae", best_cv_mae)

#             mlflow.sklearn.log_model(
#                 model,
#                 artifact_path="model",
#                 skops_trusted_types=["sklearn.tree._tree.Tree"],
#             )
#             _upload_pickle(bucket, MODEL_OBJECT, model)

#             run_id = run.info.run_id
#             archive_path = Path(temporary_directory) / "mlflow_run.zip"

#             with zipfile.ZipFile(
#                 archive_path,
#                 "w",
#                 compression=zipfile.ZIP_DEFLATED,
#             ) as archive:
#                 for file_path in tracking_path.rglob("*"):
#                     if file_path.is_file():
#                         archive.write(
#                             file_path,
#                             file_path.relative_to(tracking_path),
#                         )

#             mlflow_object = f"{MLFLOW_PREFIX}/{run_id}.zip"
#             bucket.blob(mlflow_object).upload_from_filename(
#                 str(archive_path),
#                 content_type="application/zip",
#             )

#     metrics["model_file"] = f"gs://{bucket.name}/{MODEL_OBJECT}"
#     metrics["metrics_file"] = f"gs://{bucket.name}/{METRICS_OBJECT}"
#     metrics["mlflow_run_id"] = run_id
#     metrics["mlflow_run_archive"] = (
#         f"gs://{bucket.name}/{mlflow_object}"
#     )

#     _upload_json(bucket, METRICS_OBJECT, metrics)
#     return metrics


import io
import json
import os
import pickle
import tempfile
import zipfile
from abc import ABC, abstractmethod
from pathlib import Path

os.environ["MLFLOW_ALLOW_FILE_STORE"] = "true"

import mlflow
import mlflow.sklearn
import numpy as np
import pandas as pd
from google.cloud import storage
from scipy.stats import randint, uniform
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Lasso, LinearRegression, Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.model_selection import GridSearchCV, RandomizedSearchCV, TimeSeriesSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.svm import SVR


BUCKET_NAME = os.environ.get("GCS_BUCKET_NAME")

X_TRAIN_OBJECT = "data/processed/X_train.pkl"
Y_TRAIN_OBJECT = "data/processed/y_train.pkl"
X_TEST_OBJECT = "data/processed/X_test.pkl"
Y_TEST_OBJECT = "data/processed/y_test.pkl"
TRANSFORM_SETTINGS_OBJECT = "data/processed/transform_settings.json"

MODEL_OBJECT = "data/processed/trained_model.pkl"
METRICS_OBJECT = "data/processed/model_metrics.json"
MLFLOW_PREFIX = "data/processed/mlflow_runs"

INTEGER_PARAMETERS = {
    "n_estimators",
    "max_depth",
    "min_samples_split",
    "min_samples_leaf",
    "degree",
}
FLOAT_PARAMETERS = {
    "C",
    "epsilon",
    "tol",
    "alpha",
    "learning_rate",
    "subsample",
}


# Adapter: jednolity interfejs do Cloud Storage.
class ObjectStorage(ABC):
    @property
    @abstractmethod
    def bucket(self):
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

    @abstractmethod
    def upload_file(
        self,
        object_name: str,
        file_path: str,
        content_type: str,
    ) -> None:
        pass


class GoogleCloudStorageAdapter(ObjectStorage):
    def __init__(self):
        if not BUCKET_NAME:
            raise ValueError(
                "Brakuje zmiennej środowiskowej GCS_BUCKET_NAME."
            )
        self._bucket = storage.Client().bucket(BUCKET_NAME)

    @property
    def bucket(self):
        return self._bucket

    def read_bytes(self, object_name: str) -> bytes:
        blob = self._bucket.blob(object_name)
        if not blob.exists():
            raise FileNotFoundError(
                f"Nie znaleziono gs://{self._bucket.name}/{object_name}"
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

    def upload_file(
        self,
        object_name: str,
        file_path: str,
        content_type: str,
    ) -> None:
        self._bucket.blob(object_name).upload_from_filename(
            file_path,
            content_type=content_type,
        )


# Repository: obsługuje zapis i odczyt artefaktów treningowych.
class TrainingRepository:
    def __init__(self, storage_adapter: ObjectStorage):
        self._storage = storage_adapter

    @property
    def bucket(self):
        return self._storage.bucket

    def read_pickle(self, object_name: str):
        return pd.read_pickle(io.BytesIO(self._storage.read_bytes(object_name)))

    def read_json(self, object_name: str) -> dict:
        return json.loads(
            self._storage.read_bytes(object_name).decode("utf-8")
        )

    def upload_pickle(self, object_name: str, value) -> None:
        buffer = io.BytesIO()
        pickle.dump(value, buffer)
        self._storage.upload_bytes(
            object_name,
            buffer.getvalue(),
            "application/octet-stream",
        )

    def upload_json(self, object_name: str, value: dict) -> None:
        content = json.dumps(value, indent=2, default=str).encode("utf-8")
        self._storage.upload_bytes(
            object_name,
            content,
            "application/json",
        )

    def upload_file(
        self,
        object_name: str,
        file_path: str,
        content_type: str,
    ) -> None:
        self._storage.upload_file(object_name, file_path, content_type)


def _repository() -> TrainingRepository:
    return TrainingRepository(GoogleCloudStorageAdapter())


# Zachowane dotychczasowe funkcje pomocnicze.
def _get_bucket():
    if not BUCKET_NAME:
        raise ValueError("Brakuje zmiennej środowiskowej GCS_BUCKET_NAME.")
    return storage.Client().bucket(BUCKET_NAME)


def _read_pickle(bucket, object_name):
    blob = bucket.blob(object_name)
    if not blob.exists():
        raise FileNotFoundError(
            f"Nie znaleziono gs://{bucket.name}/{object_name}"
        )
    return pd.read_pickle(io.BytesIO(blob.download_as_bytes()))


def _read_json(bucket, object_name):
    blob = bucket.blob(object_name)
    if not blob.exists():
        raise FileNotFoundError(
            f"Nie znaleziono gs://{bucket.name}/{object_name}"
        )
    return json.loads(blob.download_as_text())


def _upload_pickle(bucket, object_name, value):
    buffer = io.BytesIO()
    pickle.dump(value, buffer)
    buffer.seek(0)
    bucket.blob(object_name).upload_from_file(
        buffer,
        content_type="application/octet-stream",
    )


def _upload_json(bucket, object_name, value):
    bucket.blob(object_name).upload_from_string(
        json.dumps(value, indent=2, default=str),
        content_type="application/json",
    )


class PreprocessorFactory:
    """Buduje ColumnTransformer z ustawień zapisanych przez użytkownika."""

    @staticmethod
    def create(settings: dict, X: pd.DataFrame) -> ColumnTransformer:
        numeric_columns = settings.get("StandardScaler", [])
        categorical_columns = settings.get("OneHotEncoder", [])
        passthrough_columns = settings.get("passthrough", [])

        selected_columns = (
            numeric_columns + categorical_columns + passthrough_columns
        )

        if len(selected_columns) != len(set(selected_columns)):
            raise ValueError(
                "Kolumna jest przypisana do więcej niż jednej metody."
            )

        missing_columns = [
            column
            for column in selected_columns
            if column not in X.columns
        ]
        if missing_columns:
            raise ValueError(
                f"Brak kolumn z transform_settings.json: {missing_columns}"
            )

        unassigned_columns = [
            column for column in X.columns if column not in selected_columns
        ]
        if unassigned_columns:
            raise ValueError(
                "Nie wybrano transformacji dla kolumn: "
                f"{unassigned_columns}"
            )

        transformers = []

        if numeric_columns:
            transformers.append(
                ("numbers", StandardScaler(), numeric_columns)
            )

        if categorical_columns:
            transformers.append(
                (
                    "categories",
                    OneHotEncoder(handle_unknown="ignore"),
                    categorical_columns,
                )
            )

        if passthrough_columns:
            transformers.append(
                ("keep", "passthrough", passthrough_columns)
            )

        if not transformers:
            raise ValueError("Brak kolumn do przetworzenia.")

        return ColumnTransformer(
            transformers=transformers,
            remainder="drop",
        )


class RegressorFactory:
    """Tworzy wybrany model regresyjny."""

    @staticmethod
    def create(model_name: str):
        if model_name == "linear_regression":
            return LinearRegression()
        if model_name == "ridge":
            return Ridge()
        if model_name == "lasso":
            return Lasso(max_iter=10000)
        if model_name == "random_forest_regressor":
            return RandomForestRegressor(random_state=42)
        if model_name == "svr":
            return SVR()
        if model_name == "xgboost_regressor":
            try:
                from xgboost import XGBRegressor
            except ImportError as error:
                raise ValueError(
                    "XGBoost nie jest zainstalowany. Dodaj xgboost "
                    "do requirements.txt."
                ) from error

            return XGBRegressor(
                objective="reg:squarederror",
                random_state=42,
            )

        raise ValueError(f"Nieznany model: {model_name}")


def _make_preprocessor(settings, X):
    return PreprocessorFactory.create(settings, X)


def _make_model(model_name):
    return RegressorFactory.create(model_name)


def _make_pipeline(model_name, preprocessor):
    return Pipeline(
        steps=[
            ("preprocessor", preprocessor),
            ("model", _make_model(model_name)),
        ]
    )


def _prefix_parameters(parameters):
    return {
        f"model__{name}": value
        for name, value in parameters.items()
    }


class TimeSeriesValidation:
    """Tworzy walidację zachowującą kolejność czasową."""

    @staticmethod
    def create(row_count: int) -> TimeSeriesSplit:
        split_count = min(5, row_count - 1)
        if split_count < 2:
            raise ValueError(
                "Za mało wierszy treningowych do walidacji czasowej."
            )
        return TimeSeriesSplit(n_splits=split_count)


def _time_series_cv(row_count):
    return TimeSeriesValidation.create(row_count)


class RandomSearchSpaceBuilder:
    """Zamienia zakresy użytkownika na rozkłady RandomizedSearchCV."""

    @staticmethod
    def build(parameters: dict) -> dict:
        distributions = {}

        for name, value in parameters.items():
            if isinstance(value, dict) and "min" in value and "max" in value:
                low = value["min"]
                high = value["max"]

                if name in INTEGER_PARAMETERS:
                    distributions[name] = randint(
                        int(low),
                        int(high) + 1,
                    )
                else:
                    distributions[name] = uniform(
                        float(low),
                        float(high) - float(low),
                    )
            elif isinstance(value, list) and value:
                distributions[name] = value
            else:
                raise ValueError(
                    f"{name}: podaj listę wartości albo zakres min/max."
                )

        return distributions


def _random_search_distributions(parameters):
    return RandomSearchSpaceBuilder.build(parameters)


class OptunaParameterBuilder:
    """Buduje pojedynczą propozycję parametrów Optuny."""

    @staticmethod
    def suggest(trial, name: str, values: list):
        if not isinstance(values, list) or not values:
            raise ValueError(
                f"Zakres Optuna dla {name} musi być niepustą listą."
            )

        if len(values) == 2 and name in INTEGER_PARAMETERS:
            return trial.suggest_int(
                name,
                int(values[0]),
                int(values[1]),
            )

        if len(values) == 2 and name in FLOAT_PARAMETERS:
            return trial.suggest_float(
                name,
                float(values[0]),
                float(values[1]),
            )

        return trial.suggest_categorical(name, values)


def _optuna_parameter(trial, name, values):
    return OptunaParameterBuilder.suggest(trial, name, values)


class OptunaTuner:
    """Stroi model Optuną z czasową walidacją krzyżową."""

    def fit(
        self,
        model_name,
        preprocessor,
        X_train,
        y_train,
        search_space,
        n_trials,
    ):
        try:
            import optuna
        except ImportError as error:
            raise ValueError(
                "Optuna nie jest zainstalowana. Dodaj optuna "
                "do requirements.txt."
            ) from error

        if not search_space:
            raise ValueError("Podaj zakresy parametrów dla Optuna.")

        cv = _time_series_cv(len(X_train))

        def objective(trial):
            parameters = {
                name: _optuna_parameter(trial, name, values)
                for name, values in search_space.items()
            }
            fold_errors = []

            for train_indices, validation_indices in cv.split(X_train):
                model = _make_pipeline(model_name, preprocessor)
                model.set_params(**_prefix_parameters(parameters))

                X_fold_train = X_train.iloc[train_indices]
                X_fold_validation = X_train.iloc[validation_indices]
                y_fold_train = y_train.iloc[train_indices]
                y_fold_validation = y_train.iloc[validation_indices]

                model.fit(X_fold_train, y_fold_train)
                predictions = model.predict(X_fold_validation)
                fold_errors.append(
                    mean_absolute_error(y_fold_validation, predictions)
                )

            return float(np.mean(fold_errors))

        study = optuna.create_study(direction="minimize")
        study.optimize(objective, n_trials=n_trials)

        best_model = _make_pipeline(model_name, preprocessor)
        best_model.set_params(**_prefix_parameters(study.best_params))
        best_model.fit(X_train, y_train)

        return best_model, study.best_params, float(study.best_value)


def _fit_with_optuna(
    model_name,
    preprocessor,
    X_train,
    y_train,
    search_space,
    n_trials,
):
    return OptunaTuner().fit(
        model_name,
        preprocessor,
        X_train,
        y_train,
        search_space,
        n_trials,
    )


# Strategy: każda metoda strojenia ma osobną klasę.
class TuningStrategy(ABC):
    @abstractmethod
    def fit(
        self,
        model_name,
        preprocessor,
        X_train,
        y_train,
        parameters,
        n_trials,
    ):
        pass


class ManualTuningStrategy(TuningStrategy):
    def fit(
        self,
        model_name,
        preprocessor,
        X_train,
        y_train,
        parameters,
        n_trials,
    ):
        model = _make_pipeline(model_name, preprocessor)
        if parameters:
            model.set_params(**_prefix_parameters(parameters))
        model.fit(X_train, y_train)
        return model, parameters, None


class GridSearchTuningStrategy(TuningStrategy):
    def fit(
        self,
        model_name,
        preprocessor,
        X_train,
        y_train,
        parameters,
        n_trials,
    ):
        if not parameters:
            raise ValueError("Podaj listy wartości dla GridSearch.")

        model = _make_pipeline(model_name, preprocessor)
        search = GridSearchCV(
            estimator=model,
            param_grid=_prefix_parameters(parameters),
            scoring="neg_mean_absolute_error",
            cv=_time_series_cv(len(X_train)),
            n_jobs=1,
        )
        search.fit(X_train, y_train)

        best_parameters = {
            name.removeprefix("model__"): value
            for name, value in search.best_params_.items()
        }
        return (
            search.best_estimator_,
            best_parameters,
            float(-search.best_score_),
        )


class RandomSearchTuningStrategy(TuningStrategy):
    def fit(
        self,
        model_name,
        preprocessor,
        X_train,
        y_train,
        parameters,
        n_trials,
    ):
        if not parameters:
            raise ValueError(
                "Podaj listy wartości albo zakresy min/max "
                "dla RandomizedSearch."
            )

        distributions = _random_search_distributions(parameters)
        combinations = 1
        for values in distributions.values():
            if isinstance(values, list):
                combinations *= len(values)

        iterations = min(20, combinations) if combinations > 1 else 20
        model = _make_pipeline(model_name, preprocessor)

        search = RandomizedSearchCV(
            estimator=model,
            param_distributions=_prefix_parameters(distributions),
            n_iter=iterations,
            scoring="neg_mean_absolute_error",
            cv=_time_series_cv(len(X_train)),
            random_state=42,
            n_jobs=1,
        )
        search.fit(X_train, y_train)

        best_parameters = {
            name.removeprefix("model__"): value
            for name, value in search.best_params_.items()
        }
        return (
            search.best_estimator_,
            best_parameters,
            float(-search.best_score_),
        )


class OptunaTuningStrategy(TuningStrategy):
    def fit(
        self,
        model_name,
        preprocessor,
        X_train,
        y_train,
        parameters,
        n_trials,
    ):
        return _fit_with_optuna(
            model_name,
            preprocessor,
            X_train,
            y_train,
            parameters,
            n_trials,
        )


class TuningStrategyFactory:
    """Dobiera metodę strojenia wybraną przez użytkownika."""

    _strategies = {
        "manual": ManualTuningStrategy,
        "grid_search": GridSearchTuningStrategy,
        "random_search": RandomSearchTuningStrategy,
        "optuna": OptunaTuningStrategy,
    }

    @classmethod
    def create(cls, tuning_method: str) -> TuningStrategy:
        strategy_class = cls._strategies.get(tuning_method)
        if strategy_class is None:
            raise ValueError(
                f"Nieznana metoda strojenia: {tuning_method}"
            )
        return strategy_class()


def _calculate_mape(y_true, y_pred):
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    nonzero_rows = y_true != 0

    if not np.any(nonzero_rows):
        return None

    return float(
        np.mean(
            np.abs(
                (y_true[nonzero_rows] - y_pred[nonzero_rows])
                / y_true[nonzero_rows]
            )
        )
        * 100
    )


class ModelEvaluator:
    """Liczy metryki końcowe na zbiorze testowym."""

    @staticmethod
    def evaluate(
        model,
        y_test: pd.Series,
        predictions,
        model_name: str,
        tuning_method: str,
        best_parameters: dict,
        best_cv_mae,
    ) -> dict:
        return {
            "model": model_name,
            "tuning_method": tuning_method,
            "mae": float(mean_absolute_error(y_test, predictions)),
            "rmse": float(
                np.sqrt(mean_squared_error(y_test, predictions))
            ),
            "mape_percent": _calculate_mape(y_test, predictions),
            "best_parameters": best_parameters,
            "best_cv_mae": best_cv_mae,
            "test_rows": int(len(y_test)),
        }


class MLflowExperimentLogger:
    """Zapisuje eksperyment MLflow, model i archiwum przebiegu do GCS."""

    def __init__(self, repository: TrainingRepository):
        self._repository = repository

    def log_run(
        self,
        model,
        model_name,
        tuning_method,
        parameters,
        transform_settings,
        metrics,
        n_trials,
    ) -> tuple[str, str]:
        with tempfile.TemporaryDirectory() as temporary_directory:
            tracking_path = Path(temporary_directory) / "mlruns"
            tracking_path.mkdir(parents=True, exist_ok=True)

            mlflow.set_tracking_uri(tracking_path.as_uri())
            mlflow.set_experiment("ai-engineering")

            with mlflow.start_run() as run:
                mlflow.log_param("model", model_name)
                mlflow.log_param("tuning_method", tuning_method)
                mlflow.log_param("n_trials", int(n_trials))
                mlflow.log_text(
                    json.dumps(parameters, indent=2, default=str),
                    "input_parameters.json",
                )
                mlflow.log_text(
                    json.dumps(transform_settings, indent=2, default=str),
                    "transform_settings.json",
                )

                for metric_name in ("mae", "rmse", "mape_percent"):
                    value = metrics[metric_name]
                    if value is not None:
                        mlflow.log_metric(metric_name, value)

                if metrics["best_cv_mae"] is not None:
                    mlflow.log_metric(
                        "best_cv_mae",
                        metrics["best_cv_mae"],
                    )

                mlflow.sklearn.log_model(
                    model,
                    artifact_path="model",
                    skops_trusted_types=["sklearn.tree._tree.Tree"],
                )

                self._repository.upload_pickle(MODEL_OBJECT, model)
                run_id = run.info.run_id

            archive_path = Path(temporary_directory) / "mlflow_run.zip"
            with zipfile.ZipFile(
                archive_path,
                "w",
                compression=zipfile.ZIP_DEFLATED,
            ) as archive:
                for file_path in tracking_path.rglob("*"):
                    if file_path.is_file():
                        archive.write(
                            file_path,
                            file_path.relative_to(tracking_path),
                        )

            mlflow_object = f"{MLFLOW_PREFIX}/{run_id}.zip"
            self._repository.upload_file(
                mlflow_object,
                str(archive_path),
                "application/zip",
            )

        return run_id, mlflow_object


class ModelTrainingService:
    """Koordynuje wczytanie danych, strojenie, ocenę i zapis wyniku."""

    def __init__(
        self,
        repository: TrainingRepository,
        evaluator: ModelEvaluator,
        experiment_logger: MLflowExperimentLogger,
    ):
        self._repository = repository
        self._evaluator = evaluator
        self._experiment_logger = experiment_logger

    def train(
        self,
        model_name,
        tuning_method,
        parameters,
        n_trials=20,
    ) -> dict:
        X_train = self._repository.read_pickle(X_TRAIN_OBJECT)
        y_train = self._repository.read_pickle(Y_TRAIN_OBJECT)
        X_test = self._repository.read_pickle(X_TEST_OBJECT)
        y_test = self._repository.read_pickle(Y_TEST_OBJECT)
        transform_settings = self._repository.read_json(
            TRANSFORM_SETTINGS_OBJECT
        )

        if len(X_train) != len(y_train) or len(X_test) != len(y_test):
            raise ValueError("Liczba wierszy X i y jest niezgodna.")

        if list(X_train.columns) != list(X_test.columns):
            raise ValueError("Kolumny X_train i X_test są różne.")

        X_train = X_train.reset_index(drop=True)
        X_test = X_test.reset_index(drop=True)
        y_train = pd.Series(y_train).reset_index(drop=True)
        y_test = pd.Series(y_test).reset_index(drop=True)

        preprocessor = _make_preprocessor(transform_settings, X_train)
        tuning_strategy = TuningStrategyFactory.create(tuning_method)

        model, best_parameters, best_cv_mae = tuning_strategy.fit(
            model_name,
            preprocessor,
            X_train,
            y_train,
            parameters,
            n_trials,
        )

        predictions = model.predict(X_test)
        metrics = self._evaluator.evaluate(
            model=model,
            y_test=y_test,
            predictions=predictions,
            model_name=model_name,
            tuning_method=tuning_method,
            best_parameters=best_parameters,
            best_cv_mae=best_cv_mae,
        )

        run_id, mlflow_object = self._experiment_logger.log_run(
            model=model,
            model_name=model_name,
            tuning_method=tuning_method,
            parameters=parameters,
            transform_settings=transform_settings,
            metrics=metrics,
            n_trials=n_trials,
        )

        metrics["model_file"] = (
            f"gs://{self._repository.bucket.name}/{MODEL_OBJECT}"
        )
        metrics["metrics_file"] = (
            f"gs://{self._repository.bucket.name}/{METRICS_OBJECT}"
        )
        metrics["mlflow_run_id"] = run_id
        metrics["mlflow_run_archive"] = (
            f"gs://{self._repository.bucket.name}/{mlflow_object}"
        )

        self._repository.upload_json(METRICS_OBJECT, metrics)
        return metrics


# Zachowana funkcja wywoływana przez train_model_ui.py.
def train_model(model_name, tuning_method, parameters, n_trials=20):
    repository = _repository()
    service = ModelTrainingService(
        repository=repository,
        evaluator=ModelEvaluator(),
        experiment_logger=MLflowExperimentLogger(repository),
    )
    return service.train(
        model_name,
        tuning_method,
        parameters,
        n_trials,
    )