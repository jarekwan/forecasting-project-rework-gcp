from html import escape

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from forecasting.services.features.calendar.date_features import date_features


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
            table {{
                border-collapse: collapse;
                width: 100%;
                margin: 16px 0;
            }}
            th, td {{
                border: 1px solid #aaa;
                padding: 8px;
                text-align: left;
            }}
            button {{
                margin-top: 16px;
                padding: 10px 18px;
                cursor: pointer;
            }}
            .error {{ color: #a00; }}
        </style>
    </head>
    <body>
        <h1>{escape(title)}</h1>
        {body}
    </body>
    </html>
    """


@router.get("/date-features", response_class=HTMLResponse)
def show_date_features_page():
    return HTMLResponse(
        _page(
            "Cechy daty",
            """
            <p>
                Data zostanie odczytana automatycznie z indeksu.
                Aplikacja utworzy kolumny: year, month, day i dayofweek.
            </p>
            <form method="post" action="/date-features">
                <button type="submit">Utwórz cechy daty</button>
            </form>
            """,
        )
    )


@router.post("/date-features", response_class=HTMLResponse)
def run_date_features():
    try:
        result = date_features()

        return HTMLResponse(
            _page(
                "Cechy daty zapisane",
                f"""
                <p>DataFrame: {escape(result["dataframe_file"])}</p>
                <p>Liczba wierszy: {result["rows"]}</p>
                <p>Kolumny: {escape(", ".join(result["columns"]))}</p>

                <h2>Próbka zapisanego DataFrame'u</h2>
                {result["preview_html"]}

                <p>
                    <a href="/create-lags">Przejdź do tworzenia lagów</a>
                </p>
                """,
            )
        )

    except Exception as error:
        return HTMLResponse(
            _page(
                "Nie udało się utworzyć cech daty",
                f'<p class="error">{escape(str(error))}</p>',
            ),
            status_code=400,
        )