
from html import escape

from fastapi import APIRouter, Form
from fastapi.responses import HTMLResponse

from forecasting.services.features.rolling.rolling_stats import (
    get_rolling_source_preview,
    rolling_stats,
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
    """Buduje elementy option dla kolumn zwróconych przez serwis."""
    return "".join(
        f'<option value="{escape(str(column), quote=True)}">'
        f"{escape(str(column))}</option>"
        for column in columns
    )


@router.get("/rolling-stats", response_class=HTMLResponse)
def show_rolling_stats_form() -> str:
    """Pobiera podgląd i wyświetla formularz statystyk kroczących."""
    try:
        data = get_rolling_source_preview()
        options = _build_column_options(data["columns"])

        return _page(
            "Statystyki kroczące",
            f"""
            <p>Próbka danych z <code>df_lags.pkl</code>:</p>
            {data["preview_html"]}

            <form method="post" action="/rolling-stats">
                <label for="column">Kolumna liczbowa:</label>
                <select id="column" name="column" required>
                    {options}
                </select>

                <label for="window">Rozmiar okna:</label>
                <input id="window" name="window" type="number"
                       min="1" value="3" required>

                <label for="aggregation">Sposób obliczania:</label>
                <select id="aggregation" name="aggregation" required>
                    <option value="mean">Średnia</option>
                    <option value="sum">Suma</option>
                    <option value="median">Mediana</option>
                </select>

                <button type="submit">
                    Utwórz statystykę i zapisz dane
                </button>
            </form>
            """,
        )
    except Exception as error:
        return _page(
            "Nie udało się otworzyć statystyk kroczących",
            f'<p class="error">{escape(str(error))}</p>',
        )


@router.post("/rolling-stats", response_class=HTMLResponse)
def submit_rolling_stats(
    column: str = Form(...),
    window: int = Form(...),
    aggregation: str = Form(...),
) -> str:
    """Przekazuje ustawienia do serwisu i wyświetla wynik albo błąd."""
    try:
        result = rolling_stats(column, window, aggregation)

        return _page(
            "Statystyki kroczące zapisane",
            f"""
            <p>DataFrame: {escape(result["dataframe_file"])}</p>
            <p>Ustawienia: {escape(result["settings_file"])}</p>
            <p>Liczba wierszy: {result["rows"]}</p>
            <p>Kolumny: {escape(", ".join(result["columns"]))}</p>

            <h2>Próbka zapisanego DataFrame'u</h2>
            {result["preview_html"]}

            <p><a href="/set-target">
                Przejdź do wyboru celu i podziału danych
            </a></p>
            """,
        )
    except Exception as error:
        return _page(
            "Nie udało się utworzyć statystyki kroczącej",
            f'<p class="error">{escape(str(error))}</p>'
            '<p><a href="/rolling-stats">Wróć do formularza</a></p>',
        )