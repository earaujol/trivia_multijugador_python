import asyncio
import json
import uuid
from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed

HOST = "0.0.0.0"
PORT = 8765
MAX_PLAYERS = 10

QUESTIONS = [
    {"text": "¿Cuánto es 2 + 2?", "choices": ["3", "4", "5", "6"], "correct": 1},
    {"text": "¿Cuál es la capital de Ecuador?", "choices": ["Lima", "Quito", "Bogotá", "La Paz"], "correct": 1},
    {"text": "¿Cuántos días tiene una semana?", "choices": ["5", "6", "7", "8"], "correct": 2},
    {"text": "¿Qué tipo de animal es una rana?", "choices": ["Mamífero", "Ave", "Anfibio", "Reptil"], "correct": 2},
    {"text": "¿Cuánto es 5 × 3?", "choices": ["8", "10", "15", "20"], "correct": 2},
]


class GameServer:
    def __init__(self):
        self.players = []  # Cada jugador incluye su conexión WebSocket.
        self.started = False
        self.finished = False
        self.question_index = 0
        self.turn_index = 0
        self.notice = "Esperando jugadores. El primero en conectarse será el anfitrión."
        self.lock = asyncio.Lock()

    def normalize_turn_index(self):
        if not self.players:
            self.turn_index = 0
        elif self.turn_index >= len(self.players):
            self.turn_index = 0

    def remove_player(self, player):
        if player not in self.players:
            return

        old_index = self.players.index(player)
        self.players.remove(player)

        if not self.players:
            self.started = False
            self.finished = False
            self.question_index = 0
            self.turn_index = 0
            self.notice = "Sala vacía. Esperando jugadores."
            return

        if old_index < self.turn_index:
            self.turn_index -= 1
        if self.turn_index >= len(self.players):
            self.turn_index = 0

        if self.started and len(self.players) < 2:
            self.finished = True
            self.notice = "La partida terminó porque quedó menos de 2 jugadores."
        else:
            self.notice = f"{player['name']} se desconectó."

    def public_state(self):
        public_players = [
            {"id": p["id"], "name": p["name"], "score": p["score"]}
            for p in self.players
        ]
        current = None
        question = None
        if self.started and not self.finished and self.players and self.question_index < len(QUESTIONS):
            current = self.players[self.turn_index]["id"]
            q = QUESTIONS[self.question_index]
            question = {"text": q["text"], "choices": q["choices"]}

        winner = None
        if self.finished and self.players:
            winner = max(self.players, key=lambda p: p["score"])["name"]

        return {
            "players": public_players,
            "host_id": self.players[0]["id"] if self.players else None,
            "started": self.started,
            "finished": self.finished,
            "question_number": min(self.question_index + 1, len(QUESTIONS)),
            "total_questions": len(QUESTIONS),
            "current_turn_id": current,
            "question": question,
            "winner": winner,
            "notice": self.notice,
        }

    async def send(self, websocket, payload):
        await websocket.send(json.dumps(payload, ensure_ascii=False))

    async def broadcast_state(self):
        payload = {"type": "state", "state": self.public_state()}
        dead = []
        for player in list(self.players):
            try:
                await self.send(player["ws"], payload)
            except ConnectionClosed:
                dead.append(player)

        for player in dead:
            self.remove_player(player)

    async def handler(self, websocket):
        joined_player = None
        try:
            async for raw in websocket:
                try:
                    message = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    await self.send(websocket, {"type": "error", "message": "El mensaje no contiene JSON válido."})
                    continue

                action = message.get("action")
                async with self.lock:
                    if action == "join":
                        if joined_player is not None:
                            await self.send(websocket, {"type": "error", "message": "Ya estás dentro de la partida."})
                        elif self.started:
                            await self.send(websocket, {"type": "error", "message": "La partida ya comenzó; no se permiten nuevas incorporaciones."})
                        elif len(self.players) >= MAX_PLAYERS:
                            await self.send(websocket, {"type": "error", "message": "La sala está llena (máximo 10 jugadores)."})
                        else:
                            name = str(message.get("name", "Jugador")).strip()[:20] or "Jugador"
                            joined_player = {
                                "ws": websocket,
                                "id": uuid.uuid4().hex[:8],
                                "name": name,
                                "score": 0,
                            }
                            self.players.append(joined_player)
                            await self.send(websocket, {"type": "welcome", "player_id": joined_player["id"]})
                            self.notice = f"{name} se unió a la sala."
                            await self.broadcast_state()

                    elif joined_player is None:
                        await self.send(websocket, {"type": "error", "message": "Primero debes unirte a la sala."})

                    elif action == "start":
                        if not self.players or joined_player["id"] != self.players[0]["id"]:
                            await self.send(websocket, {"type": "error", "message": "Solo el anfitrión puede iniciar la partida."})
                        elif self.started:
                            await self.send(websocket, {"type": "error", "message": "La partida ya está iniciada."})
                        elif len(self.players) < 2:
                            await self.send(websocket, {"type": "error", "message": "Se necesitan al menos 2 jugadores para comenzar."})
                        else:
                            self.started = True
                            self.finished = False
                            self.question_index = 0
                            self.turn_index = 0
                            self.notice = "¡Comienza la partida! Responde cuando sea tu turno."
                            await self.broadcast_state()

                    elif action == "answer":
                        if not self.started or self.finished:
                            await self.send(websocket, {"type": "error", "message": "No hay una pregunta activa."})
                        elif not self.players or joined_player["id"] != self.players[self.turn_index]["id"]:
                            await self.send(websocket, {"type": "error", "message": "Aún no es tu turno."})
                        else:
                            try:
                                choice = int(message.get("choice"))
                            except (TypeError, ValueError):
                                choice = -1
                            question = QUESTIONS[self.question_index]
                            if choice < 0 or choice >= len(question["choices"]):
                                await self.send(websocket, {"type": "error", "message": "La opción seleccionada no es válida."})
                            else:
                                correct = choice == question["correct"]
                                if correct:
                                    joined_player["score"] += 1
                                self.notice = (
                                    f"{joined_player['name']} respondió correctamente."
                                    if correct else f"{joined_player['name']} respondió incorrectamente."
                                )
                                self.turn_index += 1
                                if self.turn_index >= len(self.players):
                                    self.turn_index = 0
                                    self.question_index += 1
                                    if self.question_index >= len(QUESTIONS):
                                        self.finished = True
                                        highest = max(p["score"] for p in self.players)
                                        winners = [p["name"] for p in self.players if p["score"] == highest]
                                        self.notice = "Fin de la partida. Ganador: " + ", ".join(winners)
                                await self.broadcast_state()
                    else:
                        await self.send(websocket, {"type": "error", "message": "Acción desconocida."})
        except ConnectionClosed:
            pass
        finally:
            async with self.lock:
                if joined_player is not None:
                    self.remove_player(joined_player)
                    await self.broadcast_state()


async def main():
    game = GameServer()
    print(f"Servidor escuchando en ws://{HOST}:{PORT}")
    async with serve(game.handler, HOST, PORT, max_size=10_000):
        await asyncio.Future()  # Mantiene el servidor ejecutándose.


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServidor detenido.")
