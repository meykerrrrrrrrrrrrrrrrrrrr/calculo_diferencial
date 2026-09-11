# -*- coding: utf-8 -*-
"""
Servidor Web Local y API de Cálculo Diferencial Uniguajira
- Sistema de Autenticación con Contraseña (login / registro)
- Chat Mundial en vivo (para todos los conectados)
- Chat Privado entre dos estudiantes (con historial por conversación)
- Sincronización de Ranking y Presencia en Tiempo Real
- Cero bots: solo usuarios reales con cuenta
"""
import http.server
import socketserver
import json
import os
import socket
import time
import sys

if sys.platform == "win32":
    try:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass

# --- LO ÚNICO QUE FALTABA PARA RENDER ---
# Leer el puerto que asigna Render automáticamente, si no hay (como en tu PC), usa el 8080
PORT = int(os.environ.get("PORT", 8080))
# -----------------------------------------

DATA_FILE = "jugadores_ranking.json"
CHAT_FILE = "chat_mensajes.json"

ONLINE_USERS = {}

def get_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

def load_players():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                players = json.load(f)
                return [p for p in players if not str(p.get('id', '')).startswith('bot_') and p.get('name') not in ['Sara Morales', 'Kevin Díaz', 'Laura Ramos']]
        except Exception:
            pass
    return []

