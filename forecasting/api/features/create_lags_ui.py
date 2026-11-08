


from html import escape

from fastapi import APIRouter, Form
from fastapi.responses import HTMLResponse

from forecasting.services.features.lags.create_lags import (
    create_lags,
    get_lag_source_preview,
)


router = APIRouter()


def _page(title: str, body: str) -> str:
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
            label {{ display: block; margin: 12px 0; }}
            input, select {{ padding: 7px; }}
            button {{ margin-top: 16px; padding: 10px 18px; cursor: pointer; }}
            table {{ border-collapse: collapse; margin: 16px 0; width: 100%; }}
            th, td {{ border: 1px solid #aaa; padding: 8px; text-align: left; }}
            .error {{ color: #a00; }}
        </style>
    </head>
    <body>
        <h1>{escape(title)}</h1>
        {body}
    </body>
    </html>
    """


def _build_column_options(columns: list[str]) -> str:
    """Buduje elementy option dla listy kolumn zwróconej przez serwis."""
    return "".join(
        f'<option value="{escape(str(column), quote=True)}">'
        f"{escape(str(column))}</option>"
        for column in columns
    )


@router.get("/create-lags", response_class=HTMLResponse)
def show_create_lags_form():
    """Pobiera podgląd danych i wyświetla formularz tworzenia lagów."""
    try:
        data = get_lag_source_preview()
        options = _build_column_options(data["columns"])

        return _page(
            "Tworzenie cech lag",
            f"""
            <p>Próbka danych z <code>df_date_features.pkl</code>:</p>
            {data["preview_html"]}

            <form method="post" action="/create-lags">
                <label for="column">Kolumna do utworzenia lagów:</label>
                <select id="column" name="column" required>
                    {options}
                </select>

                <label for="lags_text">
                    Wartości lag, oddzielone przecinkami, np. 1,2,7:
                </label>
                <input id="lags_text" name="lags_text"
                       placeholder="1,2,7" required>

                <button type="submit">Utwórz lagi i zapisz dane</button>
            </form>
            """,
        )

    except Exception as error:
        return _page(
            "Nie udało się otworzyć wyboru lagów",
            f'<p class="error">{escape(str(error))}</p>',
        )


@router.post("/create-lags", response_class=HTMLResponse)
def submit_create_lags(
    column: str = Form(...),
    lags_text: str = Form(...),
):
    """Przekazuje dane formularza do serwisu i wyświetla wynik."""
    try:
        result = create_lags(column, lags_text)

        return _page(
            "Cechy lag zapisane",
            f"""
            <p>DataFrame: {escape(result["dataframe_file"])}</p>
            <p>Ustawienia: {escape(result["settings_file"])}</p>
            <p>Liczba wierszy: {result["rows"]}</p>
            <p>Kolumny: {escape(", ".join(result["columns"]))}</p>

            <h2>Próbka zapisanego DataFrame'u</h2>
            {result["preview_html"]}

            <p><a href="/rolling-stats">Przejdź do statystyk kroczących</a></p>
            """,
        )

    except Exception as error:
        return _page(
            "Nie udało się utworzyć lagów",
            f'<p class="error">{escape(str(error))}</p>'
            '<p><a href="/create-lags">Wróć do formularza</a></p>',
        )