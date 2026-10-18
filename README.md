# Trivia multijugador en Python

Prototipo educativo de juego de preguntas por turnos para 2 a 10 jugadores.

## Requisitos
- Python 3.11 o posterior recomendado.
- Tkinter (normalmente incluido con Python; en algunas distribuciones Linux se instala aparte).
- Acceso a Internet o red entre los equipos.

## Instalación

```bash
python -m venv .venv
```

Activar el entorno virtual:
- Windows PowerShell: `.venv\Scripts\Activate.ps1`
- Linux/macOS: `source .venv/bin/activate`

Instalar dependencias:

```bash
python -m pip install -r requirements.txt
```

## Prueba en una sola computadora

Terminal 1:

```bash
python server.py
```

Terminales 2 y 3:

```bash
python client.py
```

Deja la dirección `ws://127.0.0.1:8765` para las pruebas locales. Entra con dos nombres distintos. El primer jugador conectado será el anfitrión y podrá iniciar la partida.

## Prueba en una red local

En `client.py`, escribe en Servidor la dirección LAN del equipo que ejecuta el servidor, por ejemplo `ws://192.168.1.50:8765`. La IP es solo un ejemplo: usa la dirección real del servidor. Autoriza el puerto TCP 8765 en el firewall únicamente para la red de prueba.

## Prueba por Internet

No expongas directamente este prototipo a Internet tal cual. Para una publicación real, despliega el servidor en un VPS y configura un proxy inverso con TLS para ofrecer `wss://`, límites de conexiones, autenticación, registro y protección contra abuso. Los clientes deben usar la URL `wss://` publicada.

## Reglas del prototipo
- Una sola sala compartida.
- Entre 2 y 10 jugadores.
- El primer jugador es el anfitrión.
- Solo el anfitrión inicia la partida.
- Cada jugador responde una pregunta por turno.
- Hay 5 preguntas; cada respuesta correcta suma un punto.
- La partida termina al completar todas las preguntas o si queda menos de 2 jugadores conectados.

Este código es una base de aprendizaje, no un servidor listo para producción.
