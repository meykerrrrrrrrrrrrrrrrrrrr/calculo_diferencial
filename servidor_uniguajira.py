# -*- coding: utf-8 -*-
"""
Servidor Web Local y API de Cálculo Diferencial Uniguajira
- Sistema de Autenticación con Contraseña (login / registro)
- Chat Mundial en vivo (para todos los conectados)
- Chat Privado entre dos estudiantes (con historial por conversación)
- Sincronización de Ranking y Presencia en Tiempo Real (sin bots, compañeros reales)
- MODO COMPETITIVO 1v1 EN VIVO:
  * Envío y recepción de retos / invitaciones a duelo
  * Preguntas sincronizadas ronda a ronda
  * La respuesta correcta se revela ÚNICAMENTE cuando ambos han contestado
  * Reacciones en vivo con emojis flotantes
  * Chat rápido de duelo
  * Chat de voz por micrófono (WebRTC P2P + Walkie-Talkie audio clips)
  * Otorgamiento de XP y victorias de duelo al ranking
"""
import http.server
import socketserver
import json
import os
import socket
import time
import sys
import random
import urllib.parse

if sys.platform == "win32":
    try:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass

PORT = int(os.environ.get("PORT", 8080))
socketserver.TCPServer.allow_reuse_address = True
DATA_FILE = "jugadores_ranking.json"
CHAT_FILE = "chat_mensajes.json"
QUESTIONS_FILE = "preguntas_banco.json"

ONLINE_USERS = {}
ACTIVE_DUELS = {}
PENDING_INVITATIONS = {}
QUESTION_BANK = []

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

def load_question_bank():
    global QUESTION_BANK
    paths = [
        QUESTIONS_FILE,
        r"C:\Users\DIOS ES AMOR\OneDrive\Desktop\preguntas_banco.json",
        r"C:\Users\DIOS ES AMOR\.gemini\antigravity\brain\89c26ae3-4f4d-493c-ac95-d3a12edd7a91\scratch\all_questions_100.json"
    ]
    for p in paths:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list) and len(data) > 0:
                        QUESTION_BANK = data
                        print(f"[OK] Banco de preguntas cargado ({len(QUESTION_BANK)} ejercicios)")
                        return
            except Exception as e:
                print("Error loading question bank:", e)
    
    # Fallback si no encuentra archivo
    QUESTION_BANK = [
        {
            "id": 1,
            "topic": "numeros_reales",
            "question": "¿A cuál de los siguientes conjuntos numéricos pertenece $\\sqrt{11}$?",
            "options": ["Números Irracionales ($\\mathbb{I}$)", "Números Racionales ($\\mathbb{Q}$)", "Números Enteros ($\\mathbb{Z}$)", "Números Naturales ($\\mathbb{N}$)"],
            "correct": 0,
            "explanation": "La raíz cuadrada de un número primo no es periódica ni exacta, por tanto pertenece a $\\mathbb{I}$."
        },
        {
            "id": 2,
            "topic": "factorizacion",
            "question": "Al factorizar $x^2 - 9$, se obtiene:",
            "options": ["$(x - 3)(x + 3)$", "$(x - 3)^2$", "$(x + 9)(x - 1)$", "$(x - 9)(x + 1)$"],
            "correct": 0,
            "explanation": "Es una diferencia de cuadrados: $a^2 - b^2 = (a-b)(a+b)$."
        }
    ]

def load_players():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if not content:
                    return []
                players = json.loads(content)
                if isinstance(players, list):
                    return [p for p in players if not str(p.get('id', '')).startswith('bot_')]
        except Exception as e:
            print("Error parsing players JSON:", e)
    return []

