from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templ import Templating

app = FastAPI()

# Definir la función generadora de resultados
async def generar_resultado(texto: str) -> str:
    # Simulando el proceso de generación del resultado (puede ser cualquier cosa)
    import asyncio
    await asyncio.sleep(2)  # Simula una espera de 2 segundos
    return texto.upper()

# Definir la ruta para procesar el texto y devolver el resultado
@app.post("/generar")
async def generar(texto: str):
    resultado = await generar_resultado(texto)
    return {"resultado": resultado}

# Definir la interfaz gráfica con FastAPI
class MyHTMLApp(Template):
    template = "main.html"

@app.get("/")
async def main(request: Request):
    # Crear una instancia de la interfaz gráfica
    template = Templating()
    html = await template.render_template("main.html", request=request)
    return HTMLResponse(html)

# Definir el archivo HTML para la interfaz gráfica
@app.get("/static/main.css")
async def main_css():
    # Crear una instancia del archivo CSS
    css = "/* Main Styles */\nbody {\n  background-color: #f0f0f0;\n}\n"
    return HTMLResponse(css)

# Definir el archivo HTML para la interfaz gráfica
@app.get("/static/main.html")
async def main_html():
    # Crear una instancia del archivo HTML
    html = """
    <html>
        <head>
            <title>My App</title>
        </head>
        <body>
            <h1>My App</h1>
            <form method="POST" action="/generar">
                <input type="text" name="texto" placeholder="Ingrese texto">
                <button type="submit">Generar</button>
            </form>
            <p id="resultado"></p>
        </body>
    </html>
    """
    return HTMLResponse(html)

# Definir el archivo CSS para la interfaz gráfica
@app.get("/static/main.js")
async def main_js():
    # Crear una instancia del archivo JS
    js = """
    // Get the result element
    const resultado = document.getElementById('resultado');

    // Add an event listener to the form submit event
    formulario.addEventListener('submit', (event) => {
        event.preventDefault();
        const texto = formulario.elements[0].value;
        fetch('/generar', { method: 'POST', body: JSON.stringify({ texto }) })
            .then((response) => response.json())
            .then((data) => resultado.innerText = data.resultado)
            .catch((error) => console.error(error));
    });
    """
    return HTMLResponse(js)