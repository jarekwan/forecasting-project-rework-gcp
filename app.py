import uvicorn
from fastapi import FastAPI

from forecasting.api.data.upload_ui import router as upload_router
from forecasting.api.data.columns_ui import router as columns_router
from forecasting.api.data.date_ui import router as date_router
from forecasting.api.data.clean_data_ui import router as clean_data_router
from forecasting.api.features.date_features_ui import router as date_features_router
from forecasting.api.features.create_lags_ui import router as create_lags_router
from forecasting.api.features.rolling_stats_ui import router as rolling_stats_router
from forecasting.api.modeling.set_target_ui import router as set_target_router
from forecasting.api.modeling.transform_data_ui import router as transform_data_router
from forecasting.api.modeling.train_model_ui import router as train_model_router


app = FastAPI()

app.include_router(upload_router)
app.include_router(columns_router)
app.include_router(date_router)
app.include_router(clean_data_router)
app.include_router(date_features_router)
app.include_router(create_lags_router)
app.include_router(rolling_stats_router)
app.include_router(set_target_router)
app.include_router(transform_data_router)
app.include_router(train_model_router)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)