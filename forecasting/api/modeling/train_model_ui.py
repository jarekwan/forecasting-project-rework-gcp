

import json
from html import escape

from fastapi import APIRouter, Form
from fastapi.responses import HTMLResponse

from forecasting.services.modeling.training.train_model import train_model


router = APIRouter()


MODEL_PARAMETERS = {
    "random_forest_regressor": [
        {
            "name": "n_estimators",
            "label": "Liczba drzew",
            "type": "int",
            "default": 100,
            "min": 10,
            "max": 500,
        },
        {
            "name": "max_depth",
            "label": "Maksymalna głębokość drzewa",
            "type": "int",
            "default": 10,
            "min": 1,
            "max": 50,
        },
        {
            "name": "min_samples_split",
            "label": "Minimalna liczba próbek do podziału",
            "type": "int",
            "default": 2,
            "min": 2,
            "max": 20,
        },
    ],
    "svr": [
        {
            "name": "C",
            "label": "C",
            "type": "float",
            "default": 1.0,
            "min": 0.01,
            "max": 100.0,
        },
        {
            "name": "epsilon",
            "label": "Epsilon",
            "type": "float",
            "default": 0.1,
            "min": 0.01,
            "max": 1.0,
        },
        {
            "name": "kernel",
            "label": "Kernel",
            "type": "category",
            "default": "rbf",
            "choices": ["rbf", "linear", "poly"],
        },
        {
            "name": "gamma",
            "label": "Gamma",
            "type": "category",
            "default": "scale",
            "choices": ["scale", "auto"],
        },
        {
            "name": "degree",
            "label": "Stopień wielomianu (dla kernel poly)",
            "type": "int",
            "default": 3,
            "min": 2,
            "max": 8,
        },
    ],
    "xgboost_regressor": [
        {
            "name": "n_estimators",
            "label": "Liczba drzew",
            "type": "int",
            "default": 100,
            "min": 10,
            "max": 500,
        },
        {
            "name": "max_depth",
            "label": "Maksymalna głębokość drzewa",
            "type": "int",
            "default": 6,
            "min": 1,
            "max": 20,
        },
        {
            "name": "learning_rate",
            "label": "Learning rate",
            "type": "float",
            "default": 0.1,
            "min": 0.01,
            "max": 0.3,
        },
        {
            "name": "subsample",
            "label": "Udział próbek",
            "type": "float",
            "default": 1.0,
            "min": 0.5,
            "max": 1.0,
        },
    ],
}


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
            label {{ display: block; margin: 12px 0 6px; }}
            input, select {{
                box-sizing: border-box;
                width: 100%;
                max-width: 650px;
                padding: 9px;
            }}
            button {{ margin-top: 18px; padding: 10px 18px; cursor: pointer; }}
            table {{ border-collapse: collapse; margin: 16px 0; width: 100%; }}
            th, td {{
                border: 1px solid #aaa;
                padding: 8px;
                text-align: left;
                overflow-wrap: anywhere;
            }}
            .parameter {{
                border-bottom: 1px solid #ddd;
                padding: 10px 0;
                max-width: 680px;
            }}
            .choices label {{ display: inline-block; margin-right: 16px; }}
            .hint {{ color: #555; }}
            .error {{ color: #a00; }}
        </style>
    </head>
    <body>
        <h1>{escape(title)}</h1>
        {body}
    </body>
    </html>
    """


def _form(error: str = "") -> HTMLResponse:
    error_html = (
        f'<p class="error">{escape(error)}</p>'
        if error
        else ""
    )

    schema_json = json.dumps(MODEL_PARAMETERS)

    body = f"""
        {error_html}

        <form id="training-form" method="post" action="/train-model">
            <label for="model_name">Model:</label>
            <select id="model_name" name="model_name">
                <option value="random_forest_regressor">
                    Random Forest Regressor
                </option>
                <option value="svr">SVR</option>
                <option value="xgboost_regressor">XGBoost Regressor</option>
            </select>

            <label for="tuning_method">Metoda strojenia:</label>
            <select id="tuning_method" name="tuning_method">
                <option value="manual">Ustawienia ręczne</option>
                <option value="grid_search">GridSearch</option>
                <option value="random_search">RandomizedSearch</option>
                <option value="optuna">Optuna</option>
            </select>

            <div id="parameters"></div>

            <input type="hidden" id="parameters_payload" name="parameters">

            <div id="trials-container" style="display: none;">
                <label for="n_trials">Liczba prób Optuna:</label>
                <input id="n_trials" name="n_trials"
                       type="number" min="1" max="200" value="20">
            </div>

            <p class="hint" id="method-hint"></p>

            <button type="submit">Trenuj i oceń model</button>
        </form>

        <script>
            const modelParameters = {schema_json};
            const modelSelect = document.getElementById("model_name");
            const methodSelect = document.getElementById("tuning_method");
            const parametersDiv = document.getElementById("parameters");
            const trialsContainer = document.getElementById("trials-container");
            const methodHint = document.getElementById("method-hint");

            function addLabel(parent, text) {{
                const label = document.createElement("label");
                label.textContent = text;
                parent.appendChild(label);
            }}

            function addNumberInput(parent, id, value, min, max, step) {{
                const input = document.createElement("input");
                input.type = "number";
                input.id = id;
                input.value = value;
                input.min = min;
                input.max = max;
                input.step = step;
                parent.appendChild(input);
                return input;
            }}

            function renderParameters() {{
                const modelName = modelSelect.value;
                const method = methodSelect.value;
                const definitions = modelParameters[modelName];

                parametersDiv.innerHTML = "";
                trialsContainer.style.display =
                    method === "optuna" ? "block" : "none";

                if (method === "manual") {{
                    methodHint.textContent =
                        "Wpisz wartości parametrów wybranego modelu.";
                }} else if (method === "grid_search") {{
                    methodHint.textContent =
                        "Wpisz wartości do sprawdzenia. GridSearch przetestuje kombinacje.";
                }} else if (method === "random_search") {{
                    methodHint.textContent =
                        "Dla parametrów liczbowych podaj minimum i maksimum; dla kategorii wybierz wartości.";
                }} else {{
                    methodHint.textContent =
                        "Dla parametrów liczbowych podaj minimum i maksimum; dla kategorii wybierz wartości.";
                }}

                definitions.forEach((definition) => {{
                    const section = document.createElement("div");
                    section.className = "parameter";
                    section.dataset.name = definition.name;
                    section.dataset.type = definition.type;

                    addLabel(section, definition.label);

                    if (definition.type === "category") {{
                        if (method === "manual") {{
                            const select = document.createElement("select");
                            select.id = "param-" + definition.name;

                            definition.choices.forEach((choice) => {{
                                const option = document.createElement("option");
                                option.value = choice;
                                option.textContent = choice;
                                if (choice === definition.default) {{
                                    option.selected = true;
                                }}
                                select.appendChild(option);
                            }});

                            section.appendChild(select);
                        }} else {{
                            const choices = document.createElement("div");
                            choices.className = "choices";

                            definition.choices.forEach((choice) => {{
                                const label = document.createElement("label");
                                const checkbox = document.createElement("input");
                                checkbox.type = "checkbox";
                                checkbox.value = choice;
                                checkbox.dataset.parameter = definition.name;
                                checkbox.checked =
                                    choice === definition.default;

                                label.appendChild(checkbox);
                                label.appendChild(
                                    document.createTextNode(" " + choice)
                                );
                                choices.appendChild(label);
                            }});

                            section.appendChild(choices);
                        }}
                    }} else if (method === "manual") {{
                        const step =
                            definition.type === "int" ? "1" : "any";
                        addNumberInput(
                            section,
                            "param-" + definition.name,
                            definition.default,
                            definition.min,
                            definition.max,
                            step
                        );
                    }} else if (method === "grid_search") {{
                        const input = document.createElement("input");
                        input.type = "text";
                        input.id = "param-" + definition.name;
                        input.value =
                            String(definition.min) + "," +
                            String(definition.max);
                        input.placeholder = "oddziel wartości przecinkami";
                        section.appendChild(input);
                    }} else {{
                        const step =
                            definition.type === "int" ? "1" : "any";

                        addLabel(section, "Minimum:");
                        addNumberInput(
                            section,
                            "param-min-" + definition.name,
                            definition.min,
                            definition.min,
                            definition.max,
                            step
                        );

                        addLabel(section, "Maksimum:");
                        addNumberInput(
                            section,
                            "param-max-" + definition.name,
                            definition.max,
                            definition.min,
                            definition.max,
                            step
                        );
                    }}

                    parametersDiv.appendChild(section);
                }});
            }}

            function parseValue(raw, type) {{
                if (type === "int") {{
                    return parseInt(raw, 10);
                }}
                if (type === "float") {{
                    return parseFloat(raw);
                }}
                return raw;
            }}

            function buildParameters() {{
                const method = methodSelect.value;
                const parameters = {{}};

                for (const section of document.querySelectorAll(".parameter")) {{
                    const name = section.dataset.name;
                    const type = section.dataset.type;

                    if (type === "category") {{
                        if (method === "manual") {{
                            const select =
                                document.getElementById("param-" + name);
                            parameters[name] = select.value;
                        }} else {{
                            const checked = Array.from(
                                section.querySelectorAll(
                                    'input[type="checkbox"]:checked'
                                )
                            ).map((checkbox) => checkbox.value);

                            if (checked.length > 0) {{
                                parameters[name] = checked;
                            }}
                        }}
                        continue;
                    }}

                    if (method === "manual") {{
                        const input =
                            document.getElementById("param-" + name);
                        parameters[name] = parseValue(input.value, type);
                    }} else if (method === "grid_search") {{
                        const input =
                            document.getElementById("param-" + name);
                        const values = input.value
                            .split(",")
                            .map((value) => value.trim())
                            .filter((value) => value !== "")
                            .map((value) => parseValue(value, type));

                        if (values.length === 0) {{
                            alert("Wpisz wartości dla parametru " + name + ".");
                            return false;
                        }}
                        parameters[name] = values;
                    }} else {{
                        const minInput =
                            document.getElementById("param-min-" + name);
                        const maxInput =
                            document.getElementById("param-max-" + name);
                        const minValue = parseValue(minInput.value, type);
                        const maxValue = parseValue(maxInput.value, type);

                        if (minValue > maxValue) {{
                            alert("Minimum nie może być większe od maksimum: " + name);
                            return false;
                        }}

                        if (method === "random_search") {{
                            parameters[name] = {{
                                "min": minValue,
                                "max": maxValue
                            }};
                        }} else {{
                            parameters[name] = [minValue, maxValue];
                        }}
                    }}
                }}

                document.getElementById("parameters_payload").value =
                    JSON.stringify(parameters);
                return true;
            }}

            modelSelect.addEventListener("change", renderParameters);
            methodSelect.addEventListener("change", renderParameters);

            document
                .getElementById("training-form")
                .addEventListener("submit", function(event) {{
                    if (buildParameters() === false) {{
                        event.preventDefault();
                    }}
                }});

            renderParameters();
        </script>
    """

    return HTMLResponse(_page("Trenowanie modelu", body))


@router.get("/train-model", response_class=HTMLResponse)
def show_train_model_form() -> HTMLResponse:
    """Wyświetla formularz wyboru modelu i strojenia."""
    return _form()


@router.post("/train-model", response_class=HTMLResponse)
def submit_train_model(
    model_name: str = Form(...),
    tuning_method: str = Form(...),
    parameters: str = Form("{}"),
    n_trials: int = Form(20),
) -> HTMLResponse:
    """Przyjmuje formularz, uruchamia trening i wyświetla wynik."""
    try:
        parsed_parameters = json.loads(parameters or "{}")

        if not isinstance(parsed_parameters, dict):
            raise ValueError("Nieprawidłowe parametry modelu.")

        result = train_model(
            model_name=model_name,
            tuning_method=tuning_method,
            parameters=parsed_parameters,
            n_trials=n_trials,
        )

        rows = "".join(
            f"<tr><th>{escape(str(key))}</th>"
            f"<td>{escape(str(value))}</td></tr>"
            for key, value in result.items()
        )

        return HTMLResponse(
            _page(
                "Wyniki modelu",
                f"""
                <table>{rows}</table>
                <p><a href="/train-model">Uruchom kolejny eksperyment</a></p>
                """,
            )
        )

    except Exception as error:
        return _form(str(error))