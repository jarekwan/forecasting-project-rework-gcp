# from html import escape

# from fastapi import APIRouter, Form, HTTPException
# from fastapi.responses import HTMLResponse

# from forecasting.services.data.selection.set_date import (
#     get_date_column_options,
#     save_date_settings,
#     set_date,
# )
# from forecasting.api.data.upload_ui import page

# router = APIRouter()


# @router.get("/set-date", response_class=HTMLResponse)
# def show_date_settings_form():
#     try:
#         date_columns = get_date_column_options()

#         options = "".join(
#             f'<option value="{escape(str(column), quote=True)}">'
#             f"{escape(str(column))}</option>"
#             for column in date_columns
#         )

#         return page(
#             "Ustawienia daty",
#             f"""
#             <form method="post" action="/set-date">
#                 <label for="date_column">Kolumna daty:</label>
#                 <select id="date_column" name="date_column" required>
#                     {options}
#                 </select>

#                 <label for="duplicate_method">
#                     Obsługa duplikatów dla danych liczbowych:
#                 </label>
#                 <select id="duplicate_method" name="duplicate_method">
#                     <option value="mean">Średnia</option>
#                     <option value="sum">Suma</option>
#                 </select>

#                 <label for="fill_method">Uzupełnianie braków:</label>
#                 <select id="fill_method" name="fill_method">
#                     <option value="zero">Zera</option>
#                     <option value="ffill">Poprzednia wartość</option>
#                     <option value="mean">Średnia</option>
#                 </select>

#                 <button type="submit">
#                     Zapisz ustawienia i przetwórz dane
#                 </button>
#             </form>
#             """,
#         )

#     except Exception as error:
#         raise HTTPException(status_code=400, detail=str(error))


# @router.post("/set-date", response_class=HTMLResponse)
# def submit_date_settings(
#     date_column: str = Form(...),
#     duplicate_method: str = Form(...),
#     fill_method: str = Form(...),
# ):
#     try:
#         settings_path = save_date_settings(
#             date_column=date_column,
#             duplicate_method=duplicate_method,
#             fill_method=fill_method,
#         )
#         result = set_date()

#         return page(
#             "Dane przygotowane według daty",
#             f"""
#             <p>Ustawienia: {escape(str(settings_path))}</p>
#             <p>DataFrame: {escape(str(result["dataframe_file"]))}</p>
#             <p>Liczba wierszy: {result["rows"]}</p>
#             <p>Kolumny: {escape(", ".join(result["columns"]))}</p>

#             <h2>Próbka zapisanego DataFrame'u</h2>
#             {result["preview_html"]}

#             <p><a href="/clean-data">Przejdź do czyszczenia danych</a></p>
#             <p><a href="/">Wczytaj kolejny plik</a></p>
#             """,
#         )

#     except Exception as error:
#         raise HTTPException(status_code=400, detail=str(error))

from html import escape
from typing import Any

from fastapi import APIRouter, Form, HTTPException
from fastapi.responses import HTMLResponse

from forecasting.api.data.upload_ui import page
from forecasting.services.data.selection.set_date import (
    get_date_column_options,
    save_date_settings,
    set_date,
)


router = APIRouter()


def _build_date_column_options(date_columns: list[str]) -> str:
    """Buduje HTML <option> dla dostępnych kolumn daty."""
    return "".join(
        f'<option value="{escape(str(column), quote=True)}">'
        f"{escape(str(column))}</option>"
        for column in date_columns
    )


def _build_date_settings_form(date_columns: list[str]) -> str:
    """Buduje treść formularza ustawień daty."""
    options = _build_date_column_options(date_columns)
    return f"""
        <form method="post" action="/set-date">
            <label for="date_column">Kolumna daty:</label>
            <select id="date_column" name="date_column" required>
                {options}
            </select>

            <label for="duplicate_method">
                Obsługa duplikatów dla danych liczbowych:
            </label>
            <select id="duplicate_method" name="duplicate_method">
                <option value="mean">Średnia</option>
                <option value="sum">Suma</option>
            </select>

            <label for="fill_method">Uzupełnianie braków:</label>
            <select id="fill_method" name="fill_method">
                <option value="zero">Zera</option>
                <option value="ffill">Poprzednia wartość</option>
                <option value="mean">Średnia</option>
            </select>

            <button type="submit">
                Zapisz ustawienia i przetwórz dane
            </button>
        </form>
    """


def _build_date_result_page(
    settings_path: str,
    result: dict[str, Any],
) -> str:
    """Buduje stronę z wynikiem przetwarzania dat."""
    columns = ", ".join(str(column) for column in result["columns"])
    body = f"""
        <p>Ustawienia: {escape(settings_path)}</p>
        <p>DataFrame: {escape(str(result["dataframe_file"]))}</p>
        <p>Liczba wierszy: {result["rows"]}</p>
        <p>Kolumny: {escape(columns)}</p>

        <h2>Próbka zapisanego DataFrame'u</h2>
        {result["preview_html"]}

        <p><a href="/clean-data">Przejdź do czyszczenia danych</a></p>
        <p><a href="/">Wczytaj kolejny plik</a></p>
    """
    return page("Dane przygotowane według dat", body)


@router.get("/set-date", response_class=HTMLResponse)
def show_date_settings_form() -> str:
    """Pobiera dostępne kolumny i pokazuje formularz ustawień daty."""
    try:
        date_columns = get_date_column_options()
        body = _build_date_settings_form(date_columns)
        return page("Ustawienia daty", body)
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/set-date", response_class=HTMLResponse)
def submit_date_settings(
    date_column: str = Form(...),
    duplicate_method: str = Form(...),
    fill_method: str = Form(...),
) -> str:
    """Zapisuje ustawienia, uruchamia przetwarzanie i zwraca stronę wyniku."""
    try:
        settings_path = save_date_settings(
            date_column=date_column,
            duplicate_method=duplicate_method,
            fill_method=fill_method,
        )
        result = set_date()
        return _build_date_result_page(settings_path, result)
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error)) from error