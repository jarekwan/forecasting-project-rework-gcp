from html import escape

from fastapi import APIRouter, Form, HTTPException
from fastapi.responses import HTMLResponse

from forecasting.services.data.cleaning.clean_data import (
    clean_data,
    get_cleaning_options,
    save_cleaning_methods,
)
from forecasting.api.data.upload_ui import page

router = APIRouter()


@router.get("/clean-data", response_class=HTMLResponse)
def show_cleaning_form():
    try:
        options = get_cleaning_options()

        fields = "".join(
            f"""
            <div class="section">
                <label>
                    <strong>{escape(str(item["column"]))}</strong>
                    — braków: {item["missing"]}
                </label>
                <select name="methods" required>
                    <option value="none">Bez zmian</option>
                    <option value="drop">Usuń wiersze z brakiem</option>
                    <option value="zero">Uzupełnij zerem</option>
                    <option value="ffill">Uzupełnij poprzednią wartością</option>
                    <option value="mean">Średnia (tekst: poprzednia wartość)</option>
                </select>
            </div>
            """
            for item in options
        )

        return page(
            "Czyszczenie danych",
            f"""
            <p>Dla każdej kolumny wybierz sposób obsługi brakujących wartości.
            Liczba braków pochodzi z <code>df_date.pkl</code>.</p>

            <form method="post" action="/clean-data">
                {fields}
                <button type="submit">Zapisz metody i wyczyść dane</button>
            </form>
            """,
        )

    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.post("/clean-data", response_class=HTMLResponse)
def submit_cleaning_form(methods: list[str] = Form(...)):
    try:
        options = get_cleaning_options()

        if len(methods) != len(options):
            raise ValueError("Wybierz metodę dla każdej kolumny.")

        method_map = {
            item["column"]: method
            for item, method in zip(options, methods)
        }

        settings_path = save_cleaning_methods(method_map)
        result = clean_data()

        return page(
            "Dane wyczyszczone",
            f"""
            <p>Ustawienia: {escape(str(settings_path))}</p>
            <p>DataFrame: {escape(str(result["dataframe_file"]))}</p>
            <p>Liczba wierszy: {result["rows"]}</p>
            <p>Kolumny: {escape(", ".join(result["columns"]))}</p>

            <h2>Próbka zapisanego DataFrame'u</h2>
            {result["preview_html"]}

            <p><a href="/date-features">
                Przejdź do tworzenia cech daty
            </a></p>
            """,
        )

    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))