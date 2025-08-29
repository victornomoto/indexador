import mysql.connector
from werkzeug.security import generate_password_hash
from config import DB_HOST, DB_USER, DB_PASSWORD, DB_NAME

def init():
    # conecta sem escolher DB para criar o DB se necessário
    conn = mysql.connector.connect(host=DB_HOST, user=DB_USER, password=DB_PASSWORD)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
    cur.close()
    conn.close()

    # conecta no DB recém-criado
    conn = mysql.connector.connect(host=DB_HOST, user=DB_USER, password=DB_PASSWORD, database=DB_NAME)
    cur = conn.cursor()

    # criar tabelas
    cur.execute("""
    CREATE TABLE IF NOT EXISTS usuarios (
        id INT AUTO_INCREMENT PRIMARY KEY,
        username VARCHAR(50) UNIQUE NOT NULL,
        password_hash VARCHAR(255) NOT NULL,
        role ENUM('admin','user') DEFAULT 'user'
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS campos (
        id INT AUTO_INCREMENT PRIMARY KEY,
        nome_campo VARCHAR(100) NOT NULL,
        ordem INT NOT NULL
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS indexacoes (
        id INT AUTO_INCREMENT PRIMARY KEY,
        pdf_nome VARCHAR(255) NOT NULL,
        dados LONGTEXT NOT NULL,
        data TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # cria usuário admin inicial se não existir
    admin_username = "victor.nomoto"
    admin_password = "joao1254"  # senha do admin (será hasheada)
    cur.execute("SELECT id FROM usuarios WHERE username=%s", (admin_username,))
    exists = cur.fetchone()
    if not exists:
        pw_hash = generate_password_hash(admin_password)  # PBKDF2 (Werkzeug)
        cur.execute("INSERT INTO usuarios (username, password_hash, role) VALUES (%s, %s, 'admin')",
                    (admin_username, pw_hash))
        print("Usuário admin criado:", admin_username)
    else:
        print("Usuário admin já existe.")

    conn.commit()
    cur.close()
    conn.close()
    print("Init DB concluído.")

if __name__ == "__main__":
    init()
