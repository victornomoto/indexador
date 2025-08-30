import os
import pandas as pd
import zipfile
import smtplib
import MySQLdb.cursors
from io import BytesIO
from flask import send_file
from flask import Flask, render_template, request, redirect, url_for, session, send_file, flash
from flask_mysqldb import MySQL
from werkzeug.security import check_password_hash, generate_password_hash
from config import *
from flask import send_from_directory
from itsdangerous import URLSafeTimedSerializer
from email.mime.text import MIMEText

# -------- Encaminhamento de Email ---------
def send_password_reset_email(to_email, token):
    reset_url = url_for('reset_with_token', token=token, _external=True)
    body = f'Para redefinir sua senha, clique no link abaixo:\n\n{reset_url}\n\nSe você não solicitou, ignore este email.'

    msg = MIMEText(body)
    msg['Subject'] = 'Recuperação de senha'
    msg['From'] = 'informatica@villetec.com'
    msg['To'] = to_email

    # Configurar seu servidor SMTP
    smtp_server = ''
    smtp_port = 587
    smtp_user = ''
    smtp_pass = ''

    with smtplib.SMTP(smtp_server, smtp_port) as server:
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.send_message(msg)
app = Flask(__name__)
app.secret_key = SECRET_KEY

# MySQL config
app.config['MYSQL_HOST'] = DB_HOST
app.config['MYSQL_USER'] = DB_USER
app.config['MYSQL_PASSWORD'] = DB_PASSWORD
app.config['MYSQL_DB'] = DB_NAME
app.config['MYSQL_CURSORCLASS'] = 'DictCursor'

mysql = MySQL(app)

# ---------- Helpers ----------
def is_admin():
    return session.get("role") == "admin"

def is_user():
    return session.get("role") in ("user", "admin")

# --------- Generate Password --------
serializer = URLSafeTimedSerializer(app.secret_key)

def generate_password_reset_token(user_id):
    return serializer.dumps(user_id, salt='password-reset-salt')

def verify_password_reset_token(token, expiration=3600):
    try:
        user_id = serializer.loads(token, salt='password-reset-salt', max_age=expiration)
        return user_id
    except Exception:
        return None


