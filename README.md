# Demand Forecasting Application

A modular FastAPI application for exploring sales data, preparing it for forecasting, creating time-series features, and training machine-learning models.

The user works through the application in a browser. Each stage has a user-interface module and a corresponding Python module for its data-processing logic. The main entry point is `app.py`.

## What the application does

The application supports a data-analysis and forecasting workflow:

1. Load a dataset from a file or another supported source.
2. Inspect the available columns and choose the columns used in the analysis.
3. identify the date column and prepare the time-series data.
4. Clean and inspect the data.
5. Create calendar features, lag features, and rolling statistics.
6. Choose the value to forecast and transform the data for modeling.
7. Train forecasting models and review the results.

The project includes exploratory analysis tools, data-processing modules, model-training functionality, sample CSV datasets, and a unit test for lag-feature generation.

## Main workflow in the browser

1. Open the application.
2. Upload a CSV file using the data-upload form.
3. Select the columns required for the analysis.
4. Configure the date column.
5. Clean and inspect the data.
6. Create date-based, lag, and rolling-statistics features.
7. Select the target column and transform the data.
8. Open the model-training page to train and evaluate models.

The exact controls and available options are implemented in the corresponding UI modules listed below.

## Project structure

### Application and data loading

- `app.py` — starts the FastAPI application and registers the UI routers.
- `choose_source.py` — data-source and saved-data operations.
- `upload_ui.py` — browser form for loading data.

### Selecting and preparing data

- `columns_ui.py` — browser interface for selecting columns.
- `select_columns.py` — logic for validating and saving the selected columns.
- `date_ui.py` — browser interface for configuring the date column.
- `set_date.py` — date-column processing.
- `clean_data_ui.py` — browser interface for data cleaning.
- `clean_data.py` — data-cleaning logic.
- `detect_types.py` — detects column data types.
- `eda.py` — exploratory data analysis, including descriptive statistics and visualizations.

### Creating forecasting features

- `date_features_ui.py` — browser interface for creating date features.
- `date_features.py` — creates features from dates.
- `create_lags_ui.py` — browser interface for configuring lag features.
- `create_lags.py` — creates lagged values from earlier time steps.
- `rolling_stats_ui.py` — browser interface for rolling statistics.
- `rolling_stats.py` — calculates rolling statistics over previous time steps.

### Choosing the target and training models

- `set_target_ui.py` — browser interface for choosing the target column.
- `set_target.py` — target-selection logic.
- `transform_data_ui.py` — browser interface for data transformations.
- `transform_data.py` — prepares transformed data for modeling.
- `train_model_ui.py` — browser interface for model training.
- `train_model.py` — model-training and evaluation logic.

### Tests and earlier versions

- `tests/test_create_lags.py` — unit tests for lag-feature generation.
- `taryapp.py` and `starychoose.py` — earlier project versions retained alongside the current modular application.

## Technologies

- FastAPI and Uvicorn — web application and local server.
- pandas, SciPy, and scikit-learn — data processing and machine learning.
- XGBoost — gradient-boosted tree models.
- Optuna — hyperparameter optimization.
- MLflow — experiment tracking.
- Matplotlib — data visualizations.
- Google Cloud Storage — cloud storage support.

The exact installed packages are listed in `requirements.txt`.

## How to run the application

### 1. Get the project

Clone this repository from GitHub, then open a terminal in the project folder.

### 2. Install dependencies

Create and activate a virtual environment, then install the packages listed in `requirements.txt`.

On Linux or Cloud Shell:

- Create it with `python3 -m venv .venv`
- Activate it with `source .venv/bin/activate`
- Install dependencies with `python -m pip install -r requirements.txt`

### 3. Configure Google Cloud Storage, if needed

Cloud Storage features require Google Cloud authentication and a bucket configured for the application. Set the bucket name using the `GCS_BUCKET_NAME` environment variable. In Google Cloud, the application also needs an identity with permission to access that bucket.

### 4. Start the application

From the project folder, run `python app.py`.

Open `http://localhost:8080` in your browser and follow the data-preparation and modeling workflow.

## Sample data and generated files

The repository includes the sample sales CSV files:

- `Women's Street Footwear.csv`
- `data/Men's Street Footwear.csv`

Files uploaded through the application and generated processing outputs are not required to run the source code. The `.gitignore` excludes `data/uploads/` and `data/processed/` from Git.

## Tests

The current unit test is `tests/test_create_lags.py`. Run it from the project folder with `python -m pytest`.

## Demo

[Open the deployed application](https://lnkd.in/dY53jbY7)

The demo may be unavailable while the Cloud Run service is stopped or being updated.
