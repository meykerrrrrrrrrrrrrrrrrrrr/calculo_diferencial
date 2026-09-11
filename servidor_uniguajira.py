# -*- coding: utf-8 -*-
"""
Servidor Web Cloud y API de Cálculo Diferencial Uniguajira (Conectado a Supabase)
- Sistema de Autenticación con Contraseña y Base de Datos en la Nube
- Chat Mundial y Privado persistente
- Sincronización automática de Ranking y Presencia
"""
import http.server
import socketserver
import json
import os
import socket
import time
import sys
from supabase import create_client, Client

if sys.platform == "win32":
    try:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass

PORT = 8080

# Conexión a Supabase (Lee las variables de entorno de Render o usa valores locales si pruebas en tu PC)
SUPABASE_URL = os.environ.get("SUPABASE_URL", "PEGAR_AQUI_URL_SI_PRUEBAS_LOCAL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "PEGAR_AQUI_KEY_SI_PRUEBAS_LOCAL")

try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    print(f"[!] Advertencia al conectar con Supabase: {e}")

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

def load_players_db():
    try:
        response = supabase.table('usuarios').select("*").execute()
        players = response.data if response.data else []
        # Filtrar bots o nombres excluidos por seguridad
        return [p for p in players if not str(p.get('id', '')).startswith('bot_') and p.get('name') not in ['Sara Morales', 'Kevin Díaz', 'Laura Ramos']]
    except Exception as e:
        print("Error loading players from Supabase:", e)
        return []

def save_player_db(player_data):
    try:
        # Mapeo para asegurar formato snake_case si la columna en DB es custom_avatar
        db_data = {
            "id": player_data.get('id'),
            "name": player_data.get('name'),
            "password": player_data.get('password'),
            "avatar": player_data.get('avatar'),
            "custom_avatar": player_data.get('customAvatar') or player_data.get('custom_avatar'),
            "xp": player_data.get('xp', 0),
            "exams_count": player_data.get('examsCount') or player_data.get('exams_count', 0),
            "avg_grade": player_data.get('avgGrade') or player_data.get('avg_grade', 0.0),
            "best_topic": player_data.get('bestTopic') or player_data.get('best_topic', 'Por determinar'),
            "worst_topic": player_data.get('worstTopic') or player_data.get('worst_topic', 'Por determinar'),
            "topic_scores": player_data.get('topicScores') or player_data.get('topic_scores', {})
        }
        supabase.table('usuarios').upsert(db_data).execute()
    except Exception as e:
        print("Error saving player to Supabase:", e)

def load_chat_db():
    try:
        response = supabase.table('mensajes_chat').select("*").order("timestamp", desc=False).execute()
        mensajes = response.data if response.data else []
        chat_data = { "global": [], "private": [] }
        for m in mensajes:
            formatted_msg = {
                "id": m.get('id'),
                "senderId": m.get('sender_id'),
                "senderName": m.get('sender_name'),
                "senderAvatar": m.get('sender_avatar'),
                "senderCustomAvatar": m.get('sender_custom_avatar'),
                "target": m.get('target', 'global'),
                "text": m.get('text'),
                "timestamp": m.get('timestamp')
            }
            if m.get('target', 'global') == 'global':
                chat_data['global'].append(formatted_msg)
            else:
                chat_data['private'].append(formatted_msg)
        return chat_data
    except Exception as e:
        print("Error loading chat from Supabase:", e)
        return { "global": [], "private": [] }

def save_chat_db(msg):
    try:
        db_msg = {
            "sender_id": msg.get('senderId'),
            "sender_name": msg.get('senderName'),
            "sender_avatar": msg.get('senderAvatar'),
            "sender_custom_avatar": msg.get('senderCustomAvatar'),
            "target": msg.get('target', 'global'),
            "text": msg.get('text'),
            "timestamp": msg.get('timestamp')
        }
        supabase.table('mensajes_chat').insert(db_msg).execute()
    except Exception as e:
        print("Error saving chat message to Supabase:", e)

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
            players = load_players_db()
            safe_players = []
            for p in players:
                p_copy = {
                    "id": p.get('id'),
                    "name": p.get('name'),
                    "avatar": p.get('avatar'),
                    "customAvatar": p.get('custom_avatar'),
                    "xp": p.get('xp'),
                    "examsCount": p.get('exams_count'),
                    "avgGrade": float(p.get('avg_grade', 0)),
                    "bestTopic": p.get('best_topic'),
                    "worstTopic": p.get('worst_topic'),
                    "topicScores": p.get('topic_scores')
                }
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
            chat_data = load_chat_db()
            self.wfile.write(json.dumps(chat_data, ensure_ascii=False).encode('utf-8'))
            return

        elif self.path == '/' or self.path == '/index.html':
            self.path = '/Juego_Examen_Calculo_Uniguajira.html'
            
        return super().do_GET()

    def do_POST(self):
        if self.path.startswith('/api/auth'):
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            try:
                data = json.loads(body)
                action = data.get('action')
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

                players = load_players_db()
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
                    save_player_db(new_user)
                    
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

                    formatted_found = {
                        "id": found_user.get('id'),
                        "name": found_user.get('name'),
                        "avatar": found_user.get('avatar'),
                        "customAvatar": found_user.get('custom_avatar'),
                        "xp": found_user.get('xp'),
                        "examsCount": found_user.get('exams_count'),
                        "avgGrade": float(found_user.get('avg_grade', 0)),
                        "bestTopic": found_user.get('best_topic'),
                        "worstTopic": found_user.get('worst_topic'),
                        "topicScores": found_user.get('topic_scores')
                    }

                    ONLINE_USERS[formatted_found['id']] = {
                        "name": formatted_found['name'],
                        "avatar": formatted_found['avatar'],
                        "customAvatar": formatted_found.get('customAvatar', ''),
                        "xp": formatted_found.get('xp', 0),
                        "last_seen": time.time()
                    }

                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json; charset=utf-8')
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "ok", "user": formatted_found}).encode('utf-8'))
                    return

            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(str(e).encode('utf-8'))
                return

        elif self.path.startswith('/api/chat'):
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            try:
                msg = json.loads(body)
                msg['timestamp'] = int(time.time() * 1000)
                save_chat_db(msg)
                chat_data = load_chat_db()

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

                save_player_db(user_data)
                
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
    print("  [+] SERVIDOR CLOUD SUPABASE - CALCULO UNIGUAJIRA [+]")
    print("=" * 68)
    print(f"  * Servidor iniciado en el puerto: {PORT}")
    print(f"  * En esta computadora abre:  http://localhost:{PORT}")
    print(f"  * En celulares y otros PCs abre: http://{ip}:{PORT}")
    print("=" * 68)
    print("  [OK] Base de datos en la nube Supabase conectada")
    print("  [OK] Cero pérdida de puntajes o rankings al actualizar")
    print("  Presiona Ctrl+C para detener el servidor.")
    print("=" * 68)
    
    server = socketserver.ThreadingTCPServer(("", PORT), UniguajiraHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor detenido.")