def save_players(players):
    try:
        clean_players = [p for p in players if not str(p.get('id', '')).startswith('bot_')]
        if not clean_players and os.path.exists(DATA_FILE) and os.path.getsize(DATA_FILE) > 5:
            return
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(clean_players, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("Error saving players:", e)

def load_chat():
    if os.path.exists(CHAT_FILE):
        try:
            with open(CHAT_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    return json.loads(content)
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
                "profileColor": udata.get('profileColor', ''),
                "statusEmoji": udata.get('statusEmoji', ''),
                "bio": udata.get('bio', ''),
                "stickers": udata.get('stickers', []),
                "xp": udata.get('xp', 0),
                "last_seen": udata.get('last_seen')
            })
        elif now - udata.get('last_seen', 0) > 300:
            to_delete.append(uid)
            
    for uid in to_delete:
        del ONLINE_USERS[uid]
        
    return active

def prepare_duel_questions(topics=None, num=5):
    """Selecciona y mezcla las opciones para que la respuesta correcta sea aleatoria (A, B, C o D)"""
    pool = QUESTION_BANK
    if topics and isinstance(topics, list) and len(topics) > 0 and 'all' not in topics:
        filtered = [q for q in QUESTION_BANK if q.get('topic') in topics]
        if len(filtered) >= num:
            pool = filtered
        elif len(filtered) > 0:
            remaining = [q for q in QUESTION_BANK if q.get('topic') not in topics]
            pool = filtered + remaining

    if len(pool) < num:
        selected = pool.copy()
    else:
        selected = random.sample(pool, num)
    
    duel_qs = []
    for q in selected:
        original_opts = list(q.get('options', []))
        correct_idx = q.get('correct', 0)
        correct_text = original_opts[correct_idx] if (0 <= correct_idx < len(original_opts)) else original_opts[0]
        
        # Mezclar opciones
        indices = list(range(len(original_opts)))
        random.shuffle(indices)
        shuffled_opts = [original_opts[i] for i in indices]
        new_correct_idx = shuffled_opts.index(correct_text)
        
        duel_qs.append({
            "id": q.get('id'),
            "topic": q.get('topic'),
            "subtopic": q.get('subtopic', 'General'),
            "question": q.get('question'),
            "options": shuffled_opts,
            "correct": new_correct_idx, # Se mantiene oculto del cliente hasta resolver
            "explanation": q.get('explanation', 'Solución oficial del ejercicio.')
        })
    return duel_qs

class UniguajiraHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Requested-With')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def send_json(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url_parsed = urllib.parse.urlparse(self.path)
        path = url_parsed.path
        query_params = urllib.parse.parse_qs(url_parsed.query)

        # 1. Ranking de Jugadores
        if path.startswith('/api/ranking'):
            players = load_players()
            safe_players = []
            for p in players:
                p_copy = dict(p)
                p_copy.pop('password', None)
                safe_players.append(p_copy)
            self.send_json(safe_players)
            return

        # 2. Usuarios en Línea
        elif path.startswith('/api/online'):
            online_list = get_active_online_users()
            self.send_json({
                "count": len(online_list),
                "users": online_list
            })
            return

        # 3. Mensajes de Chat
        elif path.startswith('/api/chat'):
            chat_data = load_chat()
            self.send_json(chat_data)
            return

        # 4. Modo Competitivo / Duelos (Consultas GET)
        elif path.startswith('/api/duels'):
            action = query_params.get('action', [''])[0]
            user_id = query_params.get('userId', [''])[0]
            duel_id = query_params.get('duelId', [''])[0]

            # Consultar invitaciones pendientes dirigidas a este usuario
            if action == 'get_invitations':
                now = time.time()
                pending = []
                user_id = str(query_params.get('userId', [''])[0]).strip()
                user_name = str(query_params.get('userName', [''])[0]).strip().lower()

                for inv_id, inv in list(PENDING_INVITATIONS.items()):
                    if now - inv.get('createdAt', 0) > 45:
                        inv['status'] = 'expired'
                    elif inv.get('status') == 'pending':
                        t_id = str(inv.get('toUserId', '')).strip()
                        t_name = str(inv.get('toUserName', '')).strip().lower()

                        match = False
                        if user_id and (user_id == t_id or user_id.lower() == t_name):
                            match = True
                        if user_name and (user_name == t_name or user_name == t_id.lower()):
                            match = True

                        if match:
                            pending.append(inv)
                self.send_json({ "status": "ok", "invitations": pending })
                return

            # Consultar estado de una invitación específica (para el que envió el reto)
            elif action == 'check_invite':
                inv_id = query_params.get('inviteId', [''])[0]
                inv = PENDING_INVITATIONS.get(inv_id)
                if not inv:
                    self.send_json({ "status": "error", "message": "Invitación no encontrada" }, 404)
                    return
                self.send_json({ "status": "ok", "invitation": inv })
                return

            # Consultar estado en vivo de un duelo en curso
            elif action == 'game_state':
                duel = ACTIVE_DUELS.get(duel_id)
                if not duel:
                    self.send_json({ "status": "error", "message": "Duelo no encontrado" }, 404)
                    return
                
                # Armar estado seguro (ocultar la respuesta correcta si aún no se ha revelado)
                curr_round = duel['currentRound']
                questions = duel['questions']
                
                # Si se superó el límite de rondas
                if curr_round >= len(questions):
                    duel['status'] = 'completed'
                    if duel['p1_score'] > duel['p2_score']:
                        duel['winnerId'] = duel['player1']['id']
                    elif duel['p2_score'] > duel['p1_score']:
                        duel['winnerId'] = duel['player2']['id']
                    else:
                        duel['winnerId'] = 'draw'
                    
                    # Premiar XP a los duelistas en el ranking oficial
                    if not duel.get('xpAwarded', False):
                        duel['xpAwarded'] = True
                        try:
                            players = load_players()
                            p1_id = duel['player1']['id']
                            p2_id = duel['player2']['id']
                            for p in players:
                                if p.get('id') == p1_id:
                                    if duel['winnerId'] == p1_id:
                                        p['xp'] = p.get('xp', 0) + 150
                                        p['duelWins'] = p.get('duelWins', 0) + 1
                                    elif duel['winnerId'] == 'draw':
                                        p['xp'] = p.get('xp', 0) + 75
                                    else:
                                        p['xp'] = p.get('xp', 0) + 40
                                        p['duelLosses'] = p.get('duelLosses', 0) + 1
                                elif p.get('id') == p2_id:
                                    if duel['winnerId'] == p2_id:
                                        p['xp'] = p.get('xp', 0) + 150
                                        p['duelWins'] = p.get('duelWins', 0) + 1
                                    elif duel['winnerId'] == 'draw':
                                        p['xp'] = p.get('xp', 0) + 75
                                    else:
                                        p['xp'] = p.get('xp', 0) + 40
                                        p['duelLosses'] = p.get('duelLosses', 0) + 1
                            save_players(players)
                        except Exception as e:
                            print("Error awarding duel XP:", e)

                is_completed = (duel['status'] == 'completed')
                q_data = None
                if not is_completed and curr_round < len(questions):
                    orig_q = questions[curr_round]
                    q_data = {
                        "id": orig_q['id'],
                        "topic": orig_q['topic'],
                        "subtopic": orig_q['subtopic'],
                        "question": orig_q['question'],
                        "options": orig_q['options'],
                        "roundIndex": curr_round,
                        "totalRounds": len(questions)
                    }
                    # Incluir respuesta y explicación SOLO cuando la ronda ya está revelada
                    if duel['roundRevealed']:
                        q_data['correct'] = orig_q['correct']
                        q_data['explanation'] = orig_q['explanation']

                # Entregar señales de voz pendientes para este usuario
                user_signals = [s for s in duel['voiceSignals'] if s.get('toId') == user_id]
                duel['voiceSignals'] = [s for s in duel['voiceSignals'] if s.get('toId') != user_id]

                safe_state = {
                    "id": duel['id'],
                    "player1": duel['player1'],
                    "player2": duel['player2'],
                    "topicNames": duel.get('topicNames', 'Todos los temas'),
                    "totalRounds": len(duel['questions']),
                    "p1_score": duel['p1_score'],
                    "p2_score": duel['p2_score'],
                    "currentRound": curr_round,
                    "roundRevealed": duel['roundRevealed'],
                    "p1_answered": duel['p1_answer'] is not None,
                    "p2_answered": duel['p2_answer'] is not None,
                    "roundResults": duel.get('roundResults', None),
                    "status": duel['status'],
                    "winnerId": duel.get('winnerId', None),
                    "reactions": duel.get('reactions', []),
                    "chat": duel.get('chat', [])[-20:],
                    "voiceSignals": user_signals,
                    "voiceClip": duel.get('lastVoiceClip', None),
                    "currentQuestion": q_data
                }
                self.send_json({ "status": "ok", "state": safe_state })
                return

        # 5. Servir archivo HTML
        elif path == '/' or path == '/index.html':
            self.path = '/Juego_Examen_Calculo_Uniguajira.html'
            
        return super().do_GET()

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode('utf-8') if content_length > 0 else '{}'
        try:
            data = json.loads(body)
        except Exception:
            data = {}

        # 1. Login y Registro Seguro con Contraseña
        if self.path.startswith('/api/auth'):
            action = data.get('action')
            username = data.get('username', '').strip()
            password = data.get('password', '').strip()
            avatar = data.get('avatar', '🎓')
            customAvatar = data.get('customAvatar', '')

            if not username or not password:
                self.send_json({"status": "error", "message": "Nombre de usuario y contraseña requeridos."}, 400)
                return

            players = load_players()
            found_user = next((p for p in players if p.get('name', '').lower() == username.lower()), None)

            if action == 'register':
                if found_user:
                    self.send_json({"status": "error", "message": "Ya existe una cuenta con este nombre."}, 409)
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
                    "duelWins": 0,
                    "duelLosses": 0,
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

                self.send_json({"status": "ok", "user": new_user})
                return

            elif action == 'login':
                if not found_user:
                    self.send_json({"status": "error", "message": "Estudiante no encontrado. Regístrate primero."}, 404)
                    return

                if found_user.get('password') != password:
                    self.send_json({"status": "error", "message": "Contraseña incorrecta."}, 401)
                    return

                ONLINE_USERS[found_user['id']] = {
                    "name": found_user['name'],
                    "avatar": found_user['avatar'],
                    "customAvatar": found_user.get('customAvatar', ''),
                    "xp": found_user.get('xp', 0),
                    "last_seen": time.time()
                }

                self.send_json({"status": "ok", "user": found_user})
                return

        # 2. Chat Mundial y Privado
        elif self.path.startswith('/api/chat'):
            chat_data = load_chat()
            data['timestamp'] = int(time.time() * 1000)
            target = data.get('target', 'global')
            
            if target == 'global':
                chat_data.setdefault('global', []).append(data)
                if len(chat_data['global']) > 150:
                    chat_data['global'] = chat_data['global'][-150:]
            else:
                chat_data.setdefault('private', []).append(data)
                if len(chat_data['private']) > 300:
                    chat_data['private'] = chat_data['private'][-300:]

            save_chat(chat_data)
            self.send_json({"status": "ok", "chat": chat_data})
            return

        # 3. Heartbeat de Presencia
        elif self.path.startswith('/api/heartbeat'):
            uid = data.get('id')
            if uid:
                ONLINE_USERS[uid] = {
                    "name": data.get('name', 'Estudiante'),
                    "avatar": data.get('avatar', '🎓'),
                    "customAvatar": data.get('customAvatar', ''),
                    "profileColor": data.get('profileColor', ''),
                    "statusEmoji": data.get('statusEmoji', ''),
                    "bio": data.get('bio', ''),
                    "stickers": data.get('stickers', []),
                    "xp": data.get('xp', 0),
                    "last_seen": time.time()
                }
            online_list = get_active_online_users()
            self.send_json({"status": "ok", "count": len(online_list), "users": online_list})
            return

        # 4. Actualización de Notas / Ranking del Jugador
        elif self.path.startswith('/api/ranking'):
            uid = data.get('id')
            if uid:
                ONLINE_USERS[uid] = {
                    "name": data.get('name', 'Estudiante'),
                    "avatar": data.get('avatar', '🎓'),
                    "customAvatar": data.get('customAvatar', ''),
                    "profileColor": data.get('profileColor', ''),
                    "statusEmoji": data.get('statusEmoji', ''),
                    "bio": data.get('bio', ''),
                    "stickers": data.get('stickers', []),
                    "xp": data.get('xp', 0),
                    "last_seen": time.time()
                }

            players = load_players()
            idx = next((i for i, p in enumerate(players) if p.get('id') == data.get('id') or p.get('name') == data.get('name')), -1)
            
            if idx >= 0:
                pwd = players[idx].get('password')
                players[idx] = data
                if 'password' not in data and pwd:
                    players[idx]['password'] = pwd
            else:
                players.append(data)
            
            save_players(players)
            
            safe_players = []
            for p in players:
                p_copy = dict(p)
                p_copy.pop('password', None)
                safe_players.append(p_copy)
            self.send_json({"status": "ok", "players": safe_players})
            return

        # 5. MODO COMPETITIVO / DUELOS (Acciones POST)
        elif self.path.startswith('/api/duels'):
            action = data.get('action')

            # ENVIAR DESAFÍO / INVITACIÓN
            if action == 'invite':
                from_user = data.get('fromUser')
                to_user_id = data.get('toUserId')
                to_user_name = data.get('toUserName', '')
                topics = data.get('topics', ['all'])
                topic_names = data.get('topicNames', 'Todos los temas')
                try:
                    num_questions = max(3, min(20, int(data.get('numQuestions', 5))))
                except Exception:
                    num_questions = 5

                if not from_user or (not to_user_id and not to_user_name):
                    self.send_json({"status": "error", "message": "Datos incompletos"}, 400)
                    return

                inv_id = "inv_" + str(int(time.time() * 1000)) + "_" + str(random.randint(100, 999))
                PENDING_INVITATIONS[inv_id] = {
                    "id": inv_id,
                    "fromUser": from_user,
                    "toUserId": to_user_id,
                    "toUserName": to_user_name,
                    "topics": topics,
                    "topicNames": topic_names,
                    "numQuestions": num_questions,
                    "createdAt": time.time(),
                    "status": "pending",
                    "duelId": None
                }
                self.send_json({"status": "ok", "inviteId": inv_id})
                return

            # RESPONDER A UNA INVITACIÓN (Aceptar / Rechazar)
            elif action == 'respond_invite':
                inv_id = data.get('inviteId')
                response_choice = data.get('response') # 'accept' o 'decline'
                responder_user = data.get('responderUser')

                inv = PENDING_INVITATIONS.get(inv_id)
                if not inv:
                    self.send_json({"status": "error", "message": "Invitación no válida"}, 404)
                    return

                if response_choice == 'accept':
                    inv['status'] = 'accepted'
                    duel_id = "duel_" + str(int(time.time() * 1000))
                    
                    # Preparar preguntas sincronizadas filtradas por los temas acordados y la cantidad elegida
                    topics = inv.get('topics', ['all'])
                    num_questions = int(inv.get('numQuestions', 5))
                    duel_questions = prepare_duel_questions(topics, num_questions)
                    
                    ACTIVE_DUELS[duel_id] = {
                        "id": duel_id,
                        "player1": inv['fromUser'],
                        "player2": responder_user,
                        "topicNames": inv.get('topicNames', 'Todos los temas'),
                        "numQuestions": num_questions,
                        "p1_score": 0,
                        "p2_score": 0,
                        "questions": duel_questions,
                        "currentRound": 0,
                        "roundStartTime": time.time(),
                        "roundRevealed": False,
                        "p1_answer": None,
                        "p2_answer": None,
                        "p1_time": None,
                        "p2_time": None,
                        "reactions": [],
                        "chat": [],
                        "voiceSignals": [],
                        "lastVoiceClip": None,
                        "status": "in_progress",
                        "winnerId": None
                    }
                    inv['duelId'] = duel_id
                    self.send_json({"status": "ok", "action": "accepted", "duelId": duel_id})
                    return
                else:
                    inv['status'] = 'declined'
                    self.send_json({"status": "ok", "action": "declined"})
                    return

            # RESPONDER PREGUNTA DE LA RONDA
            elif action == 'submit_answer':
                duel_id = data.get('duelId')
                user_id = data.get('userId')
                option_index = data.get('optionIndex') # 0, 1, 2, 3
                
                duel = ACTIVE_DUELS.get(duel_id)
                if not duel or duel['status'] != 'in_progress':
                    self.send_json({"status": "error", "message": "Duelo inactivo"}, 400)
                    return

                # Registrar la respuesta del jugador
                is_p1 = (duel['player1']['id'] == user_id)
                is_p2 = (duel['player2']['id'] == user_id)
                
                now = time.time()
                if is_p1 and duel['p1_answer'] is None:
                    duel['p1_answer'] = option_index
                    duel['p1_time'] = now - duel['roundStartTime']
                elif is_p2 and duel['p2_answer'] is None:
                    duel['p2_answer'] = option_index
                    duel['p2_time'] = now - duel['roundStartTime']

                # ¿AMBOS JUGADORES YA RESPONDIEORN? -> REVELAR RESPUESTA Y PUNTUAR
                if duel['p1_answer'] is not None and duel['p2_answer'] is not None and not duel['roundRevealed']:
                    curr_q = duel['questions'][duel['currentRound']]
                    correct_idx = curr_q['correct']
                    
                    p1_correct = (duel['p1_answer'] == correct_idx)
                    p2_correct = (duel['p2_answer'] == correct_idx)
                    
                    # Sistema de puntos: 100 pts por acierto + bono de velocidad (hasta 30 pts)
                    if p1_correct:
                        speed_bonus = max(0, int(30 - min(30, duel['p1_time'] or 0)))
                        duel['p1_score'] += (100 + speed_bonus)
                    if p2_correct:
                        speed_bonus = max(0, int(30 - min(30, duel['p2_time'] or 0)))
                        duel['p2_score'] += (100 + speed_bonus)

                    duel['roundRevealed'] = True
                    duel['roundResults'] = {
                        "correctIndex": correct_idx,
                        "correctText": curr_q['options'][correct_idx],
                        "explanation": curr_q['explanation'],
                        "p1_correct": p1_correct,
                        "p2_correct": p2_correct,
                        "p1_choice": duel['p1_answer'],
                        "p2_choice": duel['p2_answer']
                    }

                self.send_json({"status": "ok", "roundRevealed": duel['roundRevealed']})
                return

            # AVANZAR A LA SIGUIENTE RONDA
            elif action == 'next_round':
                duel_id = data.get('duelId')
                duel = ACTIVE_DUELS.get(duel_id)
                if not duel:
                    self.send_json({"status": "error", "message": "Duelo no encontrado"}, 404)
                    return

                if duel['roundRevealed']:
                    duel['currentRound'] += 1
                    duel['roundRevealed'] = False
                    duel['p1_answer'] = None
                    duel['p2_answer'] = None
                    duel['p1_time'] = None
                    duel['p2_time'] = None
                    duel['roundResults'] = None
                    duel['roundStartTime'] = time.time()
                    
                    # Si finalizó la 5ta pregunta
                    if duel['currentRound'] >= len(duel['questions']):
                        duel['status'] = 'completed'
                        p1_id = duel['player1']['id']
                        p2_id = duel['player2']['id']
                        
                        if duel['p1_score'] > duel['p2_score']:
                            duel['winnerId'] = p1_id
                            winner_id, loser_id = p1_id, p2_id
                        elif duel['p2_score'] > duel['p1_score']:
                            duel['winnerId'] = p2_id
                            winner_id, loser_id = p2_id, p1_id
                        else:
                            duel['winnerId'] = 'draw'
                            winner_id, loser_id = None, None

                        # Bonificación de XP en la base de datos
                        players = load_players()
                        for p in players:
                            if winner_id and p.get('id') == winner_id:
                                p['xp'] = p.get('xp', 0) + 150
                                p['duelWins'] = p.get('duelWins', 0) + 1
                            elif loser_id and p.get('id') == loser_id:
                                p['xp'] = p.get('xp', 0) + 40
                                p['duelLosses'] = p.get('duelLosses', 0) + 1
                            elif duel['winnerId'] == 'draw' and p.get('id') in [p1_id, p2_id]:
                                p['xp'] = p.get('xp', 0) + 75
                        save_players(players)

                self.send_json({"status": "ok", "currentRound": duel['currentRound'], "isCompleted": (duel['status'] == 'completed')})
                return

            # ENVIAR REACCIÓN DE EMOJI EN VIVO
            elif action == 'send_reaction':
                duel_id = data.get('duelId')
                from_user_id = data.get('fromUserId')
                emoji = data.get('emoji')
                
                duel = ACTIVE_DUELS.get(duel_id)
                if duel:
                    rx = { "fromId": from_user_id, "emoji": emoji, "timestamp": time.time() }
                    duel.setdefault('reactions', []).append(rx)
                    if len(duel['reactions']) > 15:
                        duel['reactions'] = duel['reactions'][-15:]
                self.send_json({"status": "ok"})
                return

            # ENVIAR MENSAJE DE CHAT RÁPIDO EN EL DUELO
            elif action == 'send_chat':
                duel_id = data.get('duelId')
                duel = ACTIVE_DUELS.get(duel_id)
                if duel:
                    msg = {
                        "senderId": data.get('senderId'),
                        "senderName": data.get('senderName'),
                        "text": data.get('text', ''),
                        "timestamp": int(time.time() * 1000)
                    }
                    duel.setdefault('chat', []).append(msg)
                self.send_json({"status": "ok"})
                return

            # SEÑALIZACIÓN WebRTC (Voz / Micrófono P2P)
            elif action == 'voice_signal':
                duel_id = data.get('duelId')
                duel = ACTIVE_DUELS.get(duel_id)
                if duel:
                    sig = {
                        "fromId": data.get('fromId'),
                        "toId": data.get('toId'),
                        "signal": data.get('signal'),
                        "timestamp": time.time()
                    }
                    duel.setdefault('voiceSignals', []).append(sig)
                self.send_json({"status": "ok"})
                return

            # WALKIE-TALKIE / AUDIO CLIP DIRECTO (Fallback de Micrófono)
            elif action == 'voice_clip':
                duel_id = data.get('duelId')
                duel = ACTIVE_DUELS.get(duel_id)
                if duel:
                    clip = {
                        "fromId": data.get('fromId'),
                        "fromName": data.get('fromName'),
                        "audioData": data.get('audioData'),
                        "timestamp": time.time()
                    }
                    duel['lastVoiceClip'] = clip
                self.send_json({"status": "ok"})
                return

        self.send_json({"status": "error", "message": "Ruta no encontrada"}, 404)

if __name__ == '__main__':
    load_question_bank()
    ip = get_ip()
    print("=" * 70)
    print("  [+] SERVIDOR WEB & API - CÁLCULO DIFERENCIAL UNIGUAJIRA [+]")
    print("=" * 70)
    print(f"  * Servidor iniciado en el puerto: {PORT}")
    print(f"  * En esta computadora abre:   http://localhost:{PORT}")
    print(f"  * En celulares y otros PCs:   http://{ip}:{PORT}")
    print("=" * 70)
    print("  [OK] Autenticación con contraseña para cambiar de PC/celular")
    print("  [OK] Chat Mundial y Chat Privado en vivo con Notificaciones y Badges")
    print("  [OK] Ranking oficial sincronizado con compañeros reales")
    print("  [OK] MODO COMPETITIVO 1v1: Duelos sincronizados, Micrófono y Emojis")
    print("  Presiona Ctrl+C para detener el servidor.")
    print("=" * 70)
    
    server = socketserver.ThreadingTCPServer(("", PORT), UniguajiraHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor detenido.")
