from html import escape

from fastapi import APIRouter, Form
from fastapi.responses import HTMLResponse

from forecasting.services.data.selection.set_target import get_target_options, prepare_train_test


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
            select, button {{ padding: 8px; }}
            button {{ margin-top: 16px; cursor: pointer; }}
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


@router.get("/set-target", response_class=HTMLResponse)
def show_target_form():
    try:
        data = get_target_options()

        target_options = "".join(
            f'<option value="{escape(column, quote=True)}">'
            f"{escape(column)}</option>"
            for column in data["target_columns"]
        )
        date_options = "".join(
            f'<option value="{escape(column, quote=True)}">'
            f"{escape(column)}</option>"
            for column in data["date_columns"]
        )

        return _page(
            "Wybór celu i podziału danych",
            f"""
            <p>Próbka danych z <code>df_rolling.pkl</code>:</p>
            {data["preview_html"]}

            <form method="post" action="/set-target">
                <label for="target_column">Kolumna celu y:</label>
                <select id="target_column" name="target_column" required>
                    {target_options}
                </select>

                <label for="date_column">Kolumna daty do podziału:</label>
                <select id="date_column" name="date_column" required>
                    {date_options}
                </select>

                <label for="test_fraction">Dane przeznaczone na test:</label>
                <select id="test_fraction" name="test_fraction">
                    <option value="0.2">20%</option>
                    <option value="0.25">25%</option>
                    <option value="0.3">30%</option>
                </select>

                <button type="submit">
                    Utwórz X i y oraz podziel dane w czasie
                </button>
            </form>
            """,
        )
    except Exception as error:
        return _page(
            "Nie udało się otworzyć wyboru celu",
            f'<p class="error">{escape(str(error))}</p>',
        )


@router.post("/set-target", response_class=HTMLResponse)
def submit_target_form(
    target_column: str = Form(...),
    date_column: str = Form(...),
    test_fraction: float = Form(...),
):
    try:
        result = prepare_train_test(
            target_column=target_column,
            date_column=date_column,
            test_fraction=test_fraction,
        )

        return _page(
            "Dane podzielone chronologicznie",
            f"""
            <p>Cel y: {escape(result["target_column"])}</p>
            <p>Data: {escape(result["date_column"])}</p>
            <p>Kolumny X: {escape(", ".join(result["feature_columns"]))}</p>
            <p>Wiersze treningowe: {result["train_rows"]}</p>
            <p>Wiersze testowe: {result["test_rows"]}</p>
            <p>X_train: {escape(result["X_train_file"])}</p>
            <p>X_test: {escape(result["X_test_file"])}</p>
            <p>y_train: {escape(result["y_train_file"])}</p>
            <p>y_test: {escape(result["y_test_file"])}</p>
            <p>Ustawienia: {escape(result["settings_file"])}</p>

            <h2>Próbka danych treningowych</h2>
            {result["preview_html"]}

            <p><a href="/transform-data">
                Przejdź do ColumnTransformer
            </a></p>
            """,
        )
    except Exception as error:
        return _page(
            "Nie udało się przygotować X i y",
            f'<p class="error">{escape(str(error))}</p>'
            '<p><a href="/set-target">Wróć do wyboru celu</a></p>',
        )