

# from html import escape

# from fastapi import APIRouter, Form, HTTPException, Request
# from fastapi.responses import HTMLResponse

# from forecasting.services.data.ingestion.choose_source import get_saved_dataframe_preview
# from forecasting.services.data.validation.detect_types import detect_types
# from forecasting.services.data.exploration.eda import (
#     apply_eda_adjustments,
#     clear_eda_adjustments,
#     get_descriptive_statistics,
#     get_eda_report,
# )
# from forecasting.services.data.selection.select_columns import get_saved_columns, select_dataframe_columns
# from forecasting.api.data.upload_ui import page


# router = APIRouter()


# def records_to_html(records: list, columns: list) -> str:
#     if not records:
#         return "<p>Brak danych do wyświetlenia.</p>"

#     headers = "".join(
#         f"<th>{escape(str(column))}</th>"
#         for column in columns
#     )

#     rows = []
#     for record in records:
#         cells = "".join(
#             f"<td>{escape(str(record.get(column, '')))}</td>"
#             for column in columns
#         )
#         rows.append(f"<tr>{cells}</tr>")

#     return (
#         "<table><thead><tr>"
#         + headers
#         + "</tr></thead><tbody>"
#         + "".join(rows)
#         + "</tbody></table>"
#     )


# def selection_form() -> str:
#     preview_data = get_saved_dataframe_preview()
#     columns = get_saved_columns()

#     checkboxes = "".join(
#         f'<label><input type="checkbox" name="selected_columns" '
#         f'value="{escape(str(column), quote=True)}"> '
#         f"{escape(str(column))}</label>"
#         for column in columns
#     )

#     preview_html = records_to_html(
#         preview_data["preview"],
#         preview_data["columns"],
#     )

#     return page(
#         "Wybierz kolumny",
#         f"""
#         <div class="section">
#             <p>Próbka wczytanego DataFrame'u:</p>
#             {preview_html}
#         </div>

#         <form method="post" action="/select-columns">
#             <p>Zaznacz jedną lub więcej kolumn:</p>
#             {checkboxes}
#             <button type="submit">Zapisz wybrane kolumny</button>
#         </form>
#         """,
#     )


# def _render_eda_page(
#     date_column: str = "",
#     demand_column: str = "",
#     message: str = "",
#     selected_outlier_actions: dict[str, str] | None = None,
#     selected_drop_columns: list[str] | None = None,
#     adjustment_result: dict | None = None,
# ) -> str:
#     selected_outlier_actions = selected_outlier_actions or {}
#     selected_drop_columns = selected_drop_columns or []

#     detected_types = detect_types()
#     descriptive_statistics = get_descriptive_statistics()
#     report = get_eda_report(date_column, demand_column)

#     type_labels = {
#         "numerical": "Liczbowa",
#         "categorical": "Tekstowa / kategoryczna",
#         "datetime": "Data",
#     }
#     column_types = {
#         str(column): type_labels.get(type_name, type_name)
#         for type_name, type_columns in detected_types.items()
#         for column in type_columns
#     }

#     type_rows = "".join(
#         "<tr>"
#         f"<td>{escape(str(column))}</td>"
#         f"<td>{escape(column_types.get(str(column), 'Nie rozpoznano'))}</td>"
#         "</tr>"
#         for column in report["columns"]
#     )

#     date_options = (
#         ""
#         if date_column
#         else (
#             '<option value="" disabled selected>'
#             "Wybierz kolumnę daty"
#             "</option>"
#         )
#     ) + "".join(
#         f'<option value="{escape(str(column), quote=True)}" '
#         f'{"selected" if str(column) == date_column else ""}>'
#         f"{escape(str(column))}</option>"
#         for column in report["date_options"]
#     )