# ---------- Routes ----------
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM usuarios WHERE username=%s", (username,))
        user = cur.fetchone()
        cur.close()
        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = user["role"]
            return redirect(url_for("dashboard"))
        flash("Usuário ou senha inválidos.", "danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session['user_id']

    # Lista pastas na pasta principal
    try:
        pastas = [f for f in os.listdir(PDF_FOLDER) if os.path.isdir(os.path.join(PDF_FOLDER, f))]
        pastas.sort()
    except Exception as e:
        pastas = []
        flash(f"Erro ao acessar pastas: {e}", "danger")

    # Verifica bloqueios no banco
    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cur.execute("SELECT pasta, user_id FROM bloqueios")
    bloqueios = {row['pasta']: row['user_id'] for row in cur.fetchall()}
    cur.close()

    return render_template("dashboard.html", pastas=pastas, bloqueios=bloqueios, user_id=user_id)

@app.route("/abrir_pasta/<nome_pasta>")
def abrir_pasta(nome_pasta):
    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session['user_id']

    # Cria cursor do tipo DictCursor
    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    # Verifica se já está bloqueada
    cur.execute("SELECT user_id FROM bloqueios WHERE pasta = %s", (nome_pasta,))
    bloqueio = cur.fetchone()

    if bloqueio and bloqueio['user_id'] != user_id:
        flash("Esta pasta já está sendo indexada por outro usuário.", "warning")
        cur.close()
        return redirect(url_for("dashboard"))

    # Bloqueia a pasta para o usuário atual
    cur.execute("DELETE FROM bloqueios WHERE pasta = %s", (nome_pasta,))
    cur.execute("INSERT INTO bloqueios (pasta, user_id) VALUES (%s, %s)", (nome_pasta, user_id))
    mysql.connection.commit()
    cur.close()

    # Lista PDFs dessa pasta
    pasta_path = os.path.join(PDF_FOLDER, nome_pasta)
    pdfs = [f for f in os.listdir(pasta_path) if f.lower().endswith(".pdf")]
    pdfs.sort()

    # Lista todas as pastas novamente
    try:
        pastas = [f for f in os.listdir(PDF_FOLDER) if os.path.isdir(os.path.join(PDF_FOLDER, f))]
        pastas.sort()
    except Exception as e:
        pastas = []
        flash(f"Erro ao acessar pastas: {e}", "danger")

    # Busca bloqueios novamente
    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cur.execute("SELECT pasta, user_id FROM bloqueios")
    bloqueios = {row['pasta']: row['user_id'] for row in cur.fetchall()}
    cur.close()

    return render_template(
        "dashboard.html",
        pastas=pastas,
        bloqueios=bloqueios,
        user_id=user_id,
        pasta_selecionada=nome_pasta,
        pdfs=pdfs
    )


@app.route("/liberar_pasta/<nome_pasta>")
def liberar_pasta(nome_pasta):
    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]
    role = session.get("role")

    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    # Descobre quem está com a pasta bloqueada
    cur.execute("SELECT user_id FROM bloqueios WHERE pasta = %s", (nome_pasta,))
    bloqueio = cur.fetchone()

    # Permissão para liberar:
    # 1) Admin pode liberar qualquer pasta
    # 2) Usuário que está com a pasta bloqueada também pode liberar
    if role != "admin" and (not bloqueio or bloqueio["user_id"] != user_id):
        flash("Você não tem permissão para liberar esta pasta.", "danger")
        cur.close()
        return redirect(url_for("abrir_pasta", nome_pasta=nome_pasta))

    try:
        # Remove o bloqueio
        cur.execute("DELETE FROM bloqueios WHERE pasta = %s", (nome_pasta,))

        # Se havia alguém bloqueando, envia notificação
        if bloqueio and bloqueio["user_id"] != user_id:
            mensagem = f"A pasta '{nome_pasta}' foi liberada pelo administrador."
            cur.execute(
                "INSERT INTO notificacoes (user_id, mensagem) VALUES (%s, %s)",
                (bloqueio["user_id"], mensagem)
            )

        mysql.connection.commit()
        flash(f"Pasta '{nome_pasta}' liberada com sucesso.", "success")
    except Exception as e:
        flash(f"Erro ao liberar a pasta: {e}", "danger")
    finally:
        cur.close()

    return redirect(url_for("dashboard"))


@app.route("/reset_password", methods=["GET", "POST"])
def reset_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        if not email:
            flash("Informe seu email.", "danger")
            return redirect(url_for("reset_password"))

        cur = mysql.connection.cursor()
        cur.execute("SELECT id FROM usuarios WHERE email = %s", (email,))
        user = cur.fetchone()
        cur.close()

        if not user:
            flash("Email não cadastrado.", "warning")
            return redirect(url_for("reset_password"))

        # Aqui geramos token e enviamos email (vai vir no passo 2)
        token = generate_password_reset_token(user["id"])

        send_password_reset_email(email, token)

        flash("Email de recuperação enviado. Verifique sua caixa de entrada.", "success")
        return redirect(url_for("login"))

    return render_template("reset_password.html")

@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_with_token(token):
    user_id = verify_password_reset_token(token)
    if not user_id:
        flash('O link de recuperação é inválido ou expirou.', 'danger')
        return redirect(url_for('reset_password'))

    if request.method == 'POST':
        password = request.form.get('password')
        password_confirm = request.form.get('password_confirm')
        if not password or password != password_confirm:
            flash('As senhas não coincidem ou estão vazias.', 'danger')
            return redirect(url_for('reset_with_token', token=token))

        password_hash = generate_password_hash(password)
        cur = mysql.connection.cursor()
        cur.execute("UPDATE usuarios SET password_hash = %s WHERE id = %s", (password_hash, user_id))
        mysql.connection.commit()
        cur.close()

        flash('Senha atualizada com sucesso! Faça login.', 'success')
        return redirect(url_for('login'))

    return render_template('reset_with_token.html')


