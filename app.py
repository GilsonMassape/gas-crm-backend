from flask import Flask, request, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
import os

app = Flask(__name__)

# Configurações
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'gas-crm-secret-key-2024-massape')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///crm_gas.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Configurar CORS - Render aceita CORS sem problemas
CORS(app, 
     resources={r"/api/*": {"origins": "*"}},
     supports_credentials=True,
     allow_headers=["Content-Type", "Authorization"],
     methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])

db = SQLAlchemy(app)

# ==================== MODELOS ====================

class Usuario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    senha_hash = db.Column(db.String(200), nullable=False)
    nivel = db.Column(db.String(20), default='gerente')
    ativo = db.Column(db.Boolean, default=True)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

class Cliente(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    telefone = db.Column(db.String(20), nullable=False)
    endereco = db.Column(db.String(200))
    ciclo_dias = db.Column(db.Integer, default=30)
    ultima_compra = db.Column(db.Date)
    observacoes = db.Column(db.Text)
    ativo = db.Column(db.Boolean, default=True)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)
    atualizado_em = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Mensagem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('cliente.id'))
    texto = db.Column(db.Text, nullable=False)
    enviada_em = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='enviada')
    erro = db.Column(db.Text)

class Campanha(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    descricao = db.Column(db.Text)
    template = db.Column(db.Text, nullable=False)
    criada_em = db.Column(db.DateTime, default=datetime.utcnow)
    ativa = db.Column(db.Boolean, default=True)

# ==================== INICIALIZAÇÃO ====================

with app.app_context():
    db.create_all()
    print('✅ Banco de dados inicializado!')

@app.route('/api/init-db', methods=['GET', 'POST'])
def init_db():
    try:
        db.create_all()
        tabelas = []
        with db.engine.connect() as conn:
            result = conn.execute(db.text("SELECT name FROM sqlite_master WHERE type='table'"))
            tabelas = [row[0] for row in result]
        return jsonify({'mensagem': 'BD inicializado', 'tabelas': tabelas, 'status': 'ok'})
    except Exception as e:
        return jsonify({'erro': str(e), 'status': 'erro'}), 500

# ==================== AUTENTICAÇÃO ====================

@app.route('/api/setup/verificar', methods=['GET'])
def verificar_setup():
    try:
        admin = Usuario.query.filter_by(nivel='admin').first()
        return jsonify({'configurado': admin is not None})
    except Exception as e:
        return jsonify({'configurado': False, 'erro_db': str(e), 'precisa_init': True})

@app.route('/api/setup/criar-admin', methods=['POST'])
def criar_admin():
    try:
        if Usuario.query.filter_by(nivel='admin').first():
            return jsonify({'erro': 'Sistema já configurado'}), 400
        dados = request.json
        if not dados.get('nome') or not dados.get('email') or not dados.get('senha'):
            return jsonify({'erro': 'Dados incompletos'}), 400
        admin = Usuario(
            nome=dados['nome'],
            email=dados['email'],
            senha_hash=generate_password_hash(dados['senha']),
            nivel='admin'
        )
        db.session.add(admin)
        db.session.commit()
        session['usuario_id'] = admin.id
        return jsonify({
            'mensagem': 'Administrador criado com sucesso',
            'usuario': {'id': admin.id, 'nome': admin.nome, 'email': admin.email, 'nivel': admin.nivel}
        })
    except Exception as e:
        return jsonify({'erro': f'Erro ao criar administrador: {str(e)}'}), 500

@app.route('/api/auth/login', methods=['POST'])
def login():
    dados = request.json
    usuario = Usuario.query.filter_by(email=dados.get('email')).first()
    if not usuario or not check_password_hash(usuario.senha_hash, dados.get('senha')):
        return jsonify({'erro': 'Email ou senha incorretos'}), 401
    if not usuario.ativo:
        return jsonify({'erro': 'Usuário inativo'}), 401
    session['usuario_id'] = usuario.id
    return jsonify({
        'mensagem': 'Login realizado com sucesso',
        'usuario': {'id': usuario.id, 'nome': usuario.nome, 'email': usuario.email, 'nivel': usuario.nivel}
    })

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    session.pop('usuario_id', None)
    return jsonify({'mensagem': 'Logout realizado com sucesso'})

@app.route('/api/auth/usuario-atual', methods=['GET'])
def usuario_atual():
    if 'usuario_id' not in session:
        return jsonify({'erro': 'Não autenticado'}), 401
    usuario = Usuario.query.get(session['usuario_id'])
    if not usuario:
        return jsonify({'erro': 'Usuário não encontrado'}), 404
    return jsonify({'id': usuario.id, 'nome': usuario.nome, 'email': usuario.email, 'nivel': usuario.nivel})

# ==================== CLIENTES ====================

@app.route('/api/clientes', methods=['GET'])
def listar_clientes():
    if 'usuario_id' not in session:
        return jsonify({'erro': 'Não autenticado'}), 401
    clientes = Cliente.query.filter_by(ativo=True).all()
    return jsonify([{
        'id': c.id, 'nome': c.nome, 'telefone': c.telefone, 'endereco': c.endereco,
        'ciclo_dias': c.ciclo_dias, 'ultima_compra': c.ultima_compra.isoformat() if c.ultima_compra else None,
        'observacoes': c.observacoes, 'criado_em': c.criado_em.isoformat()
    } for c in clientes])

@app.route('/api/clientes', methods=['POST'])
def criar_cliente():
    if 'usuario_id' not in session:
        return jsonify({'erro': 'Não autenticado'}), 401
    dados = request.json
    cliente = Cliente(
        nome=dados['nome'], telefone=dados['telefone'], endereco=dados.get('endereco', ''),
        ciclo_dias=dados.get('ciclo_dias', 30),
        ultima_compra=datetime.fromisoformat(dados['ultima_compra']) if dados.get('ultima_compra') else None,
        observacoes=dados.get('observacoes', '')
    )
    db.session.add(cliente)
    db.session.commit()
    return jsonify({'mensagem': 'Cliente criado com sucesso', 'id': cliente.id}), 201

@app.route('/api/clientes/<int:id>', methods=['PUT'])
def atualizar_cliente(id):
    if 'usuario_id' not in session:
        return jsonify({'erro': 'Não autenticado'}), 401
    cliente = Cliente.query.get_or_404(id)
    dados = request.json
    cliente.nome = dados.get('nome', cliente.nome)
    cliente.telefone = dados.get('telefone', cliente.telefone)
    cliente.endereco = dados.get('endereco', cliente.endereco)
    cliente.ciclo_dias = dados.get('ciclo_dias', cliente.ciclo_dias)
    if dados.get('ultima_compra'):
        cliente.ultima_compra = datetime.fromisoformat(dados['ultima_compra'])
    cliente.observacoes = dados.get('observacoes', cliente.observacoes)
    db.session.commit()
    return jsonify({'mensagem': 'Cliente atualizado com sucesso'})

@app.route('/api/clientes/<int:id>', methods=['DELETE'])
def excluir_cliente(id):
    if 'usuario_id' not in session:
        return jsonify({'erro': 'Não autenticado'}), 401
    cliente = Cliente.query.get_or_404(id)
    cliente.ativo = False
    db.session.commit()
    return jsonify({'mensagem': 'Cliente excluído com sucesso'})

# ==================== MENSAGENS ====================

@app.route('/api/mensagens/enviar', methods=['POST'])
def enviar_mensagem():
    if 'usuario_id' not in session:
        return jsonify({'erro': 'Não autenticado'}), 401
    dados = request.json
    clientes_ids = dados.get('clientes_ids', [])
    texto = dados.get('texto', '')
    if not clientes_ids:
        return jsonify({'erro': 'Nenhum cliente selecionado'}), 400
    if not texto:
        return jsonify({'erro': 'Mensagem vazia'}), 400
    enviadas = 0
    erros = []
    for cliente_id in clientes_ids:
        cliente = Cliente.query.get(cliente_id)
        if not cliente:
            erros.append(f'Cliente {cliente_id} não encontrado')
            continue
        texto_personalizado = texto.replace('[NOME]', cliente.nome)
        mensagem = Mensagem(cliente_id=cliente.id, texto=texto_personalizado, status='enviada')
        db.session.add(mensagem)
        enviadas += 1
    db.session.commit()
    return jsonify({'mensagem': f'{enviadas} mensagens enviadas', 'enviadas': enviadas, 'erros': erros})

@app.route('/api/mensagens/historico', methods=['GET'])
def historico_mensagens():
    if 'usuario_id' not in session:
        return jsonify({'erro': 'Não autenticado'}), 401
    mensagens = Mensagem.query.order_by(Mensagem.enviada_em.desc()).limit(100).all()
    return jsonify([{
        'id': m.id, 'cliente_id': m.cliente_id, 'texto': m.texto,
        'enviada_em': m.enviada_em.isoformat(), 'status': m.status
    } for m in mensagens])

# ==================== ESTATÍSTICAS ====================

@app.route('/api/estatisticas', methods=['GET'])
def estatisticas():
    if 'usuario_id' not in session:
        return jsonify({'erro': 'Não autenticado'}), 401
    total_clientes = Cliente.query.filter_by(ativo=True).count()
    hoje = datetime.now().date()
    mensagens_hoje = Mensagem.query.filter(db.func.date(Mensagem.enviada_em) == hoje).count()
    data_limite = datetime.now().date() + timedelta(days=5)
    clientes_alerta = Cliente.query.filter(Cliente.ativo == True, Cliente.ultima_compra != None).all()
    em_alerta = 0
    for c in clientes_alerta:
        proxima_compra = c.ultima_compra + timedelta(days=c.ciclo_dias)
        if proxima_compra <= data_limite:
            em_alerta += 1
    return jsonify({
        'total_clientes': total_clientes, 'mensagens_hoje': mensagens_hoje,
        'clientes_alerta': em_alerta, 'vendas_mes': 0
    })

# ==================== ROTA PRINCIPAL ====================

@app.route('/')
def index():
    return jsonify({
        'mensagem': 'API do CRM de Gás - Dr. Gilson', 'versao': '1.0.2', 'status': 'online',
        'servidor': 'Render.com',
        'endpoints': {'init_db': '/api/init-db', 'verificar_setup': '/api/setup/verificar', 'criar_admin': '/api/setup/criar-admin'}
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