#     demand_options = (
#         ""
#         if demand_column
#         else (
#             '<option value="" disabled selected>'
#             "Wybierz kolumnę popytu"
#             "</option>"
#         )
#     ) + "".join(
#         f'<option value="{escape(str(column), quote=True)}" '
#         f'{"selected" if str(column) == demand_column else ""}>'
#         f"{escape(str(column))}</option>"
#         for column in report["demand_options"]
#     )

#     message_html = (
#         f"<p><strong>{escape(message)}</strong></p>"
#         if message
#         else ""
#     )

#     adjustment_result_html = ""
#     if adjustment_result:
#         adjustment_result_html = f"""
#             <h2>DataFrame po korektach</h2>
#             <p>
#                 Zapisano:
#                 {escape(str(adjustment_result["dataframe_file"]))}
#             </p>
#             <p>Liczba wierszy: {adjustment_result["rows"]}</p>
#             <p>
#                 Kolumny:
#                 {escape(", ".join(adjustment_result["columns"]))}
#             </p>
#             {adjustment_result["preview_html"]}
#             <p>
#                 Raport EDA powyżej opisuje dane wybrane przed korektą.
#                 Skorygowany DataFrame zostanie użyty w kolejnym etapie
#                 przygotowania daty.
#             </p>
#         """

#     adjustment_form = ""

#     # Formularz korekt nie zależy od wygenerowania wykresu.
#     if report["outlier_columns"] or report["correlated_columns"]:
#         outlier_fields = ""

#         for index, column in enumerate(report["outlier_columns"]):
#             selected_action = selected_outlier_actions.get(column, "keep")

#             action_options = [
#                 ("keep", "Zostaw bez zmian"),
#                 ("clip", "Ogranicz do granic IQR/MAD"),
#                 ("median", "Zastąp medianą"),
#             ]

#             options_html = "".join(
#                 f'<option value="{action}" '
#                 f'{"selected" if selected_action == action else ""}>'
#                 f"{escape(label)}</option>"
#                 for action, label in action_options
#             )

#             outlier_fields += f"""
#                 <label>
#                     {escape(column)}:
#                     <select name="action_{index}">
#                         {options_html}
#                     </select>
#                     <input type="hidden" name="outlier_column"
#                            value="{escape(column, quote=True)}">
#                 </label>
#             """

#         eligible_correlated_columns = [
#             column
#             for column in report["correlated_columns"]
#             if column not in {date_column, demand_column}
#         ]

#         correlated_fields = "".join(
#             f'<label><input type="checkbox" name="drop_columns" '
#             f'value="{escape(column, quote=True)}" '
#             f'{"checked" if column in selected_drop_columns else ""}> '
#             f'Usuń kolumnę {escape(column)}</label>'
#             for column in eligible_correlated_columns
#         )

#         if not outlier_fields:
#             outlier_fields = (
#                 "<p>Raport nie oznaczył odstających wartości.</p>"
#             )

#         if not correlated_fields:
#             correlated_fields = (
#                 "<p>Brak kolumn do wyboru wśród silnie skorelowanych par."
#                 "</p>"
#             )

#         adjustment_form = f"""
#             <h2>Opcjonalne korekty po obejrzeniu raportu</h2>
#             <p>
#                 Formularz jest dostępny niezależnie od wykresu popytu.
#                 Wybierz działanie tylko wtedy, gdy uznasz je za potrzebne.
#                 Aplikacja niczego nie zmieni bez kliknięcia przycisku.
#             </p>

#             <form method="post" action="/apply-eda-adjustments">
#                 <label for="adjustment_date_column">
#                     Kolumna daty do zachowania:
#                 </label>
#                 <select id="adjustment_date_column"
#                         name="date_column"
#                         required>
#                     {date_options}
#                 </select>

#                 <label for="adjustment_demand_column">
#                     Kolumna popytu do zachowania:
#                 </label>
#                 <select id="adjustment_demand_column"
#                         name="demand_column"
#                         required>
#                     {demand_options}
#                 </select>