@app.route("/indexar/<pasta>/<pdf>", methods=["GET", "POST"])
def indexar(pasta, pdf):
    if "user_id" not in session:
        return redirect(url_for("login"))

    # obtém campos configurados
    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cur.execute("SELECT * FROM campos ORDER BY ordem ASC")
    campos = cur.fetchall()
    cur.close()

    if request.method == "POST":
        valores = []
        for campo in campos:
            v = request.form.get(f"field_{campo['id']}", "").strip()
            valores.append(v)
        valores.append(pdf)  # última coluna é o nome do PDF
        linha = TXT_SEPARATOR.join(valores)

        cur = mysql.connection.cursor()
        cur.execute("INSERT INTO indexacoes (pdf_nome, dados) VALUES (%s, %s)", (pdf, linha))
        mysql.connection.commit()
        cur.close()
        flash("Indexação salva com sucesso.", "success")
        return redirect(url_for("abrir_pasta", nome_pasta=pasta))

    # Path completo do PDF para visualização
    pdf_url = url_for('serve_pdf', filename=f"{pasta}/{pdf}")
    return render_template("indexar.html", pdf=pdf, pdf_url=pdf_url, campos=campos, pasta=pasta)


@app.route("/pdfs/<path:filename>")
def serve_pdf(filename):
    return send_from_directory(PDF_FOLDER, filename)

@app.route("/admin/usuarios", methods=["GET", "POST"])
def admin_usuarios():
    if not is_admin():
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        role = request.form.get("role", "indexador")

        if not username or not password or not email:
            flash("Usuário, senha e email são obrigatórios.", "danger")
        else:
            cur = mysql.connection.cursor()
            # Verifica se usuário ou email já existe
            cur.execute("SELECT id FROM usuarios WHERE username = %s OR email = %s", (username, email))
            if cur.fetchone():
                flash("Usuário ou email já existe.", "warning")
            else:
                password_hash = generate_password_hash(password)
                cur.execute(
                    "INSERT INTO usuarios (username, email, password_hash, role) VALUES (%s, %s, %s, %s)",
                    (username, email, password_hash, role),
                )
                mysql.connection.commit()
                flash("Usuário criado com sucesso.", "success")
            cur.close()

    # Lista usuários para mostrar na tela (incluindo email)
    cur = mysql.connection.cursor()
    cur.execute("SELECT id, username, email, role FROM usuarios ORDER BY username ASC")
    usuarios = cur.fetchall()
    cur.close()

    return render_template("admin_users.html", usuarios=usuarios)


@app.route('/admin/usuarios/delete/<int:usuario_id>', methods=['POST'])
def admin_delete_usuario(usuario_id):
    if not is_admin():
        flash("Você não tem permissão para excluir usuários.", "danger")
        return redirect(url_for("dashboard"))
    
    cur = mysql.connection.cursor()
    # Opcional: evita deletar o próprio usuário logado
    if usuario_id == session.get("user_id"):
        flash("Você não pode excluir seu próprio usuário.", "warning")
        cur.close()
        return redirect(url_for('admin_usuarios'))

    cur.execute("SELECT id FROM usuarios WHERE id = %s", (usuario_id,))
    if cur.fetchone() is None:
        flash("Usuário não encontrado.", "warning")
        cur.close()
        return redirect(url_for('admin_usuarios'))

    cur.execute("DELETE FROM usuarios WHERE id = %s", (usuario_id,))
    mysql.connection.commit()
    cur.close()

    flash("Usuário excluído com sucesso.", "success")
    return redirect(url_for('admin_usuarios'))


@app.route("/admin/campos", methods=["GET", "POST"])
def admin_campos():
    if not is_admin():
        return redirect(url_for("dashboard"))
    cur = mysql.connection.cursor()
    if request.method == "POST":
        nome_campo = request.form.get("nome_campo", "").strip()
        ordem = int(request.form.get("ordem", "0"))
        if nome_campo:
            cur.execute("INSERT INTO campos (nome_campo, ordem) VALUES (%s, %s)", (nome_campo, ordem))
            mysql.connection.commit()
            flash("Campo adicionado.", "success")
    cur.execute("SELECT * FROM campos ORDER BY ordem ASC")
    campos = cur.fetchall()
    cur.close()
    return render_template("admin_fields.html", campos=campos)

@app.route('/campos/delete/<int:campo_id>', methods=['POST'])
def delete_campo(campo_id):
    # Exemplo usando cursor MySQL (ajuste conforme seu banco)
    cur = mysql.connection.cursor()
    # Verifica se o campo existe (opcional)
    cur.execute("SELECT id FROM campos WHERE id = %s", (campo_id,))
    if cur.fetchone() is None:
        cur.close()
        flash("Campo não encontrado.")
        return redirect(url_for('admin_campos'))  # rota da lista de campos

    # Deleta o campo
    cur.execute("DELETE FROM campos WHERE id = %s", (campo_id,))
    mysql.connection.commit()
    cur.close()
    flash("Campo excluído com sucesso.")
    return redirect(url_for('admin_campos'))

