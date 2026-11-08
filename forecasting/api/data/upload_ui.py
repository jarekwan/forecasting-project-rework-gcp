# from pathlib import Path

# import uvicorn
# from fastapi import APIRouter, File, HTTPException, UploadFile
# from fastapi.responses import HTMLResponse, RedirectResponse

# from forecasting.services.data.ingestion.choose_source import (
#     UPLOAD_DIR,
#     clear_saved_data,
#     load_data,
#     save_dataframe,
# )

# router = APIRouter()


# def page(title: str, body: str) -> str:
#     from html import escape

#     return f"""
#     <!DOCTYPE html>
#     <html lang="pl">
#     <head>
#         <meta charset="UTF-8">
#         <meta name="viewport" content="width=device-width, initial-scale=1">
#         <title>{escape(title)}</title>
#         <style>
#             body {{
#                 font-family: Arial, sans-serif;
#                 max-width: 1100px;
#                 margin: 36px auto;
#                 padding: 0 20px;
#                 color: #222;
#             }}
#             h1 {{ margin-bottom: 22px; }}
#             label {{ display: block; margin: 10px 0; }}
#             select, input {{ padding: 6px; }}
#             button {{
#                 margin-top: 18px;
#                 padding: 10px 18px;
#                 cursor: pointer;
#             }}
#             table {{
#                 border-collapse: collapse;
#                 margin: 16px 0;
#                 width: 100%;
#             }}
#             th, td {{
#                 border: 1px solid #aaa;
#                 padding: 8px;
#                 text-align: left;
#             }}
#             .section {{ margin: 22px 0; }}
#             .error {{ color: #a00; }}
#         </style>
#     </head>
#     <body>
#         <h1>{escape(title)}</h1>
#         {body}
#     </body>
#     </html>
#     """


# @router.get("/", response_class=HTMLResponse)
# def home():
#     return page(
#         "Wczytaj plik CSV",
#         """
#         <form method="post" action="/load-csv" enctype="multipart/form-data">
#             <label for="file">Wybierz plik CSV:</label>
#             <input id="file" type="file" name="file" accept=".csv" required>
#             <button type="submit">Wczytaj CSV</button>
#         </form>
#         """,
#     )


# @router.post("/load-csv")
# async def load_csv(file: UploadFile = File(...)):
#     if not file.filename or not file.filename.lower().endswith(".csv"):
#         raise HTTPException(status_code=400, detail="Wybierz plik CSV.")

#     try:
#         clear_saved_data()

#         UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
#         saved_file = UPLOAD_DIR / Path(file.filename).name
#         saved_file.write_bytes(await file.read())

#         df = load_data("csv", str(saved_file))
#         save_dataframe(df)

#         return RedirectResponse("/select-columns", status_code=303)

#     except Exception as error:
#         raise HTTPException(status_code=400, detail=str(error))

from html import escape
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

from forecasting.services.data.ingestion.choose_source import (
    UPLOAD_DIR,
    clear_saved_data,
    load_data,
    save_dataframe,
)

router = APIRouter()


def page(title: str, body: str) -> str:
    """Buduje wspólny szablon HTML dla widoków aplikacji."""
    return f"""
    <!DOCTYPE html>
    <html lang="pl">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>{escape(title)}</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                max-width: 1100px;
                margin: 36px auto;
                padding: 0 20px;
                color: #222;
            }}
            h1 {{ margin-bottom: 22px; }}
            label {{ display: block; margin: 10px 0; }}
            select, input {{ padding: 6px; }}
            button {{
                margin-top: 18px;
                padding: 10px 18px;
                cursor: pointer;
            }}
            table {{
                border-collapse: collapse;
                margin: 16px 0;
                width: 100%;
            }}
            th, td {{
                border: 1px solid #aaa;
                padding: 8px;
                text-align: left;
            }}
            .section {{ margin: 22px 0; }}
            .error {{ color: #a00; }}
        </style>
    </head>
    <body>
        <h1>{escape(title)}</h1>
        {body}
    </body>
    </html>
    """


def _validate_csv_filename(filename: str | None) -> str:
    """Sprawdza rozszerzenie i zwraca bezpieczną nazwę pliku."""
    if not filename or not filename.lower().endswith(".csv"):
        raise ValueError("Wybierz plik CSV.")

    return Path(filename).name


def _load_csv_content(content: bytes, filename: str) -> pd.DataFrame:
    """Wczytuje CSV przez istniejącą strategię źródła."""
    with TemporaryDirectory() as temporary_directory:
        temporary_file = Path(temporary_directory) / filename
        temporary_file.write_bytes(content)
        return load_data("csv", str(temporary_file))


def _save_uploaded_file(filename: str, content: bytes) -> Path:
    """Zapisuje oryginalny plik CSV w lokalnym katalogu uploadów."""
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    saved_file = UPLOAD_DIR / filename
    saved_file.write_bytes(content)
    return saved_file


@router.get("/", response_class=HTMLResponse)
def home() -> str:
    """Pokazuje formularz przesyłania CSV."""
    return page(
        "Wczytaj plik CSV",
        """
        <form method="post" action="/load-csv" enctype="multipart/form-data">
            <label for="file">Wybierz plik CSV:</label>
            <input id="file" type="file" name="file" accept=".csv" required>
            <button type="submit">Wczytaj CSV</button>
        </form>
        """,
    )


@router.post("/load-csv")
async def load_csv(file: UploadFile = File(...)) -> RedirectResponse:
    """Koordynuje upload CSV i przekierowuje do wyboru kolumn."""
    try:
        filename = _validate_csv_filename(file.filename)
        content = await file.read()
        dataframe = _load_csv_content(content, filename)

        # Poprzednie dane są czyszczone dopiero po poprawnym odczycie CSV.
        clear_saved_data()
        _save_uploaded_file(filename, content)
        save_dataframe(dataframe)

        return RedirectResponse("/select-columns", status_code=303)

    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error)) from error