#                 <h3>Odstające wartości</h3>
#                 <p>
#                     Możesz zostawić wartości bez zmian, ograniczyć je do
#                     wyznaczonych granic albo zastąpić medianą.
#                 </p>
#                 {outlier_fields}

#                 <h3>Kolumny z silnie skorelowanych par</h3>
#                 <p>
#                     Silna korelacja oznacza, że dwie kolumny zmieniają się
#                     podobnie lub przeciwnie. Nie dowodzi, że kolumna jest
#                     błędna. Zaznacz do usunięcia tylko kolumnę, której nie
#                     chcesz używać w dalszej analizie.
#                 </p>
#                 {correlated_fields}

#                 <button type="submit">Zastosuj wybrane korekty</button>
#             </form>
#         """

#     return page(
#         "Raport EDA",
#         f"""
#         {message_html}

#         <p>DataFrame: {escape(report["dataframe_file"])}</p>
#         <p>Liczba wierszy: {report["rows"]}</p>

#         <h2>Rozpoznane typy kolumn</h2>
#         <p>
#             Ta tabela informuje, jak aplikacja rozpoznała każdą wybraną
#             kolumnę.
#         </p>
#         <table>
#             <thead>
#                 <tr><th>Kolumna</th><th>Typ</th></tr>
#             </thead>
#             <tbody>{type_rows}</tbody>
#         </table>

#         <h2>Statystyki opisowe kolumn liczbowych</h2>
#         <p>
#             Średnia i mediana opisują typowy poziom wartości, a odchylenie
#             standardowe pokazuje, jak bardzo wartości różnią się od średniej.
#             Kwartyle dzielą uporządkowane dane na części i pomagają ocenić
#             ich rozrzut.
#         </p>
#         {descriptive_statistics["statistics_html"]}
#         <p>
#             Raport CSV:
#             {escape(descriptive_statistics["statistics_file"])}
#         </p>

#         <h2>Skośność rozkładów</h2>
#         <p>
#             Skośność opisuje, czy większość wartości skupia się po jednej
#             stronie, a mniejsza liczba dużych lub małych wartości tworzy
#             długi „ogon”. Wynik bliski zeru oznacza bardziej symetryczny
#             rozkład; dodatni wskazuje ogon w stronę dużych wartości, a ujemny
#             — w stronę małych.
#         </p>
#         {report["skewness_html"]}
#         <p>
#             Przy |skośności| większej niż 1 raport do oznaczania wartości
#             odstających używa MAD; w pozostałych przypadkach używa IQR.
#         </p>
#         <p>Raport CSV: {escape(report["skewness_file"])}</p>

#         <h2>Histogramy i boxploty kolumn liczbowych</h2>
#         <p>
#             Histogram pokazuje, ile obserwacji mieści się w kolejnych
#             przedziałach wartości. Boxplot pokazuje medianę i rozrzut
#             środkowej części danych. Punkty poza głównym zakresem mogą być
#             nietypowe, ale nie muszą oznaczać błędu.
#         </p>
#         {report["distribution_html"]}

#         <h2>Potencjalne wartości odstające</h2>
#         <p>
#             Raport wskazuje wartości odległe od typowego zakresu. Mogą być
#             błędne albo przedstawiać prawdziwy przypadek, dlatego aplikacja
#             nie usuwa ich automatycznie.
#         </p>
#         {report["outlier_summary_html"]}
#         {report["outlier_details_html"]}
#         <p>Raport CSV: {escape(report["outlier_file"])}</p>

#         <h2>Korelacje kolumn liczbowych</h2>
#         <p>
#             Korelacja bliska 1 oznacza, że dwie kolumny często rosną razem;
#             bliska -1 — że jedna zwykle rośnie, gdy druga maleje; bliska 0
#             oznacza brak wyraźnego związku liniowego. Korelacja nie dowodzi,
#             że jedna kolumna powoduje zmianę drugiej.
#         </p>
#         {report["correlation_html"]}
#         <p>Macierz CSV: {escape(report["correlation_file"])}</p>