def save_players(players):
    try:
        clean_players = [p for p in players if not str(p.get('id', '')).startswith('bot_') and p.get('name') not in ['Sara Morales', 'Kevin Díaz', 'Laura Ramos']]
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(clean_players, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("Error saving players:", e)

def load_chat():
    if os.path.exists(CHAT_FILE):
        try:
            with open(CHAT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return { "global": [], "private": [] }

def save_chat(chat_data):
    try:
        with open(CHAT_FILE, "w", encoding="utf-8") as f:
            json.dump(chat_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("Error saving chat:", e)

def get_active_online_users():
    now = time.time()
    active = []
    to_delete = []
    for uid, udata in ONLINE_USERS.items():
        if now - udata.get('last_seen', 0) <= 25:
            active.append({
                "id": uid,
                "name": udata.get('name', 'Estudiante'),
                "avatar": udata.get('avatar', '🎓'),
                "customAvatar": udata.get('customAvatar', ''),
                "xp": udata.get('xp', 0),
                "last_seen": udata.get('last_seen')
            })
        elif now - udata.get('last_seen', 0) > 300:
            to_delete.append(uid)
            
    for uid in to_delete:
        del ONLINE_USERS[uid]
        
    return active

class UniguajiraHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        if self.path.startswith('/api/ranking'):
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.end_headers()
            players = load_players()
            # Devolver jugadores sin exponer las contraseñas en el ranking público
            safe_players = []
            for p in players:
                p_copy = dict(p)
                p_copy.pop('password', None)
                safe_players.append(p_copy)
            self.wfile.write(json.dumps(safe_players, ensure_ascii=False).encode('utf-8'))
            return

        elif self.path.startswith('/api/online'):
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.end_headers()
            online_list = get_active_online_users()
            resp = {
                "count": len(online_list),
                "users": online_list
            }
            self.wfile.write(json.dumps(resp, ensure_ascii=False).encode('utf-8'))
            return

        elif self.path.startswith('/api/chat'):
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.end_headers()
            chat_data = load_chat()
            self.wfile.write(json.dumps(chat_data, ensure_ascii=False).encode('utf-8'))
            return

        elif self.path == '/' or self.path == '/index.html':
            self.path = '/Juego_Examen_Calculo_Uniguajira.html'
            
        return super().do_GET()

    def do_POST(self):
        # 1. Login y Registro Seguro con Contraseña
        if self.path.startswith('/api/auth'):
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            try:
                data = json.loads(body)
                action = data.get('action') # 'login' o 'register'
                username = data.get('username', '').strip()
                password = data.get('password', '').strip()
                avatar = data.get('avatar', '🎓')
                customAvatar = data.get('customAvatar', '')

                if not username or not password:
                    self.send_response(400)
                    self.send_header('Content-Type', 'application/json; charset=utf-8')
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "error", "message": "Nombre de usuario y contraseña son obligatorios."}).encode('utf-8'))
                    return

                players = load_players()
                found_user = None
                for p in players:
                    if p.get('name', '').lower() == username.lower():
                        found_user = p
                        break

                if action == 'register':
                    if found_user:
                        self.send_response(409)
                        self.send_header('Content-Type', 'application/json; charset=utf-8')
                        self.end_headers()
                        self.wfile.write(json.dumps({"status": "error", "message": "Ya existe una cuenta con este nombre. Inicia sesión con tu contraseña."}).encode('utf-8'))
                        return

                    new_user = {
                        "id": "user_" + str(int(time.time() * 1000)),
                        "name": username,
                        "password": password,
                        "avatar": avatar,
                        "customAvatar": customAvatar,
                        "xp": 0,
                        "examsCount": 0,
                        "totalGradeSum": 0,
                        "avgGrade": 0.0,
                        "bestTopic": "Por determinar",
                        "worstTopic": "Por determinar",
                        "topicScores": {
                            "numeros_reales": 0, "expresiones_alg": 0, "productos_notables": 0,
                            "factorizacion": 0, "fracciones_alg": 0, "desigualdades": 0,
                            "linea_recta": 0, "ecuaciones": 0
                        }
                    }
                    players.append(new_user)
                    save_players(players)
                    
                    ONLINE_USERS[new_user['id']] = {
                        "name": new_user['name'],
                        "avatar": new_user['avatar'],
                        "customAvatar": new_user['customAvatar'],
                        "xp": new_user['xp'],
                        "last_seen": time.time()
                    }

                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json; charset=utf-8')
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "ok", "user": new_user}).encode('utf-8'))
                    return

                elif action == 'login':
                    if not found_user:
                        self.send_response(404)
                        self.send_header('Content-Type', 'application/json; charset=utf-8')
                        self.end_headers()
                        self.wfile.write(json.dumps({"status": "error", "message": "Estudiante no encontrado. Regístrate primero."}).encode('utf-8'))
                        return

                    if found_user.get('password') != password:
                        self.send_response(401)
                        self.send_header('Content-Type', 'application/json; charset=utf-8')
                        self.end_headers()
                        self.wfile.write(json.dumps({"status": "error", "message": "Contraseña incorrecta."}).encode('utf-8'))
                        return

                    ONLINE_USERS[found_user['id']] = {
                        "name": found_user['name'],
                        "avatar": found_user['avatar'],
                        "customAvatar": found_user.get('customAvatar', ''),
                        "xp": found_user.get('xp', 0),
                        "last_seen": time.time()
                    }

                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json; charset=utf-8')
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "ok", "user": found_user}).encode('utf-8'))
                    return

            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(str(e).encode('utf-8'))
                return

        # 2. Enviar Mensaje al Chat (Global o Privado)
        elif self.path.startswith('/api/chat'):
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            try:
                msg = json.loads(body)
                chat_data = load_chat()
                msg['timestamp'] = int(time.time() * 1000)
                
                target = msg.get('target', 'global')
                if target == 'global':
                    chat_data.setdefault('global', []).append(msg)
                    # Mantener últimos 150 mensajes globales
                    if len(chat_data['global']) > 150:
                        chat_data['global'] = chat_data['global'][-150:]
                else:
                    chat_data.setdefault('private', []).append(msg)
                    # Mantener últimos 300 mensajes privados
                    if len(chat_data['private']) > 300:
                        chat_data['private'] = chat_data['private'][-300:]

                save_chat(chat_data)

                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok", "chat": chat_data}, ensure_ascii=False).encode('utf-8'))
                return
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(str(e).encode('utf-8'))
                return

        # 3. Heartbeat de Presencia en Línea
        elif self.path.startswith('/api/heartbeat'):
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            try:
                user_data = json.loads(body)
                uid = user_data.get('id')
                if uid:
                    ONLINE_USERS[uid] = {
                        "name": user_data.get('name', 'Estudiante'),
                        "avatar": user_data.get('avatar', '🎓'),
                        "customAvatar": user_data.get('customAvatar', ''),
                        "xp": user_data.get('xp', 0),
                        "last_seen": time.time()
                    }
                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.end_headers()
                online_list = get_active_online_users()
                self.wfile.write(json.dumps({"status": "ok", "count": len(online_list), "users": online_list}, ensure_ascii=False).encode('utf-8'))
                return
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(str(e).encode('utf-8'))
                return

        # 4. Actualización de Estadísticas / Exámenes del Jugador
        elif self.path.startswith('/api/ranking'):
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            try:
                user_data = json.loads(body)
                uid = user_data.get('id')
                
                if uid:
                    ONLINE_USERS[uid] = {
                        "name": user_data.get('name', 'Estudiante'),
                        "avatar": user_data.get('avatar', '🎓'),
                        "customAvatar": user_data.get('customAvatar', ''),
                        "xp": user_data.get('xp', 0),
                        "last_seen": time.time()
                    }

                players = load_players()
                
                idx = -1
                for i, p in enumerate(players):
                    if p.get('id') == user_data.get('id') or p.get('name') == user_data.get('name'):
                        idx = i
                        break
                
                if idx >= 0:
                    # Preservar contraseña existente si no viene en el body
                    pwd = players[idx].get('password')
                    players[idx] = user_data
                    if 'password' not in user_data and pwd:
                        players[idx]['password'] = pwd
                else:
                    players.append(user_data)
                
                save_players(players)
                
                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok"}, ensure_ascii=False).encode('utf-8'))
                return
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(str(e).encode('utf-8'))
                return

if __name__ == '__main__':
    ip = get_ip()
    print("=" * 68)
    print("  [+] SERVIDOR ONLINE CON CHAT Y LOGIN - CALCULO UNIGUAJIRA [+]")
    print("=" * 68)
    print(f"  * Servidor iniciado en el puerto: {PORT}")
    print(f"  * En esta computadora abre:  http://localhost:{PORT}")
    print(f"  * En celulares y otros PCs abre: http://{ip}:{PORT}")
    print("=" * 68)
    print("  [OK] Autenticacion con contrasena para cambiar de PC/celular")
    print("  [OK] Chat Mundial y Chat Privado en vivo")
    print("  [OK] Cero bots: Solo estudiantes reales")
    print("  Presiona Ctrl+C para detener el servidor.")
    print("=" * 68)
    
    server = socketserver.ThreadingTCPServer(("", PORT), UniguajiraHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor detenido.")
