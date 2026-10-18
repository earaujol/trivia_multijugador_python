import asyncio
import json
import queue
import threading
import tkinter as tk
from tkinter import messagebox

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed


class NetworkClient:
    """Ejecuta la conexión WebSocket en un hilo separado de Tkinter."""
    def __init__(self, incoming_queue):
        self.incoming_queue = incoming_queue
        self.loop = None
        self.websocket = None
        self.thread = None

    def start(self, uri):
        self.thread = threading.Thread(target=self._thread_main, args=(uri,), daemon=True)
        self.thread.start()

    def _thread_main(self, uri):
        asyncio.run(self._run(uri))

    async def _run(self, uri):
        self.loop = asyncio.get_running_loop()
        try:
            async with connect(uri, open_timeout=8) as websocket:
                self.websocket = websocket
                self.incoming_queue.put({"type": "connected"})
                async for raw in websocket:
                    try:
                        self.incoming_queue.put(json.loads(raw))
                    except json.JSONDecodeError:
                        self.incoming_queue.put({"type": "error", "message": "El servidor envió un mensaje inválido."})
        except Exception as exc:
            self.incoming_queue.put({"type": "error", "message": f"No se pudo mantener la conexión: {exc}"})
        finally:
            self.websocket = None
            self.incoming_queue.put({"type": "disconnected"})

    async def _send(self, payload):
        if self.websocket is not None:
            await self.websocket.send(json.dumps(payload, ensure_ascii=False))

    def send(self, payload):
        if self.loop is not None and self.websocket is not None:
            asyncio.run_coroutine_threadsafe(self._send(payload), self.loop)


class GameClientApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Trivia multijugador")
        self.root.geometry("640x570")
        self.root.minsize(560, 500)
        self.incoming = queue.Queue()
        self.network = None
        self.player_id = None
        self.player_name = "Jugador"
        self.state = None

        connection = tk.Frame(root, padx=10, pady=10)
        connection.pack(fill="x")
        tk.Label(connection, text="Servidor:").grid(row=0, column=0, sticky="w")
        self.server_entry = tk.Entry(connection, width=30)
        self.server_entry.insert(0, "ws://127.0.0.1:8765")
        self.server_entry.grid(row=0, column=1, padx=5, sticky="ew")
        tk.Label(connection, text="Tu nombre:").grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.name_entry = tk.Entry(connection, width=22)
        self.name_entry.insert(0, "Jugador")
        self.name_entry.grid(row=1, column=1, padx=5, pady=(8, 0), sticky="w")
        self.connect_button = tk.Button(connection, text="Conectar y entrar", command=self.connect)
        self.connect_button.grid(row=0, column=2, rowspan=2, padx=5)
        connection.columnconfigure(1, weight=1)

        self.status_label = tk.Label(root, text="Desconectado", anchor="w", padx=10, fg="navy")
        self.status_label.pack(fill="x")
        tk.Label(root, text="Jugadores y puntuación", font=("Arial", 11, "bold")).pack(anchor="w", padx=10, pady=(8, 0))
        self.players_list = tk.Listbox(root, height=6)
        self.players_list.pack(fill="x", padx=10, pady=5)

        self.start_button = tk.Button(root, text="Iniciar partida (anfitrión)", command=self.start_game, state="disabled")
        self.start_button.pack(pady=5)
        self.question_label = tk.Label(root, text="Conéctate y espera a que se unan al menos 2 jugadores.",
                                        font=("Arial", 13, "bold"), wraplength=600, justify="center", pady=12)
        self.question_label.pack(fill="x", padx=10)

        self.answer_buttons = []
        answers = tk.Frame(root, padx=10)
        answers.pack(fill="x")
        for index in range(4):
            button = tk.Button(answers, text=f"Opción {index + 1}", state="disabled",
                               command=lambda i=index: self.answer(i), height=2)
            button.pack(fill="x", pady=3)
            self.answer_buttons.append(button)

        self.notice_label = tk.Label(root, text="", wraplength=600, fg="darkgreen", pady=8)
        self.notice_label.pack(fill="x", padx=10)

        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(100, self.poll_messages)
        self.reset_ui()

    def set_status(self, text, color="navy"):
        self.status_label.config(text=text, fg=color)

    def reset_ui(self):
        self.player_id = None
        self.state = None
        self.start_button.config(state="disabled")
        self.players_list.delete(0, tk.END)
        self.question_label.config(text="Conéctate y espera a que se unan al menos 2 jugadores.",
                                  fg="black")
        self.notice_label.config(text="", fg="darkgreen")
        for index, button in enumerate(self.answer_buttons):
            button.config(text=f"Opción {index + 1}", state="disabled")

    def connect(self):
        if self.network is not None:
            return
        uri = self.server_entry.get().strip()
        name = self.name_entry.get().strip() or "Jugador"
        if not uri.startswith(("ws://", "wss://")):
            messagebox.showerror("Dirección inválida", "La dirección debe comenzar con ws:// o wss://")
            return
        self.player_name = name[:20]
        self.connect_button.config(state="disabled")
        self.set_status("Conectando…")
        self.reset_ui()
        self.network = NetworkClient(self.incoming)
        self.network.start(uri)

    def start_game(self):
        if self.network:
            self.network.send({"action": "start"})
            self.start_button.config(state="disabled")

    def answer(self, choice):
        if self.network:
            self.network.send({"action": "answer", "choice": choice})
            for button in self.answer_buttons:
                button.config(state="disabled")

    def poll_messages(self):
        while True:
            try:
                message = self.incoming.get_nowait()
            except queue.Empty:
                break
            kind = message.get("type")
            if kind == "connected":
                self.set_status("Conectado; entrando a la sala…")
                if self.network:
                    self.network.send({"action": "join", "name": self.player_name})
            elif kind == "welcome":
                self.player_id = message.get("player_id")
                self.set_status(f"Conectado como {self.player_name} (ID {self.player_id})")
            elif kind == "state":
                self.state = message.get("state", {})
                self.render_state()
            elif kind == "error":
                self.notice_label.config(text=message.get("message", "Error de conexión."), fg="firebrick")
            elif kind == "disconnected":
                self.set_status("Desconectado del servidor", color="firebrick")
                self.connect_button.config(state="normal")
                self.network = None
                self.reset_ui()
        self.root.after(100, self.poll_messages)

    def render_state(self):
        state = self.state or {}
        self.players_list.delete(0, tk.END)
        for player in state.get("players", []):
            suffix = " (anfitrión)" if player["id"] == state.get("host_id") else ""
            self.players_list.insert(tk.END, f"{player['name']}: {player['score']} punto(s){suffix}")

        self.notice_label.config(text=state.get("notice", ""), fg="darkgreen")
        is_host = self.player_id is not None and self.player_id == state.get("host_id")
        can_start = is_host and not state.get("started") and len(state.get("players", [])) >= 2
        self.start_button.config(state="normal" if can_start else "disabled")

        question = state.get("question")
        is_my_turn = self.player_id is not None and self.player_id == state.get("current_turn_id")
        if state.get("finished"):
            self.question_label.config(text=f"¡Partida terminada! Ganador: {state.get('winner') or 'sin ganador'}", fg="black")
            for button in self.answer_buttons:
                button.config(state="disabled")
        elif not state.get("started"):
            self.question_label.config(text="Esperando al anfitrión. Se necesitan al menos 2 jugadores.", fg="black")
            for button in self.answer_buttons:
                button.config(state="disabled")
        elif question:
            self.question_label.config(
                text=f"Pregunta {state.get('question_number')} de {state.get('total_questions')}\n\n{question['text']}\n\n" + ("Es tu turno." if is_my_turn else "Espera tu turno."),
                fg="black",
            )
            for index, button in enumerate(self.answer_buttons):
                if index < len(question["choices"]):
                    button.config(text=question["choices"][index], state="normal" if is_my_turn else "disabled")
                else:
                    button.config(state="disabled")
        else:
            self.question_label.config(text="Preparando pregunta…", fg="black")
            for button in self.answer_buttons:
                button.config(state="disabled")

    def close(self):
        if self.network and self.network.websocket is not None and self.network.loop is not None:
            try:
                asyncio.run_coroutine_threadsafe(self.network.websocket.close(), self.network.loop)
            except RuntimeError:
                pass
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = GameClientApp(root)
    root.mainloop()