#         <h3>Najsilniej powiązane pary</h3>
#         {report["correlated_pairs_html"]}
#         <p>Raport par CSV: {escape(report["correlated_pairs_file"])}</p>

#         <h2>Wykres popytu w czasie</h2>
#         <p>
#             Wykres pokazuje zmiany wybranej wartości popytu w kolejnych
#             datach. Powtarzające się daty są na potrzeby wykresu sumowane.
#         </p>

#         <form method="post" action="/eda-report">
#             <label for="date_column">Kolumna daty:</label>
#             <select id="date_column" name="date_column" required>
#                 {date_options}
#             </select>

#             <label for="demand_column">Kolumna popytu:</label>
#             <select id="demand_column" name="demand_column" required>
#                 {demand_options}
#             </select>

#             <button type="submit">Pokaż wykres popytu</button>
#         </form>

#         {report["time_plot_html"]}

#         {adjustment_form}
#         {adjustment_result_html}

#         <h2>Próbka wybranego DataFrame'u</h2>
#         {report["preview_html"]}

#         <p><a href="/set-date">Przejdź do ustawień daty</a></p>
#         <p><a href="/">Wczytaj kolejny plik</a></p>
#         """,
#     )


# @router.get("/select-columns", response_class=HTMLResponse)
# def show_column_selection_form():
#     try:
#         return selection_form()
#     except Exception as error:
#         raise HTTPException(status_code=400, detail=str(error))


# @router.post("/select-columns", response_class=HTMLResponse)
# def submit_column_selection(
#     selected_columns: list[str] = Form(default=[]),
# ):
#     try:
#         select_dataframe_columns(selected_columns)
#         clear_eda_adjustments()
#         return _render_eda_page()
#     except Exception as error:
#         raise HTTPException(status_code=400, detail=str(error))


# @router.post("/eda-report", response_class=HTMLResponse)
# def show_eda_report(
#     date_column: str = Form(...),
#     demand_column: str = Form(...),
# ):
#     try:
#         return _render_eda_page(date_column, demand_column)
#     except Exception as error:
#         return HTMLResponse(
#             page(
#                 "Nie udało się przygotować raportu EDA",
#                 f"<p>{escape(str(error))}</p>"
#                 '<p><a href="/select-columns">Wróć</a></p>',
#             ),
#             status_code=400,
#         )


# @router.post("/apply-eda-adjustments", response_class=HTMLResponse)
# async def submit_eda_adjustments(request: Request):
#     form = await request.form()

#     date_column = str(form.get("date_column", ""))
#     demand_column = str(form.get("demand_column", ""))

#     drop_columns = [
#         str(value)
#         for value in form.getlist("drop_columns")
#     ]
#     outlier_columns = [
#         str(value)
#         for value in form.getlist("outlier_column")
#     ]

#     outlier_actions = {}
#     for index, column in enumerate(outlier_columns):
#         outlier_actions[column] = str(
#             form.get(f"action_{index}", "keep")
#         )

#     try:
#         result = apply_eda_adjustments(
#             outlier_actions=outlier_actions,
#             drop_columns=drop_columns,
#             date_column=date_column,
#             demand_column=demand_column,
#         )

#         message = (
#             "Korekty zapisano. df_selected.pkl pozostał bez zmian."
#         )

#         return _render_eda_page(
#             date_column=date_column,
#             demand_column=demand_column,
#             message=message,
#             selected_outlier_actions=outlier_actions,
#             selected_drop_columns=drop_columns,
#             adjustment_result=result,
#         )

