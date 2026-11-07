from html import escape

from fastapi import APIRouter, Form
from fastapi.responses import HTMLResponse

from forecasting.services.modeling.preprocessing.transform_data import get_transform_summary, transform_data


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
                padding: 7px;
                text-align: left;
            }}
            select, button {{
                padding: 8px;
                margin: 6px 0 16px;
            }}
            .column {{
                display: grid;
                grid-template-columns: minmax(180px, 1fr) 240px;
                gap: 16px;
                align-items: center;
                border-bottom: 1px solid #ddd;
                padding: 8px 0;
            }}
            .error {{ color: #a00; }}
            .section {{ margin: 24px 0; }}
        </style>
    </head>
    <body>
        <h1>{escape(title)}</h1>
        {body}
    </body>
    </html>
    """


def _selection_page(error_message: str = "") -> HTMLResponse:
    summary = get_transform_summary()
    columns = summary["columns"]

    error_html = (
        f'<p class="error">{escape(error_message)}</p>'
        if error_message
        else ""
    )

    column_fields = "".join(
        f"""
        <label class="column">
            <span>{escape(column)}</span>
            <select name="column_methods" required>
                <option value="passthrough" selected>
                    Bez transformacji
                </option>
                <option value="scale">StandardScaler</option>
                <option value="onehot">OneHotEncoder</option>
            </select>
        </label>
        """
        for column in columns
    )

    body = f"""
        {error_html}

        <p>
            Przypisz metodę osobno do każdej kolumny z X_train.
            Kolumna celu y nie jest tutaj wyświetlana.
        </p>

        <div class="section">
            <h2>Próbka X_train przed transformacją</h2>
            {summary["preview_html"]}
        </div>

        <form method="post" action="/transform-data">
            <h2>Wybór metody dla kolumn</h2>
            {column_fields}
            <button type="submit">Zapisz wybór i uruchom ColumnTransformer</button>
        </form>
    """

    return HTMLResponse(_page("Wybierz transformację kolumn", body))


def _result_page(result: dict) -> HTMLResponse:
    scale_columns = result["selected_methods"]["StandardScaler"]
    onehot_columns = result["selected_methods"]["OneHotEncoder"]
    passthrough_columns = result["selected_methods"]["passthrough"]

    body = f"""
        <p><strong>StandardScaler:</strong>
        {escape(", ".join(scale_columns) if scale_columns else "brak")}</p>

        <p><strong>OneHotEncoder:</strong>
        {escape(", ".join(onehot_columns) if onehot_columns else "brak")}</p>

        <p><strong>Bez transformacji:</strong>
        {escape(", ".join(passthrough_columns) if passthrough_columns else "brak")}</p>

        <p>Wiersze X_train: {result["X_train_rows"]}</p>
        <p>Wiersze X_test: {result["X_test_rows"]}</p>
        <p>Wiersze y_train: {result["y_train_rows"]}</p>
        <p>Wiersze y_test: {result["y_test_rows"]}</p>

        <h2>Zapisane pliki w bucketcie</h2>
        <p>X_train: {escape(result["X_train_file"])}</p>
        <p>X_test: {escape(result["X_test_file"])}</p>
        <p>Fitted preprocessing: {escape(result["preprocessor_file"])}</p>
        <p>Ustawienia kolumn: {escape(result["settings_file"])}</p>

        <h2>Próbka przekształconego X_train</h2>
        {result["preview_html"]}

        <p>
            <a href="/train-model">
                Przejdź do wyboru modelu i trenowania
            </a>
        </p>
        <p><a href="/transform-data">Wróć do wyboru kolumn</a></p>
    """

    return HTMLResponse(_page("Transformacja zakończona", body))


@router.get("/transform-data", response_class=HTMLResponse)
def show_transform_form():
    try:
        return _selection_page()
    except Exception as error:
        return HTMLResponse(
            _page(
                "Nie udało się wczytać danych",
                f'<p class="error">{escape(str(error))}</p>',
            ),
            status_code=400,
        )


@router.post("/transform-data", response_class=HTMLResponse)
def submit_transform(
    column_methods: list[str] = Form(...),
):
    try:
        result = transform_data(column_methods)
        return _result_page(result)
    except Exception as error:
        try:
            return _selection_page(str(error))
        except Exception as read_error:
            return HTMLResponse(
                _page(
                    "Nie udało się przekształcić danych",
                    f'<p class="error">{escape(str(error))}</p>'
                    f'<p class="error">{escape(str(read_error))}</p>',
                ),
                status_code=400,
            )