@app.route("/exportar/txt")
def exportar_txt():
    if "user_id" not in session:
        return redirect(url_for("login"))
    
    # Buscar campos para cabeçalho
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM campos ORDER BY ordem ASC")
    campos = cur.fetchall()
    
    # Buscar indexações
    cur.execute("SELECT pdf_nome, dados FROM indexacoes ORDER BY id ASC")
    registros = cur.fetchall()
    cur.close()
    
    os.makedirs(EXPORT_FOLDER, exist_ok=True)
    
    arquivos_gerados = []
    
    for r in registros:
        pdf_name = r["pdf_nome"]
        dados = r["dados"]
        
        txt_name = pdf_name.rsplit('.', 1)[0] + ".txt"
        path = os.path.join(EXPORT_FOLDER, txt_name)
        
        with open(path, "w", encoding="utf-8") as f:
            cabecalho = ";".join(c["nome_campo"] for c in campos)
            cabecalho += ";Arquivo"
            f.write(cabecalho + "\n")
            f.write(dados + "\n")
        
        arquivos_gerados.append(txt_name)  # só o nome do arquivo para link
    
    return redirect(url_for("lista_txt"))

@app.route("/exportar/txt/lista")
def lista_txt():
    if "user_id" not in session:
        return redirect(url_for("login"))
    
    # lista arquivos txt na pasta exportação
    try:
        arquivos = [f for f in os.listdir(EXPORT_FOLDER) if f.endswith(".txt")]
        arquivos.sort()
    except Exception as e:
        arquivos = []
        flash(f"Erro ao acessar arquivos de exportação: {e}", "danger")
    
    return render_template("lista_txt.html", arquivos=arquivos)
from flask import send_from_directory

@app.route("/exportar/txt/download/<nome_arquivo>")
def download_txt(nome_arquivo):
    if "user_id" not in session:
        return redirect(url_for("login"))
    return send_from_directory(EXPORT_FOLDER, nome_arquivo, as_attachment=True)

@app.route("/exportar/txt/baixar_zip")
def baixar_zip_txt():
    if "user_id" not in session:
        return redirect(url_for("login"))
    
    # Lista arquivos txt na pasta exportação
    arquivos = [f for f in os.listdir(EXPORT_FOLDER) if f.endswith(".txt")]
    if not arquivos:
        flash("Nenhum arquivo TXT para compactar.", "warning")
        return redirect(url_for("lista_txt"))
    
    # Cria um arquivo ZIP na memória
    mem_zip = BytesIO()
    with zipfile.ZipFile(mem_zip, mode="w") as zf:
        for arquivo in arquivos:
            caminho = os.path.join(EXPORT_FOLDER, arquivo)
            zf.write(caminho, arcname=arquivo)
    mem_zip.seek(0)
    
    return send_file(mem_zip, mimetype="application/zip", as_attachment=True, download_name="exportacao_txt.zip")

@app.route("/exportar/excel")
def exportar_excel():
    if "user_id" not in session:
        return redirect(url_for("login"))
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM campos ORDER BY ordem ASC")
    campos = cur.fetchall()
    cur.execute("SELECT dados FROM indexacoes ORDER BY id ASC")
    registros = cur.fetchall()
    cur.close()

    rows = []
    for r in registros:
        parts = r["dados"].split(TXT_SEPARATOR)
        rows.append(parts)

    # substitui "pdf_name" por "Arquivo"
    col_names = [c["nome_campo"] for c in campos] + ["Arquivo"]
    df = pd.DataFrame(rows, columns=col_names)
    os.makedirs(EXPORT_FOLDER, exist_ok=True)
    path = os.path.join(EXPORT_FOLDER, "exportacao.xlsx")
    df.to_excel(path, index=False)
    return send_file(path, as_attachment=True)


# Run
if __name__ == "__main__":
    # cria pasta de export se necessário
    os.makedirs(EXPORT_FOLDER, exist_ok=True)
    app.run(host="0.0.0.0", port=5000)