#     except Exception as error:
#         try:
#             return HTMLResponse(
#                 _render_eda_page(
#                     date_column=date_column,
#                     demand_column=demand_column,
#                     message=f"Nie udało się zastosować korekty: {error}",
#                     selected_outlier_actions=outlier_actions,
#                     selected_drop_columns=drop_columns,
#                 ),
#                 status_code=400,
#             )
#         except Exception as read_error:
#             return HTMLResponse(
#                 page(
#                     "Nie udało się zastosować korekty",
#                     f"<p>{escape(str(error))}</p>"
#                     f"<p>{escape(str(read_error))}</p>",
#                 ),
#                 status_code=400,
#             )


from html import escape

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from starlette.datastructures import FormData

from forecasting.services.data.ingestion.choose_source import get_saved_dataframe_preview
from forecasting.services.data.validation.detect_types import detect_types
from forecasting.services.data.exploration.eda import (
    apply_eda_adjustments,
    clear_eda_adjustments,
    get_descriptive_statistics,
    get_eda_report,
)
from forecasting.services.data.selection.select_columns import (
    get_saved_columns,
    select_dataframe_columns,
)
from forecasting.api.data.upload_ui import page


router = APIRouter()


def records_to_html(records: list[dict], columns: list[str]) -> str:
    """Buduje tabelę HTML z rekordów podglądu."""
    if not records:
        return "<p>Brak danych do wyświetlenia.</p>"

    headers = "".join(
        f"<th>{escape(str(column))}</th>"
        for column in columns
    )

    rows = []
    for record in records:
        cells = "".join(
            f"<td>{escape(str(record.get(column, '')))}</td>"
            for column in columns
        )
        rows.append(f"<tr>{cells}</tr>")

    return (
        "<table><thead><tr>"
        + headers
        + "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def selection_form() -> str:
    """Przygotowuje stronę podglądu danych i formularz wyboru kolumn."""
    preview_data = get_saved_dataframe_preview()
    columns = get_saved_columns()

    checkboxes = "".join(
        f'<label><input type="checkbox" name="selected_columns" '
        f'value="{escape(str(column), quote=True)}"> '
        f"{escape(str(column))}</label>"
        for column in columns
    )

    preview_html = records_to_html(
        preview_data["preview"],
        preview_data["columns"],
    )

    return page(
        "Wybierz kolumny",
        f"""
        <div class="section">
            <p>Próbka wczytanego DataFrame'u:</p>
            {preview_html}
        </div>

        <form method="post" action="/select-columns">
            <p>Zaznacz jedną lub więcej kolumn:</p>
            {checkboxes}
            <button type="submit">Zapisz wybrane kolumny</button>
        </form>
        """,
    )


def _build_select_options(
    columns: list[str],
    selected_column: str,
    placeholder: str,
) -> str:
    """Buduje opcje HTML dla listy wyboru kolumn."""
    placeholder_html = ""

    if not selected_column:
        placeholder_html = (
            '<option value="" disabled selected>'
            f"{escape(placeholder)}"
            "</option>"
        )

    options_html = "".join(
        f'<option value="{escape(str(column), quote=True)}" '
        f'{"selected" if str(column) == selected_column else ""}>'
        f"{escape(str(column))}</option>"
        for column in columns
    )

    return placeholder_html + options_html


def _parse_eda_adjustments_form(
    form: FormData,
) -> tuple[str, str, dict[str, str], list[str]]:
    """Odczytuje wybory kolumn i działań z formularza korekt."""
    date_column = str(form.get("date_column", ""))
    demand_column = str(form.get("demand_column", ""))

    drop_columns = [
        str(value)
        for value in form.getlist("drop_columns")
    ]
    outlier_columns = [
        str(value)
        for value in form.getlist("outlier_column")
    ]

    outlier_actions = {
        column: str(form.get(f"action_{index}", "keep"))
        for index, column in enumerate(outlier_columns)
    }

    return date_column, demand_column, outlier_actions, drop_columns


def _render_eda_page(
    date_column: str = "",
    demand_column: str = "",
    message: str = "",
    selected_outlier_actions: dict[str, str] | None = None,
    selected_drop_columns: list[str] | None = None,
    adjustment_result: dict | None = None,
) -> str:
    """Pobiera dane raportu EDA i składa stronę HTML."""
    selected_outlier_actions = selected_outlier_actions or {}
    selected_drop_columns = selected_drop_columns or []

    detected_types = detect_types()
    descriptive_statistics = get_descriptive_statistics()
    report = get_eda_report(date_column, demand_column)

    type_labels = {
        "numerical": "Liczbowa",
        "categorical": "Tekstowa / kategoryczna",
        "datetime": "Data",
    }
    column_types = {
        str(column): type_labels.get(type_name, type_name)
        for type_name, type_columns in detected_types.items()
        for column in type_columns
    }

    type_rows = "".join(
        "<tr>"
        f"<td>{escape(str(column))}</td>"
        f"<td>{escape(column_types.get(str(column), 'Nie rozpoznano'))}</td>"
        "</tr>"
        for column in report["columns"]
    )

    date_options = _build_select_options(
        columns=report["date_options"],
        selected_column=date_column,
        placeholder="Wybierz kolumnę daty",
    )
    demand_options = _build_select_options(
        columns=report["demand_options"],
        selected_column=demand_column,
        placeholder="Wybierz kolumnę popytu",
    )

    message_html = (
        f"<p><strong>{escape(message)}</strong></p>"
        if message
        else ""
    )

    adjustment_result_html = ""
    if adjustment_result:
        adjustment_result_html = f"""
            <h2>DataFrame po korektach</h2>
            <p>
                Zapisano:
                {escape(str(adjustment_result["dataframe_file"]))}
            </p>
            <p>Liczba wierszy: {adjustment_result["rows"]}</p>
            <p>
                Kolumny:
                {escape(", ".join(adjustment_result["columns"]))}
            </p>
            {adjustment_result["preview_html"]}
            <p>
                Raport EDA powyżej opisuje dane wybrane przed korektą.
                Skorygowany DataFrame zostanie użyty w kolejnym etapie
                przygotowania daty.
            </p>
        """

    adjustment_form = ""

    # Formularz korekt nie zależy od wygenerowania wykresu.
    if report["outlier_columns"] or report["correlated_columns"]:
        outlier_fields = ""

        for index, column in enumerate(report["outlier_columns"]):
            selected_action = selected_outlier_actions.get(column, "keep")

            action_options = [
                ("keep", "Zostaw bez zmian"),
                ("clip", "Ogranicz do granic IQR/MAD"),
                ("median", "Zastąp medianą"),
            ]

            options_html = "".join(
                f'<option value="{action}" '
                f'{"selected" if selected_action == action else ""}>'
                f"{escape(label)}</option>"
                for action, label in action_options
            )

            outlier_fields += f"""
                <label>
                    {escape(column)}:
                    <select name="action_{index}">
                        {options_html}
                    </select>
                    <input type="hidden" name="outlier_column"
                           value="{escape(column, quote=True)}">
                </label>
            """

        eligible_correlated_columns = [
            column
            for column in report["correlated_columns"]
            if column not in {date_column, demand_column}
        ]

        correlated_fields = "".join(
            f'<label><input type="checkbox" name="drop_columns" '
            f'value="{escape(column, quote=True)}" '
            f'{"checked" if column in selected_drop_columns else ""}> '
            f'Usuń kolumnę {escape(column)}</label>'
            for column in eligible_correlated_columns
        )

        if not outlier_fields:
            outlier_fields = (
                "<p>Raport nie oznaczył odstających wartości.</p>"
            )

        if not correlated_fields:
            correlated_fields = (
                "<p>Brak kolumn do wyboru wśród silnie skorelowanych par."
                "</p>"
            )

        adjustment_form = f"""
            <h2>Opcjonalne korekty po obejrzeniu raportu</h2>
            <p>
                Formularz jest dostępny niezależnie od wykresu popytu.
                Wybierz działanie tylko wtedy, gdy uznasz je za potrzebne.
                Aplikacja niczego nie zmieni bez kliknięcia przycisku.
            </p>

            <form method="post" action="/apply-eda-adjustments">
                <label for="adjustment_date_column">
                    Kolumna daty do zachowania:
                </label>
                <select id="adjustment_date_column"
                        name="date_column"
                        required>
                    {date_options}
                </select>

                <label for="adjustment_demand_column">
                    Kolumna popytu do zachowania:
                </label>
                <select id="adjustment_demand_column"
                        name="demand_column"
                        required>
                    {demand_options}
                </select>

                <h3>Odstające wartości</h3>
                <p>
                    Możesz zostawić wartości bez zmian, ograniczyć je do
                    wyznaczonych granic albo zastąpić medianą.
                </p>
                {outlier_fields}

                <h3>Kolumny z silnie skorelowanych par</h3>
                <p>
                    Silna korelacja oznacza, że dwie kolumny zmieniają się
                    podobnie lub przeciwnie. Nie dowodzi, że kolumna jest
                    błędna. Zaznacz do usunięcia tylko kolumnę, której nie
                    chcesz używać w dalszej analizie.
                </p>
                {correlated_fields}

                <button type="submit">Zastosuj wybrane korekty</button>
            </form>
        """

    return page(
        "Raport EDA",
        f"""
        {message_html}

        <p>DataFrame: {escape(report["dataframe_file"])}</p>
        <p>Liczba wierszy: {report["rows"]}</p>

        <h2>Rozpoznane typy kolumn</h2>
        <p>
            Ta tabela informuje, jak aplikacja rozpoznała każdą wybraną
            kolumnę.
        </p>
        <table>
            <thead>
                <tr><th>Kolumna</th><th>Typ</th></tr>
            </thead>
            <tbody>{type_rows}</tbody>
        </table>

        <h2>Statystyki opisowe kolumn liczbowych</h2>
        <p>
            Średnia i mediana opisują typowy poziom wartości, a odchylenie
            standardowe pokazuje, jak bardzo wartości różnią się od średniej.
            Kwartyle dzielą uporządkowane dane na części i pomagają ocenić
            ich rozrzut.
        </p>
        {descriptive_statistics["statistics_html"]}
        <p>
            Raport CSV:
            {escape(descriptive_statistics["statistics_file"])}
        </p>

        <h2>Skośność rozkładów</h2>
        <p>
            Skośność opisuje, czy większość wartości skupia się po jednej
            stronie, a mniejsza liczba dużych lub małych wartości tworzy
            długi „ogon”. Wynik bliski zeru oznacza bardziej symetryczny
            rozkład; dodatni wskazuje ogon w stronę dużych wartości, a ujemny
            — w stronę małych.
        </p>
        {report["skewness_html"]}
        <p>
            Przy |skośności| większej niż 1 raport do oznaczania wartości
            odstających używa MAD; w pozostałych przypadkach używa IQR.
        </p>
        <p>Raport CSV: {escape(report["skewness_file"])}</p>

        <h2>Histogramy i boxploty kolumn liczbowych</h2>
        <p>
            Histogram pokazuje, ile obserwacji mieści się w kolejnych
            przedziałach wartości. Boxplot pokazuje medianę i rozrzut
            środkowej części danych. Punkty poza głównym zakresem mogą być
            nietypowe, ale nie muszą oznaczać błędu.
        </p>
        {report["distribution_html"]}

        <h2>Potencjalne wartości odstające</h2>
        <p>
            Raport wskazuje wartości odległe od typowego zakresu. Mogą być
            błędne albo przedstawiać prawdziwy przypadek, dlatego aplikacja
            nie usuwa ich automatycznie.
        </p>
        {report["outlier_summary_html"]}
        {report["outlier_details_html"]}
        <p>Raport CSV: {escape(report["outlier_file"])}</p>

        <h2>Korelacje kolumn liczbowych</h2>
        <p>
            Korelacja bliska 1 oznacza, że dwie kolumny często rosną razem;
            bliska -1 — że jedna zwykle rośnie, gdy druga maleje; bliska 0
            oznacza brak wyraźnego związku liniowego. Korelacja nie dowodzi,
            że jedna kolumna powoduje zmianę drugiej.
        </p>
        {report["correlation_html"]}
        <p>Macierz CSV: {escape(report["correlation_file"])}</p>

        <h3>Najsilniej powiązane pary</h3>
        {report["correlated_pairs_html"]}
        <p>Raport par CSV: {escape(report["correlated_pairs_file"])}</p>

        <h2>Wykres popytu w czasie</h2>
        <p>
            Wykres pokazuje zmiany wybranej wartości popytu w kolejnych
            datach. Powtarzające się daty są na potrzeby wykresu sumowane.
        </p>

        <form method="post" action="/eda-report">
            <label for="date_column">Kolumna daty:</label>
            <select id="date_column" name="date_column" required>
                {date_options}
            </select>

            <label for="demand_column">Kolumna popytu:</label>
            <select id="demand_column" name="demand_column" required>
                {demand_options}
            </select>

            <button type="submit">Pokaż wykres popytu</button>
        </form>

        {report["time_plot_html"]}

        {adjustment_form}
        {adjustment_result_html}

        <h2>Próbka wybranego DataFrame'u</h2>
        {report["preview_html"]}

        <p><a href="/set-date">Przejdź do ustawień daty</a></p>
        <p><a href="/">Wczytaj kolejny plik</a></p>
        """,
    )


@router.get("/select-columns", response_class=HTMLResponse)
def show_column_selection_form():
    try:
        return selection_form()
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.post("/select-columns", response_class=HTMLResponse)
def submit_column_selection(
    selected_columns: list[str] = Form(default=[]),
):
    try:
        select_dataframe_columns(selected_columns)
        clear_eda_adjustments()
        return _render_eda_page()
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.post("/eda-report", response_class=HTMLResponse)
def show_eda_report(
    date_column: str = Form(...),
    demand_column: str = Form(...),
):
    try:
        return _render_eda_page(date_column, demand_column)
    except Exception as error:
        return HTMLResponse(
            page(
                "Nie udało się przygotować raportu EDA",
                f"<p>{escape(str(error))}</p>"
                '<p><a href="/select-columns">Wróć</a></p>',
            ),
            status_code=400,
        )


@router.post("/apply-eda-adjustments", response_class=HTMLResponse)
async def submit_eda_adjustments(request: Request):
    form = await request.form()
    (
        date_column,
        demand_column,
        outlier_actions,
        drop_columns,
    ) = _parse_eda_adjustments_form(form)

    try:
        result = apply_eda_adjustments(
            outlier_actions=outlier_actions,
            drop_columns=drop_columns,
            date_column=date_column,
            demand_column=demand_column,
        )

        message = (
            "Korekty zapisano. df_selected.pkl pozostał bez zmian."
        )

        return _render_eda_page(
            date_column=date_column,
            demand_column=demand_column,
            message=message,
            selected_outlier_actions=outlier_actions,
            selected_drop_columns=drop_columns,
            adjustment_result=result,
        )

    except Exception as error:
        try:
            return HTMLResponse(
                _render_eda_page(
                    date_column=date_column,
                    demand_column=demand_column,
                    message=f"Nie udało się zastosować korekty: {error}",
                    selected_outlier_actions=outlier_actions,
                    selected_drop_columns=drop_columns,
                ),
                status_code=400,
            )
        except Exception as read_error:
            return HTMLResponse(
                page(
                    "Nie udało się zastosować korekty",
                    f"<p>{escape(str(error))}</p>"
                    f"<p>{escape(str(read_error))}</p>",
                ),
                status_code=400,
            )